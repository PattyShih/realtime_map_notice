// ops 儀表板服務：壓測觸發、容器狀態蒐集、compose 模式的模擬 HPA 與流量輪詢。
// 以 Node 內建模組實作（零依賴）；主機需有 Docker，K8s 模式另需 kubectl 與已部署叢集。
// 兩種模式：
//   k8s     — 狀態讀 kubectl（pods/top/hpa），壓測走 load-generator Job，擴展交給真 HPA。
//   compose — 壓測以一次性容器執行 simulator，經本服務的 round-robin proxy 分流到
//             location-service 各副本（primary 8001、額外副本 18001/18002），
//             擴縮由內建 autoscaler 依平均 CPU 決定（等效 K8s Service + HPA 的 demo 替身）。
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { promisify } = require('util');

const exec = promisify(execFile);

const PORT = Number(process.env.OPS_PORT || 8090);
const ROOT = path.resolve(__dirname, '..');
const SIMULATOR_SCRIPT = path.join(ROOT, 'simulator', 'simulate_users.py');
const EVENT_GEN_SCRIPT = path.join(__dirname, 'event_gen.py');
const JOB_YAML = path.join(ROOT, 'k8s', 'load-generator-job.yaml');
const COMPOSE_PROJECT = 'realtime_map_notice';
const COMPOSE_NET = `${COMPOSE_PROJECT}_default`;
const PRIMARY_CONTAINER = `${COMPOSE_PROJECT}-location-service-1`;
const K8S_NS = 'realtime-map-notice';
const PRIMARY_PORT = 8001;
const REPLICA_PORTS = [18001, 18002]; // 額外副本發布到主機的埠（r2、r3）
const MAX_REPLICAS = 1 + REPLICA_PORTS.length;
const SCALE_UP_CPU = Number(process.env.OPS_SCALE_UP_CPU || 25); // 平均 CPU 高於此值 → 擴展
const SCALE_DOWN_CPU = Number(process.env.OPS_SCALE_DOWN_CPU || 8); // 平均 CPU 低於此值連續 N 次 → 縮回
const SCALE_DOWN_TICKS = 2;
const SCALE_UP_TICKS = 1; // 一次達標即擴展：demo 節奏優先（人數指標本身可控，不會誤觸發）
const CHECK_MS = 1000;
// 單一模擬程序約 800 人後自身飽和（見 k8s/README.md），人數多時拆多個 worker 容器
const LOAD_WORKERS = [
  { max: 800, count: 1 },
  { max: 1600, count: 2 },
  { max: Infinity, count: 3 },
];

const state = {
  mode: 'compose',
  load: { running: false, users: 0 },
  replicas: 1,
  rrIndex: 0,
  lowTicks: 0,
  upTicks: 0,
  scaling: false,
  events: [], // { t: 'HH:MM:SS', msg }
  eventGen: { running: false },
  peakUsers: 0, // 本次壓測以來的最大人數：讓遞增過程副本只增不減
};

function logEvent(msg) {
  const t = new Date().toTimeString().slice(0, 8);
  state.events.unshift({ t, msg });
  if (state.events.length > 50) state.events.pop();
  console.log(`[${t}] ${msg}`);
}

async function sh(cmd, args, opts = {}) {
  try {
    const { stdout } = await exec(cmd, args, { windowsHide: true, maxBuffer: 10 * 1024 * 1024, ...opts });
    return { ok: true, out: stdout };
  } catch (err) {
    return { ok: false, out: err.stdout || '', err: String(err.message || err).split('\n')[0] };
  }
}

// ---------- compose 模式 ----------

function parseCpu(pct) {
  const n = parseFloat(pct);
  return Number.isFinite(n) ? n : null;
}

async function composeStats() {
  const r = await sh('docker', [
    'stats', '--no-stream',
    '--format', '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}',
  ]);
  if (!r.ok) return [];
  return r.out.trim().split('\n').filter(Boolean).map((line) => {
    const [name, cpu, mem] = line.split('\t');
    const isLocation = name === PRIMARY_CONTAINER || /^ops-location-r\d+$/.test(name);
    return {
      name,
      short: name.replace(`${COMPOSE_PROJECT}-`, '').replace(/-\d+$/, ''),
      cpu: parseCpu(cpu),
      mem,
      replica: /^ops-location-r\d+$/.test(name),
      location: isLocation,
    };
  });
}

async function detectImage() {
  const r = await sh('docker', ['inspect', PRIMARY_CONTAINER, '--format', '{{.Config.Image}}']);
  return r.ok ? r.out.trim() : null;
}

function extraReplicaNames(count) {
  return REPLICA_PORTS.slice(0, count).map((port, i) => ({ name: `ops-location-r${i + 2}`, port }));
}

async function scaleTo(target) {
  if (state.scaling) return;
  state.scaling = true;
  try {
    const extras = extraReplicaNames(Math.max(0, target - 1));
    for (const { name, port } of extras) {
      const running = await sh('docker', ['inspect', name]);
      if (!running.ok) {
        const image = await detectImage();
        if (!image) { logEvent('⚠️ 無法取得 location-service 映像，擴展失敗'); return; }
        const r = await sh('docker', [
          'run', '-d', '--name', name,
          '--network', COMPOSE_NET,
          '--network-alias', 'location-service',
          '-e', 'REDIS_URL=redis://redis:6379/0',
          '-e', `CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:3000`,
          '-p', `${port}:8000`,
          image,
        ]);
        logEvent(r.ok
          ? `📈 擴展：location-service → ${target} 副本（${name} 於 :${port} 上線）`
          : `⚠️ 擴展失敗：${r.err}`);
      }
    }
    const keep = new Set(extras.map((e) => e.name));
    const current = extraReplicaNames(state.replicas - 1);
    for (const { name } of current) {
      if (!keep.has(name)) {
        await sh('docker', ['rm', '-f', name]);
        logEvent(`📉 縮回：移除 ${name}，location-service → ${target} 副本`);
      }
    }
    state.replicas = target;
  } finally {
    state.scaling = false;
  }
}

function loadWorkerNames(count) {
  return Array.from({ length: count }, (_, i) => `ops-load-gen-${i + 1}`);
}

// 壓測結束後主動清除模擬使用者（u-* 與真實使用者的 user_* 前缀不同，不會誤傷），
// 讓前端「即時在線人數」在數秒內回落，不必等 last_seen TTL 與背景清理週期。
async function purgeSimUsers() {
  await sh('docker', ['rm', '-f', 'ops-redis-purge']);
  const script = [
    "members=$(redis-cli -h redis --scan --pattern 'realtime_map_notice:user:last_seen:u-*' | sed 's/.*last_seen://')",
    '[ -n "$members" ] && redis-cli -h redis zrem user:locations $members',
    "redis-cli -h redis --scan --pattern 'realtime_map_notice:user:last_seen:u-*' | xargs -r redis-cli -h redis del",
    'echo purged',
  ].join(' && ');
  return sh('docker', [
    'run', '--rm', '--name', 'ops-redis-purge', '--network', COMPOSE_NET,
    'redis:7-alpine', 'sh', '-c', script,
  ]);
}

async function startLoadCompose(users) {
  await stopLoadCompose();
  const count = LOAD_WORKERS.find((w) => users <= w.max).count;
  const perWorker = Math.ceil(users / count);
  const target = 'http://host.docker.internal:8090/fwd/location';
  for (const name of loadWorkerNames(count)) {
    await sh('docker', [
      'run', '-d', '--name', name,
      '--network', COMPOSE_NET,
      '-v', `${SIMULATOR_SCRIPT}:/code/simulate_users.py:ro`,
      'python:3.12-slim',
      'sh', '-c',
      `pip install -q httpx==0.28.1 && python /code/simulate_users.py --users ${perWorker} --target ${target} --interval 0.5`,
    ]);
  }
  state.load = { running: true, users };
  state.peakUsers = Math.max(state.peakUsers, users);

  // 事件流併入：人越多事件越多（每 50 人 1 則/秒，上限 10 則/秒）
  const evtRate = Math.min(10, Math.max(1, Math.round(users / 50)));
  await startEventGenCompose(evtRate);

  logEvent(`⚡ 開始模擬：${users} 人湧入（${count} 個模擬 worker × ${perWorker} 人）＋ 事件流每秒約 ${evtRate} 則`);
}

// 事件流：只發布測試事件（不打流量），事件會真實出現在地圖上
async function startEventGenCompose(rate = 10) {
  await stopEventGenCompose();
  const r = await sh('docker', [
    'run', '-d', '--name', 'ops-event-gen',
    '--network', COMPOSE_NET,
    '-v', `${EVENT_GEN_SCRIPT}:/code/event_gen.py:ro`,
    'python:3.12-slim',
    'sh', '-c',
    `pip install -q httpx==0.28.1 && EVENT_RATE=${rate} EVENT_DURATION_MINUTES=60 python /code/event_gen.py`,
  ]);
  state.eventGen = { running: r.ok };
  logEvent(r.ok
    ? `📢 事件流啟動：每秒約 ${rate} 則輔大校園測試事件（地圖上即時可見）`
    : `⚠️ 事件流啟動失敗：${r.err}`);
}

async function stopEventGenCompose() {
  const r = await sh('docker', ['rm', '-f', 'ops-event-gen']);
  if (r.ok && state.eventGen.running) logEvent('⏹ 事件模式：已停止發布');
  state.eventGen = { running: false };
}

async function stopLoadCompose() {
  let had = false;
  for (const name of [...loadWorkerNames(LOAD_WORKERS.at(-1).count), 'ops-event-gen', 'ops-load-generator']) {
    const r = await sh('docker', ['rm', '-f', name]);
    if (r.ok) had = true;
  }
  if (had && state.load.running) logEvent(`⏹ 停止模擬（${state.load.users} 人與事件流已撤）`);
  state.load = { running: false, users: 0, workers: 0 };
  state.lowTicks = 0;
  state.upTicks = 0;
  state.peakUsers = 0; // 峰值歸零：下一次壓測從 1 副本重新開始
  if (had) {
    const purged = await purgeSimUsers();
    if (purged.ok) logEvent('🧹 已清除模擬使用者在線紀錄（在線人數即時回落）');
  }
}

async function composeStatus() {
  const stats = await composeStats();
  const locContainers = stats.filter((s) => s.location);
  state.replicas = Math.max(1, locContainers.length);
  const workers = stats.filter((s) => /^ops-load-gen-\d+$/.test(s.name));
  if (workers.length && !state.load.running) state.load.running = true;
  if (!workers.length) state.load = { running: false, users: 0, workers: 0 };
  const eventGenRunning = stats.some((s) => s.name === 'ops-event-gen');
  state.eventGen = { running: eventGenRunning };
  const avgCpu = locContainers.length
    ? Math.round(locContainers.reduce((s, c) => s + (c.cpu || 0), 0) / locContainers.length)
    : null;

  // 每個副本的獨立資訊（給前端「容器擴展現場」面板畫方塊）
  const extraPort = { 'ops-location-r2': REPLICA_PORTS[0], 'ops-location-r3': REPLICA_PORTS[1] };
  const pods = locContainers.map((c, i) => ({
    id: c.name,
    label: c.name === PRIMARY_CONTAINER ? ':8001' : `:${extraPort[c.name] || '?'}`,
    cpu: c.cpu,
    idx: i,
  }));

  // 卡片：location-service 各副本合併為一張；ops 自己的輔助容器不佔卡片
  const byService = new Map();
  for (const s of stats) {
    if (/^ops-(load-gen-\d+|event-gen|redis-purge|load-generator)$/.test(s.name)) continue;
    const key = s.location ? 'location-service' : s.short;
    const entry = byService.get(key) || { short: key, cpus: [], mem: s.mem, replicas: 0 };
    entry.cpus.push(s.cpu || 0);
    entry.replicas += 1;
    byService.set(key, entry);
  }
  const services = [...byService.values()].map((e) => ({
    short: e.short,
    // 保留一位小數：低流量服務（0.x%）也看得出變化
    cpu: Math.round((e.cpus.reduce((a, b) => a + b, 0) / e.cpus.length) * 10) / 10,
    mem: e.mem,
    replicas: e.replicas,
  }));

  return {
    mode: 'compose',
    autoscaler: { up: SCALE_UP_CPU, down: SCALE_DOWN_CPU, max: MAX_REPLICAS, avgCpu },
    pool: [PRIMARY_PORT, ...REPLICA_PORTS.slice(0, state.replicas - 1)],
    pods,
    chart: {
      series: [{ label: 'location-service CPU%', value: avgCpu }],
      guide: SCALE_UP_CPU,
    },
    services,
    load: { ...state.load, workers: workers.length },
    eventGen: state.eventGen,
    events: state.events.slice(0, 30),
  };
}

// compose 模式的模擬 HPA：以「本次壓測峰值人數」為唯一指標（棘輪設計）。
// 人數從 0 慢慢遞增到 500 的過程中，副本只會增加不會減少——
// CPU 噪音不再參與判斷（之前 avg 在門檻上下來回，造成副本忽多忽少）。
// 按下停止壓測後峰值歸零，副本才會縮回 1 個。
async function autoscalerTick() {
  if (state.scaling) return;
  const stats = await composeStats();
  const loc = stats.filter((s) => s.location);
  if (!loc.length) return;
  const replicas = Math.max(1, loc.length);
  state.replicas = replicas;

  const users = state.load.running ? state.load.users : 0;
  if (users > state.peakUsers) state.peakUsers = users;

  let desired = 1;
  if (state.peakUsers >= 400) desired = MAX_REPLICAS;
  else if (state.peakUsers >= 100) desired = 2;

  if (desired > replicas) {
    await scaleTo(desired);
    logEvent(`📈 擴展：${replicas} → ${desired} 副本（峰值人數 ${state.peakUsers}）`);
  } else if (desired < replicas && !state.load.running) {
    // 只有停止壓測（峰值歸零）才縮減，demo 遞增過程中不縮
    await scaleTo(desired);
    logEvent(`📉 壓測已停止，縮回 ${desired} 副本`);
  }
}

// ---------- k8s 模式 ----------

async function startLoadK8s(users) {
  const tmp = (name) => path.join(require('os').tmpdir(), `${name}-${Date.now()}.yaml`);
  const cmFile = tmp('simulator-cm');
  const cm = await sh('kubectl', ['-n', K8S_NS, 'create', 'configmap', 'simulator-code',
    '--from-file', `simulate_users.py=${SIMULATOR_SCRIPT}`, '--dry-run=client', '-o', 'yaml']);
  if (!cm.ok) { logEvent(`⚠️ ConfigMap 建立失敗：${cm.err}`); return; }
  fs.writeFileSync(cmFile, cm.out);
  await sh('kubectl', ['apply', '-f', cmFile]);
  fs.unlinkSync(cmFile);
  const jobFile = tmp('load-generator');
  fs.writeFileSync(jobFile, fs.readFileSync(JOB_YAML, 'utf8').replace(/--users \d+/, `--users ${users}`));
  await sh('kubectl', ['-n', K8S_NS, 'delete', 'job', 'load-generator', '--ignore-not-found']);
  const r = await sh('kubectl', ['apply', '-f', jobFile]);
  fs.unlinkSync(jobFile);
  state.load = { running: r.ok, users: r.ok ? users : 0 };
  await startEventGenK8s(); // 事件流跟著人數一起啟動
  logEvent(r.ok ? `⚡ K8s 模擬：Job load-generator 已建立（${users} 人）＋ 事件流` : `⚠️ Job 建立失敗：${r.err}`);
}

async function startEventGenK8s() {
  const cmFile = tmp('event-gen-cm');
  const cm = await sh('kubectl', ['-n', K8S_NS, 'create', 'configmap', 'event-gen-code',
    '--from-file', `event_gen.py=${EVENT_GEN_SCRIPT}`, '--dry-run=client', '-o', 'yaml']);
  if (!cm.ok) { logEvent(`⚠️ ConfigMap 建立失敗：${cm.err}`); return; }
  fs.writeFileSync(cmFile, cm.out);
  await sh('kubectl', ['apply', '-f', cmFile]);
  fs.unlinkSync(cmFile);
  await sh('kubectl', ['-n', K8S_NS, 'delete', 'job', 'event-gen', '--ignore-not-found']);
  const r = await sh('kubectl', ['apply', '-f', path.join(__dirname, '..', 'k8s', 'event-gen-job.yaml')]);
  state.eventGen = { running: r.ok };
  logEvent(r.ok ? '📢 K8s 事件模式：Job event-gen 已建立（持續發布輔大校園事件）' : `⚠️ Job 建立失敗：${r.err}`);
}

async function stopEventGenK8s() {
  const r = await sh('kubectl', ['-n', K8S_NS, 'delete', 'job', 'event-gen', '--ignore-not-found']);
  if (state.eventGen.running) logEvent('⏹ K8s 事件模式：Job 已刪除');
  state.eventGen = { running: false };
  if (!r.ok) logEvent(`⚠️ Job 刪除失敗：${r.err}`);
}

async function stopLoadK8s() {
  await stopEventGenK8s();
  const r = await sh('kubectl', ['-n', K8S_NS, 'delete', 'job', 'load-generator', '--ignore-not-found']);
  if (state.load.running) logEvent('⏹ K8s 模擬：Job 已刪除');
  state.load = { running: false, users: 0 };
  if (!r.ok) logEvent(`⚠️ Job 刪除失敗：${r.err}`);
}

async function k8sStatus() {
  const pods = await sh('kubectl', ['-n', K8S_NS, 'get', 'pods', '-o', 'json']);
  const top = await sh('kubectl', ['-n', K8S_NS, 'top', 'pods', '--no-headers']);
  const hpa = await sh('kubectl', ['-n', K8S_NS, 'get', 'hpa', '-o', 'json']);
  const job = await sh('kubectl', ['-n', K8S_NS, 'get', 'job', 'load-generator', '-o', 'json']);
  const evtJob = await sh('kubectl', ['-n', K8S_NS, 'get', 'job', 'event-gen', '-o', 'json']);

  const cpuByPod = {};
  for (const line of top.out.trim().split('\n').filter(Boolean)) {
    const [name, cpu] = line.split(/\s+/);
    cpuByPod[name] = cpu;
  }
  const services = [];
  if (pods.ok) {
    for (const item of JSON.parse(pods.out).items) {
      const name = item.metadata.name;
      const labels = item.metadata.labels || {};
      services.push({
        name,
        short: labels.app || name,
        phase: item.status.phase,
        cpu: cpuByPod[name] || '?',
        replica: false,
      });
    }
  }
  let hpaInfo = null;
  if (hpa.ok) {
    const item = JSON.parse(hpa.out).items[0];
    if (item) {
      hpaInfo = {
        min: item.spec.minReplicas,
        max: item.spec.maxReplicas,
        targetCpu: item.spec.targetCPUUtilizationPercentage,
        current: item.status.currentReplicas,
        desired: item.status.desiredReplicas,
        cpu: item.status.currentCPUUtilizationPercentage,
      };
    }
  }
  let load = { running: false, users: state.load.users };
  if (job.ok) {
    const j = JSON.parse(job.out);
    load = { running: (j.status.active || 0) > 0, users: state.load.users };
  }
  let eventGen = { running: false };
  if (evtJob.ok) {
    const j = JSON.parse(evtJob.out);
    eventGen = { running: (j.status.active || 0) > 0 };
  }
  return {
    mode: 'k8s',
    autoscaler: hpaInfo,
    eventGen,
    pool: [],
    pods: services
      .filter((s) => s.short === 'location-service')
      .map((s) => ({ id: s.name, label: s.name.replace(/-location-service.*/, ''), cpu: s.cpu })),
    chart: {
      series: [{ label: 'HPA CPU%', value: hpaInfo ? hpaInfo.cpu : null }],
      guide: hpaInfo ? hpaInfo.targetCpu : null,
    },
    services,
    load,
    events: state.events.slice(0, 30),
  };
}

// ---------- HTTP：API + 靜態頁 + round-robin proxy ----------

function forward(req, res, port) {
  const upstream = http.request(
    { host: '127.0.0.1', port, path: req.url.replace(/^\/fwd\/location/, ''), method: req.method, headers: { ...req.headers, host: `127.0.0.1:${port}` } },
    (ur) => {
      res.writeHead(ur.statusCode, ur.headers);
      ur.pipe(res);
    },
  );
  upstream.on('error', () => {
    res.writeHead(502, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ detail: 'ops proxy: upstream unavailable' }));
  });
  req.pipe(upstream);
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks).toString('utf8');
}

function sendJson(res, code, obj) {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(obj));
}

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' };

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://localhost:${PORT}`);

    if (url.pathname.startsWith('/fwd/location/')) {
      const pool = [PRIMARY_PORT, ...REPLICA_PORTS.slice(0, state.replicas - 1)];
      const port = pool[state.rrIndex++ % pool.length];
      return forward(req, res, port);
    }

    if (url.pathname === '/api/status') {
      const status = state.mode === 'k8s' ? await k8sStatus() : await composeStatus();
      return sendJson(res, 200, status);
    }

    if (url.pathname === '/api/load/start' && req.method === 'POST') {
      const body = JSON.parse((await readBody(req)) || '{}');
      const users = Math.min(3000, Math.max(100, Number(body.users) || 500));
      if (state.mode === 'k8s') await startLoadK8s(users);
      else await startLoadCompose(users);
      return sendJson(res, 200, { ok: true, users });
    }

    if (url.pathname === '/api/events/start' && req.method === 'POST') {
      if (state.mode === 'k8s') await startEventGenK8s();
      else await startEventGenCompose();
      return sendJson(res, 200, { ok: true });
    }

    if (url.pathname === '/api/events/stop' && req.method === 'POST') {
      if (state.mode === 'k8s') await stopEventGenK8s();
      else await stopEventGenCompose();
      return sendJson(res, 200, { ok: true });
    }

    if (url.pathname === '/api/load/stop' && req.method === 'POST') {
      if (state.mode === 'k8s') await stopLoadK8s();
      else await stopLoadCompose();
      return sendJson(res, 200, { ok: true });
    }

    // 靜態頁面
    let file = url.pathname === '/' ? '/index.html' : url.pathname;
    file = path.normalize(file).replace(/^(\.\.[/\\])+/, '');
    const full = path.join(__dirname, 'static', file);
    if (!full.startsWith(path.join(__dirname, 'static'))) { res.writeHead(403); return res.end(); }
    fs.readFile(full, (err, data) => {
      if (err) { res.writeHead(404); return res.end('not found'); }
      res.writeHead(200, { 'content-type': MIME[path.extname(full)] || 'application/octet-stream' });
      res.end(data);
    });
  } catch (err) {
    sendJson(res, 500, { error: String(err.message || err) });
  }
});

async function main() {
  const k8s = await sh('kubectl', ['-n', K8S_NS, 'get', 'ns', K8S_NS]);
  state.mode = k8s.ok ? 'k8s' : 'compose';
  const exists = await sh('docker', ['inspect', PRIMARY_CONTAINER]);
  if (!exists.ok) logEvent(`⚠️ 找不到 ${PRIMARY_CONTAINER}，請先 docker compose up -d`);
  logEvent(state.mode === 'k8s'
    ? `偵測到 K8s 命名空間 ${K8S_NS} → k8s 模式（真 HPA）`
    : `未偵測到 K8s → compose 模式（模擬 HPA：${SCALE_UP_CPU}% 擴展 / ${SCALE_DOWN_CPU}%×${SCALE_DOWN_TICKS} 縮回，最多 ${MAX_REPLICAS} 副本）`);
  if (state.mode === 'compose') setInterval(() => autoscalerTick().catch(() => {}), CHECK_MS);
  server.listen(PORT, () => console.log(`ops dashboard → http://localhost:${PORT}`));
}

main();

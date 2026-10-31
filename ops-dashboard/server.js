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
const REPLICA_PORTS = [18001, 18002, 18003, 18004]; // 額外副本發布到主機的埠（r2–r5）
const MAX_REPLICAS = 1 + REPLICA_PORTS.length;
const SCALE_UP_CPU = Number(process.env.OPS_SCALE_UP_CPU || 25); // 平均 CPU 高於此值 → 擴展
const SCALE_UP_TICKS = 2; // CPU 連續超標秒數：滿 2 秒才擴，避免瞬間雜訊誤觸
const CHECK_MS = 1000;
// 單一模擬程序約 400 人後自身飽和（Python 事件迴圈先成為瓶頸，服務端 CPU 反而測不高），
// 每個 worker 控制在 400 人內，確保壓力真實落在 location-service 上
const LOAD_WORKERS = [
  { max: 400, count: 1 },
  { max: 800, count: 2 },
  { max: Infinity, count: 3 },
];

const state = {
  mode: 'compose',
  load: { running: false, users: 0 },
  replicas: 1,
  rrIndex: 0,
  upTicks: 0,
  maxWarned: false,
  scaling: false,
  events: [], // { t: 'HH:MM:SS', msg }
  k8sReplicas: null, // k8s 模式上一輪的 HPA 副本數，用來偵測擴縮
  eventGen: { running: false },
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
    '[ -n "$members" ] && redis-cli -h redis zrem realtime_map_notice:user:locations $members',
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
  state.upTicks = 0;
  state.maxWarned = false;

  // 事件流併入：人越多事件越多（每 50 人 1 則/秒，上限 10 則/秒）
  const evtRate = Math.min(10, Math.max(1, Math.round(users / 50)));
  await startEventGenCompose(evtRate);

  logEvent(`⚡ 開始模擬：${users} 人湧入（${count} 個模擬 worker × ${perWorker} 人）＋ 事件流每秒約 ${evtRate} 則`);
}

// 清空所有事件：刪除事件本體、GEO 索引與反垃圾紀錄（demo 重來用），
// 並發布 reset 廣播讓所有前端立即清空地圖（不必等 15 秒定期同步）
async function clearEventsCompose() {
  const script = [
    "redis-cli --scan --pattern 'event:*' | xargs -r redis-cli del",
    'redis-cli del event_locations',
    "redis-cli --scan --pattern 'event_antispam:*' | xargs -r redis-cli del",
    "redis-cli publish realtime_map_notice:ops:reset '{\"type\":\"reset\"}'",
    'echo cleared',
  ].join(' && ');
  const r = await sh('docker', ['exec', `${COMPOSE_PROJECT}-redis-1`, 'sh', '-c', script]);
  logEvent(r.ok ? '🧹 已清空所有事件與反垃圾紀錄' : `⚠️ 清空失敗：${r.err}`);
  return r;
}

// 事件流：只發布測試事件（不打流量），事件會真實出現在地圖上
async function startEventGenCompose(rate = 10) {
  await stopEventGenCompose();
  // 與 docker-compose 的 INTERNAL_API_KEY 預設值保持一致（.env 可覆寫）
  const internalKey = process.env.INTERNAL_API_KEY || 'dev-internal-key';
  const r = await sh('docker', [
    'run', '-d', '--name', 'ops-event-gen',
    '--network', COMPOSE_NET,
    '-v', `${EVENT_GEN_SCRIPT}:/code/event_gen.py:ro`,
    '-e', `INTERNAL_API_KEY=${internalKey}`,
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
  await sh('docker', ['rm', '-f', 'ops-event-gen']);
  // 保險起見確認真的移除了；rm -f 對剛啟動（pip install 中）的容器偶發未生效
  const check = await sh('docker', ['inspect', 'ops-event-gen']);
  if (check.ok) await sh('docker', ['rm', '-f', 'ops-event-gen']);
  if (state.eventGen.running) logEvent('⏹ 事件模式：已停止發布');
  state.eventGen = { running: false };
}

async function stopLoadCompose() {
  // 先停事件流並確認容器已死：確保沒有任何來源繼續寫入事件，再清資料
  await stopEventGenCompose();
  let had = false;
  for (const name of [...loadWorkerNames(LOAD_WORKERS.at(-1).count), 'ops-load-generator']) {
    const r = await sh('docker', ['rm', '-f', name]);
    if (r.ok) had = true;
  }
  const wasRunning = state.load.running;
  if (wasRunning) logEvent(`⏹ 停止模擬（${state.load.users} 人與事件流已撤）`);
  state.load = { running: false, users: 0, workers: 0 };
  state.upTicks = 0;
  state.maxWarned = false;
  if (had || wasRunning) {
    const purged = await purgeSimUsers();
    if (purged.ok) logEvent('🧹 已清除模擬使用者在線紀錄（在線人數即時回落）');
    await clearEventsCompose();
    logEvent('🗺️ 地圖已清空（所有事件與數據歸零）');
    // 追加二次清空：捕捉清空當下仍在途中的寫入（事件最後幾筆請求、
    // 前端 15 秒定期抓取的競態），確保地圖不會再長出殘留事件
    setTimeout(() => {
      clearEventsCompose().then(() => logEvent('🧹 二次清空完成（確認無殘留）'));
    }, 2500);
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
  const extraPort = Object.fromEntries(
    extraReplicaNames(REPLICA_PORTS.length).map(({ name, port }) => [name, port]),
  );
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
    autoscaler: { up: SCALE_UP_CPU, max: MAX_REPLICAS, avgCpu },
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

// compose 模式的模擬 HPA：與真 HPA 相同的「CPU 超過門檻才擴展」行為。
// 擴展：平均 CPU ≥ 門檻連續 SCALE_UP_TICKS 秒 → +1 副本（階梯式，方塊依序彈出）；
// 壓測進行中不縮減（避免 demo 過程忽多忽少）；停止壓測後一律縮回 1 副本。
// 這樣 CPU 曲線會真實呈現「爬升 → 穿越門檻 → 擴展 → 回落」的 HPA 生命週期。
async function autoscalerTick() {
  if (state.scaling) return;
  const stats = await composeStats();
  const loc = stats.filter((s) => s.location);
  if (!loc.length) return;
  const replicas = Math.max(1, loc.length);
  state.replicas = replicas;
  const avgCpu = Math.round((loc.reduce((s, c) => s + (c.cpu || 0), 0) / loc.length) * 10) / 10;

  if (!state.load.running) {
    state.upTicks = 0;
    state.maxWarned = false;
    if (replicas > 1) {
      await scaleTo(1);
      logEvent('📉 壓測已停止，縮回 1 副本');
    }
    return;
  }

  if (avgCpu >= SCALE_UP_CPU) state.upTicks += 1;
  else state.upTicks = 0;

  if (state.upTicks >= SCALE_UP_TICKS && replicas < MAX_REPLICAS) {
    state.upTicks = 0;
    const next = replicas + 1;
    await scaleTo(next);
    logEvent(`📈 擴展：CPU ${avgCpu}% ≥ 門檻 ${SCALE_UP_CPU}%，${replicas} → ${next} 副本`);
  } else if (replicas >= MAX_REPLICAS && !state.maxWarned && state.upTicks >= SCALE_UP_TICKS) {
    state.maxWarned = true;
    logEvent(`⚠️ CPU ${avgCpu}% 仍高於門檻，已達最大副本數 ${MAX_REPLICAS}`);
  }
}

// ---------- k8s 模式 ----------

const tmp = (name) => path.join(require('os').tmpdir(), `${name}-${Date.now()}.yaml`);

async function startLoadK8s(users) {
  const cmFile = tmp('simulator-cm');
  const cm = await sh('kubectl', ['-n', K8S_NS, 'create', 'configmap', 'simulator-code',
    '--from-file', `simulate_users.py=${SIMULATOR_SCRIPT}`, '--dry-run=client', '-o', 'yaml']);
  if (!cm.ok) { logEvent(`⚠️ ConfigMap 建立失敗：${cm.err}`); return; }
  fs.writeFileSync(cmFile, cm.out);
  await sh('kubectl', ['apply', '-f', cmFile]);
  fs.unlinkSync(cmFile);
  const jobFile = tmp('load-generator');
  fs.writeFileSync(jobFile, fs.readFileSync(JOB_YAML, 'utf8').replace(/--users \d+/, `--users ${users}`));
  await killJobK8s('load-generator', true);
  const r = await sh('kubectl', ['apply', '-f', jobFile]);
  fs.unlinkSync(jobFile);
  state.load = { running: r.ok, users: r.ok ? users : 0 };
  await startEventGenK8s(); // 事件流跟著人數一起啟動
  logEvent(r.ok ? `⚡ K8s 模擬：Job load-generator 已建立（${users} 人）＋ 事件流` : `⚠️ Job 建立失敗：${r.err}`);
}

async function clearEventsK8s() {
  const script = [
    "redis-cli --scan --pattern 'event:*' | xargs -r redis-cli del",
    'redis-cli del event_locations',
    "redis-cli --scan --pattern 'event_antispam:*' | xargs -r redis-cli del",
    "redis-cli publish realtime_map_notice:ops:reset '{\"type\":\"reset\"}'",
    'echo cleared',
  ].join(' && ');
  const r = await sh('kubectl', ['-n', K8S_NS, 'exec', 'deploy/redis', '--', 'sh', '-c', script]);
  logEvent(r.ok ? '🧹 已清空所有事件與反垃圾紀錄' : `⚠️ 清空失敗：${r.err}`);
  return r;
}

async function startEventGenK8s() {
  const cmFile = tmp('event-gen-cm');
  const cm = await sh('kubectl', ['-n', K8S_NS, 'create', 'configmap', 'event-gen-code',
    '--from-file', `event_gen.py=${EVENT_GEN_SCRIPT}`, '--dry-run=client', '-o', 'yaml']);
  if (!cm.ok) { logEvent(`⚠️ ConfigMap 建立失敗：${cm.err}`); return; }
  fs.writeFileSync(cmFile, cm.out);
  await sh('kubectl', ['apply', '-f', cmFile]);
  fs.unlinkSync(cmFile);
  await killJobK8s('event-gen', true);
  const r = await sh('kubectl', ['apply', '-f', path.join(__dirname, '..', 'k8s', 'event-gen-job.yaml')]);
  state.eventGen = { running: r.ok };
  logEvent(r.ok ? '📢 K8s 事件模式：Job event-gen 已建立（持續發布輔大校園事件）' : `⚠️ Job 建立失敗：${r.err}`);
}

// 刪 Job 後立刻強制刪掉它的 Pod：不等 30 秒寬限期，流量與事件馬上斷
// waitGone：重新建立同名 Job 前要等舊的真正刪除，否則 apply 會撞到「正在刪除」
async function killJobK8s(name, waitGone = false) {
  const r = await sh('kubectl', ['-n', K8S_NS, 'delete', 'job', name, '--ignore-not-found', '--wait=false']);
  await sh('kubectl', ['-n', K8S_NS, 'delete', 'pod', '-l', `app=${name}`,
    '--grace-period=0', '--force', '--ignore-not-found']);
  if (waitGone) {
    await sh('kubectl', ['-n', K8S_NS, 'wait', '--for=delete', `job/${name}`, '--timeout=20s']);
  }
  return r;
}

// 與 compose 版 purgeSimUsers 相同：清掉模擬使用者（u-*）讓在線人數立即回落
async function purgeSimUsersK8s() {
  const script = [
    "members=$(redis-cli --scan --pattern 'realtime_map_notice:user:last_seen:u-*' | sed 's/.*last_seen://')",
    '{ [ -z "$members" ] || redis-cli zrem realtime_map_notice:user:locations $members; }',
    "redis-cli --scan --pattern 'realtime_map_notice:user:last_seen:u-*' | xargs -r redis-cli del",
    'echo purged',
  ].join(' && ');
  return sh('kubectl', ['-n', K8S_NS, 'exec', 'deploy/redis', '--', 'sh', '-c', script]);
}

async function stopEventGenK8s() {
  const r = await killJobK8s('event-gen');
  if (state.eventGen.running) logEvent('⏹ K8s 事件模式：Job 已刪除');
  state.eventGen = { running: false };
  if (!r.ok) logEvent(`⚠️ Job 刪除失敗：${r.err}`);
}

async function stopLoadK8s() {
  // 流量與事件兩個 Job 同時砍，再清資料
  const [, r] = await Promise.all([stopEventGenK8s(), killJobK8s('load-generator')]);
  if (state.load.running) logEvent('⏹ K8s 模擬：Job 已刪除');
  state.load = { running: false, users: 0 };
  if (!r.ok) logEvent(`⚠️ Job 刪除失敗：${r.err}`);
  const purged = await purgeSimUsersK8s();
  logEvent(purged.ok ? '🧹 已清除模擬使用者在線紀錄（在線人數即時回落）' : `⚠️ 清除模擬使用者失敗：${purged.err}`);
  await clearEventsK8s();
  logEvent('🗺️ 地圖已清空（所有事件與數據歸零）');
  // 二次清空：捕捉 Pod 被砍當下仍在途中的最後幾筆請求
  setTimeout(() => {
    Promise.all([purgeSimUsersK8s(), clearEventsK8s()])
      .then(() => logEvent('🧹 二次清空完成（確認無殘留）'));
  }, 2500);
}

// kubectl 的 CPU 數量：'104m' → 104、'0.5' → 500、'1' → 1000
function toMilli(v) {
  if (v == null || v === '?') return null;
  const s = String(v);
  const n = parseFloat(s);
  if (Number.isNaN(n)) return null;
  return s.endsWith('m') ? n : n * 1000;
}

async function k8sStatus() {
  const [pods, top, hpa, job, evtJob] = await Promise.all([
    sh('kubectl', ['-n', K8S_NS, 'get', 'pods', '-o', 'json']),
    sh('kubectl', ['-n', K8S_NS, 'top', 'pods', '--no-headers']),
    sh('kubectl', ['-n', K8S_NS, 'get', 'hpa', '-o', 'json']),
    sh('kubectl', ['-n', K8S_NS, 'get', 'job', 'load-generator', '-o', 'json']),
    sh('kubectl', ['-n', K8S_NS, 'get', 'job', 'event-gen', '-o', 'json']),
  ]);

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
      const reqMilli = toMilli(item.spec.containers?.[0]?.resources?.requests?.cpu);
      const useMilli = toMilli(cpuByPod[name]);
      services.push({
        name,
        short: labels.app || name,
        phase: item.status.phase,
        cpu: cpuByPod[name] || '?',
        // 與 HPA 同基準：用量 ÷ requests，方便和門檻直接比較
        cpuPct: reqMilli && useMilli != null ? Math.round((useMilli / reqMilli) * 100) : null,
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
        targetCpu: item.spec.targetCPUUtilizationPercentage ?? item.spec.metrics?.find((m) => m.resource?.name === 'cpu')?.resource?.target?.averageUtilization,
        current: item.status.currentReplicas,
        desired: item.status.desiredReplicas,
        cpu: item.status.currentCPUUtilizationPercentage ?? item.status.currentMetrics?.find((m) => m.resource?.name === 'cpu')?.resource?.current?.averageUtilization,
      };
    }
  }
  // 真 HPA 的擴縮由叢集決定，ops 只觀察副本數變化並寫進事件紀錄
  if (hpaInfo && hpaInfo.current != null) {
    const prev = state.k8sReplicas;
    if (prev != null && hpaInfo.current > prev) {
      logEvent(`📈 HPA 擴展：location-service ${prev} → ${hpaInfo.current} 副本（CPU ${hpaInfo.cpu ?? '?'}% ≥ 門檻 ${hpaInfo.targetCpu}%）`);
    } else if (prev != null && hpaInfo.current < prev) {
      logEvent(`📉 HPA 縮減：location-service ${prev} → ${hpaInfo.current} 副本`);
    }
    state.k8sReplicas = hpaInfo.current;
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
      .map((s) => ({ id: s.name, label: s.name.replace(/^location-service-/, ''), cpu: s.cpu, cpuPct: s.cpuPct, phase: s.phase })),
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
      const users = Math.min(3000, Math.max(10, Number(body.users) || 500));
      if (state.mode === 'k8s') await startLoadK8s(users);
      else await startLoadCompose(users);
      return sendJson(res, 200, { ok: true, users });
    }

    if (url.pathname === '/api/events/clear' && req.method === 'POST') {
      if (state.mode === 'k8s') await clearEventsK8s();
      else await clearEventsCompose();
      return sendJson(res, 200, { ok: true });
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
  const exists = state.mode === 'compose' ? await sh('docker', ['inspect', PRIMARY_CONTAINER]) : { ok: true };
  if (!exists.ok) logEvent(`⚠️ 找不到 ${PRIMARY_CONTAINER}，請先 docker compose up -d`);
  logEvent(state.mode === 'k8s'
    ? `偵測到 K8s 命名空間 ${K8S_NS} → k8s 模式（真 HPA）`
    : `未偵測到 K8s → compose 模式（模擬 HPA：平均 CPU ${SCALE_UP_CPU}% 連續 ${SCALE_UP_TICKS} 秒擴展，最多 ${MAX_REPLICAS} 副本，停止後縮回 1）`);
  if (state.mode === 'compose') setInterval(() => autoscalerTick().catch(() => {}), CHECK_MS);
  server.listen(PORT, () => console.log(`ops dashboard → http://localhost:${PORT}`));
}

main();

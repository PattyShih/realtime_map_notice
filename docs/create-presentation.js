#!/usr/bin/env node
const pptxgen = require('pptxgenjs');
const fs = require('fs');

const slides = JSON.parse(fs.readFileSync('docs/slides-content.json', 'utf8'));
const icons = JSON.parse(fs.readFileSync('docs/icons.json', 'utf8'));

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = 'realtime_map_notice';
pres.title = '即時校園地圖通知系統';

// Colors
const NAVY = '1E2761';
const ICE = 'CADCFC';
const TEAL = '0891B2';
const WHITE = 'FFFFFF';
const LIGHT = 'F0F4FF';
const DARK = '0F172A';
const GRAY = '64748B';
const LGRAY = 'E2E8F0';
const GREEN = '10B981';
const RED = 'EF4444';
const ORANGE = 'F59E0B';

// Helper: fresh shadow each call
const mkShadow = () => ({ type: 'outer', color: '000000', blur: 4, offset: 2, angle: 135, opacity: 0.1 });

// ============ SLIDE MASTERS ============
// Dark title/section slide
function addDarkSlide(title, subtitle, bullets, notes, icon) {
  const slide = pres.addSlide();
  slide.background = { color: NAVY };
  // Accent line top
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: TEAL } });
  // Title
  slide.addText(title, { x: 0.8, y: 1.2, w: 8.4, h: 1.2, fontSize: 36, fontFace: 'Arial Black', color: WHITE, bold: true });
  if (subtitle) {
    slide.addText(subtitle, { x: 0.8, y: 2.4, w: 8.4, h: 0.5, fontSize: 18, fontFace: 'Calibri', color: ICE, italic: true });
  }
  if (bullets && bullets.length > 0) {
    const items = bullets.map((b, i) => ({
      text: b,
      options: { bullet: true, breakLine: i < bullets.length - 1, fontSize: 16, color: LGRAY }
    }));
    slide.addText(items, { x: 0.8, y: subtitle ? 3.1 : 2.6, w: 8.4, h: 2.2, fontFace: 'Calibri', paraSpaceAfter: 6 });
  }
  if (icon && icons[icon]) {
    slide.addImage({ data: icons[icon], x: 8.6, y: 0.4, w: 0.8, h: 0.8, transparency: 30 });
  }
  // Bottom accent
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.5, w: 10, h: 0.125, fill: { color: TEAL } });
  if (notes) slide.addNotes(notes);
  return slide;
}

// Light content slide
function addLightSlide(title, bullets, notes, extra) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  // Top bar
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.04, fill: { color: TEAL } });
  // Title area
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.04, w: 10, h: 0.9, fill: { color: NAVY } });
  slide.addText(title, { x: 0.6, y: 0.1, w: 8.8, h: 0.8, fontSize: 24, fontFace: 'Arial Black', color: WHITE, bold: true });
  // Bottom bar
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.5, w: 10, h: 0.125, fill: { color: NAVY } });
  // Page number
  slide.addText(String(slide.slideNumber || ''), { x: 9.2, y: 5.1, w: 0.5, h: 0.3, fontSize: 10, color: GRAY, align: 'right' });

  if (bullets && bullets.length > 0) {
    const items = bullets.map((b, i) => ({
      text: b,
      options: { bullet: true, breakLine: i < bullets.length - 1, fontSize: 15, color: DARK, paraSpaceAfter: 6 }
    }));
    slide.addText(items, { x: 0.8, y: 1.3, w: 8.4, h: 3.8, fontFace: 'Calibri', valign: 'top' });
  }
  if (extra) extra(slide);
  if (notes) slide.addNotes(notes);
  return slide;
}

// ============ BUILD SLIDES ============
slides.forEach((s, idx) => {
  const n = s.slide;
  const isDark = [1, 2, 3, 33, 34, 35].includes(n);

  if (isDark) {
    // ---- DARK SLIDES ----
    if (n === 1) {
      // Title slide — special layout
      const sl = pres.addSlide();
      sl.background = { color: NAVY };
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: TEAL } });
      if (icons.globe) sl.addImage({ data: icons.globe, x: 4.1, y: 0.6, w: 1.8, h: 1.8, transparency: 20 });
      sl.addText('即時校園地圖通知系統', { x: 0.8, y: 2.5, w: 8.4, h: 1.0, fontSize: 38, fontFace: 'Arial Black', color: WHITE, bold: true, align: 'center' });
      sl.addText('Real-time Campus Map Notification System', { x: 0.8, y: 3.4, w: 8.4, h: 0.5, fontSize: 16, fontFace: 'Calibri', color: ICE, align: 'center', italic: true });
      sl.addShape(pres.shapes.RECTANGLE, { x: 3.5, y: 4.1, w: 3, h: 0.03, fill: { color: TEAL } });
      // Team
      const team = [
        '成員A：Web 前端 UI/UX',
        '成員B：後端 API 開發',
        '成員C：Redis / WebSocket 推播',
        '成員D：Docker / 壓測 / 部署'
      ].map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < 3, fontSize: 13, color: LGRAY } }));
      sl.addText(team, { x: 2.5, y: 4.3, w: 5, h: 1.0, fontFace: 'Calibri', align: 'center' });
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.5, w: 10, h: 0.125, fill: { color: TEAL } });
    } else if (n === 33) {
      // Q&A
      const sl = pres.addSlide();
      sl.background = { color: NAVY };
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: TEAL } });
      if (icons.comments) sl.addImage({ data: icons.comments, x: 4.3, y: 1.0, w: 1.4, h: 1.4, transparency: 20 });
      sl.addText('Q & A', { x: 0.8, y: 2.6, w: 8.4, h: 1.0, fontSize: 48, fontFace: 'Arial Black', color: WHITE, bold: true, align: 'center' });
      sl.addText('歡迎提問與討論', { x: 0.8, y: 3.6, w: 8.4, h: 0.5, fontSize: 18, fontFace: 'Calibri', color: ICE, align: 'center' });
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.5, w: 10, h: 0.125, fill: { color: TEAL } });
    } else if (n === 34) {
      // Demo
      const sl = pres.addSlide();
      sl.background = { color: NAVY };
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: TEAL } });
      if (icons.rocket) sl.addImage({ data: icons.rocket, x: 4.3, y: 0.8, w: 1.4, h: 1.4, transparency: 20 });
      sl.addText('Live Demo', { x: 0.8, y: 2.4, w: 8.4, h: 0.8, fontSize: 40, fontFace: 'Arial Black', color: WHITE, bold: true, align: 'center' });
      sl.addText('https://map2.avision-gb10.org', { x: 0.8, y: 3.3, w: 8.4, h: 0.5, fontSize: 20, fontFace: 'Calibri', color: TEAL, align: 'center', hyperlink: { url: 'https://map2.avision-gb10.org' } });
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.5, w: 10, h: 0.125, fill: { color: TEAL } });
    } else if (n === 35) {
      // Thank you
      const sl = pres.addSlide();
      sl.background = { color: NAVY };
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: TEAL } });
      sl.addText('感謝聆聽', { x: 0.8, y: 2.0, w: 8.4, h: 1.0, fontSize: 44, fontFace: 'Arial Black', color: WHITE, bold: true, align: 'center' });
      sl.addShape(pres.shapes.RECTANGLE, { x: 3.5, y: 3.1, w: 3, h: 0.03, fill: { color: TEAL } });
      sl.addText('即時校園地圖通知系統 | 專題展示', { x: 0.8, y: 3.4, w: 8.4, h: 0.5, fontSize: 16, fontFace: 'Calibri', color: ICE, align: 'center' });
      sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.5, w: 10, h: 0.125, fill: { color: TEAL } });
    } else {
      addDarkSlide(s.title, s.subtitle, s.bullets, s.notes);
    }
  } else if (n === 2) {
    // 動機 — dark with icon cards
    addDarkSlide(s.title, s.subtitle, s.bullets, s.notes, 'warning');
  } else if (n === 3) {
    // 使用情境 — two column cards
    const sl = addLightSlide(s.title, null, s.notes);
    // Left: general
    sl.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.3, w: 4.2, h: 3.8, fill: { color: LIGHT }, shadow: mkShadow() });
    sl.addText('📋 一般事件', { x: 0.9, y: 1.5, w: 3.6, h: 0.5, fontSize: 18, fontFace: 'Arial Black', color: NAVY, bold: true });
    const general = ['圖書館 3 樓目前有空位', '學餐某攤排隊人潮很長', '校園廣場有免費活動', '某棟大樓附近有遺失物'].map((t,i) => ({ text: t, options: { bullet: true, breakLine: i < 3, fontSize: 14, color: DARK } }));
    sl.addText(general, { x: 0.9, y: 2.1, w: 3.6, h: 2.5, fontFace: 'Calibri' });
    // Right: urgent
    sl.addShape(pres.shapes.RECTANGLE, { x: 5.2, y: 1.3, w: 4.2, h: 3.8, fill: { color: 'FFF5F5' }, shadow: mkShadow() });
    sl.addText('🚨 緊急事件', { x: 5.5, y: 1.5, w: 3.6, h: 0.5, fontSize: 18, fontFace: 'Arial Black', color: RED, bold: true });
    const urgent = ['路上有走失的寵物', '某區域施工或封路', '天橋臨時無法通行', '校內突發安全提醒'].map((t,i) => ({ text: t, options: { bullet: true, breakLine: i < 3, fontSize: 14, color: DARK } }));
    sl.addText(urgent, { x: 5.5, y: 2.1, w: 3.6, h: 2.5, fontFace: 'Calibri' });

  } else if (n === 4) {
    // 系統架構概覽 — flow diagram
    const sl = addLightSlide(s.title, null, s.notes);
    const boxes = [
      { label: '瀏覽器\nReact + Leaflet', x: 0.4, y: 1.5, w: 1.8, h: 1.0, color: TEAL, textColor: WHITE },
      { label: 'nginx\n:8080→:8095', x: 2.8, y: 1.5, w: 1.8, h: 1.0, color: '475569', textColor: WHITE },
      { label: '定位服務\n:8001 ×4', x: 5.2, y: 1.3, w: 1.8, h: 0.7, color: GREEN, textColor: WHITE },
      { label: '事件服務\n:8002 ×4', x: 5.2, y: 2.2, w: 1.8, h: 0.7, color: '3B82F6', textColor: WHITE },
      { label: '通知服務\n:8003 ×1', x: 5.2, y: 3.1, w: 1.8, h: 0.7, color: ORANGE, textColor: WHITE },
      { label: 'Redis 7\nGEO+LIST+PubSub', x: 7.8, y: 1.8, w: 1.8, h: 1.4, color: '7C3AED', textColor: WHITE },
    ];
    boxes.forEach(b => {
      sl.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: b.x, y: b.y, w: b.w, h: b.h, fill: { color: b.color }, rectRadius: 0.08, shadow: mkShadow() });
      sl.addText(b.label, { x: b.x, y: b.y, w: b.w, h: b.h, fontSize: 11, fontFace: 'Calibri', color: b.textColor, align: 'center', valign: 'middle', bold: true });
    });
    // Arrows (text-based)
    const arrows = ['→', '→', '→', '↗', '↘'];
    sl.addText('→', { x: 2.2, y: 1.7, w: 0.6, h: 0.5, fontSize: 22, color: GRAY, align: 'center' });
    sl.addText('→', { x: 4.6, y: 1.7, w: 0.6, h: 0.5, fontSize: 22, color: GRAY, align: 'center' });
    sl.addText('→', { x: 7.0, y: 2.2, w: 0.6, h: 0.5, fontSize: 22, color: GRAY, align: 'center' });
    // Flow annotations
    sl.addText('WebSocket ←──────────────────────────┘', { x: 5.2, y: 3.9, w: 4.5, h: 0.4, fontSize: 11, color: GRAY, italic: true });
    sl.addText('Cloudflare Tunnel: map2.avision-gb10.org → localhost:8095', { x: 0.4, y: 4.5, w: 9.2, h: 0.4, fontSize: 12, color: TEAL, italic: true });

  } else if ([20, 21, 22].includes(n)) {
    // Stress test slides — with chart
    const users = n === 20 ? 200 : n === 21 ? 500 : 1000;
    const locPct = n === 20 ? 99.1 : n === 21 ? 98.4 : 95.5;
    const evtPct = n === 20 ? 99.0 : 100;
    const cmtPct = n === 20 ? 100 : n === 21 ? 99.1 : 100;
    const qryPct = 100;
    const rps = n === 20 ? 112 : n === 21 ? 277 : 271;

    const sl = addLightSlide(s.title, null, s.notes);
    // Bar chart
    sl.addChart(pres.charts.BAR, [{
      name: '成功率 %',
      labels: ['Location', 'Event', 'Comment', 'Query'],
      values: [locPct, evtPct, cmtPct, qryPct]
    }], {
      x: 0.5, y: 1.3, w: 5.5, h: 3.5,
      barDir: 'col',
      chartColors: [TEAL],
      showValue: true,
      dataLabelPosition: 'outEnd',
      dataLabelColor: DARK,
      valAxisMin: 90,
      valAxisMax: 101,
      catAxisLabelColor: DARK,
      valAxisLabelColor: GRAY,
      valGridLine: { color: LGRAY, size: 0.5 },
      catGridLine: { style: 'none' },
      showLegend: false,
    });
    // Stats cards
    const stats = [
      { label: '並發使用者', val: String(users), color: NAVY },
      { label: '總 RPS', val: String(rps), color: TEAL },
      { label: 'Event 成功率', val: evtPct + '%', color: GREEN },
    ];
    stats.forEach((st, i) => {
      const sy = 1.4 + i * 1.2;
      sl.addShape(pres.shapes.RECTANGLE, { x: 6.5, y: sy, w: 3.0, h: 0.9, fill: { color: LIGHT }, shadow: mkShadow() });
      sl.addText(st.val, { x: 6.6, y: sy + 0.05, w: 2.8, h: 0.5, fontSize: 24, fontFace: 'Arial Black', color: st.color, bold: true });
      sl.addText(st.label, { x: 6.6, y: sy + 0.5, w: 2.8, h: 0.3, fontSize: 12, color: GRAY });
    });

  } else if (n === 24) {
    // Redis Pub/Sub optimization — before/after comparison
    const sl = addLightSlide(s.title, null, s.notes);
    // Before card
    sl.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.4, w: 4.0, h: 3.5, fill: { color: 'FFF5F5' }, shadow: mkShadow() });
    sl.addText('❌ 優化前：HTTP Fanout', { x: 0.9, y: 1.6, w: 3.4, h: 0.5, fontSize: 16, fontFace: 'Arial Black', color: RED, bold: true });
    const before = [
      'Event Service 逐筆 HTTP POST 通知',
      '500 人時 Event 成功率僅 8.1%',
      'fanout 佔用回應時間 90%+',
      '跨服務耦合嚴重'
    ].map((t,i) => ({ text: t, options: { bullet: true, breakLine: i < 3, fontSize: 13, color: DARK } }));
    sl.addText(before, { x: 0.9, y: 2.3, w: 3.4, h: 2.2, fontFace: 'Calibri' });

    // After card
    sl.addShape(pres.shapes.RECTANGLE, { x: 5.4, y: 1.4, w: 4.0, h: 3.5, fill: { color: 'F0FFF4' }, shadow: mkShadow() });
    sl.addText('✅ 優化後：Redis Pub/Sub', { x: 5.7, y: 1.6, w: 3.4, h: 0.5, fontSize: 16, fontFace: 'Arial Black', color: GREEN, bold: true });
    const after = [
      'Event Service 只 PUBLISH 一條命令',
      '500 人 Event 成功率 → 100%',
      '微秒級回應，無跨服務等待',
      '完全解耦，各自擴展'
    ].map((t,i) => ({ text: t, options: { bullet: true, breakLine: i < 3, fontSize: 13, color: DARK } }));
    sl.addText(after, { x: 5.7, y: 2.3, w: 3.4, h: 2.2, fontFace: 'Calibri' });

  } else if (n === 27) {
    // 分工 — 4 columns
    const sl = addLightSlide(s.title, null, s.notes);
    const members = [
      { name: '成員 A', role: 'Web 前端', items: ['React + Vite 架構', 'Leaflet 地圖整合', 'UI/UX 設計', '事件表單與快選'] },
      { name: '成員 B', role: '後端 API', items: ['FastAPI 微服務', '事件 CRUD', '商業邏輯', 'API 設計'] },
      { name: '成員 C', role: 'Redis / WebSocket', items: ['Redis GEO 查詢', 'Pub/Sub 推播', 'WebSocket 管理', '離線佇列'] },
      { name: '成員 D', role: 'DevOps / 壓測', items: ['Docker Compose', 'nginx 設定', '壓力測試腳本', 'Cloudflare 部署'] },
    ];
    members.forEach((m, i) => {
      const mx = 0.4 + i * 2.4;
      sl.addShape(pres.shapes.RECTANGLE, { x: mx, y: 1.3, w: 2.2, h: 3.6, fill: { color: LIGHT }, shadow: mkShadow() });
      sl.addShape(pres.shapes.RECTANGLE, { x: mx, y: 1.3, w: 2.2, h: 0.06, fill: { color: TEAL } });
      sl.addText(m.name, { x: mx + 0.15, y: 1.5, w: 1.9, h: 0.4, fontSize: 16, fontFace: 'Arial Black', color: NAVY, bold: true });
      sl.addText(m.role, { x: mx + 0.15, y: 1.9, w: 1.9, h: 0.3, fontSize: 12, color: TEAL, italic: true });
      const items = m.items.map((t,j) => ({ text: t, options: { bullet: true, breakLine: j < m.items.length-1, fontSize: 12, color: DARK } }));
      sl.addText(items, { x: mx + 0.15, y: 2.4, w: 1.9, h: 2.2, fontFace: 'Calibri' });
    });

  } else if (n === 23) {
    // 效能瓶頸 — trend chart
    const sl = addLightSlide(s.title, null, s.notes);
    sl.addChart(pres.charts.LINE, [
      { name: 'Location', labels: ['200人', '500人', '1000人'], values: [99.1, 98.4, 95.5] },
      { name: 'Event', labels: ['200人', '500人', '1000人'], values: [99.0, 100, 100] },
      { name: 'Comment', labels: ['200人', '500人', '1000人'], values: [100, 99.1, 100] },
      { name: 'Query', labels: ['200人', '500人', '1000人'], values: [100, 100, 100] },
    ], {
      x: 0.5, y: 1.3, w: 6.0, h: 3.8,
      lineSize: 3,
      lineSmooth: false,
      chartColors: [ORANGE, TEAL, '3B82F6', GREEN],
      showLegend: true,
      legendPos: 'b',
      valAxisMin: 93,
      valAxisMax: 101,
      catAxisLabelColor: DARK,
      valAxisLabelColor: GRAY,
      valGridLine: { color: LGRAY, size: 0.5 },
      showValue: false,
    });
    sl.addText('瓶頸：Location Service\n1000 人時降至 95.5%\n\n解決方向：\n• 加 workers\n• Redis pipeline batch', {
      x: 7.0, y: 1.5, w: 2.5, h: 3.0, fontSize: 13, fontFace: 'Calibri', color: DARK, valign: 'top'
    });

  } else if (n === 10) {
    // Redis 資料結構 — 3 cards
    const sl = addLightSlide(s.title, null, s.notes);
    const redis = [
      { title: 'GEO', desc: '儲存使用者座標\nGEORADIUS 查詢附近\nO(N+log(M)) 複雜度', color: TEAL },
      { title: 'LIST', desc: '事件歷史（最新100筆）\n留言（每事件100則）\n離線佇列 pending:{uid}', color: GREEN },
      { title: 'Pub/Sub', desc: 'event_channel 事件推播\nPUBLISH 微秒級回應\nSUBSCRIBE 訂閱解耦', color: '7C3AED' },
    ];
    redis.forEach((r, i) => {
      const rx = 0.5 + i * 3.1;
      sl.addShape(pres.shapes.RECTANGLE, { x: rx, y: 1.4, w: 2.9, h: 3.2, fill: { color: LIGHT }, shadow: mkShadow() });
      sl.addShape(pres.shapes.RECTANGLE, { x: rx, y: 1.4, w: 2.9, h: 0.06, fill: { color: r.color } });
      sl.addText(r.title, { x: rx + 0.2, y: 1.6, w: 2.5, h: 0.5, fontSize: 20, fontFace: 'Arial Black', color: r.color, bold: true });
      sl.addText(r.desc, { x: rx + 0.2, y: 2.2, w: 2.5, h: 2.0, fontSize: 13, fontFace: 'Calibri', color: DARK });
    });

  } else if (n === 32) {
    // 結論 — big stats
    const sl = addLightSlide(s.title, null, s.notes);
    const stats = [
      { val: '1000', unit: '人', label: '壓測通過', color: TEAL },
      { val: '100%', unit: '', label: 'Event 成功率', color: GREEN },
      { val: '271', unit: 'RPS', label: '總吞吐量', color: NAVY },
      { val: '~470', unit: 'MB', label: '記憶體佔用', color: ORANGE },
    ];
    stats.forEach((st, i) => {
      const sx = 0.5 + i * 2.4;
      sl.addShape(pres.shapes.RECTANGLE, { x: sx, y: 1.5, w: 2.2, h: 2.0, fill: { color: LIGHT }, shadow: mkShadow() });
      sl.addText(st.val + st.unit, { x: sx, y: 1.6, w: 2.2, h: 1.0, fontSize: 36, fontFace: 'Arial Black', color: st.color, bold: true, align: 'center' });
      sl.addText(st.label, { x: sx, y: 2.7, w: 2.2, h: 0.4, fontSize: 13, color: GRAY, align: 'center' });
    });
    sl.addText('核心成果', { x: 0.5, y: 4.0, w: 9.0, h: 0.4, fontSize: 16, fontFace: 'Arial Black', color: NAVY, bold: true });
    const achievements = [
      'Redis Pub/Sub 解耦架構，Event/Comment/Query 1000 人零失敗',
      '完整微服務架構：3 後端 + Redis + nginx + 前端',
      '離線通知佇列、事件過期、留言系統、冪等性全部實作'
    ].map((t,i) => ({ text: t, options: { bullet: true, breakLine: i < 2, fontSize: 14, color: DARK } }));
    sl.addText(achievements, { x: 0.5, y: 4.4, w: 9.0, h: 1.0, fontFace: 'Calibri' });

  } else if (n === 19) {
    // 部署架構 — flow with cards
    const sl = addLightSlide(s.title, null, s.notes);
    const flow = [
      { label: 'Cloudflare\nTunnel', sub: 'map2.avision-\ngb10.org', color: ORANGE },
      { label: 'nginx\n:8080', sub: '反向代理\n靜態+API+WS', color: '475569' },
      { label: 'Docker\nCompose', sub: '5 容器\n~470MB', color: TEAL },
      { label: 'DGX Spark\nGB10', sub: '20-core ARM\n119GB RAM', color: NAVY },
    ];
    flow.forEach((f, i) => {
      const fx = 0.4 + i * 2.4;
      sl.addShape(pres.shapes.RECTANGLE, { x: fx, y: 1.5, w: 2.1, h: 2.5, fill: { color: LIGHT }, shadow: mkShadow() });
      sl.addShape(pres.shapes.RECTANGLE, { x: fx, y: 1.5, w: 2.1, h: 0.06, fill: { color: f.color } });
      sl.addText(f.label, { x: fx + 0.15, y: 1.7, w: 1.8, h: 1.0, fontSize: 15, fontFace: 'Arial Black', color: f.color, bold: true, align: 'center' });
      sl.addText(f.sub, { x: fx + 0.15, y: 2.7, w: 1.8, h: 1.0, fontSize: 12, color: GRAY, align: 'center' });
      if (i < flow.length - 1) {
        sl.addText('→', { x: fx + 2.1, y: 2.3, w: 0.3, h: 0.5, fontSize: 22, color: TEAL, align: 'center' });
      }
    });

  } else {
    // ---- DEFAULT LIGHT SLIDE ----
    addLightSlide(s.title, s.bullets, s.notes);
  }
});

// Save
pres.writeFile({ fileName: 'docs/presentation.pptx' }).then(() => {
  const stats = fs.statSync('docs/presentation.pptx');
  console.log(`✅ Saved docs/presentation.pptx (${(stats.size / 1024).toFixed(0)} KB, ${slides.length} slides)`);
}).catch(e => {
  console.error('Failed:', e);
  process.exit(1);
});

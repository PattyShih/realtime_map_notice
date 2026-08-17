#!/usr/bin/env node
// Step 1: Generate slide content using DeepSeek API directly (bypassing LiteLLM)
const https = require('https');

const DEEPSEEK_KEY = 'sk-ae9455da07f948169ca696bf3ff8f90a';

function deepseek(messages, maxTokens = 2048) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({ model: 'deepseek-chat', messages, max_tokens: maxTokens });
    const opts = {
      hostname: 'api.deepseek.com',
      path: '/chat/completions',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${DEEPSEEK_KEY}` }
    };
    const req = https.request(opts, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        try { resolve(JSON.parse(body)); }
        catch(e) { reject(new Error(body)); }
      });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function main() {
  const systemPrompt = `你是一個簡報設計助手。請為以下專題生成 35 張投影片的詳細內容（每一張的標題 + 要點）。

專題名稱：即時校園地圖通知系統
成員：成員A（Web前端的UI/UX）、成員B（後端API）、成員C（Redis/WebSocket推播）、成員D（Docker/壓測/部署）
技術：React+Vite+TypeScript+Leaflet前端、FastAPI微服務、Redis 7（ GEO+LIST+Pub/Sub）、nginx、Docker Compose

請嚴格輸出 35 項 JSON陣列，每項格式：
{
  "slide": 1,
  "title": "標題（繁體中文）",
  "subtitle": "副標（可選）",
  "bullets": ["要點1", "要點2", ...],
  "notes": "台上講稿備註（可選）"
}

請確保覆蓋：動機與問題、使用情境、系統架構、前端、後端微服務（定位/事件/通知）、Redis資料結構、事件推播流程、離線通知機制、前端功能展示（事件快選/有效期限/留言）、WebSocket即時通訊、安全性設計、部署架構、壓力測試（200/500/1000人結果）、效能瓶頸分析、Redis Pub/Sub優化對比、容量與資源、開發過程、分工、遇到的挑戰與解決方案、未來展望、結論。

直接輸出JSON陣列，不需要任何其他文字。`;

  console.log('Calling DeepSeek API...');
  const resp = await deepseek([
    { role: 'system', content: systemPrompt },
    { role: 'user', content: '請為這個專題生成35張投影片的內容' }
  ], 4096);

  const content = resp.choices?.[0]?.message?.content || '';
  // Extract JSON from response
  let jsonStart = content.indexOf('[');
  let jsonEnd = content.lastIndexOf(']') + 1;
  if (jsonStart < 0 || jsonEnd <= 0) {
    // Try outer braces
    jsonStart = content.indexOf('{');
    jsonEnd = content.lastIndexOf('}') + 1;
  }
  const jsonStr = content.substring(jsonStart, jsonEnd);
  const slides = JSON.parse(jsonStr);
  require('fs').writeFileSync('docs/slides-content.json', JSON.stringify(slides, null, 2));
  console.log(`Generated ${slides.length} slides, saved to docs/slides-content.json`);
  console.log('First slide:', JSON.stringify(slides[0], null, 2));
}

main().catch(e => { console.error(e); process.exit(1); });

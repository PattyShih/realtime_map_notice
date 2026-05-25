# Web App

這個資料夾是 `realtime_map_notice` 的瀏覽器前端。Demo 介面以 Web App 為主，不開發 iOS 或 Android 原生 App。

## 技術

- React + Vite + TypeScript
- Leaflet + OpenStreetMap tiles
- Browser Geolocation API
- Fetch API 串接 Location Service 與 Event Service
- WebSocket 串接 Notification Service

## 常用指令

```powershell
npm install
npm run dev
npm run lint
npm run build
npm run preview
```

開發伺服器預設：

```text
http://localhost:5173
```

## 環境變數

請參考 [.env.example](./.env.example)。

```text
VITE_LOCATION_SERVICE_URL=http://localhost:8001
VITE_EVENT_SERVICE_URL=http://localhost:8002
VITE_NOTIFICATION_WS_URL=ws://localhost:8003
```

若未設定，程式會使用上面的 localhost 預設值。

## 目前功能

| 功能 | 狀態 | 說明 |
|------|------|------|
| 地圖顯示 | 已有 | Leaflet 顯示校園地圖 |
| 使用者定位 | 已有 | 使用 `navigator.geolocation.watchPosition`，失敗時使用預設校園座標 |
| 定期位置上傳 | 已有 | `App.tsx` 每 1.5 秒呼叫 Location Service |
| 事件插旗表單 | 已有 | 點擊地圖後可建立事件 |
| 事件 marker | 已有 | 本機建立事件與 WebSocket 收到事件都會顯示 |
| WebSocket 通知 | 已有 | 支援斷線重連與 app-level ping/pong |
| 通知 Banner | 已有 | 收到通知後可顯示並移動到事件位置 |
| 手機版細節 | 待加強 | 需要更多 responsive QA |

## UI/UX 注意事項

- 地圖是主畫面核心，資訊卡片與表單不可長時間遮住主要地圖內容。
- 一般事件應保持低干擾，緊急事件需要明顯呈現。
- 插旗表單需短而清楚，Demo 時最好 20 秒內可送出事件。
- 定位被拒絕時，要顯示可理解的狀態，並使用預設校園座標或手動選點。
- 通知 Banner 需要顯示事件標題、距離與查看位置動作。
- 手機寬度下，主要按鈕、事件卡片與通知 Banner 不能互相遮擋。
- 按鈕觸控區域建議至少 44px 高。

## 地圖服務與 API key

目前預設使用 Leaflet + OpenStreetMap tiles，通常不需要 API key。

其他選項：

| 方案 | 是否需要 API key | 適合情境 |
|------|------------------|----------|
| Leaflet + OpenStreetMap tiles | 通常不需要 | 初期開發與低風險 Demo |
| MapLibre GL JS + 外部 tile/style provider | 視 provider 而定 | 需要更細緻的地圖視覺 |
| Google Maps JavaScript API | 需要 | 需要完整商用地圖能力 |

若改用 Google Maps：

- 啟用 Maps JavaScript API。
- 限制 HTTP referrers，例如 `localhost:5173` 與正式網域。
- 設定 quota 或 budget alert。
- 不要把真實 key commit 到 GitHub。

## 相關文件

- [../readme.md](../readme.md)：專案總覽。
- [../system.md](../system.md)：系統架構與 API contract。
- [../development.md](../development.md)：本機開發、測試與 Demo 流程。
- [../docs/project-plan.md](../docs/project-plan.md)：專案計畫。
- [../docs/progress.md](../docs/progress.md)：即時進度表。

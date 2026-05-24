# Web App 初始方向

這個資料夾保留給前端 Web App，以瀏覽器作為主要 Demo 介面。

建議功能：

- 全螢幕地圖介面
- 使用 browser Geolocation API 取得目前位置
- 在地圖上新增事件插旗
- 事件列表與緊急通知 Banner
- 透過 WebSocket 接收 500 公尺內事件通知

UI/UX 注意事項請參考 [../docs/ui-ux-guidelines.md](../docs/ui-ux-guidelines.md)。

建議技術：

- React + Vite
- 地圖元件可使用 Leaflet、MapLibre GL JS 或 Google Maps JavaScript API
- WebSocket client 串接 Notification Service
- Fetch API 串接 Location Service 與 Event Service

設計重點：

- 地圖是主畫面核心，資訊卡片與表單不可長時間遮住主要地圖內容。
- 事件標記需依嚴重程度區分，一般事件低干擾，緊急事件明顯呈現。
- 定位失敗時需提供手動選點或預設校園座標。
- WebSocket 斷線時需顯示重連狀態。
- 手機瀏覽器寬度下，事件列表建議使用底部抽屜。

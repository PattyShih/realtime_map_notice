# Web App 初始方向

這個資料夾保留給前端 Web App，以瀏覽器作為主要 Demo 介面。

建議功能：

- 全螢幕地圖介面
- 使用 browser Geolocation API 取得目前位置
- 在地圖上新增事件插旗
- 事件列表與緊急通知 Banner
- 透過 WebSocket 接收 500 公尺內事件通知

建議技術：

- React + Vite
- 地圖元件可使用 Leaflet、MapLibre GL JS 或 Google Maps JavaScript API
- WebSocket client 串接 Notification Service
- Fetch API 串接 Location Service 與 Event Service

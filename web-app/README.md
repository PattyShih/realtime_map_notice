# Web App 初始方向

這個資料夾保留給前端 Web App，以瀏覽器作為主要 Demo 介面。

建議功能：

- 全螢幕地圖介面
- 使用 browser Geolocation API 取得目前位置
- 在地圖上新增事件插旗
- 即時更新使用者位置 marker 與事件 marker
- 事件列表與緊急通知 Banner
- 透過 WebSocket 接收 500 公尺內事件通知

UI/UX 注意事項請參考 [../docs/ui-ux-guidelines.md](../docs/ui-ux-guidelines.md)。
即時位置更新資料規格請參考 [../docs/realtime-location-requirements.md](../docs/realtime-location-requirements.md)。

建議技術：

- React + Vite
- 地圖元件可使用 Leaflet、MapLibre GL JS 或 Google Maps JavaScript API
- WebSocket client 串接 Notification Service
- Fetch API 串接 Location Service 與 Event Service

建議目錄：

```text
web-app/
├── src/
│   ├── components/
│   │   ├── MapView.tsx
│   │   ├── EventForm.tsx
│   │   ├── EventList.tsx
│   │   └── NotificationBanner.tsx
│   ├── hooks/
│   │   ├── useGeolocation.ts
│   │   └── useNotificationSocket.ts
│   ├── services/
│   │   ├── locationApi.ts
│   │   ├── eventApi.ts
│   │   └── websocket.ts
│   ├── types/
│   │   └── api.ts
│   └── App.tsx
├── package.json
└── vite.config.ts
```

設計重點：

- 地圖是主畫面核心，資訊卡片與表單不可長時間遮住主要地圖內容。
- 事件標記需依嚴重程度區分，一般事件低干擾，緊急事件明顯呈現。
- 定位失敗時需提供手動選點或預設校園座標。
- WebSocket 斷線時需顯示重連狀態。
- 手機瀏覽器寬度下，事件列表建議使用底部抽屜。

核心元件職責：

| 元件 | 職責 |
|------|------|
| `MapView` | 顯示地圖、使用者位置與事件標記 |
| `EventForm` | 新增事件，包含類型、嚴重程度、標題與說明 |
| `EventList` | 顯示附近事件，支援點擊後移動地圖 |
| `NotificationBanner` | 顯示緊急事件通知與「查看位置」動作 |
| `useGeolocation` | 封裝瀏覽器定位、權限錯誤與 fallback 座標 |
| `useNotificationSocket` | 封裝 WebSocket 連線、斷線重連與訊息解析 |

位置更新規則：

- Demo 預設每 1 秒上傳一次目前位置。
- 一般使用情境可改成每 2-3 秒，或移動超過 10 公尺才上傳。
- 定位精度大於 100 公尺時，畫面需提示定位不準。
- 定位失敗時使用手動選點或預設校園座標。
- WebSocket 收到事件通知時，地圖要新增事件 marker，通知 Banner 的「查看位置」要能移動到該座標。

環境變數建議：

```text
VITE_LOCATION_SERVICE_URL=http://localhost:8001
VITE_EVENT_SERVICE_URL=http://localhost:8002
VITE_NOTIFICATION_WS_URL=ws://localhost:8003
```

前端完成條件：

- 可以顯示地圖與目前位置。
- 可以定期呼叫 `POST /locations`。
- 目前位置 marker 會隨定位資料更新。
- 可以發布事件並在地圖上看到標記。
- 可以建立 WebSocket 連線並收到通知。
- 收到通知後可以在地圖上看到事件 marker。
- 定位失敗、API 失敗、WebSocket 斷線時都有畫面提示。

# 四人團隊分工

## 成員 A：前端 UI/UX 開發

- 建立 Web App 專案與主要畫面
- 決定地圖函式庫（Leaflet / MapLibre GL JS / Google Maps）
- 使用地圖元件顯示校園地圖、使用者定位、事件插旗
- **實作 WebSocket client 斷線重連（exponential backoff）與錯誤處理 UI**
- 設計地圖上方資訊卡片、事件列表、緊急通知 Banner
- 串接 Location Service、Event Service 與 WebSocket
- **撰寫前端相關的 WebSocket 連線測試與 API 串接測試**
- 交付 `web-app/`、地圖主畫面、事件表單與通知元件
- Demo 時負責展示一般使用者如何查看地圖與發布事件

## 成員 B：後端 API 與商業邏輯

- 維護 Event Service
- 設計事件資料格式與 API contract
- 實作登入雛形、發布事件、事件分類
- **在 Event Service 加入 CORS middleware**
- **實作 Event Service 多副本冪等性（事件去重）**
- **優化通知發送方式（asyncio.gather 批次發送或改用 Redis Pub/Sub 直發）**
- 補上 API 測試與錯誤處理
- **撰寫 Event Service 與 Location Service 的 API 測試（pytest + httpx.AsyncClient）**
- 交付事件 API、事件 payload 文件與測試指令
- Demo 時負責說明事件如何從 Web App 進入後端流程

## 成員 C：資料庫與即時連線

- 維護 Redis GEO 結構
- 維護 Notification Service 與 WebSocket 連線管理
- **補上 WebSocket ping/pong 心跳，清理 ghost connection**
- **在 Notification Service 加入 CORS middleware**
- 設計即時通知 payload
- 測試 500 公尺附近查詢結果
- 交付 Redis GEO 查詢流程、WebSocket 推播流程與測試結果
- **撰寫 Notification Service 的 WebSocket 連線測試**
- Demo 時負責說明為什麼即時位置使用 Redis，而不是每秒寫入傳統資料庫

## 成員 D：DevOps 與 K8s 架構

- 撰寫 Dockerfile 與 Kubernetes YAML
- **建立根目錄 .dockerignore，優化 Docker build 速度**
- 設定 Deployment、Service、HPA、Resource requests/limits
- 撰寫 3,000 虛擬使用者壓測腳本
- Demo 時展示 `kubectl get hpa -w` 與刪除 Pod 容錯
- 交付 `k8s/`、`simulator/`、HPA 截圖與 Pod 容錯截圖
- Demo 時負責操作終端機展示自動擴展與容錯

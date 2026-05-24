# 四人團隊分工

這份文件把四位成員的責任拆成「主要工作、交付物、Demo 說明重點」。實作時可以平行進行，但 API contract、WebSocket payload 與 K8s 部署方式需要定期同步，避免最後整合時才發現前後端對不上。

## 成員 A：前端 UI/UX 開發

- 建立 Web App 專案與主要畫面
- 決定地圖函式庫（Leaflet / MapLibre GL JS / Google Maps）
- 使用地圖元件顯示校園地圖、使用者定位、事件插旗
- 依照 [ui-ux-guidelines.md](./ui-ux-guidelines.md) 設計地圖、事件列表、插旗表單與通知 Banner
- **實作 WebSocket client 斷線重連（exponential backoff）與錯誤處理 UI**
- 設計地圖上方資訊卡片、事件列表、緊急通知 Banner
- 串接 Location Service、Event Service 與 WebSocket
- **撰寫前端相關的 WebSocket 連線測試與 API 串接測試**
- 交付 `web-app/`、地圖主畫面、事件表單、通知元件與 UI/UX 檢查清單
- Demo 時負責展示一般使用者如何查看地圖與發布事件

需要與其他成員同步：

- 與 B 確認 `POST /events` payload 欄位。
- 與 C 確認 WebSocket notification JSON 格式。
- 與 D 確認本機與 K8s port-forward 後的 API URL。

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

需要與其他成員同步：

- 與 A 確認前端事件表單欄位與錯誤訊息格式。
- 與 C 確認附近使用者查詢結果與通知 payload。
- 與 D 確認 event-service replica 數量與環境變數。

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

需要與其他成員同步：

- 與 A 確認 WebSocket 斷線重連與通知 UI 狀態。
- 與 B 確認 Event Service 呼叫 Notification Service 的方式。
- 與 D 確認 Redis 與 Notification Service 多副本部署行為。

## 成員 D：DevOps 與 K8s 架構

- 撰寫 Dockerfile 與 Kubernetes YAML
- **建立根目錄 .dockerignore，優化 Docker build 速度**
- 設定 Deployment、Service、HPA、Resource requests/limits
- 撰寫 3,000 虛擬使用者壓測腳本
- Demo 時展示 `kubectl get hpa -w` 與刪除 Pod 容錯
- 交付 `k8s/`、`simulator/`、HPA 截圖與 Pod 容錯截圖
- Demo 時負責操作終端機展示自動擴展與容錯

需要與其他成員同步：

- 與 B、C 確認 Docker image 名稱與環境變數。
- 與 A 確認前端是否使用 port-forward 或 docker-compose URL。
- 與全員確認 Demo 腳本、截圖備案與現場操作順序。

## 整合會議建議

- 每週至少一次 15 分鐘同步 API 與 Demo 進度。
- 第 3 週開始固定確認 Web App 能否連到後端。
- 第 6 週開始固定確認 Redis GEO 與 WebSocket 完整鏈路。
- 第 8 週前完成第一版 HPA 截圖與 Pod 容錯截圖。
- 第 9 週開始只修 Demo 風險，不再加入大型新功能。

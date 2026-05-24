# 專案詳細計畫

這份文件把 `realtime_map_notice` 拆成可執行的開發階段、四人分工、Demo 流程與驗收標準。目標不是一次做成正式產品，而是在專題期限內完成一個技術重點清楚、展示效果強、分工明確的系統。

## 專案範圍

必做功能：

- Web App 顯示校園或街區地圖。
- 使用者可以在地圖上發布事件。
- 使用者位置會定期上傳到 Location Service。
- 後端使用 Redis GEO 儲存即時位置。
- 發布緊急事件時，只通知半徑 500 公尺內使用者。
- 使用 WebSocket 將事件主動推送到前端。
- 使用 Python 腳本模擬 3,000 位虛擬使用者持續移動。
- 使用 Kubernetes 展示 Location Service 自動擴展。
- 使用 Kubernetes 展示 Notification Service Pod 容錯。

暫不納入第一版：

- 正式會員註冊與密碼管理。
- 複雜社群功能，例如留言、按讚、好友。
- 長期軌跡分析與歷史熱區報表。
- 原生手機 App。
- 正式上架與公開營運。

## 階段規劃

### 第 1 階段：架構與後端骨架

目標：

- 先讓系統的微服務邊界清楚。
- 建立可本機啟動的後端環境。
- 讓每個組員有明確可接手的模組。

工作項目：

- 建立 `location-service`，提供位置上傳 API。
- 建立 `event-service`，提供事件發布 API。
- 建立 `notification-service`，提供 WebSocket 連線與通知 API。
- 建立 `shared`，放共用 schema、Redis client 與設定。
- 建立 Redis GEO key 命名規則。
- 建立 `docker-compose.yml`，讓本機可以一次啟動所有後端服務。
- 建立每個服務的 Dockerfile。

交付物：

- 三個 FastAPI 微服務。
- Redis 連線設定。
- 基本 API 文件，可透過 `/docs` 查看。
- 本機啟動文件。

驗收標準：

- 可以成功呼叫 `POST /locations` 更新使用者座標。
- 可以成功呼叫 `GET /locations/nearby` 查詢附近使用者。
- 可以成功呼叫 `POST /events` 建立事件。
- Notification Service 可以接受 WebSocket 連線。

### 第 2 階段：Web App 前端

目標：

- 建立可展示的使用者介面。
- 讓教授能直觀看到「地圖、插旗、附近通知」。
- 前端以瀏覽器為主，不開發原生手機 App。

工作項目：

- 建立 Web App 專案。
- 設計全螢幕地圖主畫面。
- 使用 browser Geolocation API 取得目前位置。
- 定期呼叫 Location Service 上傳位置。
- 建立事件發布表單，包含標題、內容、類型、嚴重程度。
- 在地圖上顯示事件標記。
- 建立 WebSocket client，接收 Notification Service 推播。
- 收到緊急事件時顯示通知 Banner 或側邊事件卡片。

交付物：

- 可在瀏覽器執行的 Web App。
- 地圖頁面、事件表單、通知元件。
- 與三個後端服務的串接。

驗收標準：

- 使用者開啟 Web App 後可以看到地圖。
- 使用者允許定位後，前端會定期上傳座標。
- 使用者可以從 Web App 發布事件。
- 當附近有緊急事件時，Web App 會即時顯示通知。

### 第 3 階段：即時資料與推播整合

目標：

- 確保 500 公尺區域推播邏輯正確。
- 讓多個 Notification Service Pod 也能處理 WebSocket 分散問題。

工作項目：

- 使用 Redis GEO 的 `GEOADD` 儲存使用者位置。
- 使用 Redis GEO 的 `GEOSEARCH` 查詢半徑內使用者。
- Event Service 對每個附近使用者送出通知請求。
- Notification Service 使用 Redis Pub/Sub 發布使用者專屬通知。
- 持有 WebSocket 連線的 Pod 訂閱對應 channel 並推送給前端。
- 補上事件 payload 格式與錯誤處理。

交付物：

- 500 公尺內使用者查詢流程。
- 多副本 Notification Service 可用的通知流程。
- 測試資料與測試指令。

驗收標準：

- 半徑內使用者會收到通知。
- 半徑外使用者不會收到通知。
- Notification Service 多副本時，通知仍能送到正確 WebSocket 連線。

### 第 4 階段：Kubernetes 與壓測

目標：

- 展示 K8s 的高併發處理、自動擴展與容錯能力。
- 讓專題 Demo 有明確技術亮點。

工作項目：

- 建立 Redis、Location Service、Event Service、Notification Service 的 K8s YAML。
- 為服務設定 resource requests 與 limits。
- 為 Location Service 設定 HPA。
- 為服務設定 readiness probe 與 liveness probe。
- 建立 3,000 人虛擬使用者壓測腳本。
- Demo 時觀察 Pod 數量變化與 HPA 狀態。
- Demo 時刪除一個 Notification Service Pod，觀察自動重建。

交付物：

- `k8s/` 部署檔。
- `simulator/` 壓測腳本。
- Demo 操作指令。
- HPA 與 Pod 狀態截圖。

驗收標準：

- `kubectl apply -f k8s/` 可以部署系統。
- 壓測期間 Location Service Pod 會自動擴展。
- 刪除 Pod 後 Kubernetes 會自動補回副本。
- 系統在 Demo 過程中仍可處理位置更新與事件推播。

### 第 5 階段：報告與展示整理

目標：

- 把技術成果轉成教授容易理解的展示內容。
- 每位組員都有清楚貢獻與可說明的技術點。

工作項目：

- 整理系統架構圖。
- 整理資料流圖。
- 整理 API 表格。
- 整理 K8s 部署圖。
- 整理壓測結果與截圖。
- 撰寫四人分工與心得。
- 準備 8 到 10 分鐘 Demo 腳本。

交付物：

- 專題簡報。
- 專題報告。
- Demo 腳本。
- GitHub repo。

驗收標準：

- 報告能清楚說明為什麼使用 Redis GEO、WebSocket 與 K8s。
- Demo 能在限制時間內完整展示日常情境與技術亮點。
- 每位成員都能說明自己的負責模組。

## 四人詳細分工

### 成員 A：Web App 與 UI/UX

主要責任：

- 建立 Web App 專案。
- 設計地圖主畫面。
- 實作事件插旗表單。
- 實作即時通知 Banner 或通知列表。
- 串接 Location Service、Event Service 與 WebSocket。

建議交付：

- `web-app/` 前端專案。
- 地圖頁面截圖。
- 前端操作 Demo 影片或截圖。

報告可寫重點：

- 使用瀏覽器定位取得使用者位置。
- 使用地圖 UI 呈現空間資訊。
- 使用 WebSocket 達成即時通知體驗。

### 成員 B：後端 API 與事件邏輯

主要責任：

- 維護 Event Service。
- 定義事件 API payload。
- 實作事件建立、事件分類與嚴重程度。
- 呼叫 Redis GEO 查詢附近使用者。
- 呼叫 Notification Service 發送通知。

建議交付：

- Event Service API。
- API 文件與測試指令。
- 事件流程說明。

報告可寫重點：

- 微服務拆分與 API contract。
- 事件發布流程。
- 區域推播的商業邏輯。

### 成員 C：Redis 與即時推播

主要責任：

- 維護 Redis GEO key 與資料格式。
- 維護 Notification Service。
- 實作 WebSocket 連線管理。
- 實作 Redis Pub/Sub 通知同步。
- 測試半徑內與半徑外通知結果。

建議交付：

- Redis GEO 操作說明。
- WebSocket 推播流程。
- 500 公尺通知測試結果。

報告可寫重點：

- 為什麼即時位置適合放 Redis。
- Redis GEO 如何支援附近查詢。
- 多副本 WebSocket 服務如何透過 Pub/Sub 協作。

### 成員 D：DevOps、K8s 與壓測

主要責任：

- 撰寫 Dockerfile。
- 撰寫 Kubernetes YAML。
- 設定 HPA、resource requests、readiness probe。
- 撰寫 3,000 人壓測腳本。
- 規劃 Demo 操作流程。

建議交付：

- `k8s/` 部署檔。
- `simulator/` 壓測腳本。
- HPA 擴展截圖。
- Pod 容錯截圖。

報告可寫重點：

- Kubernetes Deployment 與 Service。
- HPA 自動擴展。
- Pod failure recovery。
- 壓測如何模擬真實使用者流量。

## Demo 腳本

1. 開啟 Web App，說明校園即時地圖情境。
2. 使用瀏覽器定位，讓系統開始上傳目前位置。
3. 在地圖上新增一般事件，例如圖書館有空位。
4. 開啟另一個測試使用者頁面，展示 WebSocket 連線。
5. 發布緊急事件，展示半徑內使用者收到通知。
6. 啟動 3,000 人壓測腳本，說明大量座標更新。
7. 使用 `kubectl get hpa -w` 展示 Location Service 自動擴展。
8. 刪除一個 Notification Service Pod。
9. 使用 `kubectl get pods -w` 展示 Kubernetes 自動重建。
10. 總結 Redis GEO、WebSocket、K8s 在系統中的角色。

## 風險與備案

風險：本機效能不足以穩定模擬 3,000 人。

備案：先用 300 到 1,000 人展示流程，報告中說明參數可調，並保留 3,000 人腳本設定。

風險：HPA 沒有擴展。

備案：確認 metrics-server 是否啟用，並調低 Location Service CPU request 或壓測 interval。

風險：瀏覽器定位權限被拒絕。

備案：提供手動選點或使用預設校園座標。

風險：WebSocket 多副本通知沒有命中正確 Pod。

備案：使用 Redis Pub/Sub，讓所有 Notification Service Pod 都能訂閱使用者通知 channel。

風險：Demo 網路不穩或 Docker/K8s 啟動過慢。

備案：提前準備截圖、錄影與已啟動環境，現場以短指令展示關鍵狀態。


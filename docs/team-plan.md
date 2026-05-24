# 四人團隊分工

## 成員 A：前端 UI/UX 開發

- 建立 Web App 專案與主要畫面
- 使用地圖元件顯示校園地圖、使用者定位、事件插旗
- 設計地圖上方資訊卡片、事件列表、緊急通知 Banner
- 串接 Location Service、Event Service 與 WebSocket

## 成員 B：後端 API 與商業邏輯

- 維護 Event Service
- 設計事件資料格式與 API contract
- 實作登入雛形、發布事件、事件分類
- 補上 API 測試與錯誤處理

## 成員 C：資料庫與即時連線

- 維護 Redis GEO 結構
- 維護 Notification Service 與 WebSocket 連線管理
- 設計即時通知 payload
- 測試 500 公尺附近查詢結果

## 成員 D：DevOps 與 K8s 架構

- 撰寫 Dockerfile 與 Kubernetes YAML
- 設定 Deployment、Service、HPA、Resource requests/limits
- 撰寫 3,000 虛擬使用者壓測腳本
- Demo 時展示 `kubectl get hpa -w` 與刪除 Pod 容錯

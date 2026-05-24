# Development Guide

這份文件描述 `realtime_map_notice` 的初步開發方式、測試方式與 Demo 流程。現階段目標是先完成可展示的專案骨架，後續再逐步補齊正式功能。

> **CORS 注意：** 所有後端服務預設沒有 CORS 設定。前端開發伺服器與後端不同 origin 時，瀏覽器會擋掉請求。需在 docker-compose 或各服務啟動前補上 CORS middleware，否則 Web App 無法串接 API。

> **.dockerignore 注意：** 根目錄目前沒有 `.dockerignore`。Docker build 時會把 `.git`、`__pycache__` 等不必要檔案送入 build context，導致建置變慢。

## 環境需求

建議安裝：

- Python 3.12+
- Docker Desktop
- Kubernetes 環境，例如 Docker Desktop Kubernetes 或 minikube
- kubectl
- metrics-server，用於 HPA 指標
- Node.js 20+，用於 Web App 開發

## 本機開發流程

建立 Python 虛擬環境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安裝壓測腳本依賴：

```powershell
pip install -r simulator/requirements.txt
```

啟動本機服務：

```powershell
docker compose up --build
```

預設服務位置：

- Location Service: http://localhost:8001/docs
- Event Service: http://localhost:8002/docs
- Notification Service: ws://localhost:8003/ws/{user_id}
- Redis: localhost:6379

## API 初步測試

更新使用者位置：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8001/locations `
  -ContentType application/json `
  -Body '{"user_id":"u-0001","latitude":25.0173,"longitude":121.5397}'
```

查詢附近使用者：

```powershell
Invoke-RestMethod "http://localhost:8001/locations/nearby?latitude=25.0173&longitude=121.5397&radius_meters=500"
```

發布事件：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8002/events `
  -ContentType application/json `
  -Body '{"title":"Library seats","message":"3F has seats near windows","latitude":25.0173,"longitude":121.5397,"severity":"info","radius_meters":500}'
```

## 基本測試

專案目前沒有任何自動化測試。建議在第二階段開始前補上各服務的基礎 API 測試：

- Location Service：測試 `POST /locations`、`GET /locations/nearby`。
- Event Service：測試 `POST /events`，確認附近查詢與推播呼叫正確。
- Notification Service：測試 WebSocket 連線與斷線行為。

測試框架建議使用 `pytest` + `httpx.AsyncClient`，Redis 可使用 `fakeredis` 或 docker-compose 提供的實體 Redis。完整測試計畫與案例請參考 [docs/test-plan.md](./docs/test-plan.md)。

## 壓測模擬

模擬 3,000 名虛擬使用者每秒上傳位置：

```powershell
python simulator/simulate_users.py --users 3000 --target http://localhost:8001 --interval 1
```

若本機效能不足，可以先用較小數字測試：

```powershell
python simulator/simulate_users.py --users 300 --target http://localhost:8001 --interval 1
```

## Kubernetes Demo 流程

建立 Docker image：

```powershell
docker build -t realtime-map-notice/location-service:latest -f backend/location-service/Dockerfile .
docker build -t realtime-map-notice/event-service:latest -f backend/event-service/Dockerfile .
docker build -t realtime-map-notice/notification-service:latest -f backend/notification-service/Dockerfile .
```

部署到 Kubernetes：

```powershell
kubectl apply -f k8s/
```

觀察 Pod：

```powershell
kubectl -n realtime-map-notice get pods -w
```

觀察 HPA：

```powershell
kubectl -n realtime-map-notice get hpa -w
```

刪除一個 Notification Service Pod 展示容錯：

```powershell
$pod = kubectl -n realtime-map-notice get pod -l app=notification-service -o jsonpath="{.items[0].metadata.name}"
kubectl -n realtime-map-notice delete pod $pod
```

## 開發里程碑

詳細分工與驗收標準請參考 [docs/project-plan.md](./docs/project-plan.md)。

### 第一階段：專案骨架

- 建立三個後端服務的基本 API。
- 建立 Redis GEO 位置儲存雛形。
- 建立 WebSocket 推播雛形。
- 建立 Dockerfile、docker-compose 與 Kubernetes YAML。
- 建立壓測腳本。

完成條件：

- `docker compose up --build` 可以啟動 Redis 與三個後端服務。
- Location Service 可以接收座標並寫入 Redis。
- Event Service 可以查詢 500 公尺內使用者。
- Notification Service 可以透過 WebSocket 推送事件。
- simulator 可以產生可調整人數的座標更新流量。

### 第二階段：功能整合

- Web App 定位上傳。
- Web App 地圖插旗。
- WebSocket 接收附近事件通知。
- 事件分類、嚴重程度與基本登入。

完成條件：

- 使用者可以在瀏覽器地圖上看到目前位置。
- 使用者可以新增一般事件與緊急事件。
- 緊急事件只通知半徑內的測試使用者。
- 前端能清楚顯示通知內容、距離與事件類型。
- API 錯誤時前端有基本提示，不會靜默失敗。

### 第三階段：Demo 強化

- HPA 自動擴展示範。
- Pod 刪除後自動復原展示。
- 壓測數據截圖與報告整理。
- API、架構圖與簡報素材整理。

完成條件：

- 可用 `kubectl get hpa -w` 看到 Location Service Pod 數量上升。
- 可手動刪除 Notification Service Pod 並看到 Kubernetes 自動重建。
- Demo 流程可在 8 到 10 分鐘內完整呈現。
- 報告包含架構圖、資料流、K8s 展示截圖與四人貢獻。

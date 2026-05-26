# Development Guide

這份文件描述 `realtime_map_notice` 的初步開發方式、測試方式與 Demo 流程。現階段目標是先完成可展示的專案骨架，後續再逐步補齊正式功能。

> **CORS 注意：** 三個後端服務已加入 CORS middleware，預設允許 `http://localhost:5173` 與 `http://localhost:3000`。若前端改用其他 port 或正式網域，請更新 `CORS_ALLOW_ORIGINS`。

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

建議使用兩種開發模式：

- 後端模式：只啟動 Redis 與三個 FastAPI 服務，優先測 API、Redis GEO 與 WebSocket。
- 前後端整合模式：同時啟動 Web App dev server 與後端服務，測瀏覽器定位、CORS 與即時通知。

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

建議每次開發前先確認服務健康狀態：

```powershell
Invoke-RestMethod http://localhost:8001/healthz
Invoke-RestMethod http://localhost:8002/healthz
Invoke-RestMethod http://localhost:8003/healthz
```

若其中一個服務沒有回應，先檢查：

- `docker compose ps`
- `docker compose logs location-service`
- `docker compose logs event-service`
- `docker compose logs notification-service`

啟動 `docker compose up --build -d` 後，也可以直接跑一鍵 smoke test。這會檢查三個服務健康狀態、寫入兩個測試使用者位置、查詢 500 公尺附近使用者、建立 urgent event 並確認通知 fan-out：

```powershell
.\scripts\compose-smoke-test.ps1
```

成功時最後會看到：

```text
COMPOSE SMOKE TEST PASSED
```

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

測試 WebSocket 通知時，可以先用瀏覽器或 WebSocket client 連到：

```text
ws://localhost:8003/ws/u-0001
```

再呼叫 Notification Service：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8003/notify/u-0001 `
  -ContentType application/json `
  -Body '{"event_id":"demo-event","title":"Urgent notice","message":"Test notification","latitude":25.0173,"longitude":121.5397,"severity":"urgent","distance_meters":120}'
```

如果 WebSocket client 收到 JSON 訊息，代表 Notification Service 的基本推播流程正常。

## 基本測試

專案目前已有第一批後端單元測試，涵蓋 schema 驗證、active user 過濾與通知發送 helper。建議接著補上各服務的基礎 API 測試：

- Location Service：測試 `POST /locations`、`GET /locations/nearby`。
- Event Service：測試 `POST /events`，確認附近查詢與推播呼叫正確。
- Notification Service：測試 WebSocket 連線與斷線行為。

執行目前已有的單元測試：

```powershell
python -m pytest tests/unit -v
```

測試框架建議使用 `pytest` + `httpx.AsyncClient`，Redis 可使用 `fakeredis` 或 docker-compose 提供的實體 Redis。完整測試計畫與案例請參考 [docs/test-plan.md](./docs/test-plan.md)。

## 壓測模擬

初期建議先模擬 500-1,000 名虛擬使用者每秒上傳位置：

```powershell
python simulator/simulate_users.py --users 500 --target http://localhost:8001 --interval 1
python simulator/simulate_users.py --users 1000 --target http://localhost:8001 --interval 1
```

進階展示或截圖時，再挑戰 3,000 人：

```powershell
python simulator/simulate_users.py --users 3000 --target http://localhost:8001 --interval 1
```

若本機效能不足，可以先用較小數字測試：

```powershell
python simulator/simulate_users.py --users 300 --target http://localhost:8001 --interval 1
```

壓測時建議分三段：

1. `--users 100`：確認服務能接收流量且沒有明顯錯誤。
2. `--users 500`：初期目標，適合一般筆電預演。
3. `--users 1000`：初期進階目標，觀察 HPA 是否有擴展跡象。
4. `--users 3000`：最終挑戰或截圖用，觀察服務極限，不作為初期成功標準。

壓測時同步觀察：

```powershell
docker compose logs -f location-service
```

## Kubernetes Demo 流程

建立 Docker image：

```powershell
.\scripts\k8s-build-images.ps1
```

部署到 Kubernetes：

```powershell
.\scripts\k8s-deploy.ps1
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
.\scripts\k8s-delete-notification-pod.ps1
```

Demo 前檢查清單：

- `kubectl -n realtime-map-notice get pods` 顯示所有 Pod Running。
- `kubectl -n realtime-map-notice get svc` 顯示三個服務與 Redis。
- `kubectl -n realtime-map-notice get hpa` 不應長期顯示 `<unknown>`。
- 已準備好 HPA 擴展截圖與 Pod 重建截圖作為備案。
- 壓測腳本先用 300 人做 smoke test，正式 Demo 目標使用 500 人起跳，確認不會在 Demo 現場立刻失敗。

## 公開網址與 Cloudflare Tunnel 規劃

若後續要讓非開發者容易使用，不建議要求對方連 `localhost`、記三個後端 port，或手動開前端 dev server。建議改成：

```text
使用者 -> https://map.example.com -> Cloudflare -> Cloudflare Tunnel -> 本機 / K8s 入口
```

建議工作項目：

1. 註冊一個專題展示用網域，並把 DNS 交給 Cloudflare 管理。
2. 建立 Cloudflare Tunnel，讓 `cloudflared` 從本機或展示主機主動連到 Cloudflare。
3. 加入反向代理或 Kubernetes Ingress，把多個服務整理成單一公開入口：

```text
https://map.example.com/              -> Web App
https://map.example.com/api/location  -> Location Service
https://map.example.com/api/events    -> Event Service
wss://map.example.com/ws/{user_id}    -> Notification Service
```

4. 更新前端環境變數，讓 API 與 WebSocket 指向正式網域。
5. 更新三個後端服務的 `CORS_ALLOW_ORIGINS`，只允許正式網域與必要的本機開發 origin。
6. Demo 前確認 Cloudflare proxy 下 WebSocket 連線、ping/pong heartbeat 與通知推播都正常。

最短 Demo 方案可以先使用 Cloudflare Tunnel 暫時網址，但正式展示建議使用固定網域，避免每次重啟 tunnel 後網址改變。

## 開發里程碑

詳細分工與驗收標準請參考 [docs/project-plan.md](./docs/project-plan.md)。

### 第一階段：專案骨架

- 建立三個後端服務的基本 API。
- 建立 Redis GEO 位置儲存雛形。
- 建立 WebSocket 推播雛形。
- 建立 Dockerfile、docker-compose 與 Kubernetes YAML。
- 建立壓測腳本。

完成條件：

- `docker compose up --build` 可以啟動 Redis 與三個後端服務。 ✅
- Location Service 可以接收座標並寫入 Redis。 ✅
- Event Service 可以查詢 500 公尺內使用者。 ✅
- Notification Service 可以透過 WebSocket 推送事件。 ✅
- simulator 可以產生可調整人數的座標更新流量。 ✅

### 第二階段：功能整合

- Web App 定位上傳。
- Web App 地圖插旗。
- WebSocket 接收附近事件通知。
- 事件分類、嚴重程度與 Demo 用簡易 user_id。

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

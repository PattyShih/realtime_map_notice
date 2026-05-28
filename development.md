# Development Guide

這份文件描述 `realtime_map_notice` 的初步開發方式、測試方式與 Demo 流程。現階段目標是先完成可展示的專案骨架，後續再逐步補齊正式功能。

> **CORS 注意：** 三個後端服務已加入 CORS middleware，預設允許 `http://localhost:5173` 與 `http://localhost:3000`。若前端改用其他 port 或正式網域，請更新 `CORS_ALLOW_ORIGINS`。

> **.dockerignore 注意：** 根目錄已有 `.dockerignore`，會排除 `.git`、`.venv`、`__pycache__`、`node_modules` 與多數 Markdown 文件，減少 Docker build context。

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

```bash
python -m venv .venv
source .venv/bin/activate
```

安裝壓測腳本依賴：

```bash
pip install -r simulator/requirements.txt
```

啟動本機服務：

```bash
docker compose up --build
```

預設服務位置：

- Location Service: http://localhost:8001/docs
- Event Service: http://localhost:8002/docs
- Notification Service: ws://localhost:8003/ws/{user_id}
- Redis: localhost:6379

建議每次開發前先確認服務健康狀態：

```bash
curl http://localhost:8001/healthz
curl http://localhost:8002/healthz
curl http://localhost:8003/healthz
```

若其中一個服務沒有回應，先檢查：

- `docker compose ps`
- `docker compose logs location-service`
- `docker compose logs event-service`
- `docker compose logs notification-service`

啟動 `docker compose up --build -d` 後，也可以直接跑一鍵 smoke test。這會檢查三個服務健康狀態、寫入兩個測試使用者位置、查詢 500 公尺附近使用者、建立 urgent event 並確認通知 fan-out：

```bash
bash scripts/compose-smoke-test.sh
```

成功時最後會看到：

```text
COMPOSE SMOKE TEST PASSED
```

## API 初步測試

更新使用者位置：

```bash
curl -X POST http://localhost:8001/locations \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u-0001","latitude":25.0173,"longitude":121.5397}'
```

查詢附近使用者：

```bash
curl "http://localhost:8001/locations/nearby?latitude=25.0173&longitude=121.5397&radius_meters=500"
```

發布事件：

```bash
curl -X POST http://localhost:8002/events \
  -H "Content-Type: application/json" \
  -d '{"title":"Library seats","message":"3F has seats near windows","latitude":25.0173,"longitude":121.5397,"severity":"info","radius_meters":500}'
```

測試 WebSocket 通知時，可以先用瀏覽器或 WebSocket client 連到：

```text
ws://localhost:8003/ws/u-0001
```

WebSocket 通知已改用 Redis Pub/Sub，不再透過 HTTP API 觸發。測試方式：開啟兩個瀏覽器視窗連線 WebSocket，在其中一個視窗發布事件，確認另一個視窗收到通知。

## 基本測試

專案目前已有第一批後端單元測試，涵蓋 schema 驗證、active user 過濾與通知發送 helper。建議接著補上各服務的基礎 API 測試：

- Location Service：測試 `POST /locations`、`GET /locations/nearby`。
- Event Service：測試 `POST /events`，確認附近查詢與推播呼叫正確。
- Notification Service：測試 WebSocket 連線與斷線行為。

執行目前已有的單元測試：

```bash
python -m pytest tests/unit -v
```

執行跨服務整合測試時，需要 Docker Desktop 正在執行。此腳本會啟動 docker-compose、等待三個服務健康，然後驗證 Location → Redis → Event → Notification → WebSocket 的 Demo 核心鏈路：

```bash
bash scripts/run-integration-tests.sh
```

測試框架建議使用 `pytest` + `httpx.AsyncClient`，Redis 可使用 `fakeredis` 或 docker-compose 提供的實體 Redis。完整測試計畫與案例請參考 [docs/test-plan.md](./docs/test-plan.md)。

## 壓測模擬

```bash
# 200 人
python stress_test.py --users 200

# 500 人
python stress_test.py --users 500

# 1000 人
python stress_test.py --users 1000
```

壓測時同步觀察：

```bash
docker compose logs -f location-service
```

> **以下 K8s 相關操作為進階展示，目前主要部署方式為 Docker Compose。**

## Kubernetes Demo 流程

建立 Docker image：

```bash
bash scripts/k8s-build-images.sh
```

若尚未安裝 metrics-server，先執行下列指令，讓 HPA 可以讀到 CPU 指標。Docker Desktop Kubernetes 或 minikube 本機環境預設會套用 kubelet TLS patch：

```bash
bash scripts/k8s-install-metrics-server.sh
```

部署到 Kubernetes：

```bash
bash scripts/k8s-deploy.sh
```

觀察 Pod：

```bash
kubectl -n realtime-map-notice get pods -w
```

觀察 HPA：

```bash
kubectl -n realtime-map-notice get hpa -w
```

固定跑 60 秒的 K8s 壓測：

```bash
bash scripts/k8s-load-test.sh --users 500 --interval 1 --duration 60
```

大量壓測建議改用 cluster 內部 Job，直接打 Kubernetes Service，避免 `kubectl port-forward` 先成為瓶頸：

```bash
bash scripts/k8s-load-test-job.sh --users 500 --interval 1 --duration 60 --timeout 5
```

實測時，500 users / 60s 的 cluster 內部壓測可觸發 Location Service HPA 從 1 個 Pod 擴到 5 個 Pod。

刪除一個 Notification Service Pod 展示容錯：

```bash
bash scripts/k8s-delete-notification-pod.sh
```

Demo 前檢查清單：

- `kubectl -n realtime-map-notice get pods` 顯示所有 Pod Running。
- `kubectl -n realtime-map-notice get svc` 顯示三個服務與 Redis。
- `kubectl -n realtime-map-notice get hpa` 不應長期顯示 `<unknown>`。
- `kubectl top nodes` 與 `kubectl top pods -n realtime-map-notice` 可以看到 CPU / memory 指標。
- 已準備好 HPA 擴展截圖與 Pod 重建截圖作為備案。
- 壓測腳本先用 300 人做 smoke test，正式 Demo 目標使用 500 人起跳，確認不會在 Demo 現場立刻失敗。

## 公開網址與 Cloudflare Tunnel（已完成）

Cloudflare Tunnel 已上線，可透過以下網址存取：

- **線上展示**: https://map2.avision-gb10.org

架構：

```text
使用者 -> https://map2.avision-gb10.org -> Cloudflare -> Cloudflare Tunnel -> nginx 反向代理 -> 本機服務
```

已完成的項目：

- Cloudflare Tunnel 已建立並指向 `map2.avision-gb10.org`，`cloudflared` 從本機主動連到 Cloudflare。
- nginx 反向代理已設定，將多個服務整理成單一公開入口：

```text
https://map2.avision-gb10.org/              -> Web App
https://map2.avision-gb10.org/api/location  -> Location Service
https://map2.avision-gb10.org/api/events    -> Event Service
wss://map2.avision-gb10.org/ws/{user_id}    -> Notification Service
```

- HTTPS 與 WebSocket 皆可透過 Cloudflare Tunnel 正常運作。
- 前端環境變數已更新，API 與 WebSocket 指向正式網域。
- 三個後端服務的 `CORS_ALLOW_ORIGINS` 已設定允許正式網域。

詳細設定請參考 [infra/cloudflare/README.md](./infra/cloudflare/README.md)。

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

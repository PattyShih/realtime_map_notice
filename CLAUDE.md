# CLAUDE.md — realtime\_map\_notice

> 本文件是 Claude Code（或任何 AI coding assistant）的操作指南。請在每次修改程式碼前完整閱讀。

## 專案簡介

校園即時動態地圖 Web App。使用者在地圖上插旗回報突發狀況（空位、排隊、遺失物、緊急事件），系統只通知座標 500 公尺內的使用者。微服務架構：三個 FastAPI 後端 + Redis GEO + WebSocket + Kubernetes。

## Repository 結構

```
realtime_map_notice/
├── backend/
│   ├── location-service/       # :8001 — GPS 座標上傳 + 附近查詢
│   ├── event-service/          # :8002 — 事件建立 + 半徑查詢 + 觸發通知
│   ├── notification-service/   # :8003 — WebSocket + Redis Pub/Sub 推播
│   └── shared/                 # 共用 schemas / config / redis_client / cors
├── web-app/                    # 前端（尚未實作，僅有 README 規格）
├── simulator/                  # simulate_users.py — async 壓測腳本
├── k8s/                        # K8s Deployment / Service / HPA / Namespace
├── docs/                       # project-plan / test-plan / README
├── docker-compose.yml          # 本機開發：Redis + 三個後端服務
├── system.md                   # 系統架構與 API contract
├── development.md              # 開發流程與 Demo 步驟
└── readme.md                   # 專案總覽
```

## 技術棧

- **Backend**: Python 3.12, FastAPI, Pydantic v2, uvicorn
- **Realtime Store**: Redis 7 (GEOADD / GEOSEARCH / Pub/Sub)
- **Realtime Push**: WebSocket (FastAPI `WebSocket`)
- **HTTP Client**: httpx (Event Service → Notification Service)
- **Container**: Docker (python:3.12-slim), docker-compose
- **Orchestration**: Kubernetes (Deployment, Service, HPA autoscaling/v2)
- **Load Test**: asyncio + httpx (`simulator/simulate_users.py`)
- **Frontend** (planned): React + Vite + Leaflet / MapLibre GL JS

## 本機啟動

```bash
docker compose up --build
```

服務埠口：

- Location Service → `http://localhost:8001`
- Event Service → `http://localhost:8002`
- Notification Service → `http://localhost:8003` (WebSocket at `ws://localhost:8003/ws/{user_id}`)
- Redis → `localhost:6379`

健康檢查：`GET /healthz`（三個服務都有，會 ping Redis）。

## 環境變數

| 變數 | 預設值 | 用途 |
|------|--------|------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 連線 |
| `USER_LOCATION_KEY` | `realtime_map_notice:user:locations` | Redis GEO key |
| `USER_LAST_SEEN_PREFIX` | `realtime_map_notice:user:last_seen` | last_seen key prefix |
| `DEFAULT_ALERT_RADIUS_METERS` | `500` | 預設推播半徑 |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173,http://localhost:3000` | CORS 白名單 |
| `NOTIFICATION_SERVICE_URL` | `http://localhost:8003` | Event Service 呼叫 Notification Service 的位址 |

## API 端點

### Location Service (:8001)

| Method | Path | 用途 |
|--------|------|------|
| `POST` | `/locations` | 上傳使用者 GPS 座標 → Redis GEOADD + last_seen (TTL 60s) |
| `GET` | `/locations/nearby?latitude=&longitude=&radius_meters=500` | Redis GEOSEARCH 半徑內使用者 |
| `GET` | `/healthz` | 健康檢查（ping Redis） |

### Event Service (:8002)

| Method | Path | 用途 |
|--------|------|------|
| `POST` | `/events` | 建立事件 → GEOSEARCH 找附近使用者 → 逐一 HTTP POST 通知 |
| `GET` | `/healthz` | 健康檢查 |

### Notification Service (:8003)

| Method | Path | 用途 |
|--------|------|------|
| `WS` | `/ws/{user_id}` | 前端 WebSocket 即時通知連線 |
| `POST` | `/notify/{user_id}` | 發布通知 → Redis Pub/Sub channel |
| `GET` | `/healthz` | 健康檢查 |

## Pydantic Schemas (`backend/shared/schemas.py`)

- **LocationUpdate**: `user_id: str`, `latitude: float [-90,90]`, `longitude: float [-180,180]`
- **EventCreate**: `title: str`, `message: str`, `latitude`, `longitude`, `severity: str = "info"`, `radius_meters: int = 500 [50-3000]`
- **EventNotification**: `event_id`, `title`, `message`, `latitude`, `longitude`, `severity`, `distance_meters: float | None`

## Dockerfile 模式

三個服務共用相同模式：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app
COPY backend/<service>/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/shared /app/backend/shared
COPY backend/<service>/app /app/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

容器內部統一 port 8000，由 docker-compose / K8s Service 映射到對外埠。

## Redis 資料設計

| Key | 類型 | TTL | 用途 |
|-----|------|-----|------|
| `realtime_map_notice:user:locations` | GEO set | 無（靠 last_seen 判斷） | 使用者目前座標 |
| `realtime_map_notice:user:last_seen:{user_id}` | String | 60s | 最後上線時間 |
| `realtime_map_notice:user:{user_id}:notifications` | Pub/Sub channel | — | 指定使用者通知頻道 |

## K8s 部署

```bash
# 建置 images
docker build -t realtime-map-notice/location-service:latest -f backend/location-service/Dockerfile .
docker build -t realtime-map-notice/event-service:latest -f backend/event-service/Dockerfile .
docker build -t realtime-map-notice/notification-service:latest -f backend/notification-service/Dockerfile .

# 部署
kubectl apply -f k8s/

# 觀察
kubectl -n realtime-map-notice get pods -w
kubectl -n realtime-map-notice get hpa -w
```

- **Namespace**: `realtime-map-notice`
- **Location Service**: 1 replica (HPA: 1-5, CPU 60%)
- **Event Service**: 2 replicas
- **Notification Service**: 2-3 replicas (容錯展示)
- **HPA target**: CPU utilization 60%, max 5 replicas

## 壓測

```bash
python simulator/simulate_users.py --users 500 --target http://localhost:8001 --interval 1
```

- 預設模擬台大校園 (25.0173, 121.5397) 附近座標
- 每位使用者每 interval 秒上傳一次隨機偏移座標
- 進階可挑戰 `--users 3000`

## 已知技術債與待完成項目

### 缺失

- ❌ `.dockerignore` — .git / \_\_pycache\_\_ / .venv 會進入 build context
- ❌ `tests/` — 沒有任何自動化測試
- ❌ `web-app/` — 前端尚未實作（僅有 README 規格）
- ❌ WebSocket ping/pong 心跳 — ghost connection 不會被清理
- ❌ Event Service 批次通知 — 目前 `async for` 逐一 HTTP POST，500 人會很慢
- ❌ Event Service 冪等性 — 多副本可能重複推播

### 改善方向

- Event Service 通知改用 `asyncio.gather` 或直接 Redis Pub/Sub（跳過 HTTP 層）
- WebSocket 斷線重連（前端需實作 exponential backoff）
- API payload 擴充：`accuracy_meters`, `client_timestamp`, `sequence`, `source`
- 前端錯誤處理：定位拒絕 / API 失敗 / WebSocket 斷線都需 UI 提示

## 開發慣例

- 後端資料夾使用 hyphen 命名（`location-service`），測試 import 需用 `importlib`
- 所有服務共用 `backend/shared/` 的 schema、config、redis\_client、cors
- Python 環境用 `python -m venv .venv`（Windows: PowerShell）
- CORS 設定由 `CORS_ALLOW_ORIGINS` 環境變數統一管理
- `PYTHONPATH=/app`（Dockerfile 內設定，讓 `from backend.shared import ...` 正常運作）

## 四人分工

- **成員 A**: Web App 前端（地圖、定位、插旗、通知 UI）
- **成員 B**: Event Service + 後端 API 商業邏輯
- **成員 C**: Redis GEO + Notification Service + WebSocket
- **成員 D**: Dockerfile / K8s / HPA / 壓測腳本 / Demo

## 參考文件

- `system.md` — 系統架構、API contract、資料流、容量規劃
- `development.md` — 開發流程、API 測試指令、Demo 步驟
- `docs/project-plan.md` — 十週進度表、驗收標準、Demo 腳本
- `docs/test-plan.md` — 測試策略、測試案例、跨服務整合測試
- `k8s/README.md` — Kubernetes 部署與 HPA 操作
- `web-app/README.md` — 前端 UI/UX 規格、元件職責、環境變數

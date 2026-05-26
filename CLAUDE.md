# CLAUDE.md

## Build & Run

```bash
docker compose up --build          # 啟動全部（Redis + 3 services）
docker compose up --build -d       # 背景啟動
docker compose logs -f <service>   # 看日誌
docker compose down                # 停掉
```

Services bind to host ports 8001/8002/8003 (internal: 8000).

## Test

```bash
# 目前沒有 tests/，尚未實作。建立測試時：
pytest                              # 跑全部
pytest tests/unit/                  # 只跑 unit
pytest tests/integration/           # 需先 docker compose up
```

## Architecture

```
Web App → Location Service (:8001) → Redis GEO
Web App → Event Service (:8002) → Redis GEOSEARCH → Notification Service (:8003) → Redis Pub/Sub → WebSocket → Web App
```

Three independent FastAPI services share `backend/shared/` (schemas, config, redis_client, cors). Each has its own Dockerfile. Redis is the only stateful dependency.

## Code Conventions

- **PYTHONPATH=/app** inside Docker. All imports use `from backend.shared import ...`.
- Folder names use hyphens (`location-service`), NOT underscores. Cannot do normal Python import from these paths — use `importlib` if importing outside Docker.
- Pydantic v2 models live in `backend/shared/schemas.py`. Add new fields there.
- Redis client factory: `backend/shared/redis_client.py` → `create_redis()`.
- CORS config: `backend/shared/cors.py` → reads `CORS_ALLOW_ORIGINS` env var.
- Each service: `backend/<service>/app/main.py` is the FastAPI app entrypoint.
- Dockerfile copies `backend/shared` then `backend/<service>/app` into `/app/`.

## Env Vars

| Var | Default | Where |
|-----|---------|-------|
| `REDIS_URL` | `redis://localhost:6379/0` | shared/config.py |
| `USER_LOCATION_KEY` | `realtime_map_notice:user:locations` | shared/config.py |
| `USER_LAST_SEEN_PREFIX` | `realtime_map_notice:user:last_seen` | shared/config.py |
| `DEFAULT_ALERT_RADIUS_METERS` | `500` | shared/config.py |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173,http://localhost:3000` | shared/config.py |
| `NOTIFICATION_SERVICE_URL` | `http://localhost:8003` | event-service only |

## Gotchas

- `.dockerignore` doesn't exist yet — `.git` and `__pycache__` bloat build context. Create one if editing Dockerfiles.
- Event Service notifies nearby users one-by-one (`async for` loop). For 500+ users this is slow. Use `asyncio.gather` or bypass HTTP via direct Redis Pub/Sub.
- No WebSocket heartbeat — disconnected clients leave ghost connections.
- No test suite exists yet. See `docs/test-plan.md` for planned test structure.
- `web-app/` is empty (only a README). Frontend is not implemented.
- No `.env` file tracked — copy from `.env.example`.

## K8s

```bash
# Build images first (no CI/CD pipeline)
docker build -t realtime-map-notice/location-service:latest -f backend/location-service/Dockerfile .
docker build -t realtime-map-notice/event-service:latest -f backend/event-service/Dockerfile .
docker build -t realtime-map-notice/notification-service:latest -f backend/notification-service/Dockerfile .

kubectl apply -f k8s/
kubectl -n realtime-map-notice get pods -w
kubectl -n realtime-map-notice get hpa -w
```

Namespace: `realtime-map-notice`. Location Service has HPA (1–5 replicas, CPU 60%). Event/Notification: 2+ replicas.

## Load Testing

```bash
python simulator/simulate_users.py --users 500 --target http://localhost:8001 --interval 1
# Advanced: --users 3000
```

Requires: `pip install -r simulator/requirements.txt`

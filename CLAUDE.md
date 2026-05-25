# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`realtime_map_notice` is a campus/neighborhood real-time map notice system. Users see a map, post events (library seats, food lines, emergencies), and receive location-based push notifications. The core gimmick: urgent events are only pushed to users within 500m of the event coordinates.

The project is a university capstone with a 10-week timeline (see `docs/project-plan.md`). It's designed to showcase microservices, Redis GEO, WebSocket push, and Kubernetes autoscaling.

## Commands

### Backend (Python/FastAPI)

```bash
# Start all services locally
docker compose up --build

# Services are at:
#   Location Service:      http://localhost:8001/docs
#   Event Service:         http://localhost:8002/docs
#   Notification Service:  ws://localhost:8003/ws/{user_id}
#   Redis:                 localhost:6379

# Health checks
curl http://localhost:8001/healthz
curl http://localhost:8002/healthz
curl http://localhost:8003/healthz

# Run the location simulator (500-1000 virtual users)
python simulator/simulate_users.py --users 500 --target http://localhost:8001 --interval 1

# Run backend unit tests.
# On Windows, prefer python -m pytest because direct pytest may hit shim issues.
python -m pytest tests/unit -v
```

### Web App (React + Vite + Leaflet)

```bash
cd web-app
npm install
npm run dev       # Vite dev server on :5173
npm run build     # TypeScript + Vite production build
npm run lint      # ESLint
npm run preview   # Preview production build
```

### Kubernetes (Docker Desktop K8s or minikube)

```bash
# Build images
docker build -t realtime-map-notice/location-service:latest -f backend/location-service/Dockerfile .
docker build -t realtime-map-notice/event-service:latest -f backend/event-service/Dockerfile .
docker build -t realtime-map-notice/notification-service:latest -f backend/notification-service/Dockerfile .

# Deploy
kubectl apply -f k8s/

# Watch HPA scaling during load test
kubectl -n realtime-map-notice get hpa -w
kubectl -n realtime-map-notice get pods -w

# Demo: kill a pod to show fault tolerance
kubectl -n realtime-map-notice delete pod <notification-pod-name>
```

## Architecture

Three FastAPI microservices + Redis, coordinated via Docker Compose (local) or Kubernetes (production demo).

```
Web App (React/Leaflet)
  ├── POST /locations ──────────► Location Service ──► Redis GEO (GEOADD)
  ├── POST /events ─────────────► Event Service ─────► Redis GEO (GEOSEARCH 500m)
  │                                   │
  │                                   └──► Notification Service ──► Redis Pub/Sub
  │                                            │
  └── WS /ws/{user_id} ◄───────────────────────┘ (WebSocket push)
```

**Data flow for location updates:** Web App → Location Service → `GEOADD realtime_map_notice:user:locations`

**Data flow for event notifications:** Web App → Event Service → `GEOSEARCH` nearby users → POST `/notify/{user_id}` to Notification Service → `PUBLISH` to Redis Pub/Sub channel → any Notification Service pod subscribed to that channel → WebSocket push to browser

The "any Notification Service pod" part is critical: because WebSocket connections are sticky to specific pods, Redis Pub/Sub is used so that whichever pod holds the target user's WebSocket connection can receive and forward the notification.

### Shared backend module (`backend/shared/`)

All three services import from this directory (copied into each Docker image). It contains:

- `config.py` — env var reading (`REDIS_URL`, `USER_LOCATION_KEY`, `CORS_ALLOW_ORIGINS`, etc.)
- `schemas.py` — Pydantic models (`LocationUpdate`, `EventCreate`, `EventNotification`); event severity is restricted to `info` or `urgent`
- `redis_client.py` — `create_redis()` factory using `redis.asyncio`
- `cors.py` — `configure_cors(app)` helper that applies `CORSMiddleware` from `CORS_ALLOW_ORIGINS`

### Implementation notes / known gaps (from `system.md`)

1. **WebSocket heartbeat exists** — Notification Service sends app-level `{type:"ping"}` messages every 15s, and the Web App replies with `{type:"pong"}`. Full delivery acknowledgement and offline notification are still not implemented.
2. **Event Service fan-out is batched but still HTTP-based** — `POST /events` uses `asyncio.gather` with `NOTIFICATION_FANOUT_CONCURRENCY` to notify nearby users concurrently, but still sends one HTTP request per recipient. A later optimization could publish directly to Redis Pub/Sub.
3. **Optional event idempotency exists** — `POST /events` accepts `client_event_id`; Event Service stores it with Redis `SET NX` for `EVENT_IDEMPOTENCY_TTL_SECONDS` to avoid duplicate notifications on client retry.
4. **Initial unit tests exist** — `tests/unit/` covers Pydantic validation, active-user filtering, and notification delivery helper behavior. API, Redis, WebSocket, and frontend tests are still planned in `docs/test-plan.md`.
5. **`.dockerignore` exists** but verify it's effective — excludes `.git`, `__pycache__`, `node_modules`, `.md` files (except readme.md).

## Environment variables

See `.env.example`. Key vars:

| Variable | Default | Used by |
|----------|---------|---------|
| `REDIS_URL` | `redis://localhost:6379/0` | All services |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173,http://localhost:3000` | All services |
| `NOTIFICATION_SERVICE_URL` | `http://localhost:8003` | Event Service |
| `NOTIFICATION_FANOUT_CONCURRENCY` | `100` | Event Service |
| `EVENT_IDEMPOTENCY_PREFIX` | `realtime_map_notice:event:idempotency` | Event Service |
| `EVENT_IDEMPOTENCY_TTL_SECONDS` | `300` | Event Service |
| `VITE_LOCATION_SERVICE_URL` | `http://localhost:8001` | Web App |
| `VITE_EVENT_SERVICE_URL` | `http://localhost:8002` | Web App |
| `VITE_NOTIFICATION_WS_URL` | `ws://localhost:8003` | Web App |

## Redis keys

| Key | Type | Purpose |
|-----|------|---------|
| `realtime_map_notice:user:locations` | GEO set | Current user coordinates |
| `realtime_map_notice:user:last_seen:{user_id}` | String (TTL 60s) | Last upload timestamp |
| `realtime_map_notice:user:{user_id}:notifications` | Pub/Sub channel | Per-user notification channel |

Location data has a 60s TTL via `last_seen` keys. The GEO set itself has no per-member TTL — stale entries are filtered by checking `last_seen` in both `/locations/nearby` and `POST /events` before notifying.

## Key files

- `backend/shared/config.py` — all env var defaults
- `backend/shared/schemas.py` — canonical API models (Pydantic)
- `web-app/src/types/api.ts` — TypeScript mirror of schemas
- `backend/location-service/app/main.py` — GPS upload + nearby query
- `backend/event-service/app/main.py` — event creation + nearby lookup + notification dispatch
- `backend/notification-service/app/main.py` — WebSocket management + Pub/Sub relay
- `simulator/simulate_users.py` — asyncio-based GPS traffic generator
- `docker-compose.yml` — local dev environment (Redis + 3 services)
- `system.md` — architecture, data flow, capacity planning, bottlenecks
- `development.md` — dev setup, API test commands (PowerShell), K8s demo flow
- `docs/test-plan.md` — detailed test strategy and cases (not yet implemented)

## Frontend details

- **Map library:** Leaflet via `react-leaflet` with OpenStreetMap tiles
- **Geolocation:** `navigator.geolocation.watchPosition` in `useGeolocation` hook; falls back to NTU campus coordinates (25.0173, 121.5397) if denied
- **Location upload:** every 1.5s via `setInterval` in `App.tsx`
- **WebSocket reconnection:** exponential backoff (1s → 30s max) in `services/websocket.ts`
- **User ID:** ephemeral, generated from `Date.now()` on each page load — no auth system

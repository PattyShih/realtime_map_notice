# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A real-time campus map web app where users report events (available seats, queues, emergencies) and only users within a configurable radius (default 500m, adjustable via UI slider 100–2000m) receive push notifications via WebSocket. Built as a university capstone project with four contributors.

## Commands

### Backend
```bash
# Start all services (Redis + 3 FastAPI microservices + nginx)
docker compose up --build

# Run unit tests
python -m pytest tests/unit -v

# Run integration tests (requires services running)
python -m pytest tests/integration -v

# Run a single test file
python -m pytest tests/unit/test_schemas.py -v

# Run a specific test by name
python -m pytest tests/unit/test_schemas.py::test_function_name -v
```

### Frontend
```bash
cd web-app
npm run dev       # Vite dev server on :5173
npm run build     # TypeScript check + production build
npm run lint      # ESLint
npm test          # Vitest frontend unit tests
```

### Load Simulation
```bash
python simulator/simulate_users.py --users 500 --target http://localhost:8001 --interval 1
```

### Kubernetes
```bash
.\scripts\k8s-build-images.ps1
.\scripts\k8s-deploy.ps1
kubectl -n realtime-map-notice get pods -w
```

## Architecture

Three FastAPI microservices behind a shared Redis 7 instance, an nginx reverse proxy, and a React frontend:

```
Browser → nginx (:8090) → Location Service (:8001) → Redis GEO
                          → Event Service (:8002)    → Redis GEO + LIST → Notification Service
Browser ← nginx (/ws/*) ← Notification Service ← WebSocket / Redis Pub/Sub
```

- **Location Service** (`backend/location-service/`) — Accepts GPS coordinates, stores in Redis GEO, queries nearby users within a radius
- **Event Service** (`backend/event-service/`) — Creates events with idempotency (client_event_id + TTL), persists to Redis LIST, queries nearby users, fans out notifications via HTTP
- **Notification Service** (`backend/notification-service/`) — Manages per-user WebSocket connections, Redis Pub/Sub for cross-instance coordination, offline notification queuing, app-level ping/pong heartbeat
- **nginx** (`nginx/nginx.conf`) — Reverse proxy: serves static frontend, routes `/api/*` to backend services, `/ws/*` to notification service with WebSocket upgrade

### Shared Code (`backend/shared/`)
- `schemas.py` — Pydantic models: `LocationUpdate`, `EventCreate`, `EventNotification`, `EventRecord`
- `config.py` — Environment-driven config (REDIS_URL, CORS, idempotency TTL, fanout concurrency, event history max, structured logging)
- `redis_client.py` — Shared Redis connection pool (max_connections=20, socket_timeout=5)
- `cors.py` — CORS middleware setup

### Frontend (`web-app/src/`)
- `components/` — MapView (Leaflet), EventForm (with radius slider), NotificationBanner
- `hooks/` — useGeolocation (browser Geolocation API), useNotificationSocket (WebSocket with auto wss:// detection)
- `services/` — API clients for location, event, and WebSocket

## Key Design Decisions

- **Ports**: Each service runs on :8000 internally, mapped to :8001/:8002/:8003 via Docker Compose; nginx on :8080 mapped to :8090
- **Redis GEO** for spatial queries (not PostGIS) — keeps the stack simple for the project scope
- **Redis Pub/Sub** for coordinating WebSocket connections across multiple notification-service replicas
- **Idempotency**: Event Service uses `client_event_id` (generated via `crypto.randomUUID()` in frontend) with a Redis TTL to prevent duplicate event processing
- **Event Persistence**: Events stored in Redis LIST (latest 100), queryable via `GET /events`
- **Offline Queue**: When user is offline (no Pub/Sub subscriber), notifications are queued in Redis LIST and replayed on WebSocket reconnect
- **Redis Connection Pool**: Managed via FastAPI lifespan with graceful shutdown (aclose)
- **Structured Logging**: All services use `logging` module with consistent format, configurable via `LOG_LEVEL` env var
- **Docker Security**: All containers run as non-root user (`appuser`)
- **Severity levels**: `info` (general) and `urgent` (triggers proximity-based push)
- **Radius**: Configurable per event via UI slider (100–2000m), defaults to 500m
- **CORS**: Configured via `CORS_ALLOW_ORIGINS` env var, includes `map2.avision-gb10.org`
- **WebSocket URL**: Auto-detected from page protocol (`ws:`/`wss:`) and host, no hardcoded URL needed in production

## Testing

- Backend tests use `pytest` + `httpx.AsyncClient` + `fakeredis`
- Unit tests in `tests/unit/`, integration tests in `tests/integration/`
- Test files map to services: `test_location_service.py`, `test_event_service.py`, `test_notification_service.py`, `test_schemas.py`
- Integration tests cover API contracts and WebSocket connection behavior
- Frontend Vitest tests currently cover WebSocket client ping/pong, notification parsing, and reconnect behavior

## Deployment

Production deployment uses Docker Compose with nginx reverse proxy:
- `docker compose up --build -d` starts all services
- nginx serves frontend static files and proxies API/WebSocket requests
- Cloudflare Tunnel maps `map2.avision-gb10.org` → `localhost:8090`

## Language

Documentation and code comments are written in Traditional Chinese (繁體中文). The project is a Taiwanese university capstone.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A real-time campus map web app where users report events (available seats, queues, emergencies) and only users within 500m of the event coordinates receive push notifications via WebSocket. Built as a university capstone project with four contributors.

## Commands

### Backend
```bash
# Start all services (Redis + 3 FastAPI microservices)
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

Three FastAPI microservices behind a shared Redis 7 instance, plus a React frontend:

```
Browser → Location Service (:8001) → Redis GEO
Browser → Event Service (:8002)    → Redis GEO (nearby query) → Notification Service (:8003)
Browser ← Notification Service (:8003) ← WebSocket / Redis Pub/Sub
```

- **Location Service** (`backend/location-service/`) — Accepts GPS coordinates, stores in Redis GEO, queries nearby users within a radius
- **Event Service** (`backend/event-service/`) — Creates events with idempotency (client_event_id + TTL), queries nearby users, fans out notifications to Notification Service via HTTP
- **Notification Service** (`backend/notification-service/`) — Manages per-user WebSocket connections, uses Redis Pub/Sub for cross-instance coordination, app-level ping/pong heartbeat

### Shared Code (`backend/shared/`)
- `schemas.py` — Pydantic models: `LocationUpdate`, `EventCreate`, `EventNotification`
- `config.py` — Environment-driven config (REDIS_URL, CORS, idempotency TTL, fanout concurrency)
- `redis_client.py` — Shared Redis connection
- `cors.py` — CORS middleware setup

### Frontend (`web-app/src/`)
- `components/` — MapView (Leaflet), EventForm, NotificationBanner
- `hooks/` — useGeolocation (browser Geolocation API), useNotificationSocket (WebSocket)
- `services/` — API clients for location, event, and WebSocket

## Key Design Decisions

- **Ports**: Each service runs on :8000 internally, mapped to :8001/:8002/:8003 via Docker Compose
- **Redis GEO** for spatial queries (not PostGIS) — keeps the stack simple for the project scope
- **Redis Pub/Sub** for coordinating WebSocket connections across multiple notification-service replicas
- **Idempotency**: Event Service uses `client_event_id` with a Redis TTL to prevent duplicate event processing
- **Severity levels**: `info` (general) and `urgent` (triggers proximity-based push)
- **CORS**: Configured via `CORS_ALLOW_ORIGINS` env var, defaults to `http://localhost:5173,http://localhost:3000`

## Testing

- Backend tests use `pytest` + `httpx.AsyncClient` + `fakeredis`
- Unit tests in `tests/unit/`, integration tests in `tests/integration/`
- Test files map to services: `test_location_service.py`, `test_event_service.py`, `test_notification_service.py`, `test_schemas.py`
- Integration tests cover API contracts and WebSocket connection behavior

## Language

Documentation and code comments are written in Traditional Chinese (繁體中文). The project is a Taiwanese university capstone.

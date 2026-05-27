import asyncio
import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI

from backend.shared.config import (
    EVENT_IDEMPOTENCY_PREFIX,
    EVENT_IDEMPOTENCY_TTL_SECONDS,
    NOTIFICATION_FANOUT_CONCURRENCY,
    USER_LAST_SEEN_PREFIX,
    USER_LOCATION_KEY,
)
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventCreate, EventNotification

NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    "http://localhost:8003",
)

log = logging.getLogger(__name__)


# ── Lifespan: 管理 httpx client 生命週期 ─────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=3.0)
    log.info("event-service started, httpx client initialized")
    yield
    await app.state.http.aclose()
    log.info("event-service shutting down, httpx client closed")


app = FastAPI(title="realtime_map_notice Event Service", version="0.1.0", lifespan=lifespan)
configure_cors(app)
redis = create_redis()


def event_idempotency_key(client_event_id: str) -> str:
    return f"{EVENT_IDEMPOTENCY_PREFIX}:{client_event_id}"


async def reserve_event_idempotency(
    client_event_id: str | None,
    event_id: str,
) -> str | None:
    if not client_event_id:
        return None

    key = event_idempotency_key(client_event_id)
    created = await redis.set(
        key,
        event_id,
        ex=EVENT_IDEMPOTENCY_TTL_SECONDS,
        nx=True,
    )
    if created:
        return None

    existing_event_id = await redis.get(key)
    return existing_event_id or event_id


async def filter_active_nearby_users(
    nearby_users: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    if not nearby_users:
        return []

    last_seen_values = await redis.mget(
        [f"{USER_LAST_SEEN_PREFIX}:{user_id}" for user_id, _ in nearby_users],
    )
    return [
        nearby_user
        for nearby_user, last_seen in zip(nearby_users, last_seen_values)
        if last_seen is not None
    ]


async def deliver_notification(
    client: httpx.AsyncClient,
    user_id: str,
    notification: EventNotification,
) -> str | None:
    try:
        response = await client.post(
            f"{NOTIFICATION_SERVICE_URL}/notify/{user_id}",
            json=notification.model_dump(),
        )
        response.raise_for_status()
        log.debug("deliver.ok user=%s event=%s", user_id, notification.event_id)
    except httpx.HTTPError as exc:
        log.warning("deliver.fail user=%s event=%s error=%s", user_id, notification.event_id, exc)
        return None
    return user_id


async def deliver_notification_with_limit(
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    user_id: str,
    notification: EventNotification,
) -> str | None:
    async with semaphore:
        return await deliver_notification(client, user_id, notification)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    try:
        await redis.ping()
        return {"status": "ok"}
    except Exception:
        log.exception("healthz: Redis ping failed")
        raise


@app.post("/events")
async def create_event(payload: EventCreate) -> dict[str, object]:
    event_id = str(uuid4())
    duplicate_event_id = await reserve_event_idempotency(
        payload.client_event_id,
        event_id,
    )
    if duplicate_event_id is not None:
        log.info("event.duplicate client_event_id=%s existing_event_id=%s", payload.client_event_id, duplicate_event_id)
        return {
            "event_id": duplicate_event_id,
            "nearby_user_count": 0,
            "delivered_count": 0,
            "delivered_to": [],
            "status": "duplicate",
        }

    log.info("event.create event_id=%s title=%q severity=%s radius=%dm",
             event_id, payload.title, payload.severity, payload.radius_meters)

    nearby_users = await redis.geosearch(
        USER_LOCATION_KEY,
        longitude=payload.longitude,
        latitude=payload.latitude,
        radius=payload.radius_meters,
        unit="m",
        withdist=True,
    )
    active_nearby_users = await filter_active_nearby_users(nearby_users)

    # 使用 lifespan 管理的 httpx client（不再每次新建）
    client: httpx.AsyncClient = app.state.http
    semaphore = asyncio.Semaphore(NOTIFICATION_FANOUT_CONCURRENCY)
    delivery_results = await asyncio.gather(
        *(
            deliver_notification_with_limit(
                semaphore,
                client,
                user_id,
                EventNotification(
                    event_id=event_id,
                    title=payload.title,
                    message=payload.message,
                    latitude=payload.latitude,
                    longitude=payload.longitude,
                    severity=payload.severity,
                    distance_meters=float(distance),
                ),
            )
            for user_id, distance in active_nearby_users
        )
    )
    delivered_to = [user_id for user_id in delivery_results if user_id is not None]

    failed_count = len(active_nearby_users) - len(delivered_to)
    if failed_count:
        log.warning("event.deliver_partial event_id=%s delivered=%d failed=%d",
                    event_id, len(delivered_to), failed_count)

    log.info("event.complete event_id=%s nearby=%d delivered=%d",
             event_id, len(active_nearby_users), len(delivered_to))

    return {
        "event_id": event_id,
        "nearby_user_count": len(active_nearby_users),
        "delivered_count": len(delivered_to),
        "delivered_to": delivered_to[:20],
        "status": "created",
    }

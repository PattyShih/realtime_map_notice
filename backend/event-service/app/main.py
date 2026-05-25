import asyncio
import os
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

app = FastAPI(title="realtime_map_notice Event Service", version="0.1.0")
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
    except httpx.HTTPError:
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
    await redis.ping()
    return {"status": "ok"}


@app.post("/events")
async def create_event(payload: EventCreate) -> dict[str, object]:
    event_id = str(uuid4())
    duplicate_event_id = await reserve_event_idempotency(
        payload.client_event_id,
        event_id,
    )
    if duplicate_event_id is not None:
        return {
            "event_id": duplicate_event_id,
            "nearby_user_count": 0,
            "delivered_count": 0,
            "delivered_to": [],
            "status": "duplicate",
        }

    nearby_users = await redis.geosearch(
        USER_LOCATION_KEY,
        longitude=payload.longitude,
        latitude=payload.latitude,
        radius=payload.radius_meters,
        unit="m",
        withdist=True,
    )
    active_nearby_users = await filter_active_nearby_users(nearby_users)

    async with httpx.AsyncClient(timeout=3.0) as client:
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

    return {
        "event_id": event_id,
        "nearby_user_count": len(active_nearby_users),
        "delivered_count": len(delivered_to),
        "delivered_to": delivered_to[:20],
        "status": "created",
    }

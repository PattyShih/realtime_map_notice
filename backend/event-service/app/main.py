import os
from collections.abc import Sequence
from uuid import uuid4

import asyncio
import httpx
from fastapi import FastAPI

from backend.shared.config import USER_LAST_SEEN_PREFIX, USER_LOCATION_KEY
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


async def get_active_users(nearby_users: Sequence[tuple[str, str]]) -> list[tuple[str, float]]:
    if not nearby_users:
        return []

    pipe = redis.pipeline(transaction=False)
    for user_id, _ in nearby_users:
        pipe.get(f"{USER_LAST_SEEN_PREFIX}:{user_id}")

    last_seen_values = await pipe.execute()

    active_users: list[tuple[str, float]] = []
    for (user_id, distance), last_seen in zip(nearby_users, last_seen_values):
        if last_seen:
            active_users.append((user_id, float(distance)))

    return active_users


async def deliver_notification(
    client: httpx.AsyncClient,
    user_id: str,
    notification: EventNotification,
) -> bool:
    try:
        response = await client.post(
            f"{NOTIFICATION_SERVICE_URL}/notify/{user_id}",
            json=notification.model_dump(),
        )
    except httpx.HTTPError:
        return False

    return response.status_code < 400


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    await redis.ping()
    return {"status": "ok"}


@app.post("/events")
async def create_event(payload: EventCreate) -> dict[str, object]:
    event_id = str(uuid4())
    nearby_users = await redis.geosearch(
        USER_LOCATION_KEY,
        longitude=payload.longitude,
        latitude=payload.latitude,
        radius=payload.radius_meters,
        unit="m",
        withdist=True,
    )
    active_users = await get_active_users(nearby_users)

    delivered_to: list[str] = []
    async with httpx.AsyncClient(timeout=3.0) as client:
        tasks = []
        for user_id, distance in active_users:
            notification = EventNotification(
                event_id=event_id,
                title=payload.title,
                message=payload.message,
                latitude=payload.latitude,
                longitude=payload.longitude,
                severity=payload.severity,
                distance_meters=float(distance),
            )
            tasks.append(deliver_notification(client, user_id, notification))

        results = await asyncio.gather(*tasks) if tasks else []
        for (user_id, _), success in zip(active_users, results):
            if success:
                delivered_to.append(user_id)

    return {
        "event_id": event_id,
        "nearby_user_count": len(nearby_users),
        "active_user_count": len(active_users),
        "delivered_count": len(delivered_to),
        "delivered_to": delivered_to[:20],
    }

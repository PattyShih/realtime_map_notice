import os
from uuid import uuid4

import httpx
from fastapi import FastAPI

from backend.shared.config import USER_LOCATION_KEY
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventCreate, EventNotification

NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    "http://localhost:8003",
)

app = FastAPI(title="realtime_map_notice Event Service", version="0.1.0")
redis = create_redis()


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

    delivered_to: list[str] = []
    async with httpx.AsyncClient(timeout=3.0) as client:
        for user_id, distance in nearby_users:
            notification = EventNotification(
                event_id=event_id,
                title=payload.title,
                message=payload.message,
                latitude=payload.latitude,
                longitude=payload.longitude,
                severity=payload.severity,
                distance_meters=float(distance),
            )
            response = await client.post(
                f"{NOTIFICATION_SERVICE_URL}/notify/{user_id}",
                json=notification.model_dump(),
            )
            if response.status_code < 400:
                delivered_to.append(user_id)

    return {
        "event_id": event_id,
        "nearby_user_count": len(nearby_users),
        "delivered_count": len(delivered_to),
        "delivered_to": delivered_to[:20],
    }

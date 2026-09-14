import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import FastAPI, Query

from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventCreate, EventResponse

NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    "http://localhost:8003",
)

EVENT_LOCATION_KEY = "event_locations"

logger = logging.getLogger(__name__)


async def broadcast_to_notification_service(broadcast_payload: dict) -> dict:
    """Stage 5：推播統一走 Notification Service 的 /broadcast/nearby。

    event-service 只負責事件建立與單次 HTTP 呼叫；GEO 比對、離線過濾與
    批次發布全部由 Notification Service 處理。通知服務暫時不可用時，
    事件仍會成功建立（已先存 Redis），只是推播統計歸零。
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{NOTIFICATION_SERVICE_URL}/broadcast/nearby",
                json=broadcast_payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.warning(f"⚠️ broadcast failed (event still created): {e}")
        return {}

app = FastAPI(title="realtime_map_notice Event Service", version="0.1.0")
configure_cors(app)
redis = create_redis()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    await redis.ping()
    return {"status": "ok"}

@app.get("/events", response_model=list[EventResponse])
async def get_events(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius: int = Query(3000, ge=1, le=3000),
):
    event_ids = await redis.geosearch(
        EVENT_LOCATION_KEY,
        longitude=longitude,
        latitude=latitude,
        radius=radius,
        unit="m",
    )

    if not event_ids:
        return []

    pipe = redis.pipeline(transaction=False)

    for event_id in event_ids:
        pipe.get(f"event:{event_id}")

    event_data_list = await pipe.execute()

    events = []
    expired_events = []

    for event_id, event_data in zip(event_ids, event_data_list):
        # Redis TTL 到期，event 不存在
        if event_data is None:
            expired_events.append(event_id)
            continue

        try:
            event = json.loads(event_data)
        except json.JSONDecodeError:
            expired_events.append(event_id)
            continue

        events.append(
            EventResponse(
                event_id=event_id,
                title=event["title"],
                message=event["message"],
                severity=event["severity"],
                latitude=event["latitude"],
                longitude=event["longitude"],
                radius_meters=event["radius_meters"],
                created_at=event["created_at"],
                duration_minutes=event.get("duration_minutes", 60),
                image_url=event.get("image_url"),
            )
        )

    # 清掉已過期的 GEO 資料
    if expired_events:
        await redis.zrem(
            EVENT_LOCATION_KEY,
            *expired_events,
        )

    return events

@app.post("/events")
async def create_event(payload: EventCreate) -> dict[str, object]:
    event_id = str(uuid4())

    event_data = payload.model_dump()
    event_data["created_at"] = datetime.now(timezone.utc).isoformat()

    await redis.set(
        f"event:{event_id}",
        json.dumps(event_data),
        ex=payload.duration_minutes * 60,
    )

    await redis.geoadd(
        EVENT_LOCATION_KEY,
        (
            payload.longitude,
            payload.latitude,
            event_id,
        ),
    )

    # Stage 5：推播統一走 Notification Service，只發一次 HTTP 呼叫
    broadcast_stats = await broadcast_to_notification_service(
        {
            "event_id": event_id,
            "title": payload.title,
            "message": payload.message,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "severity": payload.severity,
            "radius_meters": payload.radius_meters,
            "duration_minutes": payload.duration_minutes,
            "image_base64": payload.image_base64,
            "image_url": payload.image_url,
        }
    )

    return {
        "event_id": event_id,
        "nearby_user_count": broadcast_stats.get("total_nearby_users", 0),
        "active_user_count": broadcast_stats.get("active_user_count", 0),
        "delivered_count": broadcast_stats.get("delivered_count", 0),
        # 維持原 API 契約：delivered_to 為 user_id 字串列表
        "delivered_to": [d.get("user_id", "") for d in broadcast_stats.get("delivered_to", [])][:20],
    }

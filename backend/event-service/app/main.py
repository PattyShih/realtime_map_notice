import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query
from redis.exceptions import RedisError

from backend.shared.antispam import EventAntiSpam
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventCreate, EventResponse, EventUpdate

NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    "http://localhost:8003",
)
AI_SERVICE_URL = os.getenv(
    "AI_SERVICE_URL",
    "http://localhost:8004",
)

EVENT_LOCATION_KEY = "event_locations"

logger = logging.getLogger(__name__)


async def moderate_event_content(title: str, message: str) -> None:
    """送 AI Service 審核內容；判定垃圾訊息時 raise 422。

    與 antispam 互補：antispam 擋行為（洗頻、重複），AI 擋內容（廣告、辱罵）。
    AI 服務不可用時 fail-open 放行，不阻擋正常發布。
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AI_SERVICE_URL}/moderate",
                json={"title": title, "message": message},
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"⚠️ moderation unavailable (event allowed): {e}")
        return

    if result.get("verdict") == "spam":
        reason = result.get("reason") or "內容疑似垃圾訊息"
        raise HTTPException(
            status_code=422,
            detail=f"內容未通過審核：{reason}",
        )


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
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"⚠️ broadcast failed (event still created): {e}")
        return {}

app = FastAPI(title="realtime_map_notice Event Service", version="0.1.0")
configure_cors(app)
redis = create_redis()
antispam = EventAntiSpam(redis)


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
    try:
        event_ids = await redis.geosearch(
            EVENT_LOCATION_KEY,
            longitude=longitude,
            latitude=latitude,
            radius=radius,
            unit="m",
        )
    except RedisError as e:
        logger.error("Event lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

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
                    user_id=event.get("user_id", ""),
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            expired_events.append(event_id)
            continue

    # 清掉已過期的 GEO 資料
    if expired_events:
        await redis.zrem(
            EVENT_LOCATION_KEY,
            *expired_events,
        )

    return events

async def _load_owned_event(event_id: str, user_id: str) -> dict:
    """載入事件並驗證操作者是發布者；不存在回 404、非發布者回 403。"""
    raw = await redis.get(f"event:{event_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail="事件不存在或已過期")

    event = json.loads(raw)
    if event.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="只有發布者可以修改或刪除這則事件")
    return event


@app.put("/events/{event_id}")
async def update_event(event_id: str, payload: EventUpdate) -> dict[str, object]:
    event = await _load_owned_event(event_id, payload.user_id)

    # 編輯後的內容同樣要過 AI 審核（antispam 計數不重跑：
    # 編輯不產生新事件也不推播，重複偵測對「只改幾個字」反而誤擋）
    await moderate_event_content(payload.title, payload.message)

    event["title"] = payload.title
    event["message"] = payload.message
    event["severity"] = payload.severity

    event_key = f"event:{event_id}"
    ttl = await redis.ttl(event_key)
    if ttl <= 0:
        # get 與 ttl 之間剛好過期：視為不存在，避免復活死事件
        raise HTTPException(status_code=404, detail="事件不存在或已過期")

    try:
        await redis.set(event_key, json.dumps(event), ex=ttl)
    except RedisError as e:
        logger.error("Event update failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    return {"status": "updated", "event_id": event_id}


@app.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    user_id: str = Query(..., min_length=1, max_length=64),
) -> dict[str, object]:
    await _load_owned_event(event_id, user_id)

    try:
        await redis.delete(f"event:{event_id}")
        await redis.zrem(EVENT_LOCATION_KEY, event_id)
    except RedisError as e:
        logger.error("Event delete failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    return {"status": "deleted", "event_id": event_id}


@app.post("/events")
async def create_event(payload: EventCreate) -> dict[str, object]:
    event_id = str(uuid4())

    # 反垃圾訊息：頻率限制、重複偵測；未通過會直接 raise 429/409
    await antispam.check_and_register(
        payload.user_id,
        payload.title,
        payload.message,
        event_id,
        payload.duration_minutes,
    )

    # AI 內容審核：判定垃圾訊息會 raise 422；服務不可用時放行
    await moderate_event_content(payload.title, payload.message)

    event_data = payload.model_dump()
    event_data["created_at"] = datetime.now(timezone.utc).isoformat()

    try:
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
    except RedisError as e:
        logger.error("Event storage failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    # Stage 5：推播統一走 Notification Service，只發一次 HTTP 呼叫
    broadcast_stats = await broadcast_to_notification_service(
        {
            "event_id": event_id,
            "user_id": payload.user_id,
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

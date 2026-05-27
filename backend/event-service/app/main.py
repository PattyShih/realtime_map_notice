import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from fastapi import FastAPI, Query

from backend.shared.config import (
    EVENT_HISTORY_KEY,
    EVENT_HISTORY_MAX,
    EVENT_IDEMPOTENCY_PREFIX,
    EVENT_IDEMPOTENCY_TTL_SECONDS,
    NOTIFICATION_FANOUT_CONCURRENCY,
    USER_LAST_SEEN_PREFIX,
    USER_LOCATION_KEY,
)
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import Comment, CommentCreate, EventCreate, EventNotification, EventRecord

NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    "http://localhost:8003",
)

log = logging.getLogger(__name__)


# ── Lifespan: 管理 httpx client + Redis 生命週期 ──────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=3.0)
    app.state.redis = create_redis()
    log.info("event-service started, httpx + Redis initialized")
    yield
    await app.state.http.aclose()
    await app.state.redis.aclose()
    log.info("event-service shutting down")


app = FastAPI(title="realtime_map_notice Event Service", version="0.1.0", lifespan=lifespan)
configure_cors(app)


def event_idempotency_key(client_event_id: str) -> str:
    return f"{EVENT_IDEMPOTENCY_PREFIX}:{client_event_id}"


async def reserve_event_idempotency(
    redis,
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
    redis,
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


async def persist_event(redis, record: EventRecord) -> None:
    """存事件到 Redis LIST，保留最近 EVENT_HISTORY_MAX 筆"""
    pipe = redis.pipeline()
    pipe.lpush(EVENT_HISTORY_KEY, record.model_dump_json())
    pipe.ltrim(EVENT_HISTORY_KEY, 0, EVENT_HISTORY_MAX - 1)
    await pipe.execute()
    log.debug("event.persisted event_id=%s", record.event_id)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    redis = app.state.redis
    try:
        await redis.ping()
        return {"status": "ok"}
    except Exception:
        log.exception("healthz: Redis ping failed")
        raise


@app.get("/events")
async def list_events(
    limit: int = Query(default=50, ge=1, le=100),
) -> list[EventRecord]:
    """取得最近的事件歷史（最新在前，已過期的不回傳）"""
    redis = app.state.redis
    raw_events = await redis.lrange(EVENT_HISTORY_KEY, 0, limit - 1)
    now = datetime.now(UTC)
    events = []
    for raw in raw_events:
        with suppress(json.JSONDecodeError, ValueError):
            record = EventRecord.model_validate_json(raw)
            if record.expires_at:
                try:
                    exp = datetime.fromisoformat(record.expires_at)
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=UTC)
                    if exp < now:
                        continue
                except (ValueError, TypeError):
                    pass
            events.append(record)
    return events


@app.post("/events")
async def create_event(payload: EventCreate) -> dict[str, object]:
    redis = app.state.redis
    event_id = str(uuid4())
    duplicate_event_id = await reserve_event_idempotency(
        redis,
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

    created_at = datetime.now(UTC).isoformat()
    from datetime import timedelta
    expires_at = (datetime.now(UTC) + timedelta(minutes=payload.expires_in)).isoformat()
    log.info("event.create event_id=%s title=%q severity=%s radius=%dm expires=%dm",
             event_id, payload.title, payload.severity, payload.radius_meters, payload.expires_in)

    # 持久化事件
    await persist_event(redis, EventRecord(
        event_id=event_id,
        title=payload.title,
        message=payload.message,
        latitude=payload.latitude,
        longitude=payload.longitude,
        severity=payload.severity,
        created_at=created_at,
        expires_at=expires_at,
    ))

    nearby_users = await redis.geosearch(
        USER_LOCATION_KEY,
        longitude=payload.longitude,
        latitude=payload.latitude,
        radius=payload.radius_meters,
        unit="m",
        withdist=True,
    )
    active_nearby_users = await filter_active_nearby_users(redis, nearby_users)

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


# ── 留言 API ──────────────────────────────────────────────
COMMENT_PREFIX = "event:comments"


@app.get("/events/{event_id}/comments")
async def list_comments(event_id: str) -> list[Comment]:
    """取得某事件的留言（最新在前）"""
    redis = app.state.redis
    key = f"{COMMENT_PREFIX}:{event_id}"
    raw_comments = await redis.lrange(key, 0, 99)
    comments = []
    for raw in raw_comments:
        with suppress(json.JSONDecodeError, ValueError):
            comments.append(Comment.model_validate_json(raw))
    return comments


@app.post("/events/{event_id}/comments")
async def add_comment(event_id: str, payload: CommentCreate) -> Comment:
    """新增留言"""
    redis = app.state.redis
    comment = Comment(
        comment_id=str(uuid4()),
        event_id=event_id,
        author=payload.author,
        content=payload.content,
        created_at=datetime.now(UTC).isoformat(),
    )
    key = f"{COMMENT_PREFIX}:{event_id}"
    pipe = redis.pipeline()
    pipe.lpush(key, comment.model_dump_json())
    pipe.ltrim(key, 0, 99)
    await pipe.execute()
    log.info("comment.added event_id=%s comment_id=%s", event_id, comment.comment_id)
    return comment

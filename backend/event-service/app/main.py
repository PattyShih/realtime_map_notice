import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from fastapi import FastAPI, Query

from backend.shared.config import (
    EVENT_HISTORY_KEY,
    EVENT_HISTORY_MAX,
    EVENT_IDEMPOTENCY_PREFIX,
    EVENT_IDEMPOTENCY_TTL_SECONDS,
    USER_LAST_SEEN_PREFIX,
    USER_LOCATION_KEY,
)
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import Comment, CommentCreate, EventCreate, EventNotification, EventRecord

log = logging.getLogger(__name__)

# Redis channel: event-service 發布新事件，notification-service 訂閱
EVENT_FANOUT_CHANNEL = "realtime_map_notice:events:fanout"


# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=3.0)
    app.state.redis = create_redis()
    log.info("event-service started")
    yield
    await app.state.http.aclose()
    await app.state.redis.aclose()
    log.info("event-service shutting down")


app = FastAPI(title="realtime_map_notice Event Service", version="0.3.0", lifespan=lifespan)
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


async def persist_event(redis, record: EventRecord) -> None:
    """存事件到 Redis LIST，保留最近 EVENT_HISTORY_MAX 筆"""
    pipe = redis.pipeline()
    pipe.lpush(EVENT_HISTORY_KEY, record.model_dump_json())
    pipe.ltrim(EVENT_HISTORY_KEY, 0, EVENT_HISTORY_MAX - 1)
    await pipe.execute()


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
    """建立事件 — 持久化 + Redis PUBLISH，不做 HTTP fanout"""
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
            "status": "duplicate",
        }

    created_at = datetime.now(UTC).isoformat()
    expires_at = (datetime.now(UTC) + timedelta(minutes=payload.expires_in)).isoformat()
    log.info("event.create event_id=%s title=%s severity=%s radius=%dm expires=%dm",
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

    # 發布到 Redis channel（notification-service 會訂閱並做 geosearch + 推播）
    fanout_msg = EventNotification(
        event_id=event_id,
        title=payload.title,
        message=payload.message,
        latitude=payload.latitude,
        longitude=payload.longitude,
        severity=payload.severity,
        distance_meters=0,  # notification-service 會重算
        expires_at=expires_at,
    ).model_dump_json()

    subscriber_count = await redis.publish(EVENT_FANOUT_CHANNEL, fanout_msg)
    log.info("event.fanout_published event_id=%s subscribers=%d", event_id, subscriber_count)

    return {
        "event_id": event_id,
        "status": "created",
        "fanout_subscribers": subscriber_count,
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

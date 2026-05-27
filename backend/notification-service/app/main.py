import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.shared.config import USER_LAST_SEEN_PREFIX, USER_LOCATION_KEY
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventNotification

log = logging.getLogger(__name__)

PENDING_MAX = 200  # 每用戶最多暫存 200 條離線通知
EVENT_FANOUT_CHANNEL = "realtime_map_notice:events:fanout"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = create_redis()
    # 啟動 fanout 訂閱背景任務
    app.state.fanout_task = asyncio.create_task(_fanout_subscriber(app))
    log.info("notification-service started, fanout subscriber active")
    yield
    app.state.fanout_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.fanout_task
    await app.state.redis.aclose()
    log.info("notification-service shutting down")


app = FastAPI(title="realtime_map_notice Notification Service", version="0.2.0", lifespan=lifespan)
configure_cors(app)

HEARTBEAT_INTERVAL_SECONDS = 15.0
HEARTBEAT_TIMEOUT_SECONDS = 45.0


@dataclass
class ConnectionState:
    last_pong_at: float


def user_channel(user_id: str) -> str:
    return f"realtime_map_notice:user:{user_id}:notifications"


def pending_key(user_id: str) -> str:
    return f"realtime_map_notice:user:{user_id}:pending"


async def forward_user_notifications(
    redis,
    websocket: WebSocket,
    user_id: str,
    send_lock: asyncio.Lock,
) -> None:
    pubsub = redis.pubsub()
    channel = user_channel(user_id)
    await pubsub.subscribe(channel)
    log.info("pubsub.subscribe user=%s channel=%s", user_id, channel)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message["type"] == "message":
                async with send_lock:
                    await websocket.send_text(message["data"])
                log.debug("ws.forward user=%s", user_id)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        log.info("pubsub.unsubscribe user=%s", user_id)


async def send_heartbeat(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    state: ConnectionState,
) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        if time.monotonic() - state.last_pong_at > HEARTBEAT_TIMEOUT_SECONDS:
            log.warning("heartbeat.timeout user closing connection")
            await websocket.close(code=1001, reason="heartbeat timeout")
            return

        async with send_lock:
            await websocket.send_json({"type": "ping"})


async def receive_client_messages(
    websocket: WebSocket,
    state: ConnectionState,
) -> None:
    while True:
        message = await websocket.receive_text()
        with suppress(json.JSONDecodeError):
            payload = json.loads(message)
            if isinstance(payload, dict) and payload.get("type") == "pong":
                state.last_pong_at = time.monotonic()


async def replay_pending(redis, websocket: WebSocket, user_id: str, send_lock: asyncio.Lock) -> int:
    """重連時回放離線期間的暫存通知，回傳回放數量"""
    key = pending_key(user_id)
    raw_items = await redis.lrange(key, 0, -1)
    if not raw_items:
        return 0

    count = 0
    for raw in raw_items:
        async with send_lock:
            await websocket.send_text(raw)
        count += 1

    # 清空已回放的通知
    await redis.delete(key)
    log.info("pending.replay user=%s count=%d", user_id, count)
    return count


async def _deliver_to_user(redis, user_id: str, notification: EventNotification, distance: float) -> None:
    """透過 Redis Pub/Sub 推播給單一用戶（線上直推，離線暫存）"""
    notification.distance_meters = round(distance, 1)
    payload_json = notification.model_dump_json()
    subscriber_count = await redis.publish(
        user_channel(user_id),
        payload_json,
    )
    if subscriber_count == 0:
        # 用戶不在線，暫存通知
        key = pending_key(user_id)
        pipe = redis.pipeline()
        pipe.rpush(key, payload_json)
        pipe.ltrim(key, -PENDING_MAX, -1)
        await pipe.execute()


async def _fanout_subscriber(app: FastAPI) -> None:
    """訂閱 event fanout channel，收到事件後做 geosearch + 推播"""
    redis = app.state.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe(EVENT_FANOUT_CHANNEL)
    log.info("fanout.subscriber started on channel=%s", EVENT_FANOUT_CHANNEL)

    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message["type"] == "message":
                try:
                    notification = EventNotification.model_validate_json(message["data"])
                except Exception:
                    log.exception("fanout.parse_error")
                    continue

                try:
                    # 查附近用戶
                    nearby_users = await redis.geosearch(
                        USER_LOCATION_KEY,
                        longitude=notification.longitude,
                        latitude=notification.latitude,
                        radius=5000,  # 預設 5km，之後可從 event 取
                        unit="m",
                        withdist=True,
                    )
                    if not nearby_users:
                        continue

                    # 過濾活躍用戶
                    last_seen_values = await redis.mget(
                        [f"{USER_LAST_SEEN_PREFIX}:{uid}" for uid, _ in nearby_users],
                    )
                    active_nearby = [
                        (uid, dist)
                        for (uid, dist), last_seen in zip(nearby_users, last_seen_values)
                        if last_seen is not None
                    ]

                    # 並發推播
                    semaphore = asyncio.Semaphore(200)
                    async def _deliver(uid: str, dist: float) -> None:
                        async with semaphore:
                            await _deliver_to_user(redis, uid, notification, dist)

                    await asyncio.gather(*(
                        _deliver(uid, dist) for uid, dist in active_nearby
                    ))
                    log.info("fanout.complete event_id=%s nearby=%d",
                             notification.event_id, len(active_nearby))
                except Exception:
                    log.exception("fanout.error event_id=%s", notification.event_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("fanout.subscriber_fatal")
        raise
    finally:
        await pubsub.unsubscribe(EVENT_FANOUT_CHANNEL)
        await pubsub.close()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    redis = app.state.redis
    try:
        await redis.ping()
        return {"status": "ok"}
    except Exception:
        log.exception("healthz: Redis ping failed")
        raise


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    redis = app.state.redis
    await websocket.accept()
    log.info("ws.connect user=%s", user_id)
    send_lock = asyncio.Lock()
    state = ConnectionState(last_pong_at=time.monotonic())

    # 回放離線暫存
    replayed = await replay_pending(redis, websocket, user_id, send_lock)
    if replayed:
        log.info("ws.replay user=%s replayed=%d", user_id, replayed)

    tasks = [
        asyncio.create_task(forward_user_notifications(redis, websocket, user_id, send_lock)),
        asyncio.create_task(send_heartbeat(websocket, send_lock, state)),
        asyncio.create_task(receive_client_messages(websocket, state)),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, WebSocketDisconnect):
                await task
        log.info("ws.disconnect user=%s", user_id)


# 保留 HTTP notify endpoint（向後兼容，也用於直接推送）
@app.post("/notify/{user_id}")
async def notify_user(user_id: str, notification: EventNotification) -> dict[str, object]:
    redis = app.state.redis
    payload_json = notification.model_dump_json()
    subscriber_count = await redis.publish(
        user_channel(user_id),
        payload_json,
    )

    if subscriber_count == 0:
        key = pending_key(user_id)
        pipe = redis.pipeline()
        pipe.rpush(key, payload_json)
        pipe.ltrim(key, -PENDING_MAX, -1)
        await pipe.execute()
        log.info("notify.queued user=%s event=%s (offline)", user_id, notification.event_id)
    else:
        log.info("notify.delivered user=%s event=%s subscribers=%d",
                 user_id, notification.event_id, subscriber_count)

    return {
        "user_id": user_id,
        "subscriber_count": subscriber_count,
        "queued": subscriber_count == 0,
        "status": "published",
    }

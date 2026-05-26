import asyncio
import json
import time
from contextlib import suppress
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventNotification

app = FastAPI(title="realtime_map_notice Notification Service", version="0.1.0")
configure_cors(app)
redis = create_redis()

HEARTBEAT_INTERVAL_SECONDS = 15.0
HEARTBEAT_TIMEOUT_SECONDS = 45.0


@dataclass
class ConnectionState:
    last_pong_at: float


def user_channel(user_id: str) -> str:
    return f"realtime_map_notice:user:{user_id}:notifications"


async def forward_user_notifications(
    websocket: WebSocket,
    user_id: str,
    send_lock: asyncio.Lock,
) -> None:
    pubsub = redis.pubsub()
    channel = user_channel(user_id)
    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message["type"] == "message":
                async with send_lock:
                    await websocket.send_text(message["data"])
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def send_heartbeat(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    state: ConnectionState,
) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        if time.monotonic() - state.last_pong_at > HEARTBEAT_TIMEOUT_SECONDS:
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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    await redis.ping()
    return {"status": "ok"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    await websocket.accept()
    send_lock = asyncio.Lock()
    state = ConnectionState(last_pong_at=time.monotonic())
    tasks = [
        asyncio.create_task(forward_user_notifications(websocket, user_id, send_lock)),
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


@app.post("/notify/{user_id}")
async def notify_user(user_id: str, notification: EventNotification) -> dict[str, object]:
    subscriber_count = await redis.publish(
        user_channel(user_id),
        notification.model_dump_json(),
    )
    return {
        "user_id": user_id,
        "subscriber_count": subscriber_count,
        "status": "published",
    }

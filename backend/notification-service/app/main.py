import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventNotification

app = FastAPI(title="realtime_map_notice Notification Service", version="0.1.0")
configure_cors(app)
redis = create_redis()

# WebSocket heartbeat settings
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 60  # seconds


def user_channel(user_id: str) -> str:
    return f"realtime_map_notice:user:{user_id}:notifications"


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    await redis.ping()
    return {"status": "ok"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    await websocket.accept()
    # 階段一檢核機制：連線時發送 Hello 訊息
    await websocket.send_text('{"type":"hello","message":"Hello"}')
    pubsub = redis.pubsub()
    await pubsub.subscribe(user_channel(user_id))

    ping_task = asyncio.create_task(ping_sender(websocket))

    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )

            if message and message["type"] == "message":
                await websocket.send_text(message["data"])

            # Check for client messages (pong response)
            try:
                client_msg = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.1,
                )
                # Client responded, connection is alive
            except asyncio.TimeoutError:
                pass  # No client message, continue loop

    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        await pubsub.unsubscribe(user_channel(user_id))
        await pubsub.close()


async def ping_sender(websocket: WebSocket) -> None:
    """Send periodic ping messages to detect dead connections."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text('{"type":"ping"}')
            except Exception:
                # WebSocket already closed
                break
    except asyncio.CancelledError:
        pass


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

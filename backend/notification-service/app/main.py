from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventNotification

app = FastAPI(title="realtime_map_notice Notification Service", version="0.1.0")
redis = create_redis()


def user_channel(user_id: str) -> str:
    return f"realtime_map_notice:user:{user_id}:notifications"


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    await redis.ping()
    return {"status": "ok"}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    await websocket.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe(user_channel(user_id))
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(user_channel(user_id))
        await pubsub.close()


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

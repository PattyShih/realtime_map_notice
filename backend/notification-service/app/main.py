import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from backend.shared.config import DEFAULT_ALERT_RADIUS_METERS, USER_LOCATION_KEY
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import EventNotification, NearbyBroadcast

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="realtime_map_notice Notification Service", version="0.1.0")
configure_cors(app)
redis = create_redis()

# WebSocket heartbeat settings
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 60  # seconds
PONG_TIMEOUT = 10  # seconds - wait for pong response
INITIAL_GRACE_PERIOD = 60  # seconds - grace period after connection establishment


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
    await websocket.send_text('{"type":"hello","message":"Connected to notification service"}')

    logger.info(f"✅ User {user_id} connected, sending hello message")

    pubsub = redis.pubsub()
    await pubsub.subscribe(user_channel(user_id))

    # 追蹤最後一次收到 pong 的時間
    last_pong_time = asyncio.get_event_loop().time()
    connection_start_time = asyncio.get_event_loop().time()

    ping_task = asyncio.create_task(ping_sender(websocket))

    try:
        while True:
            # 1. 檢查是否有 Redis 訊息
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=2.0
                )

                if message and message["type"] == "message":
                    await websocket.send_text(message["data"])
                    logger.info(f"📤 Sent notification to user {user_id}")
            except asyncio.TimeoutError:
                pass  # 沒有 Redis 訊息，繼續迴圈

            # 2. 檢查客戶端訊息 (pong response)
            try:
                client_msg = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.5,
                )
                # 解析客戶端訊息
                try:
                    msg_data = json.loads(client_msg)
                    if msg_data.get("type") == "pong":
                        last_pong_time = asyncio.get_event_loop().time()
                        logger.info(f"📡 User {user_id} pong received")
                    else:
                        logger.info(f"📨 User {user_id} sent: {client_msg[:50]}...")
                except json.JSONDecodeError:
                    logger.info(f"📨 User {user_id} sent non-JSON: {client_msg[:50]}...")
            except asyncio.TimeoutError:
                pass  # 沒有客戶端訊息，繼續迴圈

            # 3. 檢查是否超時 (連線建立後等待第一個心跳週期，再開始檢查 pong 超時)
            current_time = asyncio.get_event_loop().time()
            connection_age = current_time - connection_start_time

            # 只有在連線超過一個心跳週期後，才開始檢查 pong 超時
            if connection_age > HEARTBEAT_INTERVAL:
                time_since_last_pong = current_time - last_pong_time
                if time_since_last_pong > PONG_TIMEOUT:
                    logger.warning(f"⏰ User {user_id} pong timeout ({time_since_last_pong:.1f}s > {PONG_TIMEOUT}s), closing connection")
                    break

            # 每 60 秒打印一次連線狀態
            if int(connection_age) % 60 == 0 and int(connection_age) > 0:
                logger.info(f"💓 User {user_id} connection alive for {int(connection_age)}s")

    except WebSocketDisconnect:
        logger.info(f"🔌 User {user_id} disconnected normally")
    except Exception as e:
        logger.error(f"❌ WebSocket error for user {user_id}: {e}")
    finally:
        ping_task.cancel()
        await pubsub.unsubscribe(user_channel(user_id))
        await pubsub.close()
        logger.info(f"🛑 User {user_id} connection cleanup complete")


async def ping_sender(websocket: WebSocket) -> None:
    """Send periodic ping messages and wait for pong response."""
    try:
        # 等待第一個心跳間隔後才發送第一次 ping
        await asyncio.sleep(HEARTBEAT_INTERVAL)

        try:
            await websocket.send_text('{"type":"ping","timestamp":' + str(int(asyncio.get_event_loop().time())) + '}')
        except Exception:
            # WebSocket already closed
            print("Ping failed: connection closed")
            return

        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text('{"type":"ping","timestamp":' + str(int(asyncio.get_event_loop().time())) + '}')
            except Exception:
                # WebSocket already closed
                print("Ping failed: connection closed")
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


@app.post("/broadcast/nearby")
async def broadcast_to_nearby_users(broadcast: NearbyBroadcast) -> dict[str, object]:
    """
    階段三：成員C實作的廣播邏輯
    當 Event Service 收到新事件時，呼叫此 endpoint 進行區域推播

    流程：
    1. 使用 Redis GEOSEARCH 查詢指定座標 radius_meters 內的使用者
    2. 對每個附近使用者透過 Redis Pub/Sub 發布通知
    3. 回傳推播結果統計
    """
    # 1. 查詢附近使用者（Redis GEOSEARCH）
    nearby_users = await redis.geosearch(
        USER_LOCATION_KEY,
        longitude=broadcast.longitude,
        latitude=broadcast.latitude,
        radius=broadcast.radius_meters,
        unit="m",
        withdist=True,  # 回傳距離資訊用於除錯
    )

    # 2. 批次推播給附近使用者
    delivered_to: list[dict[str, str | float]] = []
    failed_count = 0

    for user_id, distance in nearby_users:
        notification = EventNotification(
            event_id=broadcast.event_id,
            title=broadcast.title,
            message=broadcast.message,
            latitude=broadcast.latitude,
            longitude=broadcast.longitude,
            severity=broadcast.severity,
            distance_meters=float(distance),
            image_base64=broadcast.image_base64,
            image_url=broadcast.image_url,
        )

        # 透過 Redis Pub/Sub 發布（非阻塞，不需等待 WebSocket 回應）
        subscriber_count = await redis.publish(
            user_channel(user_id),
            notification.model_dump_json(),
        )

        if subscriber_count > 0:
            delivered_to.append({
                "user_id": user_id,
                "distance_meters": float(distance),
                "subscriber_count": subscriber_count,
            })
        else:
            # 使用者目前沒有 WebSocket 連線
            failed_count += 1

    return {
        "event_id": broadcast.event_id,
        "total_nearby_users": len(nearby_users),
        "radius_meters": broadcast.radius_meters,
        "delivered_count": len(delivered_to),
        "failed_count": failed_count,
        "delivered_to": delivered_to[:20],  # 限制回傳數量避免過大
    }

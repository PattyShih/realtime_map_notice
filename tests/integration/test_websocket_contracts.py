import asyncio
import json

from fastapi.testclient import TestClient

from tests.unit.service_loader import load_service_module


class FakePubSub:
    def __init__(self, message: str) -> None:
        self.message = message
        self.subscribed_channel: str | None = None
        self.unsubscribed_channel: str | None = None
        self.closed = False
        self.delivered = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channel = channel

    async def get_message(
        self,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> dict[str, str] | None:
        if self.delivered:
            await asyncio.sleep(timeout)
            return None

        self.delivered = True
        return {"type": "message", "data": self.message}

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed_channel = channel

    async def close(self) -> None:
        self.closed = True


class FakeWebSocketRedis:
    def __init__(self, pubsub: FakePubSub) -> None:
        self._pubsub = pubsub

    async def ping(self) -> bool:
        return True

    def pubsub(self) -> FakePubSub:
        return self._pubsub


def test_websocket_forwards_user_pubsub_message() -> None:
    module = load_service_module("notification-service")
    notification = {
        "event_id": "evt-1",
        "title": "Road blocked",
        "message": "Road blocked near library",
        "latitude": 25.0173,
        "longitude": 121.5397,
        "severity": "urgent",
        "distance_meters": 42.5,
    }
    fake_pubsub = FakePubSub(json.dumps(notification))
    module.redis = FakeWebSocketRedis(fake_pubsub)
    client = TestClient(module.app)

    with client.websocket_connect("/ws/u-near") as websocket:
        received = json.loads(websocket.receive_text())

    assert received == notification
    assert fake_pubsub.subscribed_channel == (
        "realtime_map_notice:user:u-near:notifications"
    )

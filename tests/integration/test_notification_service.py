from __future__ import annotations

from dataclasses import dataclass

import pytest
import time
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from tests.conftest import load_module


notification_service = load_module("notification_service_main", "backend/notification-service/app/main.py")


@dataclass
class FakePubSub:
    def __init__(self) -> None:
        pass

    async def subscribe(self, channel: str) -> None:
        return None

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0):
        return None

    async def unsubscribe(self, channel: str) -> None:
        return None

    async def close(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.geosearch_result: list[tuple[str, str]] = []
        self.last_seen_keys: set[str] = set()

    async def ping(self) -> bool:
        return True

    def pubsub(self) -> FakePubSub:
        return FakePubSub()

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def geosearch(self, *args, **kwargs):
        return self.geosearch_result

    def pipeline(self, transaction: bool = False) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    """模擬 pipeline：依序記錄 get/publish 指令，execute 時一次回傳結果。"""

    def __init__(self, fake_redis: FakeRedis) -> None:
        self.fake_redis = fake_redis
        self.commands: list[tuple[str, tuple]] = []

    def get(self, key: str) -> "FakePipeline":
        self.commands.append(("get", (key,)))
        return self

    def publish(self, channel: str, message: str) -> "FakePipeline":
        self.commands.append(("publish", (channel, message)))
        return self

    async def execute(self) -> list:
        results: list = []
        for name, args in self.commands:
            if name == "get":
                results.append(args[0] in self.fake_redis.last_seen_keys)
            elif name == "publish":
                self.fake_redis.published.append((args[0], args[1]))
                results.append(1)
        self.commands.clear()
        return results


@pytest.mark.asyncio
async def test_healthz(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(notification_service, "redis", fake_redis)

    transport = ASGITransport(app=notification_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_notify_user(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(notification_service, "redis", fake_redis)

    transport = ASGITransport(app=notification_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/notify/u-0001",
            json={
                "event_id": "uuid",
                "title": "Urgent notice",
                "message": "Road blocked near library",
                "latitude": 25.0173,
                "longitude": 121.5397,
                "severity": "urgent",
                "distance_meters": 120.0,
            },
        )

    assert response.status_code == 200
    assert response.json()["subscriber_count"] == 1
    assert fake_redis.published[0][0] == notification_service.user_channel("u-0001")


@pytest.mark.asyncio
async def test_broadcast_nearby_filters_offline_users(monkeypatch) -> None:
    """Stage 5：last_seen 已過期的使用者不會被 publish，活躍使用者批次發布。"""
    fake_redis = FakeRedis()
    fake_redis.geosearch_result = [("u-online", "120.0"), ("u-offline", "250.0")]
    fake_redis.last_seen_keys = {f"{notification_service.USER_LAST_SEEN_PREFIX}:u-online"}
    monkeypatch.setattr(notification_service, "redis", fake_redis)

    transport = ASGITransport(app=notification_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/broadcast/nearby",
            json={
                "event_id": "uuid-1",
                "title": "Urgent notice",
                "message": "Road blocked near library",
                "latitude": 25.0173,
                "longitude": 121.5397,
                "severity": "urgent",
                "radius_meters": 500,
                "duration_minutes": 60,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["total_nearby_users"] == 2
    assert body["active_user_count"] == 1
    assert body["delivered_count"] == 1
    assert body["failed_count"] == 0
    assert body["delivered_to"][0]["user_id"] == "u-online"

    # 只有在線使用者收到 publish
    assert [c for c, _ in fake_redis.published] == [
        notification_service.user_channel("u-online")
    ]


@pytest.mark.asyncio
async def test_broadcast_nearby_skips_publish_when_all_offline(monkeypatch) -> None:
    """半徑內有人但全部離線：不發布任何通知，統計歸零。"""
    fake_redis = FakeRedis()
    fake_redis.geosearch_result = [("u-offline-1", "120.0"), ("u-offline-2", "250.0")]
    monkeypatch.setattr(notification_service, "redis", fake_redis)

    transport = ASGITransport(app=notification_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/broadcast/nearby",
            json={
                "event_id": "uuid-2",
                "title": "Urgent notice",
                "message": "Road blocked near library",
                "latitude": 25.0173,
                "longitude": 121.5397,
                "severity": "urgent",
                "radius_meters": 500,
                "duration_minutes": 60,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["total_nearby_users"] == 2
    assert body["active_user_count"] == 0
    assert body["delivered_count"] == 0
    assert body["failed_count"] == 0
    assert body["delivered_to"] == []
    assert fake_redis.published == []


def test_websocket_heartbeat(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(notification_service, "redis", fake_redis)
    monkeypatch.setattr(notification_service, "HEARTBEAT_INTERVAL", 0.01)

    client = TestClient(notification_service.app)
    with client.websocket_connect("/ws/u-0001") as websocket:
        assert websocket.receive_json() == {
            "type": "hello",
            "message": "Connected to notification service",
        }
        message = websocket.receive_json()
        assert message["type"] == "ping"
        websocket.send_json({"type": "pong"})
        time.sleep(0.02)


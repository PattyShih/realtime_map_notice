from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import load_module


event_service = load_module("event_service_main", "backend/event-service/app/main.py")


@dataclass
class FakePipeline:
    values: dict[str, str | None]
    requested_keys: list[str]

    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.requested_keys = []

    def get(self, key: str) -> "FakePipeline":
        self.requested_keys.append(key)
        return self

    async def execute(self) -> list[str | None]:
        return [
            self.values.get(key)
            for key in self.requested_keys
        ]
    
class FakeRedis:
    def __init__(self) -> None:
        self.geosearch_result = []
        self.pipeline_values: dict[str, str | None] = {}
        self.pipeline_instance: FakePipeline | None = None
        self.set_calls = []
        self.geoadd_calls = []
        self.zrem_calls = []

    async def ping(self) -> bool:
        return True

    async def set(self, key, value, ex=None):
        self.set_calls.append(
            {
                "key": key,
                "value": value,
                "ex": ex,
            }
        )

    async def geosearch(self, *args, **kwargs):
        return self.geosearch_result

    async def geoadd(self, key, values):
        self.geoadd_calls.append(
            {
                "key": key,
                "values": values,
            }
        )

    async def zrem(self, key, *members):
        self.zrem_calls.append(
            {
                "key": key,
                "members": members,
            }
        )

    def pipeline(self, transaction: bool = False) -> FakePipeline:
        self.pipeline_instance = FakePipeline(self.pipeline_values)
        return self.pipeline_instance


class FakeAsyncClient:
    def __init__(
        self,
        timeout: float,
        response_payload: dict | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.timeout = timeout
        self.response_payload = response_payload if response_payload is not None else {}
        self.raise_error = raise_error
        self.posts: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]):
        if self.raise_error is not None:
            raise self.raise_error

        self.posts.append((url, json))
        payload = self.response_payload

        class Response:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self):
                return payload

        return Response()


@pytest.mark.asyncio
async def test_healthz(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(event_service, "redis", fake_redis)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_event_with_nearby_users(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(event_service, "redis", fake_redis)

    fake_client = FakeAsyncClient(
        timeout=5.0,
        response_payload={
            "total_nearby_users": 2,
            "active_user_count": 1,
            "delivered_count": 1,
            "delivered_to": [
                {"user_id": "u-0001", "distance_meters": 120.0, "subscriber_count": 1}
            ],
        },
    )
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "title": "Library seats",
                "message": "3F has seats near windows",
                "latitude": 25.0173,
                "longitude": 121.5397,
                "severity": "urgent",
                "radius_meters": 500,
                "duration_minutes": 60,
                "image_base64": "fake-image-base64-data",
                "image_url": "https://example.com/library.jpg",
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["nearby_user_count"] == 2
    assert body["active_user_count"] == 1
    assert body["delivered_count"] == 1
    assert body["delivered_to"] == ["u-0001"]

    # Stage 5：只發一次 broadcast 呼叫，由 Notification Service 統一處理推播
    assert len(fake_client.posts) == 1
    broadcast_url, sent_payload = fake_client.posts[0]
    assert broadcast_url.endswith("/broadcast/nearby")
    assert sent_payload["image_base64"] == "fake-image-base64-data"
    assert sent_payload["image_url"] == "https://example.com/library.jpg"
    assert sent_payload["duration_minutes"] == 60
    assert sent_payload["radius_meters"] == 500
    stored_event = json.loads(fake_redis.set_calls[0]["value"])
    assert stored_event["image_url"] == "https://example.com/library.jpg"
    assert len(fake_redis.set_calls) == 1
    assert fake_redis.set_calls[0]["ex"] == 60 * 60
    assert len(fake_redis.geoadd_calls) == 1
    assert fake_redis.geoadd_calls[0]["key"] == "event_locations"
    assert fake_redis.geoadd_calls[0]["values"][0] == 121.5397
    assert fake_redis.geoadd_calls[0]["values"][1] == 25.0173


@pytest.mark.asyncio
async def test_create_event_no_nearby_users(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(event_service, "redis", fake_redis)

    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "title": "Library seats",
                "message": "3F has seats near windows",
                "latitude": 25.0173,
                "longitude": 121.5397,
                "severity": "info",
                "radius_meters": 500,
                "duration_minutes": 30,
                "image_base64": None,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["nearby_user_count"] == 0
    assert body["active_user_count"] == 0
    assert body["delivered_count"] == 0
    assert body["delivered_to"] == []

    # event-service 不再自行查詢使用者，一律轉呼 broadcast 由 notification-service 統計
    assert len(fake_client.posts) == 1
    assert fake_client.posts[0][0].endswith("/broadcast/nearby")
    assert len(fake_redis.geoadd_calls) == 1
    assert fake_redis.geoadd_calls[0]["key"] == "event_locations"
    assert fake_redis.geoadd_calls[0]["values"][0] == 121.5397
    assert fake_redis.geoadd_calls[0]["values"][1] == 25.0173


@pytest.mark.asyncio
async def test_get_events(monkeypatch) -> None:
    fake_redis = FakeRedis()

    fake_redis.geosearch_result = [
        "event-001",
    ]

    fake_redis.pipeline_values = {
        "event:event-001": """
        {
            "title": "Library 3F has seats",
            "message": "About 10 seats near windows.",
            "severity": "info",
            "latitude": 24.6859,
            "longitude": 120.9123,
            "radius_meters": 500,
            "created_at": "2026-08-02T01:30:00+00:00",
            "image_url": "https://example.com/library.jpg"
        }
        """
    }

    monkeypatch.setattr(
        event_service,
        "redis",
        fake_redis,
    )

    transport = ASGITransport(app=event_service.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/events",
            params={
                "latitude": 24.6859,
                "longitude": 120.9123,
                "radius": 3000,
            },
        )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1

    assert body[0]["event_id"] == "event-001"
    assert body[0]["title"] == "Library 3F has seats"
    assert body[0]["severity"] == "info"
    assert body[0]["radius_meters"] == 500
    assert body[0]["duration_minutes"] == 60
    assert datetime.fromisoformat(body[0]["created_at"].replace("Z", "+00:00")) == datetime.fromisoformat("2026-08-02T01:30:00+00:00")
    assert body[0]["image_url"] == "https://example.com/library.jpg"


@pytest.mark.asyncio
async def test_get_events_invalid_latitude(monkeypatch) -> None:
    transport = ASGITransport(app=event_service.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/events",
            params={
                "latitude": 100,
                "longitude": 121.5,
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_events_empty(monkeypatch) -> None:
    fake_redis = FakeRedis()
    fake_redis.geosearch_result = []

    monkeypatch.setattr(
        event_service,
        "redis",
        fake_redis,
    )

    transport = ASGITransport(app=event_service.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/events",
            params={
                "latitude": 25.0173,
                "longitude": 121.5397,
            },
        )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_events_remove_expired_events(monkeypatch) -> None:
    fake_redis = FakeRedis()

    fake_redis.geosearch_result = [
        "expired-event-001",
    ]

    fake_redis.pipeline_values = {
        "event:expired-event-001": None,
    }

    monkeypatch.setattr(
        event_service,
        "redis",
        fake_redis,
    )

    transport = ASGITransport(app=event_service.app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/events",
            params={
                "latitude": 24.6859,
                "longitude": 120.9123,
                "radius": 3000,
            },
        )

    assert response.status_code == 200
    assert response.json() == []

    assert fake_redis.zrem_calls == [
        {
            "key": "event_locations",
            "members": ("expired-event-001",),
        }
    ]


@pytest.mark.asyncio
async def test_create_event_broadcast_failure_still_creates_event(monkeypatch) -> None:
    """Stage 5：通知服務不可用時，事件仍要成功建立（推播統計歸零）。"""
    fake_redis = FakeRedis()
    monkeypatch.setattr(event_service, "redis", fake_redis)

    fake_client = FakeAsyncClient(
        timeout=5.0,
        raise_error=httpx.ConnectError("notification-service down"),
    )
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "title": "Library seats",
                "message": "3F has seats near windows",
                "latitude": 25.0173,
                "longitude": 121.5397,
                "severity": "info",
                "radius_meters": 500,
                "duration_minutes": 60,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["event_id"]
    assert body["nearby_user_count"] == 0
    assert body["active_user_count"] == 0
    assert body["delivered_count"] == 0
    assert body["delivered_to"] == []

    # 事件本體仍寫入 Redis
    assert len(fake_redis.set_calls) == 1
    assert len(fake_redis.geoadd_calls) == 1

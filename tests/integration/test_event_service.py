from __future__ import annotations

from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import load_module


event_service = load_module("event_service_main", "backend/event-service/app/main.py")


@dataclass
class FakePipeline:
    last_seen_values: list[str | None]
    requested_keys: list[str]

    def __init__(self, last_seen_values: list[str | None]) -> None:
        self.last_seen_values = last_seen_values
        self.requested_keys = []

    def get(self, key: str) -> "FakePipeline":
        self.requested_keys.append(key)
        return self

    async def execute(self) -> list[str | None]:
        return self.last_seen_values


class FakeRedis:
    def __init__(self) -> None:
        self.geosearch_result = []
        self.pipeline_values: list[str | None] = []
        self.pipeline_instance: FakePipeline | None = None

    async def ping(self) -> bool:
        return True

    async def geosearch(self, *args, **kwargs):
        return self.geosearch_result

    def pipeline(self, transaction: bool = False) -> FakePipeline:
        self.pipeline_instance = FakePipeline(self.pipeline_values)
        return self.pipeline_instance


class FakeAsyncClient:
    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.posts: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]):
        self.posts.append((url, json))

        class Response:
            status_code = 200

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
    fake_redis.geosearch_result = [("u-0001", "120.0"), ("u-0002", "250.0")]
    fake_redis.pipeline_values = ["2026-07-05T00:00:00Z", None]
    monkeypatch.setattr(event_service, "redis", fake_redis)

    fake_client = FakeAsyncClient(timeout=3.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=3.0: fake_client)

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
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["nearby_user_count"] == 2
    assert body["active_user_count"] == 1
    assert body["delivered_count"] == 1
    assert body["delivered_to"] == ["u-0001"]
    assert fake_redis.pipeline_instance is not None
    assert fake_redis.pipeline_instance.requested_keys == [
        f"{event_service.USER_LAST_SEEN_PREFIX}:u-0001",
        f"{event_service.USER_LAST_SEEN_PREFIX}:u-0002",
    ]
    assert len(fake_client.posts) == 1


@pytest.mark.asyncio
async def test_create_event_no_nearby_users(monkeypatch) -> None:
    fake_redis = FakeRedis()
    fake_redis.geosearch_result = []
    monkeypatch.setattr(event_service, "redis", fake_redis)

    fake_client = FakeAsyncClient(timeout=3.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=3.0: fake_client)

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
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["nearby_user_count"] == 0
    assert body["active_user_count"] == 0
    assert body["delivered_count"] == 0
    assert body["delivered_to"] == []
    assert fake_client.posts == []

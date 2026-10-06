from __future__ import annotations

from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import load_module


location_service = load_module("location_service_main", "backend/location-service/app/main.py")


@dataclass
class FakeRedis:
    geoadd_calls: list[tuple[str, tuple[float, float, str]]]
    set_calls: list[tuple[str, str, int | None]]
    geosearch_result: list[str]
    members: list[str]
    kv: dict[str, str]

    def __init__(self) -> None:
        self.geoadd_calls = []
        self.set_calls = []
        self.geosearch_result = []
        self.members = []
        self.kv = {}

    async def ping(self) -> bool:
        return True

    async def geoadd(self, key: str, value: tuple[float, float, str]) -> int:
        self.geoadd_calls.append((key, value))
        return 1

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.set_calls.append((key, value, ex))
        self.kv[key] = value
        return True

    async def geosearch(self, *args, **kwargs):
        return self.geosearch_result

    async def zcard(self, key: str) -> int:
        return len(self.members)

    async def zscan_iter(self, key: str):
        # 與 redis-py 一致：吐出 (member, score) tuple
        for member in self.members:
            yield (member, 0.0)

    def pipeline(self, transaction: bool = False) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, fake: FakeRedis) -> None:
        self.fake = fake
        self.keys: list[str] = []

    def get(self, key: str) -> "FakePipeline":
        self.keys.append(key)
        return self

    async def execute(self) -> list[str | None]:
        return [self.fake.kv.get(key) for key in self.keys]


@pytest.mark.asyncio
async def test_healthz(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(location_service, "redis", fake_redis)

    transport = ASGITransport(app=location_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_update_location(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(location_service, "redis", fake_redis)

    transport = ASGITransport(app=location_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/locations",
            json={"user_id": "u-0001", "latitude": 25.0173, "longitude": 121.5397},
        )

    assert response.status_code == 200
    assert response.json()["user_id"] == "u-0001"
    assert fake_redis.geoadd_calls == [
        (
            location_service.USER_LOCATION_KEY,
            (121.5397, 25.0173, "u-0001"),
        )
    ]
    assert fake_redis.set_calls[0][0] == "realtime_map_notice:user:last_seen:u-0001"
    assert fake_redis.set_calls[0][2] == location_service.LAST_SEEN_TTL_SECONDS


@pytest.mark.asyncio
async def test_get_nearby_users(monkeypatch) -> None:
    fake_redis = FakeRedis()
    fake_redis.geosearch_result = ["u-0001", "u-0002"]
    monkeypatch.setattr(location_service, "redis", fake_redis)

    transport = ASGITransport(app=location_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/locations/nearby",
            params={"latitude": 25.0173, "longitude": 121.5397, "radius_meters": 500},
        )

    assert response.status_code == 200
    assert response.json() == {"users": ["u-0001", "u-0002"]}


@pytest.mark.asyncio
async def test_get_nearby_users_no_result(monkeypatch) -> None:
    fake_redis = FakeRedis()
    fake_redis.geosearch_result = []
    monkeypatch.setattr(location_service, "redis", fake_redis)

    transport = ASGITransport(app=location_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/locations/nearby",
            params={"latitude": 25.0173, "longitude": 121.5397, "radius_meters": 500},
        )

    assert response.status_code == 200
    assert response.json() == {"users": []}


@pytest.mark.asyncio
async def test_online_users_counts_only_active_last_seen(monkeypatch) -> None:
    fake_redis = FakeRedis()
    fake_redis.members = ["u-0000", "u-0001", "user_abc"]
    fake_redis.kv = {
        # u-0000 的 last_seen 已過期（被清理）→ 不計入
        f"{location_service.USER_LAST_SEEN_PREFIX}:u-0001": "2026-09-29T12:00:00+00:00",
        f"{location_service.USER_LAST_SEEN_PREFIX}:user_abc": "2026-09-29T12:00:30+00:00",
    }
    monkeypatch.setattr(location_service, "redis", fake_redis)

    transport = ASGITransport(app=location_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/locations/online")

    assert response.status_code == 200
    assert response.json() == {"online": 2}


@pytest.mark.asyncio
async def test_online_users_empty(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(location_service, "redis", fake_redis)

    transport = ASGITransport(app=location_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/locations/online")

    assert response.status_code == 200
    assert response.json() == {"online": 0}

import asyncio

from backend.shared.schemas import LocationUpdate
from tests.unit.service_loader import load_service_module


class FakeRedis:
    def __init__(self, values: list[str | None]) -> None:
        self.values = values
        self.keys: list[str] = []
        self.geoadd_args: tuple[str, tuple[float, float, str]] | None = None
        self.set_args: tuple[str, str, int] | None = None
        self.geosearch_kwargs: dict[str, object] | None = None

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.keys = keys
        return self.values

    async def geoadd(
        self,
        key: str,
        location: tuple[float, float, str],
    ) -> None:
        self.geoadd_args = (key, location)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.set_args = (key, value, ex)

    async def geosearch(self, key: str, **kwargs: object) -> list[str]:
        self.geosearch_kwargs = {"key": key, **kwargs}
        return ["u-1", "u-2"]


def test_filter_active_users_keeps_only_users_with_last_seen() -> None:
    module = load_service_module("location-service")
    module.redis = FakeRedis(["timestamp", None, "timestamp"])

    result = asyncio.run(module.filter_active_users(["u-1", "u-2", "u-3"]))

    assert result == ["u-1", "u-3"]
    assert module.redis.keys == [
        "realtime_map_notice:user:last_seen:u-1",
        "realtime_map_notice:user:last_seen:u-2",
        "realtime_map_notice:user:last_seen:u-3",
    ]


def test_filter_active_users_returns_empty_without_redis_call() -> None:
    module = load_service_module("location-service")
    module.redis = FakeRedis(["timestamp"])

    result = asyncio.run(module.filter_active_users([]))

    assert result == []
    assert module.redis.keys == []


def test_update_location_writes_geo_and_last_seen() -> None:
    module = load_service_module("location-service")
    module.redis = FakeRedis([])

    result = asyncio.run(
        module.update_location(
            LocationUpdate(
                user_id="u-1",
                latitude=25.0173,
                longitude=121.5397,
            ),
        ),
    )

    assert result == {"status": "accepted", "user_id": "u-1"}
    assert module.redis.geoadd_args == (
        "realtime_map_notice:user:locations",
        (121.5397, 25.0173, "u-1"),
    )
    assert module.redis.set_args is not None
    assert module.redis.set_args[0] == "realtime_map_notice:user:last_seen:u-1"
    assert module.redis.set_args[2] == 60


def test_nearby_users_filters_stale_geosearch_results() -> None:
    module = load_service_module("location-service")
    module.redis = FakeRedis(["timestamp", None])

    result = asyncio.run(
        module.nearby_users(
            latitude=25.0173,
            longitude=121.5397,
            radius_meters=500,
        ),
    )

    assert result == {"users": ["u-1"]}
    assert module.redis.geosearch_kwargs == {
        "key": "realtime_map_notice:user:locations",
        "longitude": 121.5397,
        "latitude": 25.0173,
        "radius": 500,
        "unit": "m",
    }

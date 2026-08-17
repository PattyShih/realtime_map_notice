from fastapi.testclient import TestClient

from backend.shared.schemas import EventNotification
from tests.unit.service_loader import load_service_module


class FakeLocationRedis:
    def __init__(self) -> None:
        self.geoadd_args: tuple[str, tuple[float, float, str]] | None = None
        self.set_args: tuple[str, str, int] | None = None
        self.geosearch_kwargs: dict[str, object] | None = None

    async def ping(self) -> bool:
        return True

    async def geoadd(self, key: str, location: tuple[float, float, str]) -> None:
        self.geoadd_args = (key, location)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.set_args = (key, value, ex)

    async def geosearch(self, key: str, **kwargs: object) -> list[str]:
        self.geosearch_kwargs = {"key": key, **kwargs}
        return ["u-active", "u-stale"]

    async def mget(self, keys: list[str]) -> list[str | None]:
        return ["timestamp", None]


class FakeEventRedis:
    def __init__(self) -> None:
        self.geosearch_kwargs: dict[str, object] | None = None

    async def ping(self) -> bool:
        return True

    async def set(
        self,
        key: str,
        value: str,
        ex: int,
        nx: bool,
    ) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return None

    async def geosearch(self, key: str, **kwargs: object) -> list[tuple[str, float]]:
        self.geosearch_kwargs = {"key": key, **kwargs}
        return [("u-near", 42.5), ("u-stale", 99.0)]

    async def mget(self, keys: list[str]) -> list[str | None]:
        return ["timestamp", None]


class FakeNotificationRedis:
    def __init__(self) -> None:
        self.published: tuple[str, str] | None = None

    async def ping(self) -> bool:
        return True

    async def publish(self, channel: str, message: str) -> int:
        self.published = (channel, message)
        return 2


def test_location_api_accepts_update_and_filters_nearby_users() -> None:
    module = load_service_module("location-service")
    fake_redis = FakeLocationRedis()
    module.redis = fake_redis
    client = TestClient(module.app)

    update_response = client.post(
        "/locations",
        json={"user_id": "u-active", "latitude": 25.0173, "longitude": 121.5397},
    )
    nearby_response = client.get(
        "/locations/nearby",
        params={"latitude": 25.0173, "longitude": 121.5397, "radius_meters": 500},
    )

    assert update_response.status_code == 200
    assert update_response.json() == {"status": "accepted", "user_id": "u-active"}
    assert nearby_response.status_code == 200
    assert nearby_response.json() == {"users": ["u-active"]}
    assert fake_redis.geoadd_args == (
        "realtime_map_notice:user:locations",
        (121.5397, 25.0173, "u-active"),
    )
    assert fake_redis.geosearch_kwargs == {
        "key": "realtime_map_notice:user:locations",
        "longitude": 121.5397,
        "latitude": 25.0173,
        "radius": 500,
        "unit": "m",
    }


def test_location_api_rejects_invalid_coordinates() -> None:
    module = load_service_module("location-service")
    module.redis = FakeLocationRedis()
    client = TestClient(module.app)

    response = client.post(
        "/locations",
        json={"user_id": "u-bad", "latitude": 95, "longitude": 121.5397},
    )

    assert response.status_code == 422


def test_event_api_notifies_only_active_nearby_users() -> None:
    module = load_service_module("event-service")
    fake_redis = FakeEventRedis()
    module.redis = fake_redis
    delivered: list[tuple[str, EventNotification]] = []

    async def fake_deliver_notification(
        client: object,
        user_id: str,
        notification: EventNotification,
    ) -> str:
        delivered.append((user_id, notification))
        return user_id

    module.deliver_notification = fake_deliver_notification
    client = TestClient(module.app)

    response = client.post(
        "/events",
        json={
            "title": "Road blocked",
            "message": "Road blocked near library",
            "latitude": 25.0173,
            "longitude": 121.5397,
            "severity": "urgent",
            "radius_meters": 500,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "created"
    assert body["nearby_user_count"] == 1
    assert body["delivered_count"] == 1
    assert body["delivered_to"] == ["u-near"]
    assert delivered[0][0] == "u-near"
    assert delivered[0][1].distance_meters == 42.5
    assert fake_redis.geosearch_kwargs == {
        "key": "realtime_map_notice:user:locations",
        "longitude": 121.5397,
        "latitude": 25.0173,
        "radius": 500,
        "unit": "m",
        "withdist": True,
    }


def test_notification_api_publishes_user_notification_channel() -> None:
    module = load_service_module("notification-service")
    fake_redis = FakeNotificationRedis()
    module.redis = fake_redis
    client = TestClient(module.app)

    response = client.post(
        "/notify/u-near",
        json={
            "event_id": "evt-1",
            "title": "Road blocked",
            "message": "Road blocked near library",
            "latitude": 25.0173,
            "longitude": 121.5397,
            "severity": "urgent",
            "distance_meters": 42.5,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "u-near",
        "subscriber_count": 2,
        "status": "published",
    }
    assert fake_redis.published is not None
    channel, message = fake_redis.published
    assert channel == "realtime_map_notice:user:u-near:notifications"
    assert '"event_id":"evt-1"' in message

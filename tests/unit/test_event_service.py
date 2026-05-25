import asyncio

import httpx

from backend.shared.schemas import EventCreate
from backend.shared.schemas import EventNotification
from tests.unit.service_loader import load_service_module


class FakeRedis:
    def __init__(self, values: list[str | None]) -> None:
        self.values = values
        self.keys: list[str] = []
        self.geosearch_kwargs: dict[str, object] | None = None

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.keys = keys
        return self.values

    async def geosearch(self, key: str, **kwargs: object) -> list[tuple[str, float]]:
        self.geosearch_kwargs = {"key": key, **kwargs}
        return [("u-1", 10.5), ("u-2", 20.0), ("u-3", 30.5)]


class FakeResponse:
    def raise_for_status(self) -> None:
        return None


class FakeSuccessClient:
    def __init__(self) -> None:
        self.url: str | None = None
        self.json: dict[str, object] | None = None

    async def post(self, url: str, json: dict[str, object]) -> FakeResponse:
        self.url = url
        self.json = json
        return FakeResponse()


class FakeFailingClient:
    async def post(self, url: str, json: dict[str, object]) -> FakeResponse:
        raise httpx.ConnectError("notification service unavailable")


def make_notification() -> EventNotification:
    return EventNotification(
        event_id="evt-1",
        title="Urgent notice",
        message="Road blocked near library",
        latitude=25.0173,
        longitude=121.5397,
        severity="urgent",
        distance_meters=120,
    )


def test_filter_active_nearby_users_keeps_distance_with_active_users() -> None:
    module = load_service_module("event-service")
    module.redis = FakeRedis(["timestamp", None, "timestamp"])

    result = asyncio.run(
        module.filter_active_nearby_users(
            [("u-1", 10.5), ("u-2", 20.0), ("u-3", 30.5)],
        ),
    )

    assert result == [("u-1", 10.5), ("u-3", 30.5)]
    assert module.redis.keys == [
        "realtime_map_notice:user:last_seen:u-1",
        "realtime_map_notice:user:last_seen:u-2",
        "realtime_map_notice:user:last_seen:u-3",
    ]


def test_deliver_notification_returns_user_id_on_success() -> None:
    module = load_service_module("event-service")
    client = FakeSuccessClient()

    result = asyncio.run(
        module.deliver_notification(client, "u-1", make_notification()),
    )

    assert result == "u-1"
    assert client.url == "http://localhost:8003/notify/u-1"
    assert client.json is not None
    assert client.json["event_id"] == "evt-1"


def test_deliver_notification_returns_none_on_http_error() -> None:
    module = load_service_module("event-service")

    result = asyncio.run(
        module.deliver_notification(FakeFailingClient(), "u-1", make_notification()),
    )

    assert result is None


def test_create_event_notifies_only_active_nearby_users() -> None:
    module = load_service_module("event-service")
    module.redis = FakeRedis(["timestamp", None, "timestamp"])
    delivered: list[tuple[str, EventNotification]] = []

    async def fake_deliver_notification(
        client: object,
        user_id: str,
        notification: EventNotification,
    ) -> str:
        delivered.append((user_id, notification))
        return user_id

    module.deliver_notification = fake_deliver_notification

    result = asyncio.run(
        module.create_event(
            EventCreate(
                title="Road blocked",
                message="Road blocked near library",
                latitude=25.0173,
                longitude=121.5397,
                severity="urgent",
                radius_meters=500,
            ),
        ),
    )

    assert result["nearby_user_count"] == 2
    assert result["delivered_count"] == 2
    assert result["delivered_to"] == ["u-1", "u-3"]
    assert [user_id for user_id, _ in delivered] == ["u-1", "u-3"]
    assert delivered[0][1].title == "Road blocked"
    assert delivered[0][1].distance_meters == 10.5
    assert module.redis.geosearch_kwargs == {
        "key": "realtime_map_notice:user:locations",
        "longitude": 121.5397,
        "latitude": 25.0173,
        "radius": 500,
        "unit": "m",
        "withdist": True,
    }

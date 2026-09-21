from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import load_module


event_service = load_module("event_service_main", "backend/event-service/app/main.py")

from backend.shared import antispam as antispam_module


def install_fake_redis(monkeypatch) -> FakeRedis:
    """同時替換事件儲存與反垃圾過濾器持有的 redis 連線。"""
    fake_redis = FakeRedis()
    monkeypatch.setattr(event_service, "redis", fake_redis)
    monkeypatch.setattr(
        event_service, "antispam", event_service.EventAntiSpam(fake_redis)
    )
    return fake_redis


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
        # 反垃圾過濾用的通用 key-value 儲存（含 NX 與 sorted set）
        self.store: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.fake_time = 1_000_000.0

    async def ping(self) -> bool:
        return True

    async def get(self, key):
        return self.store.get(key)

    async def ttl(self, key) -> int:
        return 3600 if key in self.store else -2

    async def delete(self, *keys) -> int:
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
        return removed

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if not nx:
            # set_calls 只追蹤事件本體寫入，NX 的頻率管制 key 不列入
            self.set_calls.append(
                {
                    "key": key,
                    "value": value,
                    "ex": ex,
                }
            )
        return True

    async def incr(self, key) -> int:
        current = int(self.store.get(key, "0")) + 1
        self.store[key] = str(current)
        return current

    async def expire(self, key, seconds) -> bool:
        return key in self.store or key in self.zsets

    async def time(self) -> tuple[float, float]:
        return (self.fake_time, 0.0)

    async def zadd(self, key, mapping: dict[str, float]) -> int:
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def zcard(self, key) -> int:
        return len(self.zsets.get(key, {}))

    async def zremrangebyscore(self, key, min_score, max_score) -> int:
        members = self.zsets.get(key, {})
        removed = [m for m, score in members.items() if score <= float(max_score)]
        for member in removed:
            del members[member]
        return len(removed)

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
    fake_redis = install_fake_redis(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_event_with_nearby_users(monkeypatch) -> None:
    fake_redis = install_fake_redis(monkeypatch)

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
                "user_id": "u-0001",
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
    # （另一通 POST 是 AI 內容審核 /moderate）
    assert len(fake_client.posts) == 2
    broadcast_url, sent_payload = fake_client.posts[1]
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
    fake_redis = install_fake_redis(monkeypatch)

    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "user_id": "u-0001",
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
    assert len(fake_client.posts) == 2
    assert fake_client.posts[1][0].endswith("/broadcast/nearby")
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
    fake_redis = install_fake_redis(monkeypatch)

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
                "user_id": "u-0001",
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


def make_event_payload(index: int = 0) -> dict:
    """產生內容互不重複的事件 payload，避免觸發重複內容偵測。"""
    return {
        "user_id": "u-spammer",
        "title": f"Spam event #{index}",
        "message": f"Spam message body #{index}",
        "latitude": 25.0173,
        "longitude": 121.5397,
        "severity": "info",
        "radius_meters": 500,
        "duration_minutes": 60,
    }


@pytest.mark.asyncio
async def test_create_event_rejects_missing_user_id(monkeypatch) -> None:
    install_fake_redis(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "title": "No owner",
                "message": "user_id is required",
                "latitude": 25.0173,
                "longitude": 121.5397,
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_event_rejects_overlong_fields(monkeypatch) -> None:
    install_fake_redis(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "user_id": "u-0001",
                "title": "T" * 101,
                "message": "title exceeds max length",
                "latitude": 25.0173,
                "longitude": 121.5397,
            },
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_event_rejects_duplicate_content(monkeypatch) -> None:
    install_fake_redis(monkeypatch)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "user_id": "u-0001",
            "title": "Library seats",
            "message": "3F has seats near windows",
            "latitude": 25.0173,
            "longitude": 121.5397,
        }
        first = await client.post("/events", json=payload)
        second = await client.post("/events", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert "重複" in second.json()["detail"]


@pytest.mark.asyncio
async def test_create_event_rejects_frequent_posting(monkeypatch) -> None:
    install_fake_redis(monkeypatch)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/events", json=make_event_payload(1))
        # 內容不同，但間隔不足：應被最小間隔檢查擋下
        second = await client.post("/events", json=make_event_payload(2))

    assert first.status_code == 200
    assert second.status_code == 429
    assert "間隔" in second.json()["detail"]


@pytest.mark.asyncio
async def test_create_event_rejects_rate_limit(monkeypatch) -> None:
    install_fake_redis(monkeypatch)
    monkeypatch.setattr(antispam_module, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(antispam_module, "RATE_LIMIT_PER_MINUTE", 2)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.post("/events", json=make_event_payload(i)) for i in range(3)
        ]

    assert [r.status_code for r in responses] == [200, 200, 429]
    assert "每分鐘" in responses[2].json()["detail"]


@pytest.mark.asyncio
async def test_create_event_rejects_too_many_active_events(monkeypatch) -> None:
    install_fake_redis(monkeypatch)
    monkeypatch.setattr(antispam_module, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(antispam_module, "RATE_LIMIT_PER_MINUTE", 100)
    monkeypatch.setattr(antispam_module, "MAX_ACTIVE_EVENTS_PER_USER", 2)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.post("/events", json=make_event_payload(i)) for i in range(3)
        ]

    assert [r.status_code for r in responses] == [200, 200, 429]
    assert "同時最多" in responses[2].json()["detail"]


@pytest.mark.asyncio
async def test_create_event_rejected_by_moderation(monkeypatch) -> None:
    """AI 審核判定垃圾訊息時，事件應被 422 拒絕且不寫入儲存。"""
    fake_redis = install_fake_redis(monkeypatch)
    fake_client = FakeAsyncClient(
        timeout=5.0,
        response_payload={"verdict": "spam", "score": 0.95, "reason": "商業廣告"},
    )
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/events", json=make_event_payload(1))

    assert response.status_code == 422
    assert "審核" in response.json()["detail"]
    # 被拒絕的事件不應寫入 Redis，也不應廣播
    assert len(fake_redis.set_calls) == 0
    assert len(fake_redis.geoadd_calls) == 0
    assert all(url.endswith("/moderate") for url, _ in fake_client.posts)


@pytest.mark.asyncio
async def test_create_event_moderation_fail_open(monkeypatch) -> None:
    """AI 服務掛掉時 fail-open：事件仍正常建立。"""
    fake_redis = install_fake_redis(monkeypatch)
    fake_client = FakeAsyncClient(
        timeout=5.0, raise_error=httpx.ConnectError("ai-service down")
    )
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/events", json=make_event_payload(1))

    assert response.status_code == 200
    assert len(fake_redis.set_calls) == 1


async def create_event_for_test(monkeypatch, user_id: str = "u-owner", title: str = "Editable event") -> tuple[dict, FakeRedis, FakeAsyncClient]:
    """建立一則事件供編輯/刪除測試使用，回傳（回應主體, fake_redis, fake_client）。"""
    fake_redis = install_fake_redis(monkeypatch)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "user_id": user_id,
                "title": title,
                "message": "original message",
                "latitude": 25.0173,
                "longitude": 121.5397,
                "severity": "info",
                "duration_minutes": 60,
            },
        )
    assert response.status_code == 200
    return response.json(), fake_redis, fake_client


@pytest.mark.asyncio
async def test_update_event_by_owner(monkeypatch) -> None:
    body, fake_redis, _ = await create_event_for_test(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            f"/events/{body['event_id']}",
            json={
                "user_id": "u-owner",
                "title": "Updated title",
                "message": "updated message",
                "severity": "warning",
            },
        )

    assert response.status_code == 200
    stored = json.loads(fake_redis.store[f"event:{body['event_id']}"])
    assert stored["title"] == "Updated title"
    assert stored["message"] == "updated message"
    assert stored["severity"] == "warning"
    # 地點資訊不可被編輯更動
    assert stored["latitude"] == 25.0173
    assert stored["user_id"] == "u-owner"


@pytest.mark.asyncio
async def test_update_event_by_non_owner_forbidden(monkeypatch) -> None:
    body, fake_redis, _ = await create_event_for_test(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            f"/events/{body['event_id']}",
            json={
                "user_id": "u-attacker",
                "title": "hijacked",
                "message": "hijacked",
                "severity": "urgent",
            },
        )

    assert response.status_code == 403
    # 內容未被竄改
    stored = json.loads(fake_redis.store[f"event:{body['event_id']}"])
    assert stored["title"] == "Editable event"


@pytest.mark.asyncio
async def test_update_missing_event_returns_404(monkeypatch) -> None:
    install_fake_redis(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/events/no-such-event",
            json={
                "user_id": "u-owner",
                "title": "t",
                "message": "m",
                "severity": "info",
            },
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_event_rejected_by_moderation(monkeypatch) -> None:
    body, fake_redis, _ = await create_event_for_test(monkeypatch)
    fake_client = FakeAsyncClient(
        timeout=5.0,
        response_payload={"verdict": "spam", "score": 1.0, "reason": "廣告"},
    )
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            f"/events/{body['event_id']}",
            json={
                "user_id": "u-owner",
                "title": "spam edit",
                "message": "spam edit body",
                "severity": "info",
            },
        )

    assert response.status_code == 422
    stored = json.loads(fake_redis.store[f"event:{body['event_id']}"])
    assert stored["title"] == "Editable event"


@pytest.mark.asyncio
async def test_delete_event_by_owner(monkeypatch) -> None:
    body, fake_redis, _ = await create_event_for_test(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            f"/events/{body['event_id']}", params={"user_id": "u-owner"}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    # 事件本體與 GEO 索引都要移除
    assert f"event:{body['event_id']}" not in fake_redis.store
    assert fake_redis.zrem_calls == [
        {"key": "event_locations", "members": (body["event_id"],)}
    ]


@pytest.mark.asyncio
async def test_delete_event_by_non_owner_forbidden(monkeypatch) -> None:
    body, fake_redis, _ = await create_event_for_test(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            f"/events/{body['event_id']}", params={"user_id": "u-attacker"}
        )

    assert response.status_code == 403
    assert f"event:{body['event_id']}" in fake_redis.store

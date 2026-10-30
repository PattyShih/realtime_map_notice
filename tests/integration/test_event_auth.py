"""Google 登入與 JWT 身分驗證的整合測試。

Google ID token 的密碼學驗證（google-auth 套件、Google 公開金鑰）在測試中
以 monkeypatch 假造——這裡測的是「我們自己的流程」：token 換發、user_id
覆蓋、401 拒絕與內部金鑰通道。
"""
from __future__ import annotations

import json

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration import test_event_service as ev
from tests.integration.test_event_service import AUTH, FakeAsyncClient, install_fake_redis

from backend.shared import antispam as antispam_module

# 重要：沿用 test_event_service 載入的同一個模組實例——load_module 不會快取，
# 各自再載一次會拿到兩個獨立實例，monkeypatch 就會打錯目標。
event_service = ev.event_service

TEST_JWT_SECRET = "test-jwt-secret"


@pytest.fixture
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)


def make_jwt(user_id: str, name: str = "測試同學", email: str = "test@example.com") -> str:
    import datetime as dt

    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user_id,
        "name": name,
        "email": email,
        "exp": int((now + dt.timedelta(hours=1)).timestamp()),
        "iat": int(now.timestamp()),
    }
    return pyjwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def fake_google_info(sub: str = "1234567890") -> dict:
    return {
        "sub": sub,
        "email": "frogshih@example.com",
        "name": "施佩岑",
        "picture": "https://lh3.googleusercontent.com/a/example",
    }


@pytest.mark.asyncio
async def test_create_event_without_auth_returns_401(monkeypatch) -> None:
    install_fake_redis(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            json={
                "user_id": "u-0001",
                "title": "Library seats",
                "message": "3F has seats",
                "latitude": 25.0173,
                "longitude": 121.5397,
            },
        )

    assert response.status_code == 401
    assert "登入" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_event_with_wrong_internal_key_returns_401(monkeypatch) -> None:
    install_fake_redis(monkeypatch)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            headers={"X-Internal-Key": "wrong-key"},
            json={
                "user_id": "u-0001",
                "title": "Library seats",
                "message": "3F has seats",
                "latitude": 25.0173,
                "longitude": 121.5397,
            },
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_google_login_issues_jwt_and_stores_profile(monkeypatch, jwt_secret) -> None:
    fake_redis = install_fake_redis(monkeypatch)
    monkeypatch.setattr(event_service, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(
        event_service, "_verify_google_credential", lambda credential: fake_google_info()
    )

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/google", json={"credential": "fake-google-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == "g_1234567890"
    assert body["user"]["email"] == "frogshih@example.com"

    # 核發的 JWT 可用測試金鑰驗證，sub 即登入者 user_id
    payload = pyjwt.decode(body["token"], TEST_JWT_SECRET, algorithms=["HS256"])
    assert payload["sub"] == "g_1234567890"

    # 使用者資料已寫入 Redis
    assert fake_redis.hashes["user:g_1234567890"]["email"] == "frogshih@example.com"


@pytest.mark.asyncio
async def test_google_login_rejects_invalid_credential(monkeypatch, jwt_secret) -> None:
    install_fake_redis(monkeypatch)
    monkeypatch.setattr(event_service, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")

    def raise_value_error(credential: str) -> dict:
        raise ValueError("Invalid token")

    monkeypatch.setattr(event_service, "_verify_google_credential", raise_value_error)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/google", json={"credential": "bad-token"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_google_login_returns_503_when_client_id_unset(monkeypatch, jwt_secret) -> None:
    install_fake_redis(monkeypatch)
    monkeypatch.setattr(event_service, "GOOGLE_CLIENT_ID", "")

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/google", json={"credential": "any"})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_auth_me_with_valid_jwt(monkeypatch, jwt_secret) -> None:
    install_fake_redis(monkeypatch)
    token = make_jwt("g_1234567890")

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "g_1234567890"
    assert body["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_auth_me_rejects_expired_or_forged_jwt(monkeypatch, jwt_secret) -> None:
    install_fake_redis(monkeypatch)

    forged = pyjwt.encode({"sub": "g_hacker"}, "another-secret", algorithm="HS256")

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        forged_response = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {forged}"}
        )
        empty_response = await client.get("/auth/me")

    assert forged_response.status_code == 401
    assert empty_response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_overrides_body_user_id_on_create(monkeypatch, jwt_secret) -> None:
    """安全關鍵：JWT 登入者就算在 body 填別人的 user_id，事件仍歸給 token 擁有者。"""
    fake_redis = install_fake_redis(monkeypatch)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)
    token = make_jwt("g_real-user")

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_id": "g_someone-else",  # 冒用他人身分
                "title": "Pretend to be someone",
                "message": "body user_id should be ignored",
                "latitude": 25.0173,
                "longitude": 121.5397,
            },
        )

    assert response.status_code == 200
    stored = json.loads(fake_redis.set_calls[0]["value"])
    assert stored["user_id"] == "g_real-user"


@pytest.mark.asyncio
async def test_jwt_user_cannot_delete_others_event_with_fake_query(monkeypatch, jwt_secret) -> None:
    """JWT 使用者在 query 帶事件擁有者的 user_id 也拿不到刪除權（token 為準）。"""
    fake_redis = install_fake_redis(monkeypatch)
    # 內部金鑰先以 u-owner 建立一則事件
    fake_redis.store["event:evt-1"] = json.dumps({
        "user_id": "u-owner",
        "title": "owner's event",
        "message": "m",
        "severity": "info",
        "latitude": 25.0,
        "longitude": 121.5,
        "radius_meters": 500,
        "created_at": "2026-01-01T00:00:00+00:00",
        "duration_minutes": 60,
    })
    token = make_jwt("g_attacker")

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            "/events/evt-1", params={"user_id": "u-owner"}, headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 403
    assert "event:evt-1" in fake_redis.store


@pytest.mark.asyncio
async def test_internal_key_still_allows_simulator(monkeypatch) -> None:
    """ops 儀表板的事件模擬器：內部金鑰 + body user_id 照舊可用。"""
    fake_redis = install_fake_redis(monkeypatch)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/events",
            headers=AUTH,
            json={
                "user_id": "u-9001",
                "title": "Simulator event",
                "message": "from event_gen",
                "latitude": 25.0372,
                "longitude": 121.4325,
            },
        )

    assert response.status_code == 200
    stored = json.loads(fake_redis.set_calls[0]["value"])
    assert stored["user_id"] == "u-9001"


@pytest.mark.asyncio
async def test_rejected_event_leaves_no_duplicate_fingerprint(monkeypatch) -> None:
    """被 429「間隔太短」擋下的內容不得留下指紋：
    30 秒後重發同一內容應該成功，而不是被誤判 409 重複。"""
    fake_redis = install_fake_redis(monkeypatch)
    monkeypatch.setattr(antispam_module, "MIN_INTERVAL_SECONDS", 30)
    fake_client = FakeAsyncClient(timeout=5.0)
    monkeypatch.setattr(event_service.httpx, "AsyncClient", lambda timeout=5.0: fake_client)

    payload = {
        "user_id": "u-0001",
        "title": "Same content",
        "message": "identical body",
        "latitude": 25.0173,
        "longitude": 121.5397,
    }
    # 先發一則別的內容建立「間隔」狀態
    transport = ASGITransport(app=event_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/events", headers=AUTH, json=payload)
        assert first.status_code == 200

        too_soon = dict(payload, title="Different title")
        rejected = await client.post("/events", headers=AUTH, json=too_soon)
        assert rejected.status_code == 429
        assert "間隔" in rejected.json()["detail"]

        # 被拒的內容重發（內容完全相同）：指紋不存在，不應被誤判重複
        # （FakeRedis 的時間不會前進，但 interval key 在 30 秒後本該過期；
        #   這裡直接清掉 interval key 模擬時間流逝）
        fake_redis.store = {
            k: v for k, v in fake_redis.store.items() if ":interval:" not in k
        }
        retry = await client.post("/events", headers=AUTH, json=too_soon)

    assert retry.status_code == 200, retry.json()

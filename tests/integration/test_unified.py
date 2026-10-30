"""Unified API 掛載測試：驗證四個子應用與健康檢查端點。"""
from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from backend.shared import campus as campus_module

from tests.conftest import load_module

unified = load_module("unified_main", "backend/unified-service/app/main.py")


async def fake_road(lat: float, lng: float) -> str | None:
    return None


@pytest.mark.asyncio
async def test_shell_healthz(monkeypatch) -> None:
    transport = ASGITransport(app=unified.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["services"]) == {"location", "event", "notification", "ai"}


@pytest.mark.asyncio
async def test_mounted_location_resolve(monkeypatch) -> None:
    """掛載於 /loc 的定位服務：校園座標回大樓名。"""
    monkeypatch.setattr(unified.location, "resolve_road_name", fake_road)

    transport = ASGITransport(app=unified.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/loc/locations/resolve",
            params={"latitude": 25.036230, "longitude": 121.434509},
        )

    assert response.status_code == 200
    assert response.json() == {"label": "輔大總圖書館"}


@pytest.mark.asyncio
async def test_mounted_event_validation(monkeypatch) -> None:
    """掛載於 /event 的事件服務：缺身分時 401（fail-closed）。"""
    transport = ASGITransport(app=unified.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/event/events",
            json={"title": "t", "message": "m", "latitude": 25.0, "longitude": 121.0},
        )
    # 無任何身分（無 JWT、無內部金鑰）→ 401
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mounted_ai_healthz() -> None:
    transport = ASGITransport(app=unified.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ai/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mounted_routes_registered() -> None:
    """四個子應用的關鍵路由皆已註冊於統一應用。"""
    from starlette.routing import Mount

    mounts = {r.path: r for r in unified.app.routes if isinstance(r, Mount)}
    assert set(mounts) == {"/loc", "/event", "/notify", "/ai"}

    expected = {
        "/loc": ["/locations/resolve", "/locations/online", "/healthz"],
        "/event": ["/events", "/auth/google", "/auth/me"],
        "/notify": ["/broadcast/nearby", "/ws/{user_id}", "/push/public-key"],
        "/ai": ["/evaluate-event", "/moderate", "/analyze-event"],
    }
    for prefix, routes in expected.items():
        sub_paths = {getattr(r, "path", "") for r in mounts[prefix].routes}
        for route in routes:
            assert route in sub_paths, f"{prefix} 缺少路由 {route}"

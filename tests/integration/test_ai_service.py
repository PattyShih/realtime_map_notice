from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import load_module


ai_service = load_module("ai_service_main", "backend/ai-service/app/main.py")


class FakeLLMResponse:
    status_code = 200

    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self.content}}]}


class FakeAsyncClient:
    def __init__(
        self,
        timeout: float,
        content: str = "{}",
        raise_error: Exception | None = None,
    ) -> None:
        self.timeout = timeout
        self.content = content
        self.raise_error = raise_error
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        if self.raise_error is not None:
            raise self.raise_error
        self.posts.append((url, json))
        return FakeLLMResponse(self.content)


def make_moderate_payload() -> dict:
    return {"title": "Library seats", "message": "3F has seats near windows"}


async def post_moderate(payload: dict) -> httpx.Response:
    transport = ASGITransport(app=ai_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/moderate", json=payload)


@pytest.mark.asyncio
async def test_healthz() -> None:
    transport = ASGITransport(app=ai_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_keyword_provider_blocks_spam(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "keyword")

    response = await post_moderate(
        {"title": "超好康", "message": "免費 領獎金，加好友了解"}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["verdict"] == "spam"
    assert body["provider"] == "keyword"
    assert body["score"] == 1.0


@pytest.mark.asyncio
async def test_keyword_provider_allows_normal_event(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "keyword")

    response = await post_moderate(make_moderate_payload())

    body = response.json()
    assert body["verdict"] == "ok"
    assert body["score"] == 0.0


@pytest.mark.asyncio
async def test_off_provider_allows_everything(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "off")

    response = await post_moderate(
        {"title": "免費", "message": "中獎"}
    )

    assert response.json()["verdict"] == "ok"


@pytest.mark.asyncio
async def test_llm_provider_spam_verdict(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "test-key")
    llm_json = json.dumps(
        {"spam": True, "score": 0.95, "reason": "商業廣告"}, ensure_ascii=False
    )
    fake_client = FakeAsyncClient(timeout=8.0, content=llm_json)
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda timeout=8.0: fake_client)

    response = await post_moderate(make_moderate_payload())

    body = response.json()
    assert body["verdict"] == "spam"
    assert body["provider"] == "llm"
    assert body["score"] == 0.95
    assert body["reason"] == "商業廣告"


@pytest.mark.asyncio
async def test_llm_provider_parses_code_fenced_json(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "test-key")
    fenced = '```json\n{"spam": false, "score": 0.1, "reason": "正常"}\n```'
    fake_client = FakeAsyncClient(timeout=8.0, content=fenced)
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda timeout=8.0: fake_client)

    response = await post_moderate(make_moderate_payload())

    assert response.json()["verdict"] == "ok"


@pytest.mark.asyncio
async def test_llm_provider_fails_open_on_error(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "test-key")
    fake_client = FakeAsyncClient(
        timeout=8.0, raise_error=httpx.ConnectError("llm down")
    )
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda timeout=8.0: fake_client)

    response = await post_moderate(make_moderate_payload())

    assert response.json()["verdict"] == "ok"


@pytest.mark.asyncio
async def test_llm_provider_without_api_key_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "OPENAI_API_KEY", "")

    response = await post_moderate(make_moderate_payload())

    body = response.json()
    assert body["verdict"] == "ok"
    assert "未設定" in body["reason"]


def test_extract_json_handles_fences() -> None:
    text = '```json\n{"spam": true, "score": 0.9, "reason": "ad"}\n```'
    assert ai_service._extract_json(text) == {"spam": True, "score": 0.9, "reason": "ad"}

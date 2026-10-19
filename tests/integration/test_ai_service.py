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


class FakeGeminiResponse(FakeLLMResponse):
    def json(self) -> dict:
        return {
            "candidates": [
                {"content": {"parts": [{"text": self.content}]}}
            ]
        }


class FakeAsyncClient:
    def __init__(
        self,
        timeout: float,
        content: str = "{}",
        raise_error: Exception | None = None,
        gemini: bool = False,
    ) -> None:
        self.timeout = timeout
        self.content = content
        self.raise_error = raise_error
        self.gemini = gemini
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        if self.raise_error is not None:
            raise self.raise_error
        self.posts.append((url, json))
        response_class = FakeGeminiResponse if self.gemini else FakeLLMResponse
        return response_class(self.content)


def make_moderate_payload() -> dict:
    return {"title": "Library seats", "message": "3F has seats near windows"}


async def post_moderate(payload: dict) -> httpx.Response:
    transport = ASGITransport(app=ai_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/moderate", json=payload)


async def post_analyze(payload: dict) -> httpx.Response:
    transport = ASGITransport(app=ai_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/analyze-event", json=payload)


async def post_evaluate(payload: dict) -> httpx.Response:
    transport = ASGITransport(app=ai_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/evaluate-event", json=payload)


@pytest.mark.asyncio
async def test_healthz() -> None:
    transport = ASGITransport(app=ai_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_llm_healthz_reports_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "")

    transport = ASGITransport(app=ai_service.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz/llm")

    assert response.status_code == 200
    assert response.json() == {"status": "not_configured", "provider": "gemini"}


@pytest.mark.asyncio
async def test_gemini_url_does_not_duplicate_path_separator(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_service,
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/",
    )
    client = FakeAsyncClient(timeout=8.0, content='{"ping":"ok"}', gemini=True)
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda timeout: client)

    result = await ai_service._request_llm_json("system", "user")

    assert result == {"ping": "ok"}
    assert client.posts[0][0] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{ai_service.GEMINI_MODEL}:generateContent"
    )


@pytest.mark.asyncio
async def test_analyze_event_detects_suspected_stalking() -> None:
    response = await post_analyze(
        {
            "title": "有人一直跟著我",
            "message": "我在捷運站，陌生人已經尾隨我兩個出口。",
            "latitude": 25.033,
            "longitude": 121.565,
        }
    )

    body = response.json()
    assert response.status_code == 200
    assert body["category"] == "suspected_stalking"
    assert body["suggested_severity"] == "urgent"
    assert "110" in body["emergency_contacts"]
    assert "事件類型" in body["report_summary"]


@pytest.mark.asyncio
async def test_analyze_event_rejects_invalid_coordinates() -> None:
    response = await post_analyze(
        {
            "title": "事件",
            "message": "測試內容",
            "latitude": 100,
        }
    )

    assert response.status_code == 422


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


@pytest.mark.asyncio
async def test_gemini_provider_moderates_json(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    fake_client = FakeAsyncClient(timeout=8.0, content=json.dumps(
        {"spam": False, "score": 0.05, "reason": "正常事件"}, ensure_ascii=False
    ))
    fake_client_response = FakeGeminiResponse(fake_client.content)

    class GeminiClient(FakeAsyncClient):
        async def post(self, url: str, json: dict, headers: dict | None = None):
            self.posts.append((url, json))
            return fake_client_response

    gemini_client = GeminiClient(timeout=8.0, content=fake_client.content)
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda timeout=8.0: gemini_client)

    response = await post_moderate(make_moderate_payload())

    assert response.status_code == 200
    assert response.json()["verdict"] == "ok"
    assert gemini_client.posts[0][0].endswith(":generateContent")
    assert gemini_client.posts[0][1]["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.asyncio
async def test_gemini_provider_analyzes_event(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    analysis = {
        "category": "suspected_stalking",
        "suggested_severity": "urgent",
        "summary": "疑似跟蹤",
        "incident_facts": ["陌生人持續尾隨"],
        "advice": ["前往人多的地方"],
        "emergency_contacts": ["110"],
        "report_summary": "事件類型：疑似跟蹤",
        "confidence": 0.9,
    }
    gemini_client = FakeAsyncClient(timeout=8.0, content=json.dumps(analysis, ensure_ascii=False))
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda timeout=8.0: _GeminiTestClient(gemini_client),
    )

    response = await post_analyze(make_moderate_payload())

    assert response.status_code == 200
    assert response.json()["category"] == "suspected_stalking"


@pytest.mark.asyncio
async def test_evaluate_event_rejects_non_event_content(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    evaluation = {
        "decision": "reject",
        "reason": "內容是在評論發文，不是地圖事件",
        "category": "other",
        "suggested_severity": "info",
        "summary": "非事件內容",
        "incident_facts": [],
        "advice": [],
        "emergency_contacts": [],
        "report_summary": "非事件內容",
        "confidence": 0.98,
    }
    client = FakeAsyncClient(timeout=8.0, content=json.dumps(evaluation, ensure_ascii=False))
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda timeout: _GeminiTestClient(client),
    )

    response = await post_evaluate(
        {"title": "提醒", "message": "大家不要發廢文", "severity": "info"}
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "reject"
    assert response.json()["analysis"]["provider"] == "llm"


@pytest.mark.asyncio
async def test_evaluate_event_publishes_strange_but_observable_content(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    evaluation = {
        "decision": "publish",
        "reason": "內容描述了可觀察的現象，即使尚未確認",
        "category": "other",
        "suggested_severity": "info",
        "summary": "操場上看到疑似大型鳥類飛過",
        "incident_facts": ["使用者看到大型物體飛過操場"],
        "advice": ["如再次出現可補充照片或時間"],
        "emergency_contacts": [],
        "report_summary": "尚未確認的校園現象",
        "confidence": 0.45,
    }
    client = FakeAsyncClient(timeout=8.0, content=json.dumps(evaluation, ensure_ascii=False))
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda timeout: _GeminiTestClient(client),
    )

    response = await post_evaluate(
        {"title": "操場怪事", "message": "剛剛看到很大的鳥飛過操場", "severity": "info"}
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "publish"
    assert response.json()["analysis"]["provider"] == "llm"


@pytest.mark.asyncio
async def test_evaluate_event_keyword_mode_does_not_require_api_key(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "keyword")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "keyword")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEYS", [])

    response = await post_evaluate(
        {"title": "圖書館空位", "message": "三樓窗邊還有座位", "severity": "info"}
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "publish"
    assert response.json()["analysis"]["provider"] == "keyword"


@pytest.mark.asyncio
async def test_evaluate_event_normalizes_common_llm_localized_fields(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    evaluation = {
        "decision": "publish",
        "reason": "描述了可觀察事件",
        "category": "其他",
        "suggested_severity": "一般",
        "summary": "校園事件",
        "incident_facts": "現場有可觀察現象",
        "advice": "請補充更多細節",
        "emergency_contacts": [],
        "report_summary": "測試事件",
        "confidence": 0.5,
    }
    client = FakeAsyncClient(timeout=8.0, content=json.dumps(evaluation, ensure_ascii=False))
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda timeout: _GeminiTestClient(client),
    )

    response = await post_evaluate(
        {"title": "測試事件", "message": "校園有可觀察現象", "severity": "info"}
    )

    assert response.status_code == 200
    assert response.json()["analysis"]["category"] == "other"
    assert response.json()["analysis"]["advice"] == ["請補充更多細節"]


@pytest.mark.asyncio
async def test_evaluate_event_retries_invalid_llm_shape(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    valid = {
        "decision": "reject",
        "reason": "沒有具體事件",
        "category": "other",
        "suggested_severity": "info",
        "summary": "無效內容",
        "incident_facts": [],
        "advice": [],
        "emergency_contacts": [],
        "report_summary": "無效內容",
        "confidence": 1.0,
    }
    client = FakeAsyncClient(
        timeout=8.0,
        content=json.dumps({"decision": "maybe"}, ensure_ascii=False),
    )
    client.responses = [
        json.dumps({"decision": "maybe"}, ensure_ascii=False),
        json.dumps(valid, ensure_ascii=False),
    ]

    class RetryClient(_GeminiTestClient):
        async def post(self, url: str, json: dict, headers: dict | None = None):
            content = self.delegate.responses.pop(0)
            self.delegate.content = content
            return await super().post(url, json, headers)

    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda timeout: RetryClient(client),
    )

    response = await post_evaluate(
        {"title": "測試", "message": "沒有具體事件", "severity": "info"}
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "reject"


@pytest.mark.asyncio
async def test_evaluate_event_fills_optional_model_fields(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    evaluation = {"decision": "reject", "reason": "沒有具體事件"}
    client = FakeAsyncClient(timeout=8.0, content=json.dumps(evaluation))
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda timeout: _GeminiTestClient(client),
    )

    response = await post_evaluate(
        {"title": "啊啊啊啊", "message": "啊啊啊啊", "severity": "info"}
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "reject"
    assert response.json()["analysis"]["summary"] == "啊啊啊啊"


@pytest.mark.asyncio
async def test_evaluation_request_uses_gemini_response_schema(monkeypatch) -> None:
    monkeypatch.setattr(ai_service, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_service, "MODERATION_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "ANALYSIS_PROVIDER", "llm")
    monkeypatch.setattr(ai_service, "GEMINI_API_KEY", "fake-gemini-key")
    client = FakeAsyncClient(
        timeout=8.0,
        content=json.dumps(
            {
                "decision": "reject",
                "reason": "沒有具體事件",
                "category": "other",
                "suggested_severity": "info",
                "summary": "無效內容",
                "incident_facts": [],
                "advice": [],
                "emergency_contacts": [],
                "report_summary": "無效內容",
                "confidence": 1.0,
            }
        ),
    )
    monkeypatch.setattr(
        ai_service.httpx,
        "AsyncClient",
        lambda timeout: _GeminiTestClient(client),
    )

    response = await post_evaluate(
        {"title": "測試", "message": "啊啊啊啊", "severity": "info"}
    )

    assert response.status_code == 200
    request = client.posts[0][1]
    assert request["generationConfig"]["responseSchema"] == (
        ai_service.EVALUATION_RESPONSE_SCHEMA
    )


class _GeminiTestClient:
    def __init__(self, delegate: FakeAsyncClient) -> None:
        self.delegate = delegate
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.posts.append((url, json))
        self.delegate.posts.append((url, json))
        return FakeGeminiResponse(self.delegate.content)


def test_extract_json_handles_fences() -> None:
    text = '```json\n{"spam": true, "score": 0.9, "reason": "ad"}\n```'
    assert ai_service._extract_json(text) == {"spam": True, "score": 0.9, "reason": "ad"}

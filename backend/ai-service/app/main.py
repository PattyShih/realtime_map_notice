"""AI 服務：事件內容審核（垃圾訊息偵測）。

Event Service 在建立事件前會呼叫 POST /moderate，判斷內容是否為垃圾訊息。
與 event-service 的行為式過濾（antispam.py）互補：
- antispam 擋「行為」（洗頻、重複貼文）
- ai-service 擋「內容」（廣告、詐騙、辱罵等每則內容都不同的垃圾）

AI provider 用環境變數 AI_PROVIDER 切換：
- openai：呼叫 OpenAI 相容 API
- gemini：呼叫 Google Gemini API

審核 provider 用環境變數 MODERATION_PROVIDER 切換：
- off：停用，一律放行
- keyword：本機關鍵字比對（不需 API key，Demo/離線用）
- llm：使用 AI_PROVIDER 指定的 LLM 做語意判斷

任何內部錯誤都回覆 verdict=ok（fail-open），審核服務故障不應拖垮發布功能。
"""

import json
import logging
import os

import httpx
from fastapi import FastAPI

from backend.shared.cors import configure_cors
from backend.shared.schemas import (
    EventAnalysisRequest,
    EventAnalysisResponse,
    ModerationRequest,
    ModerationResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# off / keyword / llm
MODERATION_PROVIDER = os.getenv("MODERATION_PROVIDER") or "keyword"
# keyword provider 用的封鎖詞，逗號分隔（環境變數設空字串時用預設清單）
DEFAULT_BLOCKED_KEYWORDS = "免費,賺錢,優惠碼,中獎,點擊連結,借錢,加好友,代開發票,兼職日結"
MODERATION_BLOCKED_KEYWORDS = [
    word.strip()
    for word in (os.getenv("MODERATION_BLOCKED_KEYWORDS") or DEFAULT_BLOCKED_KEYWORDS).split(",")
    if word.strip()
]
# LLM provider 設定；空字串一律回落預設值
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
AI_PROVIDER = os.getenv("AI_PROVIDER") or "openai"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or ""
GEMINI_API_KEYS = [
    key.strip()
    for key in (os.getenv("GEMINI_API_KEYS") or "").split(",")
    if key.strip()
]
GEMINI_BASE_URL = (
    os.getenv("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta"
).rstrip("/")
# Gemini 模型集中由 GEMINI_MODEL 控制
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"

# 生成逾時時間，避免較慢的模型回應被過早切斷
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
ANALYSIS_PROVIDER = os.getenv("ANALYSIS_PROVIDER") or "keyword"
_gemini_key_index = 0

MODERATION_SYSTEM_PROMPT = (
    "你是校園地圖公告板的內容審核員。判斷使用者發布的事件是否為垃圾訊息："
    "商業廣告、詐騙、釣魚連結、辱罵人身攻擊、與校園生活無關的行銷內容都算垃圾。"
    "正常的校園生活資訊（空位、遺失物、活動、交通、突發事件）不是垃圾。"
    '只回覆 JSON：{"spam": true 或 false, "score": 0.0 到 1.0 的垃圾信心分數, "reason": "簡短繁體中文原因"}'
)

ANALYSIS_SYSTEM_PROMPT = (
    "你是校園安全事件整理助手。請把使用者的自然語言描述整理成結構化事件資料。\n"
    "原則：\n"
    "1. 客觀求證與常理推論：不可憑空捏造未提及的具體人名、電話或精確時間。"
    "但若描述涉及反常、誇張或非典型現象（例如天上飛的動物、不明飛行物），"
    "請在 summary 結合常理提出合理研判（例如：疑似造形氣球、風箏、空拍機、視錯覺或惡作劇），並給出相對應的信心度。\n"
    "2. 分級安全建議（advice）：\n"
    "   - 若涉及真實人身安全、跟蹤、暴力、火警或立即危險，必須強烈建議前往人多有工作人員處避難並提供緊急聯絡資訊。\n"
    "   - 若為非典型、疑似誤報、日常或活動事件，請提供實務查證建議（例如：請保持冷靜觀察、注意周遭環境、切勿驚慌圍觀造成推擠、必要時向校安中心或站務人員反映確認）。\n"
    "3. suggested_severity 僅為建議程度，不代表已定案犯罪。\n"
    "只回覆 JSON，欄位必須是："
    "category（suspected_stalking/safety/traffic/lost_found/activity/space/food/construction/other）、"
    "suggested_severity（info/warning/danger/urgent）、summary、incident_facts（字串陣列）、"
    "advice（字串陣列）、emergency_contacts（字串陣列）、report_summary、confidence（0 到 1）。"
)

app = FastAPI(title="realtime_map_notice AI Service", version="0.1.0")
configure_cors(app)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {
        "status": "ok",
        "provider": MODERATION_PROVIDER,
        "ai_provider": AI_PROVIDER,
        "analysis_provider": ANALYSIS_PROVIDER,
        "model": GEMINI_MODEL if AI_PROVIDER == "gemini" else OPENAI_MODEL,
    }


@app.get("/healthz/llm")
async def llm_healthz() -> dict[str, object]:
    """實際測試目前設定的 LLM provider 是否可呼叫。"""
    if AI_PROVIDER == "gemini" and not _gemini_keys():
        return {"status": "not_configured", "provider": "gemini"}
    if AI_PROVIDER != "gemini" and not OPENAI_API_KEY:
        return {"status": "not_configured", "provider": AI_PROVIDER}

    try:
        await _request_llm_json(
            "你是連線測試助手，只回覆 JSON。",
            '{"ping":"ok"}',
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        logger.warning("LLM health check failed: %s", error)
        return {
            "status": "unavailable",
            "provider": AI_PROVIDER,
            "message": "LLM 連線或回應格式檢查失敗",
        }

    model = GEMINI_MODEL if AI_PROVIDER == "gemini" else OPENAI_MODEL
    return {"status": "connected", "provider": AI_PROVIDER, "model": model}


def _keyword_moderate(payload: ModerationRequest) -> ModerationResponse:
    text = f"{payload.title}\n{payload.message}".lower()
    for keyword in MODERATION_BLOCKED_KEYWORDS:
        if keyword.lower() in text:
            return ModerationResponse(
                verdict="spam",
                score=1.0,
                provider="keyword",
                reason=f"內容包含封鎖關鍵字「{keyword}」",
            )
    return ModerationResponse(verdict="ok", score=0.0, provider="keyword", reason="未命中關鍵字")


def _extract_json(text: str) -> dict:
    """容錯解析 LLM 輸出：剝掉 markdown code fence 後取第一個 JSON 物件。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in LLM response")
    return json.loads(cleaned[start : end + 1])


def _gemini_keys() -> list[str]:
    """Return configured keys, keeping GEMINI_API_KEY as a compatibility fallback."""
    return GEMINI_API_KEYS or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])


def _next_gemini_key() -> str:
    global _gemini_key_index
    keys = _gemini_keys()
    if not keys:
        raise ValueError("GEMINI_API_KEY 或 GEMINI_API_KEYS 未設定")
    key = keys[_gemini_key_index % len(keys)]
    _gemini_key_index += 1
    return key


async def _request_llm_json(system_prompt: str, user_content: str) -> dict:
    """呼叫 OpenAI 相容 API 或 Gemini，並統一回傳 JSON 物件。"""
    if AI_PROVIDER == "gemini":
        url = f"{GEMINI_BASE_URL.rstrip('/')}/models/{GEMINI_MODEL}:generateContent"
        request = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
            },
        }
        keys = _gemini_keys()
        if not keys:
            raise ValueError("GEMINI_API_KEY 或 GEMINI_API_KEYS 未設定")

        last_error: httpx.HTTPStatusError | None = None
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
            for attempt in range(len(keys)):
                key = _next_gemini_key()
                response = await client.post(
                    url,
                    headers={"x-goog-api-key": key},
                    json=request,
                )
                if response.status_code in (403, 429) and attempt < len(keys) - 1:
                    logger.warning(
                        "Gemini key rejected with status %s; trying another configured key",
                        response.status_code,
                    )
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as error:
                    last_error = error
                    break
                content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                return _extract_json(content)
        if last_error is not None:
            raise last_error
        raise ValueError("Gemini request failed")

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY 未設定")

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return _extract_json(content)


def _keyword_analyze(payload: EventAnalysisRequest) -> EventAnalysisResponse:
    text = f"{payload.title}\n{payload.message}".lower()
    if any(word in text for word in ("跟蹤", "尾隨", "一直跟著", "stalking")):
        category = "suspected_stalking"
        suggested_severity = "urgent"
        summary = "使用者描述疑似遭到陌生人跟蹤或尾隨。"
        advice = ["前往人多且有工作人員的地方", "聯絡可信任的緊急聯絡人"]
        contacts = ["110"]
    elif any(word in text for word in ("受傷", "危險", "攻擊", "救命", "火災")):
        category = "safety"
        suggested_severity = "urgent"
        summary = "使用者描述可能涉及人身安全或緊急危險。"
        advice = ["先移動到安全且有人員協助的地方", "如有立即危險請聯絡緊急服務"]
        contacts = ["110", "119"]
    else:
        category = "other"
        suggested_severity = payload.severity
        summary = payload.title
        advice = []
        contacts = []

    facts = [payload.message]
    location = payload.location_label or (
        f"座標 {payload.latitude}, {payload.longitude}"
        if payload.latitude is not None and payload.longitude is not None
        else "地點未提供"
    )
    report_summary = f"事件類型：{category}\n地點：{location}\n事件經過：\n- {payload.message}"
    return EventAnalysisResponse(
        category=category,
        suggested_severity=suggested_severity,
        summary=summary,
        incident_facts=facts,
        advice=advice,
        emergency_contacts=contacts,
        report_summary=report_summary,
        confidence=0.75 if category != "other" else 0.2,
        provider="keyword",
    )


async def _llm_analyze(payload: EventAnalysisRequest) -> EventAnalysisResponse:
    if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        return _keyword_analyze(payload).model_copy(
            update={"provider": "keyword-fallback"}
        )
    if AI_PROVIDER == "gemini" and not _gemini_keys():
        return _keyword_analyze(payload).model_copy(
            update={"provider": "keyword-fallback"}
        )

    context = [f"標題：{payload.title}", f"內容：{payload.message}"]
    if payload.location_label:
        context.append(f"使用者提供的地點名稱：{payload.location_label}")
    if payload.latitude is not None and payload.longitude is not None:
        context.append(f"座標：{payload.latitude}, {payload.longitude}")
    if payload.occurred_at:
        context.append(f"使用者提供的發生時間：{payload.occurred_at.isoformat()}")

    try:
        result = await _request_llm_json(
            ANALYSIS_SYSTEM_PROMPT,
            "\n".join(context),
        )
        return EventAnalysisResponse.model_validate({**result, "provider": "llm"})
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
        logger.warning("LLM event analysis failed (keyword fallback): %s", e)
        return _keyword_analyze(payload).model_copy(
            update={"provider": "keyword-fallback"}
        )


async def _llm_moderate(payload: ModerationRequest) -> ModerationResponse:
    if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        # 沒設定金鑰時視同停用，不讓每次發布都白等一輪錯誤
        return ModerationResponse(
            verdict="ok", score=0.0, provider="llm", reason="OPENAI_API_KEY 未設定，審核停用"
        )
    if AI_PROVIDER == "gemini" and not _gemini_keys():
        return ModerationResponse(
            verdict="ok",
            score=0.0,
            provider="llm",
            reason="GEMINI_API_KEY 或 GEMINI_API_KEYS 未設定，審核停用",
        )

    try:
        result = await _request_llm_json(
            MODERATION_SYSTEM_PROMPT,
            f"標題：{payload.title}\n內容：{payload.message}",
        )
        return ModerationResponse(
            verdict="spam" if result.get("spam") else "ok",
            score=float(result.get("score", 0.0)),
            provider="llm",
            reason=str(result.get("reason", "")),
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
        logger.warning("LLM moderation failed (fail-open): %s", e)
        return ModerationResponse(
            verdict="ok", score=0.0, provider="llm", reason="AI 審核暫時不可用，放行"
        )


@app.post("/moderate", response_model=ModerationResponse)
async def moderate(payload: ModerationRequest) -> ModerationResponse:
    if MODERATION_PROVIDER == "off":
        return ModerationResponse(verdict="ok", score=0.0, provider="off", reason="審核停用")
    if MODERATION_PROVIDER == "llm":
        return await _llm_moderate(payload)
    return _keyword_moderate(payload)


@app.post("/analyze-event", response_model=EventAnalysisResponse)
async def analyze_event(payload: EventAnalysisRequest) -> EventAnalysisResponse:
    if ANALYSIS_PROVIDER == "llm":
        return await _llm_analyze(payload)
    return _keyword_analyze(payload)

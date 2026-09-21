"""AI 服務：事件內容審核（垃圾訊息偵測）。

Event Service 在建立事件前會呼叫 POST /moderate，判斷內容是否為垃圾訊息。
與 event-service 的行為式過濾（antispam.py）互補：
- antispam 擋「行為」（洗頻、重複貼文）
- ai-service 擋「內容」（廣告、詐騙、辱罵等每則內容都不同的垃圾）

審核 provider 用環境變數 MODERATION_PROVIDER 切換：
- off：停用，一律放行
- keyword：本機關鍵字比對（不需 API key，Demo/離線用）
- llm：呼叫 OpenAI 相容 API 的 chat completion 做語意判斷

任何內部錯誤都回覆 verdict=ok（fail-open），審核服務故障不應拖垮發布功能。
"""

import json
import logging
import os

import httpx
from fastapi import FastAPI

from backend.shared.cors import configure_cors
from backend.shared.schemas import ModerationRequest, ModerationResponse

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
# llm provider 設定（OpenAI 相容 API）；空字串一律回落預設值
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))

MODERATION_SYSTEM_PROMPT = (
    "你是校園地圖公告板的內容審核員。判斷使用者發布的事件是否為垃圾訊息："
    "商業廣告、詐騙、釣魚連結、辱罵人身攻擊、與校園生活無關的行銷內容都算垃圾。"
    "正常的校園生活資訊（空位、遺失物、活動、交通、突發事件）不是垃圾。"
    '只回覆 JSON：{"spam": true 或 false, "score": 0.0 到 1.0 的垃圾信心分數, "reason": "簡短繁體中文原因"}'
)

app = FastAPI(title="realtime_map_notice AI Service", version="0.1.0")
configure_cors(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "provider": MODERATION_PROVIDER}


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


async def _llm_moderate(payload: ModerationRequest) -> ModerationResponse:
    if not OPENAI_API_KEY:
        # 沒設定金鑰時視同停用，不讓每次發布都白等一輪錯誤
        return ModerationResponse(
            verdict="ok", score=0.0, provider="llm", reason="OPENAI_API_KEY 未設定，審核停用"
        )

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": MODERATION_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"標題：{payload.title}\n內容：{payload.message}",
                        },
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

        result = _extract_json(content)
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

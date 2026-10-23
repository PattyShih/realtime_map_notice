import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel
from redis.exceptions import RedisError

from backend.shared.antispam import EventAntiSpam
from backend.shared.campus import resolve_campus_location
from backend.shared.cors import configure_cors
from backend.shared.jwt_auth import create_token, verify_token
from backend.shared.redis_client import create_redis
from backend.shared.schemas import (
    EventAnalysisResponse,
    EventEvaluationResponse,
    EventCreate,
    EventResponse,
    EventUpdate,
)

NOTIFICATION_SERVICE_URL = os.getenv(
    "NOTIFICATION_SERVICE_URL",
    "http://localhost:8003",
)
# 校外事件的路段名稱：Nominatim 逆向地理編碼（免費，需標示 User-Agent）
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
AI_SERVICE_URL = os.getenv(
    "AI_SERVICE_URL",
    "http://localhost:8004",
)
# Must exceed the AI service's default 30-second LLM timeout so a slow model
# can still return its keyword fallback instead of being dropped here.
AI_ANALYSIS_TIMEOUT_SECONDS = float(
    os.getenv("AI_ANALYSIS_TIMEOUT_SECONDS", "35")
)
# Google 登入：後端必須用同一個 Client ID 驗證 ID token 的 audience
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
# 內部服務金鑰：ops 儀表板的事件模擬器等機器端不經 Google 登入，
# 改帶 X-Internal-Key 直通行（未設定金鑰時此通道關閉，一律走 JWT）
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

EVENT_LOCATION_KEY = "event_locations"

logger = logging.getLogger(__name__)


async def moderate_event_content(title: str, message: str) -> None:
    """送 AI Service 審核內容；判定垃圾訊息時 raise 422。

    與 antispam 互補：antispam 擋行為（洗頻、重複），AI 擋內容（廣告、辱罵）。
    此為舊版相容 helper；目前建立與編輯事件使用 evaluate_event_content，
    審核服務不可用時會 fail-closed，避免未審核內容發布。
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{AI_SERVICE_URL}/moderate",
                json={"title": title, "message": message},
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"⚠️ moderation unavailable (event allowed): {e}")
        return

    if result.get("verdict") == "spam":
        reason = result.get("reason") or "內容疑似垃圾訊息"
        raise HTTPException(
            status_code=422,
            detail=f"內容未通過審核：{reason}",
        )


async def analyze_event_content(
    title: str,
    message: str,
    severity: str,
    latitude: float,
    longitude: float,
) -> dict | None:
    """取得事件分析；AI 故障時回傳空值，不阻擋事件發布。"""
    try:
        async with httpx.AsyncClient(timeout=AI_ANALYSIS_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{AI_SERVICE_URL}/analyze-event",
                json={
                    "title": title,
                    "message": message,
                    "severity": severity,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )
            response.raise_for_status()
            return EventAnalysisResponse.model_validate(response.json()).model_dump(mode="json")
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("event analysis unavailable (event allowed): %s", e)
        return None


async def evaluate_event_content(
    title: str,
    message: str,
    severity: str,
    latitude: float,
    longitude: float,
) -> dict:
    """一次完成發布審核與事件分析；拒絕非事件內容。"""
    try:
        async with httpx.AsyncClient(timeout=AI_ANALYSIS_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{AI_SERVICE_URL}/evaluate-event",
                json={
                    "title": title,
                    "message": message,
                    "severity": severity,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )
            if response.status_code >= 400:
                logger.error(
                    "event evaluation service returned %s: %s",
                    response.status_code,
                    getattr(response, "text", "")[:500],
                )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.error("event evaluation unavailable (event rejected): %s", e)
        raise HTTPException(
            status_code=503,
            detail="事件審核服務目前無法使用，請稍後再試",
        ) from e

    if result.get("verdict") == "spam":
        reason = result.get("reason") or "內容未通過審核"
        raise HTTPException(status_code=422, detail=f"內容未通過審核：{reason}")

    if "decision" not in result:
        logger.error("event evaluation response missing decision")
        raise HTTPException(status_code=503, detail="事件審核結果無效，請稍後再試")

    if result["decision"] == "reject":
        raise HTTPException(
            status_code=422,
            detail=f"內容未通過審核：{result.get('reason') or '這不是一則事件內容'}",
        )

    try:
        return EventEvaluationResponse.model_validate(result).analysis.model_dump(
            mode="json"
        )
    except ValueError as e:
        logger.error("invalid event evaluation response: %s", e)
        raise HTTPException(status_code=503, detail="事件審核結果無效，請稍後再試") from e


async def resolve_road_name(latitude: float, longitude: float) -> str | None:
    """校外事件的路段名稱（如「縣政二路」）；純加值資訊，失敗一律靜默回 None。"""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "format": "json",
                    "lat": latitude,
                    "lon": longitude,
                    "zoom": 17,
                    "addressdetails": 1,
                },
                headers={"User-Agent": "realtime-map-notice/1.0 (campus event map)"},
            )
            response.raise_for_status()
            return (response.json().get("address") or {}).get("road") or None
    except Exception as e:
        logger.warning("road name lookup failed (event allowed): %s", e)
        return None


async def broadcast_to_notification_service(broadcast_payload: dict) -> dict:
    """Stage 5：推播統一走 Notification Service 的 /broadcast/nearby。

    event-service 只負責事件建立與單次 HTTP 呼叫；GEO 比對、離線過濾與
    批次發布全部由 Notification Service 處理。通知服務暫時不可用時，
    事件仍會成功建立（已先存 Redis），只是推播統計歸零。
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{NOTIFICATION_SERVICE_URL}/broadcast/nearby",
                json=broadcast_payload,
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"⚠️ broadcast failed (event still created): {e}")
        return {}

app = FastAPI(title="realtime_map_notice Event Service", version="0.1.0")
configure_cors(app)
redis = create_redis()
antispam = EventAntiSpam(redis)


# ==========================================
# 登入與身分驗證（Google OAuth 2.0 + 自行核發 JWT）
# ==========================================
class GoogleAuthRequest(BaseModel):
    """前端 Google Identity Services 按鈕回傳的 ID token（credential）"""
    credential: str


def _verify_google_credential(credential: str) -> dict:
    """用 Google 公開金鑰驗證 ID token，成功回傳使用者資訊（sub/email/name/picture）。

    google-auth 套件採延遲載入：未安裝或未設定 Client ID 時回 503，
    不影響其他不需要登入的功能（地圖瀏覽、健康檢查）。
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_oauth2_token(
        credential,
        google_requests.Request(),
        GOOGLE_CLIENT_ID,
    )


@dataclass
class Actor:
    """通過身分驗證的呼叫者：人類走 JWT，機器（事件模擬器）走內部金鑰"""
    user_id: str = ""  # 內部金鑰通道為空字串：user_id 由各端點自行從 body/query 取
    name: str = ""
    email: str = ""
    via: str = "jwt"  # "jwt" | "internal"


def require_actor(
    authorization: str | None = Header(default=None),
    x_internal_key: str | None = Header(default=None),
) -> Actor:
    """寫入/編輯/刪除事件的統一身分檢查：

    - ``Authorization: Bearer <jwt>``：一般使用者，user_id 一律以 token 內容為準
      （前端送什麼 user_id 都會被覆蓋，無法冒用別人發布）
    - ``X-Internal-Key``：ops 儀表板的事件模擬器，金鑰相符即放行
    - 兩者皆無或無效：401，前端會顯示「請先登入」
    """
    if x_internal_key:
        if INTERNAL_API_KEY and secrets.compare_digest(x_internal_key, INTERNAL_API_KEY):
            return Actor(via="internal")
        raise HTTPException(status_code=401, detail="內部金鑰不正確")

    if authorization and authorization.startswith("Bearer "):
        payload = verify_token(authorization[len("Bearer "):])
        if payload is None:
            raise HTTPException(status_code=401, detail="登入憑證無效或已過期，請重新登入")
        return Actor(
            user_id=payload["sub"],
            name=payload.get("name", ""),
            email=payload.get("email", ""),
            via="jwt",
        )

    raise HTTPException(status_code=401, detail="請先登入後再發布或編輯事件")


@app.post("/auth/google")
async def google_login(payload: GoogleAuthRequest) -> dict[str, object]:
    """驗證 Google ID token → 建立/更新使用者資料 → 核發系統 JWT。"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="伺服器尚未設定 GOOGLE_CLIENT_ID，請管理員設定")

    try:
        info = _verify_google_credential(payload.credential)
    except ImportError as e:
        raise HTTPException(status_code=503, detail="伺服器未安裝 google-auth 套件") from e
    except ValueError as e:
        logger.warning("Google token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Google 登入驗證失敗，請重新登入") from e

    # Google 帳號的 sub 是終身唯一識別碼；加前綴避免與舊的隨機 user_id 撞名
    user_id = f"g_{info['sub']}"
    profile = {
        "name": info.get("name", ""),
        "email": info.get("email", ""),
        "picture": info.get("picture", ""),
    }

    # 使用者資料寫入 Redis 方便日後查詢；寫入失敗不擋登入（token 已可獨立驗證）
    try:
        await redis.hset(
            f"user:{user_id}",
            mapping={**profile, "last_login": datetime.now(timezone.utc).isoformat()},
        )
    except RedisError as e:
        logger.warning("User profile write failed (login continues): %s", e)

    token = create_token(user_id, **profile)
    return {"token": token, "user": {"id": user_id, **profile}}


@app.get("/auth/me")
async def auth_me(actor: Actor = Depends(require_actor)) -> dict[str, object]:
    """回傳目前登入者資訊；前端用它確認本地 token 仍然有效。"""
    return {
        "user_id": actor.user_id,
        "name": actor.name,
        "email": actor.email,
        "via": actor.via,
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    try:
        await redis.ping()
    except RedisError as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e
    return {"status": "ok"}

@app.get("/events", response_model=list[EventResponse])
async def get_events(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    # 上限 500000（500 公里）涵蓋全台：地圖是佈告欄，所有發布都看得到
    radius: int = Query(3000, ge=1, le=500000),
):
    try:
        event_ids = await redis.geosearch(
            EVENT_LOCATION_KEY,
            longitude=longitude,
            latitude=latitude,
            radius=radius,
            unit="m",
        )
    except RedisError as e:
        logger.error("Event lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    if not event_ids:
        return []

    pipe = redis.pipeline(transaction=False)

    for event_id in event_ids:
        pipe.get(f"event:{event_id}")

    try:
        event_data_list = await pipe.execute()
    except RedisError as e:
        logger.error("Event data lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    events = []
    expired_events = []

    for event_id, event_data in zip(event_ids, event_data_list):
        # Redis TTL 到期，event 不存在
        if event_data is None:
            expired_events.append(event_id)
            continue

        try:
            event = json.loads(event_data)
            events.append(
                EventResponse(
                    event_id=event_id,
                    title=event["title"],
                    message=event["message"],
                    severity=event["severity"],
                    latitude=event["latitude"],
                    longitude=event["longitude"],
                    radius_meters=event["radius_meters"],
                    created_at=event["created_at"],
                    duration_minutes=event.get("duration_minutes", 60),
                    image_url=event.get("image_url"),
                    user_id=event.get("user_id", ""),
                    location_label=event.get("location_label"),
                    analysis=event.get("analysis"),
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            expired_events.append(event_id)
            continue

    # 清掉已過期的 GEO 資料
    if expired_events:
        try:
            await redis.zrem(
                EVENT_LOCATION_KEY,
                *expired_events,
            )
        except RedisError as e:
            logger.error("Expired event cleanup failed: %s", e)
            raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    return events

async def _load_owned_event(event_id: str, user_id: str) -> dict:
    """載入事件並驗證操作者是發布者；不存在回 404、非發布者回 403。"""
    try:
        raw = await redis.get(f"event:{event_id}")
    except RedisError as e:
        logger.error("Event lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    if raw is None:
        raise HTTPException(status_code=404, detail="事件不存在或已過期")

    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Invalid event data for %s: %s", event_id, e)
        raise HTTPException(status_code=503, detail="Event data unavailable") from e

    if not isinstance(event, dict):
        logger.error("Invalid event data for %s: expected object", event_id)
        raise HTTPException(status_code=503, detail="Event data unavailable")

    if event.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="只有發布者可以修改或刪除這則事件")
    return event


@app.post("/events/{event_id}/analysis", response_model=EventAnalysisResponse)
async def analyze_existing_event(
    event_id: str,
    actor: Actor = Depends(require_actor),
) -> EventAnalysisResponse:
    """回傳發布時已保存的分析，不重新呼叫 AI。"""
    if actor.via != "jwt":
        raise HTTPException(status_code=401, detail="請使用登入帳號分析事件")

    event = await _load_owned_event(event_id, actor.user_id)
    analysis = event.get("analysis")
    if analysis is None:
        raise HTTPException(status_code=404, detail="這則事件沒有已保存的分析結果")
    try:
        return EventAnalysisResponse.model_validate(analysis)
    except ValueError as e:
        logger.error("Invalid saved analysis for %s: %s", event_id, e)
        raise HTTPException(status_code=503, detail="Event analysis unavailable") from e


@app.put("/events/{event_id}")
async def update_event(
    event_id: str,
    payload: EventUpdate,
    actor: Actor = Depends(require_actor),
) -> dict[str, object]:
    # JWT 登入者的 user_id 一律以 token 為準，body 送誰都不算數（防冒用）
    if actor.via == "jwt":
        payload.user_id = actor.user_id
    event = await _load_owned_event(event_id, payload.user_id)

    # 編輯後的內容同樣要過 AI 審核（antispam 計數不重跑：
    # 編輯不產生新事件也不推播，重複偵測對「只改幾個字」反而誤擋）
    analysis = await evaluate_event_content(
        payload.title,
        payload.message,
        payload.severity,
        event["latitude"],
        event["longitude"],
    )

    event["title"] = payload.title
    event["message"] = payload.message
    event["severity"] = payload.severity
    if analysis is not None:
        event["analysis"] = analysis

    event_key = f"event:{event_id}"
    try:
        ttl = await redis.ttl(event_key)
    except RedisError as e:
        logger.error("Event TTL lookup failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    if ttl <= 0:
        # get 與 ttl 之間剛好過期：視為不存在，避免復活死事件
        raise HTTPException(status_code=404, detail="事件不存在或已過期")

    try:
        await redis.set(event_key, json.dumps(event), ex=ttl)
    except RedisError as e:
        logger.error("Event update failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    return {"status": "updated", "event_id": event_id}


@app.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    user_id: str = Query(..., min_length=1, max_length=64),
    actor: Actor = Depends(require_actor),
) -> dict[str, object]:
    # JWT 登入者的 user_id 一律以 token 為準，query 參數送誰都不算數（防冒用）
    effective_user_id = actor.user_id or user_id
    await _load_owned_event(event_id, effective_user_id)

    try:
        await redis.delete(f"event:{event_id}")
        await redis.zrem(EVENT_LOCATION_KEY, event_id)
    except RedisError as e:
        logger.error("Event delete failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    return {"status": "deleted", "event_id": event_id}


@app.post("/events")
async def create_event(
    payload: EventCreate,
    actor: Actor = Depends(require_actor),
) -> dict[str, object]:
    # JWT 登入者的 user_id 一律以 token 為準，body 送誰都不算數（防冒用）；
    # 內部金鑰通道（事件模擬器）沿用 body 的 user_id
    if actor.via == "jwt":
        payload.user_id = actor.user_id

    event_id = str(uuid4())

    # 先完成 AI 內容審核；被拒絕或審核服務不可用時，不應留下 antispam 登記。
    analysis = await evaluate_event_content(
        payload.title,
        payload.message,
        payload.severity,
        payload.latitude,
        payload.longitude,
    )

    # AI 通過後才登記反垃圾訊息，避免被拒絕的內容佔用活躍事件額度。
    await antispam.check_and_register(
        payload.user_id,
        payload.title,
        payload.message,
        event_id,
        payload.duration_minutes,
    )

    event_data = payload.model_dump()
    event_data["created_at"] = datetime.now(timezone.utc).isoformat()
    if analysis is not None:
        event_data["analysis"] = analysis
    # 教授建議：輔大範圍內的座標自動判別地標（哪一棟大樓／區域），
    # 隨事件與通知送出——緊急時只打「火警」兩個字，大家也知道在哪一棟
    location_label = resolve_campus_location(payload.latitude, payload.longitude)
    if location_label is None:
        # 校外事件：改顯示路段名稱（如「縣政二路」），查不到則不顯示
        location_label = await resolve_road_name(payload.latitude, payload.longitude)
    if location_label:
        event_data["location_label"] = location_label

    try:
        await redis.set(
            f"event:{event_id}",
            json.dumps(event_data),
            ex=max(1, int(payload.duration_minutes * 60)),
        )

        await redis.geoadd(
            EVENT_LOCATION_KEY,
            (
                payload.longitude,
                payload.latitude,
                event_id,
            ),
        )
    except RedisError as e:
        logger.error("Event storage failed: %s", e)
        raise HTTPException(status_code=503, detail="Event storage unavailable") from e

    # Stage 5：推播統一走 Notification Service，只發一次 HTTP 呼叫
    broadcast_stats = await broadcast_to_notification_service(
        {
            "event_id": event_id,
            "user_id": payload.user_id,
            "title": payload.title,
            "message": payload.message,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "severity": payload.severity,
            "radius_meters": payload.radius_meters,
            "duration_minutes": payload.duration_minutes,
            "image_base64": payload.image_base64,
            "image_url": payload.image_url,
            "created_at": event_data["created_at"],
            "expires_at": (
                datetime.fromisoformat(event_data["created_at"])
                + timedelta(minutes=payload.duration_minutes)
            ).isoformat(),
            "analysis": analysis,
            "location_label": location_label,
        }
    )

    return {
        "event_id": event_id,
        "location_label": location_label,
        "analysis": analysis,
        "nearby_user_count": broadcast_stats.get("total_nearby_users", 0),
        "active_user_count": broadcast_stats.get("active_user_count", 0),
        "delivered_count": broadcast_stats.get("delivered_count", 0),
        # 維持原 API 契約：delivered_to 為 user_id 字串列表
        "delivered_to": [d.get("user_id", "") for d in broadcast_stats.get("delivered_to", [])][:20],
    }

"""系統自身的 JWT 工具：登入成功後核發，各服務用同一組 JWT_SECRET 驗證。

Google 只負責「證明這個人是誰」（ID token），我們驗證後換發自己的 JWT，
之後所有 API 都只認這張 token——避免每個請求都跑去問 Google。
"""
import os
from datetime import datetime, timedelta, timezone

import jwt

# 未設定 JWT_SECRET 時的本地開發預設值；正式環境（Render/K8s）一定要覆寫
DEV_INSECURE_SECRET = "dev-insecure-secret-change-me"
TOKEN_EXPIRE_HOURS = 24


def get_jwt_secret() -> str:
    # 每次呼叫時讀取環境變數：測試可透過 monkeypatch.setenv 動態替換
    return os.getenv("JWT_SECRET") or DEV_INSECURE_SECRET


def create_token(user_id: str, name: str = "", email: str = "", picture: str = "") -> str:
    """核發一張 24 小時有效的 JWT，payload 帶使用者基本資料。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "name": name,
        "email": email,
        "picture": picture,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """驗證 JWT；通過回傳 payload，無效或過期回傳 None（不拋例外）。"""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if not payload.get("sub"):
        return None
    return payload

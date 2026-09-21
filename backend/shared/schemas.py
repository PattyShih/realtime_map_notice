from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LocationUpdate(BaseModel):
    user_id: str = Field(..., examples=["u-0001"])
    latitude: float = Field(..., ge=-90, le=90, examples=[25.0173])
    longitude: float = Field(..., ge=-180, le=180, examples=[121.5397])


class EventCreate(BaseModel):
    # 反垃圾訊息：事件必須帶發布者身份，頻率限制與重複偵測都以 user_id 為依據
    user_id: str = Field(..., min_length=1, max_length=64, examples=["u-0001"])
    title: str = Field(..., min_length=1, max_length=100, examples=["Library 3F has seats"])
    message: str = Field(..., min_length=1, max_length=1000, examples=["About 10 seats near the windows."])
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: Literal["info", "warning", "danger", "urgent"] = Field(
        "info",
        examples=["info", "warning", "danger", "urgent"],
    )
    radius_meters: int = Field(500, ge=50, le=3000)
     # 新增：事件存在時間（分鐘）
    duration_minutes: int = Field(60, ge=1, le=1440, examples=[30, 60, 1440])

    # 新增：圖片 Base64 字串
    image_base64: str | None = Field(None, description="現場照片 Base64 字串", max_length=2_000_000)
    image_url: str | None = Field(None, description="現場照片 URL 或 Base64 字串", max_length=2_000_000)


class EventUpdate(BaseModel):
    """事件編輯請求：僅開放文字內容修改，地點與時效維持原值"""
    user_id: str = Field(..., min_length=1, max_length=64, description="發布者身份，用於驗證編輯權限")
    title: str = Field(..., min_length=1, max_length=100, examples=["Library 3F has seats"])
    message: str = Field(..., min_length=1, max_length=1000, examples=["About 10 seats near the windows."])
    severity: Literal["info", "warning", "danger", "urgent"] = Field(
        "info",
        examples=["info", "warning", "danger", "urgent"],
    )


class EventNotification(BaseModel):
    event_id: str
    user_id: str = ""  # 發布者身份，前端用它顯示「自己的事件」編輯/刪除按鈕
    title: str
    message: str
    latitude: float
    longitude: float
    severity: str
    distance_meters: float | None = None
    duration_minutes: int = 60
    # 新增：通知時保留圖片
    image_base64: str | None = None
    image_url: str | None = None


class EventResponse(BaseModel):
    event_id: str
    title: str
    message: str
    severity: str
    latitude: float
    longitude: float
    radius_meters: int
    created_at: datetime
    duration_minutes: int = 60
    image_url: str | None = None
    # 舊事件資料沒有 user_id，預設空字串以維持向下相容
    user_id: str = ""


class ModerationRequest(BaseModel):
    """AI 服務內容審核請求"""
    title: str
    message: str


class ModerationResponse(BaseModel):
    """AI 服務內容審核結果：verdict=spam 表示判定為垃圾訊息"""
    verdict: Literal["ok", "spam"]
    score: float = Field(0.0, ge=0.0, le=1.0)
    provider: str = "unknown"
    reason: str = ""


class NearbyBroadcast(BaseModel):
    """廣播事件給附近使用者的請求"""
    event_id: str
    user_id: str = ""  # 發布者身份，隨通知轉發給前端
    title: str
    message: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: Literal["info", "warning", "danger", "urgent"] = Field(
        "info",
        examples=["info", "warning", "danger", "urgent"],
    )
    radius_meters: int = Field(500, ge=50, le=3000, description="通知範圍（公尺）")
    # 如果廣播也需要帶圖片，可以用
    image_base64: str | None = None
    image_url: str | None = None
    # 暫定60分鐘，之後可以調整
    duration_minutes: int = Field(60, ge=1, le=1440)


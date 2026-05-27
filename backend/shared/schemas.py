from typing import Literal

from pydantic import BaseModel, Field


class LocationUpdate(BaseModel):
    user_id: str = Field(..., examples=["u-0001"])
    latitude: float = Field(..., ge=-90, le=90, examples=[25.0173])
    longitude: float = Field(..., ge=-180, le=180, examples=[121.5397])


class EventCreate(BaseModel):
    client_event_id: str | None = Field(
        None,
        examples=["client-generated-uuid"],
    )
    title: str = Field(..., examples=["圖書館 3 樓有空位"])
    message: str = Field(..., examples=["靠窗大約還有 10 個座位"])
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: Literal["info", "urgent"] = Field("info", examples=["info", "urgent"])
    radius_meters: int = Field(500, ge=50, le=3000)
    expires_in: int = Field(30, ge=5, le=1440, description="有效期限（分鐘）")


class EventNotification(BaseModel):
    event_id: str
    title: str
    message: str
    latitude: float
    longitude: float
    severity: Literal["info", "urgent"]
    distance_meters: float | None = None


class EventRecord(BaseModel):
    """持久化的事件記錄，用於歷史查詢"""
    event_id: str
    title: str
    message: str
    latitude: float
    longitude: float
    severity: Literal["info", "urgent"]
    created_at: str
    expires_at: str | None = None

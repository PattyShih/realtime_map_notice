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
    title: str = Field(..., examples=["Library 3F has seats"])
    message: str = Field(..., examples=["About 10 seats near the windows."])
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: Literal["info", "urgent"] = Field("info", examples=["info", "urgent"])
    radius_meters: int = Field(500, ge=50, le=3000)


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

from pydantic import BaseModel, Field


class LocationUpdate(BaseModel):
    user_id: str = Field(..., examples=["u-0001"])
    latitude: float = Field(..., ge=-90, le=90, examples=[25.0173])
    longitude: float = Field(..., ge=-180, le=180, examples=[121.5397])


class EventCreate(BaseModel):
    title: str = Field(..., examples=["Library 3F has seats"])
    message: str = Field(..., examples=["About 10 seats near the windows."])
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: str = Field("info", examples=["info", "urgent"])
    radius_meters: int = Field(500, ge=50, le=3000)


class EventNotification(BaseModel):
    event_id: str
    title: str
    message: str
    latitude: float
    longitude: float
    severity: str
    distance_meters: float | None = None


class NearbyBroadcast(BaseModel):
    """廣播事件給附近使用者的請求"""
    event_id: str
    title: str
    message: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    severity: str = Field("info", examples=["info", "warning", "urgent"])
    radius_meters: int = Field(500, ge=50, le=3000, description="通知範圍（公尺）")


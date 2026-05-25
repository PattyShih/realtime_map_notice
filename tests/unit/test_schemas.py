import pytest
from pydantic import ValidationError

from backend.shared.schemas import EventCreate, EventNotification, LocationUpdate


def test_location_update_valid() -> None:
    payload = LocationUpdate(
        user_id="u-0001",
        latitude=25.0173,
        longitude=121.5397,
    )

    assert payload.user_id == "u-0001"
    assert payload.latitude == 25.0173
    assert payload.longitude == 121.5397


def test_location_update_invalid_latitude() -> None:
    with pytest.raises(ValidationError):
        LocationUpdate(user_id="u-0001", latitude=91, longitude=121.5397)


def test_location_update_invalid_longitude() -> None:
    with pytest.raises(ValidationError):
        LocationUpdate(user_id="u-0001", latitude=25.0173, longitude=181)


def test_event_create_defaults_to_info_and_500m_radius() -> None:
    payload = EventCreate(
        title="Library seats",
        message="3F has seats near windows",
        latitude=25.0173,
        longitude=121.5397,
    )

    assert payload.severity == "info"
    assert payload.radius_meters == 500


def test_event_create_rejects_too_small_radius() -> None:
    with pytest.raises(ValidationError):
        EventCreate(
            title="Library seats",
            message="3F has seats near windows",
            latitude=25.0173,
            longitude=121.5397,
            radius_meters=49,
        )


def test_event_create_rejects_too_large_radius() -> None:
    with pytest.raises(ValidationError):
        EventCreate(
            title="Library seats",
            message="3F has seats near windows",
            latitude=25.0173,
            longitude=121.5397,
            radius_meters=3001,
        )


def test_event_notification_accepts_optional_distance() -> None:
    payload = EventNotification(
        event_id="evt-1",
        title="Urgent notice",
        message="Road blocked near library",
        latitude=25.0173,
        longitude=121.5397,
        severity="urgent",
    )

    assert payload.distance_meters is None

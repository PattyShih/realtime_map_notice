import logging
from datetime import UTC, datetime

from fastapi import FastAPI

from backend.shared.config import (
    USER_LAST_SEEN_PREFIX,
    USER_LOCATION_KEY,
    logger,
)
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import LocationUpdate

app = FastAPI(title="realtime_map_notice Location Service", version="0.1.0")
configure_cors(app)
redis = create_redis()

log = logging.getLogger(__name__)


async def filter_active_users(user_ids: list[str]) -> list[str]:
    if not user_ids:
        return []

    last_seen_values = await redis.mget(
        [f"{USER_LAST_SEEN_PREFIX}:{user_id}" for user_id in user_ids],
    )
    return [
        user_id
        for user_id, last_seen in zip(user_ids, last_seen_values)
        if last_seen is not None
    ]


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    try:
        await redis.ping()
        return {"status": "ok"}
    except Exception:
        log.exception("healthz: Redis ping failed")
        raise


@app.post("/locations")
async def update_location(payload: LocationUpdate) -> dict[str, str]:
    log.info("location.update user=%s lat=%.5f lng=%.5f", payload.user_id, payload.latitude, payload.longitude)
    await redis.geoadd(
        USER_LOCATION_KEY,
        (payload.longitude, payload.latitude, payload.user_id),
    )
    await redis.set(
        f"{USER_LAST_SEEN_PREFIX}:{payload.user_id}",
        datetime.now(UTC).isoformat(),
        ex=60,
    )
    return {"status": "accepted", "user_id": payload.user_id}


@app.get("/locations/nearby")
async def nearby_users(
    latitude: float,
    longitude: float,
    radius_meters: int = 500,
) -> dict[str, list[str]]:
    users = await redis.geosearch(
        USER_LOCATION_KEY,
        longitude=longitude,
        latitude=latitude,
        radius=radius_meters,
        unit="m",
    )
    active = await filter_active_users(users)
    log.info("location.nearby lat=%.5f lng=%.5f radius=%dm total=%d active=%d",
             latitude, longitude, radius_meters, len(users), len(active))
    return {"users": active}

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Query

from backend.shared.config import GEO_CLEANUP_INTERVAL_SECONDS, LAST_SEEN_TTL_SECONDS, USER_LAST_SEEN_PREFIX, USER_LOCATION_KEY
from backend.shared.cors import configure_cors
from backend.shared.redis_client import create_redis
from backend.shared.schemas import LocationUpdate

logger = logging.getLogger(__name__)


async def cleanup_stale_locations() -> None:
    """定期清理 GEO 索引中的幽靈使用者。

    user:locations（GEO/zset）成員只進不出，壓測或長時間運行後數千個
    sim_user 會永久殘留。last_seen key 有 TTL（預設 60 秒），過期即代表
    使用者已離線，應同步從 GEO 索引移除，避免 GEOSEARCH 掃描量無限成長。
    多副本同時清理也安全：ZREM 是冪等操作。
    """
    while True:
        try:
            await asyncio.sleep(GEO_CLEANUP_INTERVAL_SECONDS)
            members = [m async for m in redis.zscan_iter(USER_LOCATION_KEY)]
            if not members:
                continue

            pipe = redis.pipeline(transaction=False)
            for member in members:
                pipe.get(f"{USER_LAST_SEEN_PREFIX}:{member}")
            last_seen_values = await pipe.execute()

            stale = [m for m, seen in zip(members, last_seen_values) if not seen]
            if stale:
                await redis.zrem(USER_LOCATION_KEY, *stale)
                logger.info(f"🧹 Cleaned {len(stale)} stale GEO entries (remain {len(members) - len(stale)} active)")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"❌ GEO cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動背景清理任務，關閉時取消。"""
    task = asyncio.create_task(cleanup_stale_locations())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="realtime_map_notice Location Service", version="0.1.0", lifespan=lifespan)
configure_cors(app)
redis = create_redis()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    await redis.ping()
    return {"status": "ok"}


@app.post("/locations")
async def update_location(payload: LocationUpdate) -> dict[str, str]:
    await redis.geoadd(
        USER_LOCATION_KEY,
        (payload.longitude, payload.latitude, payload.user_id),
    )
    await redis.set(
        f"{USER_LAST_SEEN_PREFIX}:{payload.user_id}",
        datetime.now(UTC).isoformat(),
        ex=LAST_SEEN_TTL_SECONDS,
    )
    return {"status": "accepted", "user_id": payload.user_id}


@app.get("/locations/nearby")
async def nearby_users(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_meters: int = Query(500, ge=1, le=3000),
) -> dict[str, list[str]]:
    users = await redis.geosearch(
        USER_LOCATION_KEY,
        longitude=longitude,
        latitude=latitude,
        radius=radius_meters,
        unit="m",
    )
    return {"users": users}

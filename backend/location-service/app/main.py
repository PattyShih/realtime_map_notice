import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Query

from backend.shared.config import GEO_CLEANUP_INTERVAL_SECONDS, LAST_SEEN_TTL_SECONDS, USER_LAST_SEEN_PREFIX, USER_LOCATION_KEY
from backend.shared.cors import configure_cors
from backend.shared.push import PUSH_SUBSCRIPTIONS_PREFIX
from backend.shared.redis_client import create_redis
from backend.shared.schemas import LocationUpdate

logger = logging.getLogger(__name__)


async def cleanup_stale_locations() -> None:
    """定期清理 GEO 索引中的幽靈使用者。

    user:locations（GEO/zset）成員只進不出，壓測或長時間運行後數千個
    sim_user 會永久殘留。last_seen key 有 TTL（預設 60 秒），過期即代表
    使用者已離線，應同步從 GEO 索引移除，避免 GEOSEARCH 掃描量無限成長。

    例外：有 Web Push 訂閱的使用者不會被移除——離線推播需要他們的
    最後已知位置（last_seen 過期後 WebSocket 本來就不會再通知，
    但系統推播仍應送達）。多副本同時清理也安全：ZREM 是冪等操作。
    """
    while True:
        try:
            await asyncio.sleep(GEO_CLEANUP_INTERVAL_SECONDS)
            # zscan_iter 吐出 (member, score) tuple，取 member 即可
            members = [member async for member, _score in redis.zscan_iter(USER_LOCATION_KEY)]
            if not members:
                continue

            pipe = redis.pipeline(transaction=False)
            for member in members:
                pipe.get(f"{USER_LAST_SEEN_PREFIX}:{member}")
            last_seen_values = await pipe.execute()

            offline_candidates = [m for m, seen in zip(members, last_seen_values) if not seen]
            # 離線成員中有推播訂閱者保留最後已知位置（離線推播用），其餘移除
            pipe = redis.pipeline(transaction=False)
            for member in offline_candidates:
                pipe.exists(f"{PUSH_SUBSCRIPTIONS_PREFIX}:{member}")
            sub_flags = await pipe.execute()
            stale = [
                m for m, has_sub in zip(offline_candidates, sub_flags) if not has_sub
            ]
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


@app.get("/locations/online")
async def online_users() -> dict[str, int]:
    """目前在線使用者數（last_seen 尚未過期的 GEO 成員）。

    只統計 last_seen 還活著的成員：模擬壓測停止後，人數會隨 TTL
    （預設 60 秒）自然回落，不必等背景清理週期，demo 即時性更好。
    """
    members = [member async for member, _score in redis.zscan_iter(USER_LOCATION_KEY)]
    if not members:
        return {"online": 0}
    pipe = redis.pipeline(transaction=False)
    for member in members:
        pipe.get(f"{USER_LAST_SEEN_PREFIX}:{member}")
    last_seen_values = await pipe.execute()
    return {"online": sum(1 for seen in last_seen_values if seen)}


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

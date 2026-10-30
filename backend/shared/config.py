import os


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USER_LOCATION_KEY = os.getenv("USER_LOCATION_KEY", "realtime_map_notice:user:locations")
USER_LAST_SEEN_PREFIX = os.getenv("USER_LAST_SEEN_PREFIX", "realtime_map_notice:user:last_seen")
DEFAULT_ALERT_RADIUS_METERS = int(os.getenv("DEFAULT_ALERT_RADIUS_METERS", "500"))
LAST_SEEN_TTL_SECONDS = int(os.getenv("LAST_SEEN_TTL_SECONDS", "60"))
# Stage 5：GEO 幽靈使用者清理週期（秒）。last_seen 過期的成員會被移出 GEO 索引。
GEO_CLEANUP_INTERVAL_SECONDS = int(os.getenv("GEO_CLEANUP_INTERVAL_SECONDS", "120"))
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:3000",
    ).split(",")
    if origin.strip()
]

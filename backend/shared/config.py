import os


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USER_LOCATION_KEY = os.getenv("USER_LOCATION_KEY", "realtime_map_notice:user:locations")
USER_LAST_SEEN_PREFIX = os.getenv("USER_LAST_SEEN_PREFIX", "realtime_map_notice:user:last_seen")
DEFAULT_ALERT_RADIUS_METERS = int(os.getenv("DEFAULT_ALERT_RADIUS_METERS", "500"))
NOTIFICATION_FANOUT_CONCURRENCY = int(
    os.getenv("NOTIFICATION_FANOUT_CONCURRENCY", "100"),
)
EVENT_IDEMPOTENCY_PREFIX = os.getenv(
    "EVENT_IDEMPOTENCY_PREFIX",
    "realtime_map_notice:event:idempotency",
)
EVENT_IDEMPOTENCY_TTL_SECONDS = int(
    os.getenv("EVENT_IDEMPOTENCY_TTL_SECONDS", "300"),
)
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:3000",
    ).split(",")
    if origin.strip()
]

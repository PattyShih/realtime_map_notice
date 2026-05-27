from redis.asyncio import Redis

from .config import REDIS_URL


def create_redis() -> Redis:
    return Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        max_connections=20,
        socket_timeout=5,
        socket_connect_timeout=5,
        retry_on_timeout=True,
    )

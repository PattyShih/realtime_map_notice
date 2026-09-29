import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

PUSH_SUBSCRIPTIONS_PREFIX = "realtime_map_notice:user:push_subscriptions"
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@example.com")


def subscription_key(user_id: str) -> str:
    return f"{PUSH_SUBSCRIPTIONS_PREFIX}:{user_id}"


def push_is_configured() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY and VAPID_SUBJECT)


async def get_subscriptions(redis, user_id: str) -> list[dict[str, Any]]:
    raw = await redis.get(subscription_key(user_id))
    if not raw:
        return []

    try:
        subscriptions = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid push subscriptions for user %s", user_id)
        return []

    return subscriptions if isinstance(subscriptions, list) else []


async def register_subscription(redis, user_id: str, subscription: dict[str, Any]) -> None:
    subscriptions = await get_subscriptions(redis, user_id)
    endpoint = subscription["endpoint"]
    subscriptions = [item for item in subscriptions if item.get("endpoint") != endpoint]
    subscriptions.append(subscription)
    await redis.set(
        subscription_key(user_id),
        json.dumps(subscriptions),
        ex=60 * 60 * 24 * 365,
    )


async def remove_subscription(redis, user_id: str, endpoint: str) -> bool:
    subscriptions = await get_subscriptions(redis, user_id)
    remaining = [item for item in subscriptions if item.get("endpoint") != endpoint]
    if len(remaining) == len(subscriptions):
        return False

    if remaining:
        await redis.set(
            subscription_key(user_id),
            json.dumps(remaining),
            ex=60 * 60 * 24 * 365,
        )
    else:
        await redis.delete(subscription_key(user_id))
    return True


async def send_push_notifications(redis, user_id: str, payload: dict[str, Any]) -> int:
    if not push_is_configured():
        return 0

    subscriptions = await get_subscriptions(redis, user_id)
    delivered_count = 0
    for subscription in subscriptions:
        status = await _send_one(subscription, payload)
        if status == "expired":
            await remove_subscription(redis, user_id, subscription["endpoint"])
        elif status == "delivered":
            delivered_count += 1
    return delivered_count


async def _send_one(subscription: dict[str, Any], payload: dict[str, Any]) -> str:
    try:
        from pywebpush import webpush

        await asyncio.to_thread(
            webpush,
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
        )
    except ImportError:
        logger.error("pywebpush is not installed; Web Push is disabled")
        return "failed"
    except Exception as error:
        response = getattr(error, "response", None)
        if getattr(response, "status_code", None) in (404, 410):
            return "expired"
        logger.warning("Web Push delivery failed: %s", error)
        return "failed"
    return "delivered"
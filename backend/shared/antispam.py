"""反垃圾訊息過濾：以 Redis 計數實作的行為式過濾。

針對「使用者一直洗訊息」的場景，在 POST /events 入口做四道檢查：

1. 重複內容偵測：相同 title+message 在時間窗內只允許出現一次。
2. 發布間隔：同一使用者兩則事件之間至少間隔 N 秒。
3. 每分鐘頻率上限：同一使用者每分鐘最多 N 則。
4. 進行中事件數上限：同一使用者同時存在的事件數上限，
   避免用不同內容繞過前兩道檢查把地圖洗滿。

所有 key 都帶 TTL 自動過期；Redis 故障時 fail-open（放行並記 log），
避免過濾器本身成為服務中斷點。
"""

import hashlib
import logging
import os

from fastapi import HTTPException
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# 每分鐘每使用者最多發布幾則事件
RATE_LIMIT_PER_MINUTE = int(os.getenv("EVENT_RATE_LIMIT_PER_MINUTE", "3"))
# 同一使用者兩則事件的最小間隔（秒）
MIN_INTERVAL_SECONDS = int(os.getenv("EVENT_MIN_INTERVAL_SECONDS", "30"))
# 相同內容的封鎖時間窗（秒）
DUPLICATE_WINDOW_SECONDS = int(os.getenv("EVENT_DUPLICATE_WINDOW_SECONDS", "300"))
# 同一使用者同時存在的事件數上限
MAX_ACTIVE_EVENTS_PER_USER = int(os.getenv("EVENT_MAX_ACTIVE_PER_USER", "5"))

KEY_PREFIX = "event_antispam"


def _content_hash(title: str, message: str) -> str:
    normalized = f"{title.strip()}|{message.strip()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class EventAntiSpam:
    def __init__(self, redis) -> None:
        self.redis = redis

    async def check_and_register(
        self,
        user_id: str,
        title: str,
        message: str,
        event_id: str,
        duration_minutes: int,
    ) -> None:
        """先做全部的唯讀檢查，全部通過才登記這次發布的紀錄。

        關鍵：被擋下的請求（429/409）不能留下任何痕跡——否則「間隔太短」
        被拒的內容會被指紋記住，30 秒後重發同一內容反而被誤判 409 重複。
        檢查失敗會直接 raise HTTPException，呼叫端不需要再做後續處理。
        """
        try:
            dup_key = f"{KEY_PREFIX}:dup:{_content_hash(title, message)}"
            interval_key = f"{KEY_PREFIX}:interval:{user_id}"
            rate_key = f"{KEY_PREFIX}:rate:{user_id}"
            await self._check_duplicate(dup_key)
            await self._check_interval(interval_key)
            await self._check_rate_limit(rate_key)
            await self._check_active_events(user_id)
            await self._register(
                user_id, dup_key, interval_key, rate_key, event_id, duration_minutes
            )
        except HTTPException:
            raise
        except RedisError as e:
            # fail-open：過濾器故障時不阻擋正常使用者
            logger.warning("antispam check failed (fail-open): %s", e)

    async def _check_duplicate(self, dup_key: str) -> None:
        if DUPLICATE_WINDOW_SECONDS <= 0:
            return  # 設定為 0 表示停用重複內容偵測
        # 唯讀檢查：EXISTS 而非 SET NX——檢查階段不得寫入指紋
        if await self.redis.exists(dup_key):
            raise HTTPException(
                status_code=409,
                detail="重複內容：相同的事件內容短時間內已發布過，請稍後再試或修改內容",
            )

    async def _check_interval(self, interval_key: str) -> None:
        if MIN_INTERVAL_SECONDS <= 0:
            return  # 設定為 0 表示停用最小間隔檢查
        if await self.redis.exists(interval_key):
            raise HTTPException(
                status_code=429,
                detail=f"發布太快：兩則事件之間請至少間隔 {MIN_INTERVAL_SECONDS} 秒",
            )

    async def _check_rate_limit(self, rate_key: str) -> None:
        if RATE_LIMIT_PER_MINUTE <= 0:
            return  # 設定為 0 表示停用每分鐘頻率上限
        count = int(await self.redis.get(rate_key) or 0)
        if count >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail=f"發布頻率超過上限：每分鐘最多 {RATE_LIMIT_PER_MINUTE} 則事件",
            )

    async def _check_active_events(self, user_id: str) -> None:
        if MAX_ACTIVE_EVENTS_PER_USER <= 0:
            return  # 設定為 0 表示停用活躍事件數上限
        active_key = f"{KEY_PREFIX}:active:{user_id}"
        # redis.time() 回傳 (秒, 微秒)，取秒數
        now_ts = int((await self.redis.time())[0])
        # 先清掉已過期的成員（score = 事件過期時間戳）
        await self.redis.zremrangebyscore(active_key, "-inf", now_ts)
        active_count = await self.redis.zcard(active_key)
        if active_count >= MAX_ACTIVE_EVENTS_PER_USER:
            raise HTTPException(
                status_code=429,
                detail=f"進行中事件過多：同一使用者同時最多 {MAX_ACTIVE_EVENTS_PER_USER} 則事件，請等舊事件過期",
            )

    async def _register(
        self,
        user_id: str,
        dup_key: str,
        interval_key: str,
        rate_key: str,
        event_id: str,
        duration_minutes: int,
    ) -> None:
        """檢查全數通過後的登記階段；此處才開始寫入。

        SET NX 保有原子性：兩個併發的相同內容請求都通過唯讀檢查時，
        只有先寲入指紋的那個會成功，後到的視為重複拒絕。
        """
        if DUPLICATE_WINDOW_SECONDS > 0:
            is_new = await self.redis.set(
                dup_key, user_id, ex=DUPLICATE_WINDOW_SECONDS, nx=True
            )
            if not is_new:
                raise HTTPException(
                    status_code=409,
                    detail="重複內容：相同的事件內容短時間內已發布過，請稍後再試或修改內容",
                )
        if MIN_INTERVAL_SECONDS > 0:
            is_new = await self.redis.set(
                interval_key, "1", ex=MIN_INTERVAL_SECONDS, nx=True
            )
            if not is_new:
                raise HTTPException(
                    status_code=429,
                    detail=f"發布太快：兩則事件之間請至少間隔 {MIN_INTERVAL_SECONDS} 秒",
                )
        if RATE_LIMIT_PER_MINUTE > 0:
            count = await self.redis.incr(rate_key)
            if count == 1:
                await self.redis.expire(rate_key, 60)

        active_key = f"{KEY_PREFIX}:active:{user_id}"
        now_ts = int((await self.redis.time())[0])
        expires_at = now_ts + duration_minutes * 60
        await self.redis.zadd(active_key, {event_id: expires_at})
        # 活躍清單本身設一個略長於事件壽命的 TTL，避免沒人再發布時留下死 key
        await self.redis.expire(active_key, int(duration_minutes * 60) + 60)

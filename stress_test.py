#!/usr/bin/env python3
"""
即時校園地圖通知系統 — 全面壓力測試
涵蓋：Location updates, Event creation, Event listing, Comments
"""
import argparse
import asyncio
import json
import random
import time
from collections import Counter
from dataclasses import dataclass, field

import httpx

NTU_CENTER = (25.0173, 121.5397)


@dataclass
class Stats:
    success: int = 0
    failed: int = 0
    latencies: list[float] = field(default_factory=list)
    failures: Counter = field(default_factory=Counter)
    endpoint_stats: dict[str, "Stats"] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.success + self.failed

    def failure_summary(self) -> str:
        if not self.failures:
            return "none"
        return ", ".join(f"{k}:{v}" for k, v in self.failures.most_common(5))

    def latency_summary(self) -> str:
        if not self.latencies:
            return "N/A"
        s = sorted(self.latencies)
        p50 = s[len(s) // 2]
        p95 = s[int(len(s) * 0.95)]
        p99 = s[int(len(s) * 0.99)]
        avg = sum(s) / len(s)
        return f"avg={avg*1000:.0f}ms p50={p50*1000:.0f}ms p95={p95*1000:.0f}ms p99={p99*1000:.0f}ms"


def jitter(lat: float, lng: float, spread: float = 0.004) -> tuple[float, float]:
    return lat + random.uniform(-spread, spread), lng + random.uniform(-spread, spread)


# ── Phase 1: Location Service 持續上報 ──────────────────
async def location_uploader(
    client: httpx.AsyncClient,
    user_id: str,
    target: str,
    interval: float,
    stop_at: float | None,
    stats: Stats,
) -> None:
    lat, lng = jitter(*NTU_CENTER)
    while stop_at is None or time.time() < stop_at:
        lat += random.uniform(-0.00008, 0.00008)
        lng += random.uniform(-0.00008, 0.00008)
        t0 = time.time()
        try:
            r = await client.post(
                f"{target}/locations",
                json={"user_id": user_id, "latitude": lat, "longitude": lng},
            )
            elapsed = time.time() - t0
            if r.is_success:
                stats.success += 1
            else:
                stats.failed += 1
                stats.failures[f"http_{r.status_code}"] += 1
            stats.latencies.append(elapsed)
        except httpx.TimeoutException:
            stats.failed += 1
            stats.failures["timeout"] += 1
        except httpx.ConnectError:
            stats.failed += 1
            stats.failures["connect_error"] += 1
        except Exception as exc:
            stats.failed += 1
            stats.failures[type(exc).__name__] += 1
        await asyncio.sleep(interval)


# ── Phase 2: Event 建立 + Comment 留言 ──────────────────
EVENT_TITLES = ["有空位", "排隊人多", "人潮聚集", "免費活動", "遺失物", "施工封路", "走失寵物", "安全提醒"]
EVENT_MESSAGES = [
    "靠窗大約還有 10 個座位",
    "排隊人潮較多，請留意等待時間",
    "此處人潮聚集中",
    "這裡有免費活動進行中",
    "這裡有撿到遺失物",
    "此處施工中，請改道",
    "有走失寵物在此處出沒",
    "此處有安全疑慮，請小心",
]


async def event_spammer(
    client: httpx.AsyncClient,
    user_id: str,
    target: str,
    interval: float,
    stop_at: float | None,
    stats: Stats,
    comment_stats: Stats,
) -> None:
    while stop_at is None or time.time() < stop_at:
        lat, lng = jitter(*NTU_CENTER, 0.002)
        idx = random.randint(0, len(EVENT_TITLES) - 1)
        t0 = time.time()
        try:
            r = await client.post(
                f"{target}/events",
                json={
                    "client_event_id": f"stress-{user_id}-{time.time_ns()}",
                    "title": EVENT_TITLES[idx],
                    "message": EVENT_MESSAGES[idx],
                    "latitude": lat,
                    "longitude": lng,
                    "severity": random.choice(["info", "urgent"]),
                    "radius_meters": random.randint(200, 1500),
                    "expires_in": random.choice([10, 30, 60, 120]),
                },
            )
            elapsed = time.time() - t0
            if r.is_success:
                stats.success += 1
                stats.latencies.append(elapsed)
                # 留言
                data = r.json()
                event_id = data.get("event_id")
                if event_id:
                    ct0 = time.time()
                    try:
                        cr = await client.post(
                            f"{target}/events/{event_id}/comments",
                            json={
                                "author": f"測試員{user_id[-3:]}",
                                "content": f"壓測留言 #{stats.success}",
                            },
                        )
                        ce = time.time() - ct0
                        if cr.is_success:
                            comment_stats.success += 1
                        else:
                            comment_stats.failed += 1
                        comment_stats.latencies.append(ce)
                    except Exception:
                        comment_stats.failed += 1
            else:
                stats.failed += 1
                stats.failures[f"http_{r.status_code}"] += 1
                stats.latencies.append(elapsed)
        except httpx.TimeoutException:
            stats.failed += 1
            stats.failures["timeout"] += 1
        except httpx.ConnectError:
            stats.failed += 1
            stats.failures["connect_error"] += 1
        except Exception as exc:
            stats.failed += 1
            stats.failures[type(exc).__name__] += 1
        await asyncio.sleep(interval)


# ── Phase 3: Event 查詢 ────────────────────────────────
async def event_reader(
    client: httpx.AsyncClient,
    target: str,
    interval: float,
    stop_at: float | None,
    stats: Stats,
) -> None:
    while stop_at is None or time.time() < stop_at:
        t0 = time.time()
        try:
            r = await client.get(f"{target}/events", params={"limit": 50})
            elapsed = time.time() - t0
            if r.is_success:
                stats.success += 1
            else:
                stats.failed += 1
                stats.failures[f"http_{r.status_code}"] += 1
            stats.latencies.append(elapsed)
        except Exception as exc:
            stats.failed += 1
            stats.failures[type(exc).__name__] += 1
        await asyncio.sleep(interval)


# ── 主控 ────────────────────────────────────────────────
async def run_test(
    users: int,
    event_users: int,
    readers: int,
    target: str,
    loc_target: str,
    duration: int,
    timeout: float,
) -> None:
    loc_stats = Stats()
    event_stats = Stats()
    comment_stats = Stats()
    read_stats = Stats()

    limits = httpx.Limits(
        max_connections=users + event_users + readers + 10,
        max_keepalive_connections=users + event_users + readers,
    )
    stop_at = time.time() + duration

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        tasks = []
        # Location uploaders
        for i in range(users):
            tasks.append(asyncio.create_task(
                location_uploader(client, f"stress-u-{i:04d}", loc_target, 1.5, stop_at, loc_stats)
            ))
        # Event creators + commenters
        for i in range(event_users):
            tasks.append(asyncio.create_task(
                event_spammer(
                    client, f"stress-e-{i:04d}", target,
                    random.uniform(3, 8), stop_at, event_stats, comment_stats,
                )
            ))
        # Event readers
        for i in range(readers):
            tasks.append(asyncio.create_task(
                event_reader(client, target, random.uniform(2, 5), stop_at, read_stats)
            ))

        started = time.time()
        while any(not t.done() for t in tasks):
            elapsed = int(time.time() - started)
            remaining = max(0, duration - elapsed)
            print(
                f"[{elapsed}s/{duration}s] 剩餘 {remaining}s │ "
                f"📍 Location: {loc_stats.total} (✓{loc_stats.success} ✗{loc_stats.failed}) │ "
                f"📝 Event: {event_stats.total} (✓{event_stats.success}) │ "
                f"💬 Comment: {comment_stats.total} │ "
                f"📖 Read: {read_stats.total}"
            )
            await asyncio.sleep(5)
            for t in tasks:
                if t.done():
                    t.result()

    elapsed = max(time.time() - started, 1)
    print("\n" + "=" * 70)
    print(f"壓測完成！總時長 {int(elapsed)}s")
    print("=" * 70)

    for name, s, concurrency in [
        ("📍 Location 上報", loc_stats, users),
        ("📝 Event 建立", event_stats, event_users),
        ("💬 Comment 留言", comment_stats, event_users),
        ("📖 Event 查詢", read_stats, readers),
    ]:
        rps = round(s.total / elapsed, 1) if s.total else 0
        succ_rate = round(s.success / s.total * 100, 1) if s.total else 0
        print(f"\n{name} ({concurrency} 並發)")
        print(f"  總請求: {s.total} | 成功率: {succ_rate}% | RPS: {rps}/s")
        print(f"  延遲: {s.latency_summary()}")
        if s.failures:
            print(f"  錯誤: {s.failure_summary()}")

    total_req = loc_stats.total + event_stats.total + comment_stats.total + read_stats.total
    total_ok = loc_stats.success + event_stats.success + comment_stats.success + read_stats.success
    print(f"\n🏁 總請求: {total_req} | 總成功: {total_ok} | 總 RPS: {round(total_req / elapsed, 1)}/s")


def main():
    parser = argparse.ArgumentParser(description="即時校園地圖壓力測試")
    parser.add_argument("--users", type=int, default=200, help="Location 上報模擬使用者數")
    parser.add_argument("--event-users", type=int, default=20, help="事件建立模擬使用者數")
    parser.add_argument("--readers", type=int, default=10, help="事件查詢並發數")
    parser.add_argument("--duration", type=int, default=60, help="壓測時長（秒）")
    parser.add_argument("--target", default="http://localhost:8002", help="Event Service URL")
    parser.add_argument("--location-target", default=None, help="Location Service URL (預設同 target:8001)")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    loc_target = args.location_target or args.target.replace(":8002", ":8001")

    print(f"""
╔══════════════════════════════════════════╗
║     即時校園地圖壓力測試               ║
╠══════════════════════════════════════════╣
║  📍 Location 上報:  {args.users:>4} 使用者         ║
║  📝 Event 建立:    {args.event_users:>4} 使用者         ║
║  📖 Event 查詢:    {args.readers:>4} 並發           ║
║  ⏱️  時長:          {args.duration:>4} 秒             ║
║  🎯 Event Target:    {args.target:<20}║
║  🎯 Location Target: {loc_target:<20}║
╚══════════════════════════════════════════╝
""")

    asyncio.run(run_test(
        args.users, args.event_users, args.readers,
        args.target, loc_target, args.duration, args.timeout,
    ))


if __name__ == "__main__":
    main()

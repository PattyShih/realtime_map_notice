import argparse
import asyncio
from collections import Counter
import random
import time

import httpx


NTU_CENTER = (25.0173, 121.5397)


class RunStats:
    def __init__(self) -> None:
        self.success = 0
        self.failed = 0
        self.failures: Counter[str] = Counter()

    @property
    def total(self) -> int:
        return self.success + self.failed

    def failure_summary(self) -> str:
        if not self.failures:
            return "none"

        return ",".join(
            f"{name}:{count}" for name, count in self.failures.most_common(5)
        )


def jitter_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    return (
        latitude + random.uniform(-0.004, 0.004),
        longitude + random.uniform(-0.004, 0.004),
    )


async def virtual_user(
    client: httpx.AsyncClient,
    user_id: str,
    target: str,
    interval: float,
    stop_at: float | None,
    stats: RunStats,
) -> None:
    latitude, longitude = jitter_coordinate(*NTU_CENTER)
    while stop_at is None or time.time() < stop_at:
        latitude += random.uniform(-0.00008, 0.00008)
        longitude += random.uniform(-0.00008, 0.00008)
        try:
            response = await client.post(
                f"{target}/locations",
                json={
                    "user_id": user_id,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )
            if response.is_success:
                stats.success += 1
            else:
                stats.failed += 1
                stats.failures[f"http_{response.status_code}"] += 1
        except httpx.TimeoutException:
            stats.failed += 1
            stats.failures["timeout"] += 1
        except httpx.ConnectError:
            stats.failed += 1
            stats.failures["connect_error"] += 1
        except httpx.HTTPError as exc:
            stats.failed += 1
            stats.failures[type(exc).__name__] += 1
        await asyncio.sleep(interval)


async def run(
    users: int,
    target: str,
    interval: float,
    duration: int | None,
    timeout: float,
) -> None:
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    stop_at = time.time() + duration if duration else None
    stats = RunStats()
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        tasks = [
            asyncio.create_task(
                virtual_user(client, f"u-{index:04d}", target, interval, stop_at, stats),
            )
            for index in range(users)
        ]
        started = time.time()
        while any(not task.done() for task in tasks):
            elapsed = int(time.time() - started)
            rate = round(stats.total / elapsed, 2) if elapsed > 0 else 0
            print(
                "simulating "
                f"users={users} elapsed={elapsed}s "
                f"success={stats.success} failed={stats.failed} "
                f"rate={rate}/s failures={stats.failure_summary()} target={target}",
            )
            await asyncio.sleep(5)
            for task in tasks:
                if task.done():
                    task.result()

    elapsed = max(time.time() - started, 1)
    print(
        "simulation completed "
        f"users={users} duration={int(elapsed)}s "
        f"success={stats.success} failed={stats.failed} "
        f"avg_rate={round(stats.total / elapsed, 2)}/s "
        f"failures={stats.failure_summary()}",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Campus GPS traffic simulator")
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--target", default="http://localhost:8001")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Stop after this many seconds. Omit to run until interrupted.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        run(
            args.users,
            args.target.rstrip("/"),
            args.interval,
            args.duration,
            args.timeout,
        ),
    )


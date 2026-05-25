import argparse
import asyncio
import random
import time

import httpx


NTU_CENTER = (25.0173, 121.5397)


def jitter_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    return (
        latitude + random.uniform(-0.004, 0.004),
        longitude + random.uniform(-0.004, 0.004),
    )


async def virtual_user(client: httpx.AsyncClient, user_id: str, target: str, interval: float) -> None:
    latitude, longitude = jitter_coordinate(*NTU_CENTER)
    while True:
        latitude += random.uniform(-0.00008, 0.00008)
        longitude += random.uniform(-0.00008, 0.00008)
        try:
            await client.post(
                f"{target}/locations",
                json={
                    "user_id": user_id,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )
        except httpx.HTTPError:
            pass
        await asyncio.sleep(interval)


async def run(users: int, target: str, interval: float) -> None:
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(timeout=2.0, limits=limits) as client:
        tasks = [
            asyncio.create_task(virtual_user(client, f"u-{index:04d}", target, interval))
            for index in range(users)
        ]
        started = time.time()
        while True:
            elapsed = int(time.time() - started)
            print(f"simulating users={users} elapsed={elapsed}s target={target}")
            await asyncio.sleep(5)
            for task in tasks:
                if task.done():
                    task.result()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Campus GPS traffic simulator")
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--target", default="http://localhost:8001")
    parser.add_argument("--interval", type=float, default=1.0)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.users, args.target.rstrip("/"), args.interval))


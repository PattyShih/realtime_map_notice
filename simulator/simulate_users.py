import argparse
import asyncio
import random
import socket
import time

import httpx


NTU_CENTER = (25.0173, 121.5397)


def jitter_coordinate(latitude: float, longitude: float) -> tuple[float, float]:
    return (
        latitude + random.uniform(-0.004, 0.004),
        longitude + random.uniform(-0.004, 0.004),
    )


# K8s Service（kube-proxy）只在建立新 TCP 連線時分流；keep-alive 連線會一直黏在
# 同一個 Pod，HPA 擴出的新 Pod 分不到流量、負載嚴重不均。每位虛擬使用者每隔
# 約 ROTATE_EVERY 次請求帶一次 Connection: close，讓連線輪替、重新分流到所有 Pod。
ROTATE_EVERY = 20


async def virtual_user(client: httpx.AsyncClient, user_id: str, target: str, interval: float) -> None:
    latitude, longitude = jitter_coordinate(*NTU_CENTER)
    # 起始計數錯開，避免所有使用者同一瞬間一起斷線重連
    sent = random.randrange(ROTATE_EVERY)
    while True:
        latitude += random.uniform(-0.00008, 0.00008)
        longitude += random.uniform(-0.00008, 0.00008)
        sent += 1
        headers = {"Connection": "close"} if sent % ROTATE_EVERY == 0 else None
        try:
            await client.post(
                f"{target}/locations",
                json={
                    "user_id": user_id,
                    "latitude": latitude,
                    "longitude": longitude,
                },
                headers=headers,
            )
        except httpx.HTTPError:
            pass
        await asyncio.sleep(interval)


async def run(users: int, target: str, interval: float) -> None:
    # 使用者 ID 帶上容器 hostname：多 worker 拆分時各自編號從 0 開始，
    # 不加前綴會互相覆蓋（800 人拆兩個 worker 只剩 400 個唯一使用者）
    worker_id = socket.gethostname()[:8]
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(timeout=2.0, limits=limits) as client:
        tasks = [
            asyncio.create_task(
                virtual_user(client, f"u-{worker_id}-{index:04d}", target, interval)
            )
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


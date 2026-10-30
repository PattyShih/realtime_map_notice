"""Stage 5：端到端推播延遲量化工具。

開 N 條 WebSocket 連線模擬在線使用者，逐一發布事件，
量測「POST /events → 使用者透過 WebSocket 收到通知」的端到端延遲，
輸出 P50/P95/P99 統計，作為報告中「即時性」的量化證據。

前置：docker compose up（或 K8s port-forward），三個服務與 Redis 可連線。

用法：
    python simulator/measure_latency.py --users 100 --events 10
    python simulator/measure_latency.py --users 300 --events 20 --interval 0.5
"""

import argparse
import asyncio
import json
import random
import statistics
import time

import aiohttp


def percentile(sorted_values: list[float], p: int) -> float:
    if not sorted_values:
        return 0.0
    k = max(0, min(len(sorted_values) - 1, round(p / 100 * (len(sorted_values) - 1))))
    return sorted_values[k]


async def post_locations(
    session: aiohttp.ClientSession,
    location_url: str,
    users: list[tuple[str, float, float]],
) -> int:
    """讓所有模擬使用者上報座標（保持 last_seen 活躍，TTL 60 秒）。"""
    sem = asyncio.Semaphore(50)

    async def post(user_id: str, lat: float, lon: float) -> bool:
        payload = {"user_id": user_id, "latitude": lat, "longitude": lon}
        try:
            async with session.post(
                f"{location_url}/locations",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    results = await asyncio.gather(*(post(uid, lat, lon) for uid, lat, lon in users))
    return sum(results)


async def connect_user(
    session: aiohttp.ClientSession,
    ws_url: str,
    user_id: str,
    sockets: dict,
    failed: list,
) -> None:
    try:
        sockets[user_id] = await session.ws_connect(f"{ws_url}/ws/{user_id}")
    except Exception:
        failed.append(user_id)


async def listen_one(user_id: str, ws: aiohttp.ClientWebSocketResponse, arrivals: dict) -> None:
    """持續接收訊息：hello/ping 忽略，通知類訊息記錄抵達時間。"""
    try:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            if data.get("type") in ("hello", "ping"):
                continue
            event_id = data.get("event_id")
            if event_id:
                arrivals.setdefault(event_id, {})[user_id] = time.perf_counter()
    except Exception:
        pass  # 連線中斷：該使用者後續通知視為漏收


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="端到端推播延遲量化（POST /events → WS 收到通知）")
    parser.add_argument("--users", type=int, default=100, help="模擬在線使用者（WS 連線數），預設 100")
    parser.add_argument("--events", type=int, default=10, help="測試事件數，預設 10")
    parser.add_argument("--interval", type=float, default=1.0, help="兩個事件之間的間隔秒數，預設 1")
    parser.add_argument("--timeout", type=float, default=10.0, help="每個事件的收集逾時秒數，預設 10")
    parser.add_argument("--radius", type=int, default=500, help="事件通知半徑（公尺），預設 500")
    parser.add_argument("--location-url", default="http://localhost:8001", help="Location Service URL")
    parser.add_argument("--event-url", default="http://localhost:8002", help="Event Service URL")
    parser.add_argument("--ws-url", default="ws://localhost:8003", help="Notification Service WS URL")
    parser.add_argument("--lat", type=float, default=25.063, help="中心緯度（預設大同區）")
    parser.add_argument("--lon", type=float, default=121.513, help="中心經度（預設大同區）")
    parser.add_argument("--spread", type=float, default=0.002, help="使用者座標隨機偏移範圍（約 220m）")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    print(f"📊 延遲量化：{args.users} 條 WS 連線，{args.events} 個事件，目標 {args.event_url}")

    users = [
        (
            f"lat_user_{i}",
            args.lat + random.uniform(-args.spread, args.spread),
            args.lon + random.uniform(-args.spread, args.spread),
        )
        for i in range(args.users)
    ]

    async with aiohttp.ClientSession() as session:
        # 1. 上報座標（讓使用者進入 GEO 索引且 last_seen 活躍）
        ok = await post_locations(session, args.location_url, users)
        print(f"📍 座標上報：{ok}/{args.users} 成功")

        # 2. 建立 WS 連線並啟動接收 task
        sockets: dict = {}
        failed: list = []
        sem = asyncio.Semaphore(100)

        async def connect_limited(user_id: str) -> None:
            async with sem:
                await connect_user(session, args.ws_url, user_id, sockets, failed)

        await asyncio.gather(*(connect_limited(uid) for uid, _, _ in users))
        print(f"🔌 WS 連線：{len(sockets)} 成功，{len(failed)} 失敗")

        arrivals: dict = {}  # event_id -> {user_id: perf_counter}
        listen_tasks = [
            asyncio.create_task(listen_one(uid, ws, arrivals)) for uid, ws in sockets.items()
        ]

        # 3. 逐一發布事件並收集每位使用者的通知抵達時間
        latencies_ms: list[float] = []
        missed = 0
        posts_failed = 0

        for i in range(args.events):
            await post_locations(session, args.location_url, users)  # 維持 last_seen 活躍

            payload = {
                "title": f"[latency-test] event {i}",
                "message": "latency measurement",
                "latitude": args.lat,
                "longitude": args.lon,
                "severity": "info",
                "radius_meters": args.radius,
                "duration_minutes": 5,
            }
            t0 = time.perf_counter()
            try:
                async with session.post(
                    f"{args.event_url}/events",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    body = await resp.json()
                    if resp.status != 200:
                        posts_failed += 1
                        print(f"  event {i + 1}/{args.events}: POST 失敗（HTTP {resp.status}）")
                        continue
            except Exception as e:
                posts_failed += 1
                print(f"  event {i + 1}/{args.events}: POST 例外 {type(e).__name__}")
                continue

            event_id = body.get("event_id", "")
            deadline = t0 + args.timeout
            while time.perf_counter() < deadline:
                if len(arrivals.get(event_id, {})) >= len(sockets):
                    break
                await asyncio.sleep(0.005)

            received = arrivals.get(event_id, {})
            for user_id in sockets:
                if user_id in received:
                    latencies_ms.append((received[user_id] - t0) * 1000)
                else:
                    missed += 1
            print(f"  event {i + 1}/{args.events}: {len(received)}/{len(sockets)} delivered")
            await asyncio.sleep(args.interval)

        # 4. 清理：取消接收 task 並關閉連線
        for task in listen_tasks:
            task.cancel()
        await asyncio.gather(*listen_tasks, return_exceptions=True)
        for ws in sockets.values():
            await ws.close()

    # 5. 統計輸出
    expected = len(sockets) * args.events
    latencies_ms.sort()
    print("\n📊 端到端推播延遲統計（POST /events → WS 收到通知）")
    print(f"   樣本數: {len(latencies_ms)} / 預期 {expected}（漏收 {missed}）")
    if posts_failed:
        print(f"   ⚠️ {posts_failed} 個事件發布失敗")
    if latencies_ms:
        print(f"   最小: {latencies_ms[0]:.1f} ms")
        print(f"   P50:  {percentile(latencies_ms, 50):.1f} ms")
        print(f"   P95:  {percentile(latencies_ms, 95):.1f} ms")
        print(f"   P99:  {percentile(latencies_ms, 99):.1f} ms")
        print(f"   最大: {latencies_ms[-1]:.1f} ms")
        print(f"   平均: {statistics.fmean(latencies_ms):.1f} ms")


if __name__ == "__main__":
    asyncio.run(main())

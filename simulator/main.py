import asyncio
import aiohttp
import random
import time
import argparse


async def simulate_user(user_id: int, session: aiohttp.ClientSession,
                         url: str, duration: float, base_lat: float,
                         base_lon: float, spread: float, sem: asyncio.Semaphore,
                         stats: dict):
    # 讓每個使用者隨機延遲啟動，避免瞬間全部擠在同一毫秒發送請求
    await asyncio.sleep(random.uniform(0, 2))

    end_time = time.time() + duration
    step = 0

    # 在 duration 秒內持續發送座標更新，直到時間到才停止
    # (這是要撐住 CPU 負載，讓 HPA 有機會觀察到並擴展 replica)
    while time.time() < end_time:
        step += 1
        lat = base_lat + random.uniform(-spread, spread)
        lon = base_lon + random.uniform(-spread, spread)

        payload = {
            "user_id": f"sim_user_{user_id}",
            "latitude": lat,
            "longitude": lon,
        }

        async with sem:
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        stats["success"] += 1
                    else:
                        stats["fail"] += 1
                        if stats["fail"] <= 20:
                            print(f"[使用者 {user_id}] 步驟 {step}: 失敗，狀態碼 {response.status}")
            except Exception as e:
                stats["fail"] += 1
                if stats["fail"] <= 20:
                    print(f"[使用者 {user_id}] 步驟 {step}: 連線錯誤 - {type(e).__name__}: {e}")

        # 模擬現實中走動的間隔，停留 1 到 3 秒後再發送下一個座標
        await asyncio.sleep(random.uniform(1, 3))


async def main():
    parser = argparse.ArgumentParser(description="即時地圖通知系統 - 壓測模擬器")
    parser.add_argument("--users", type=int, default=500,
                         help="模擬使用者人數 (預設 500，可測 500/1000，進階可拉到 3000)")
    parser.add_argument("--duration", type=float, default=180,
                         help="壓測持續秒數 (預設 180 秒，建議 HPA 測試至少 120 秒以上)")
    parser.add_argument("--url", type=str, default="http://localhost:8001/locations",
                         help="Location Service 的 API 端點")
    parser.add_argument("--concurrency", type=int, default=200,
                         help="同時併發送出的連線上限 (避免壓測端自己先過載，3000 人建議調高)")
    parser.add_argument("--lat", type=float, default=25.063, help="中心緯度 (預設大同區)")
    parser.add_argument("--lon", type=float, default=121.513, help="中心經度 (預設大同區)")
    parser.add_argument("--spread", type=float, default=0.005, help="座標隨機偏移範圍")
    args = parser.parse_args()

    print(f"🚀 啟動 {args.users} 人壓測，持續 {args.duration} 秒，目標 {args.url}")
    print(f"   併發上限: {args.concurrency}，中心座標: ({args.lat}, {args.lon})")

    stats = {"success": 0, "fail": 0}
    sem = asyncio.Semaphore(args.concurrency)

    connector = aiohttp.TCPConnector(limit=args.concurrency, limit_per_host=args.concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            simulate_user(i, session, args.url, args.duration, args.lat, args.lon, args.spread, sem, stats)
            for i in range(args.users)
        ]
        await asyncio.gather(*tasks)

    print("✅ 壓測執行完畢！")
    print(f"   成功請求: {stats['success']}，失敗請求: {stats['fail']}")


if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    print(f"總耗時: {time.time() - start_time:.2f} 秒")
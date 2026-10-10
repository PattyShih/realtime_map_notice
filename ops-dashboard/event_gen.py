"""demo 用低量事件產生器：壓測期間持續發布事件，
讓 event / notification / ai 服務在儀表板上也有可見流量。

設計考量（配合反垃圾訊息規則）：
- 輪替 150 個 user_id，每 0.25 秒一則，單一使用者約 37.5 秒一則，
  高於「30 秒最小間隔 / 每分鐘 3 則」門檻，不會被 429 擋下
- 內容帶遞增編號，不會觸發重複內容偵測（5 分鐘指紋）
"""
import asyncio
import os
import random

import httpx

EVENT_SERVICE = "http://event-service:8000"
# 發布間隔（秒）與事件時效（分鐘）可用環境變數調整：
# 獨立事件模式建議 2 秒一則（demo 幾分鐘地圖累積數十到百餘則）；
# 跟著壓測跑時維持 0.25 秒（重點是服務流量而非地圖可讀性）。
EVENT_INTERVAL = float(os.getenv("EVENT_INTERVAL", "0.25"))
EVENT_DURATION_MINUTES = float(os.getenv("EVENT_DURATION_MINUTES", "15"))
# 每次啟動帶隨機標籤：容器重啟後編號歸零，若標題與 5 分鐘內發過的
# 事件相同會被「重複內容偵測」整批 409，隨機標籤可避免碰撞
RUN_TAG = os.getenv("EVENT_RUN_TAG") or str(random.randint(100, 999))
USER_IDS = [f"u-{9000 + i}" for i in range(150)]
# 輔大校園及周遭的真實地標：事件落在地標附近，地圖上看起來像真實校園通報
SPOTS = [
    {"name": "輔大總圖", "lat": 25.0372, "lng": 121.4325,
     "title": "總圖 3F 有空位", "severity": "info"},
    {"name": "中美堂", "lat": 25.0360, "lng": 121.4330,
     "title": "中美堂活動排隊人潮", "severity": "warning"},
    {"name": "風雨籃球場", "lat": 25.0347, "lng": 121.4341,
     "title": "風雨籃球場場地積水", "severity": "warning"},
    {"name": "捷運輔大站", "lat": 25.0333, "lng": 121.4340,
     "title": "校門口車流回堵", "severity": "warning"},
    {"name": "理工學院", "lat": 25.0349, "lng": 121.4305,
     "title": "理工走廊機保養中", "severity": "info"},
    {"name": "學餐", "lat": 25.0365, "lng": 121.4335,
     "title": "學餐二樓人潮少", "severity": "info"},
]
JITTER = 0.0012  # 約 ±130 公尺的隨機偏移，讓事件散在校園各角落


async def main() -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        i = 0
        ok = 0
        while True:
            uid = USER_IDS[i % len(USER_IDS)]
            spot = SPOTS[i % len(SPOTS)]
            lat = spot["lat"] + random.uniform(-JITTER, JITTER)
            lng = spot["lng"] + random.uniform(-JITTER, JITTER)
            payload = {
                "user_id": uid,
                "title": f"{spot['title']} (#{RUN_TAG}-{i})",
                "message": f"{spot['name']}現場回報，提供給附近同學參考。",
                "latitude": lat,
                "longitude": lng,
                "severity": spot["severity"],
                "duration_minutes": EVENT_DURATION_MINUTES,
            }
            try:
                resp = await client.post(f"{EVENT_SERVICE}/events", json=payload)
                status = resp.status_code
                ok += status == 200
            except httpx.HTTPError:
                status = "unreachable"
            if i % 40 == 0:
                print(f"event #{i} by {uid} -> {status} (ok={ok})", flush=True)
            i += 1
            await asyncio.sleep(EVENT_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())

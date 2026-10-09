"""demo 用低量事件產生器：壓測期間持續發布事件，
讓 event / notification / ai 服務在儀表板上也有可見流量。

設計考量（配合反垃圾訊息規則）：
- 輪替 150 個 user_id，每 0.25 秒一則，單一使用者約 37.5 秒一則，
  高於「30 秒最小間隔 / 每分鐘 3 則」門檻，不會被 429 擋下
- 內容帶遞增編號，不會觸發重複內容偵測（5 分鐘指紋）
"""
import asyncio
import random

import httpx

EVENT_SERVICE = "http://event-service:8000"
USER_IDS = [f"u-{9000 + i}" for i in range(150)]
TITLES = [
    "總圖 3F 有空位",
    "校門口車流回堵",
    "風雨籃球場積水",
    "學餐二樓人潮少",
    "活動中心有市集",
    "停車場出口大排隊",
]
MESSAGES = [
    "現場觀察回報，提供給附近同學參考。",
    "剛剛經過看到的情况，大家可以避開或前往。",
    "持續更新中，歡迎補充最新狀況。",
]
CENTER = (25.0173, 121.5397)  # 台大中心，與模擬使用者同區域
SEVERITIES = ["info", "info", "warning"]


async def main() -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        i = 0
        ok = 0
        while True:
            uid = USER_IDS[i % len(USER_IDS)]
            lat, lng = CENTER[0] + random.uniform(-0.002, 0.002), CENTER[1] + random.uniform(-0.002, 0.002)
            payload = {
                "user_id": uid,
                "title": f"{TITLES[i % len(TITLES)]} (#{i})",
                "message": MESSAGES[i % len(MESSAGES)],
                "latitude": lat,
                "longitude": lng,
                "severity": SEVERITIES[i % len(SEVERITIES)],
                "duration_minutes": 15,
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
            await asyncio.sleep(0.25)


if __name__ == "__main__":
    asyncio.run(main())

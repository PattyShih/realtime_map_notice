import asyncio
import aiohttp
import random
import json

CENTER_LAT = 25.0630
CENTER_LON = 121.5130

async def simulate_user(user_id: int, session: aiohttp.ClientSession, is_inside: bool):
    offset = random.uniform(0, 0.004) if is_inside else random.uniform(0.006, 0.015)
    lat = CENTER_LAT + (offset * random.choice([1, -1]))
    lon = CENTER_LON + (offset * random.choice([1, -1]))
    
    # 【修正 1】拿掉 "user_" 前綴，改用純數字 ID 測試後端邏輯
    user_str = str(user_id) 
    
    location_payload = {"user_id": user_str, "latitude": lat, "longitude": lon}
    try:
        async with session.post("http://localhost:8001/locations", json=location_payload) as resp:
            pass 
    except Exception:
        pass

    ws_port = random.choice([8011, 8012, 8013])
    ws_url = f"ws://localhost:{ws_port}/ws/{user_str}"
    
    received_events = set() 
    
    try:
        async with session.ws_connect(ws_url) as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # 【修正 2】同時過濾 ping 跟 hello 訊息，保持畫面乾淨
                    msg_type = data.get("type")
                    if msg_type in ["ping", "hello"]:
                        continue
                    
                    event_id = data.get("event_id") or data.get("id")
                    
                    if event_id is None:
                        print(f"🔍 [除錯] 使用者 {user_str} 收到未知結構: {data}")
                        event_id = str(data) 
                    
                    if event_id in received_events:
                        print(f"❌ [警告] 使用者 {user_str} 收到重複推播: {event_id}")
                    else:
                        print(f"✅ [使用者 {user_str}] 收到推播! 事件: {event_id}")
                        received_events.add(event_id)
                        
    except Exception as e:
        pass
    finally:
        # 【修正 3】斷線偵測：如果掉線了，立刻印出紅字警告
        print(f"💔 [使用者 {user_str}] WebSocket 已斷線離開！")

async def main():
    users_count = 500
    print(f"🚀 啟動 {users_count} 人極限壓測 (斷線偵測版)...")
    
    connector = aiohttp.TCPConnector(limit=0)
    
    tasks = []
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(users_count):
            is_inside = i < 300 
            tasks.append(simulate_user(i, session, is_inside))
            
        print("⏳ 正在併發建立 500 個連線... 請確認畫面沒有瘋狂跳出『已斷線』的紅字！")
        await asyncio.gather(*tasks)
        print("🏁 所有連線都已結束。")

if __name__ == "__main__":
    asyncio.run(main())
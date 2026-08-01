import asyncio
import aiohttp
import random
import time

# Location Service 的本地端點 
# (依照你的 docker-compose 截圖，預設 port 為 8000)
URL = "http://localhost:8001/locations"

async def simulate_user(user_id: int, session: aiohttp.ClientSession):
    # 讓每個使用者隨機延遲啟動，避免瞬間全部擠在同一毫秒發送請求
    await asyncio.sleep(random.uniform(0, 2))
    
    # 每個使用者模擬 5 次座標更新 (移動 5 步)
    for step in range(5):
        # 以大同區為基準，加上隨機偏移量來模擬移動
        lat = 25.063 + random.uniform(-0.005, 0.005)
        lon = 121.513 + random.uniform(-0.005, 0.005)
        
        payload = {
            "user_id": f"sim_user_{user_id}",
            "latitude": lat,
            "longitude": lon
        }
        
        try:
            # 發送非同步 POST 請求
            async with session.post(URL, json=payload) as response:
                if response.status == 200:
                    print(f"[使用者 {user_id}] 步驟 {step+1}: 成功更新位置 (緯度: {lat:.4f}, 經度: {lon:.4f})")
                else:
                    print(f"[使用者 {user_id}] 步驟 {step+1}: 失敗，狀態碼 {response.status}")
        except Exception as e:
            print(f"[使用者 {user_id}] 步驟 {step+1}: 連線錯誤 - {e}")
            
        # 模擬現實中走動的間隔，停留 1 到 3 秒後再發送下一個座標
        await asyncio.sleep(random.uniform(1, 3))

async def main():
    users_count = 10  # 雛形階段，我們先測試 10 個人
    print(f"🚀 開始模擬 {users_count} 名虛擬使用者...")
    
    # 建立一個共用的 HTTP Session 來提高效能
    async with aiohttp.ClientSession() as session:
        # 將所有使用者的模擬任務打包起來
        tasks = [simulate_user(i, session) for i in range(users_count)]
        # 同時並發執行所有任務
        await asyncio.gather(*tasks)
        
    print("✅ 壓測雛形執行完畢！")

if __name__ == "__main__":
    start_time = time.time()
    # 啟動非同步主程式
    asyncio.run(main())
    print(f"總耗時: {time.time() - start_time:.2f} 秒")
# Stage 5：Demo 演練劇本（成員 C — 即時通訊）

> 每個橋段都能用「複製貼上」的指令重現。示範座標以大同區為中心
> `(25.0630, 121.5130)`。注意：`last_seen` TTL 為 60 秒，定位指令要在發布事件前 60 秒內執行。
>
> **PowerShell 使用者注意**：`curl` 是 `Invoke-WebRequest` 的別名，`-H` 會報錯。
> 請改用 `curl.exe -H "Content-Type: application/json" ...`，或
> `Invoke-RestMethod -Method Post -Uri <url> -ContentType "application/json" -Body '<json>'`。

## 0. 前置準備

```bash
# Docker Compose 環境
docker compose up --build -d
docker compose ps                     # 三個服務 + Redis 全部 Up

# 或 K8s 環境（部署與 port-forward 詳見 k8s/README.md）
kubectl apply -f k8s/
kubectl -n realtime-map-notice get pods
```

## 1. 即時推播（兩視窗演示）

1. 開兩個瀏覽器視窗連到前端（`http://localhost:5173`），各允許定位。
2. 視窗 A 發布事件 → 視窗 B 立刻彈出通知卡片、地圖出現標記。
3. 後端日誌可同時觀察：
   ```bash
   docker compose logs -f event-service notification-service
   ```

## 2. 500 公尺邊界實證（半徑內收到、半徑外不收）

```bash
# 使用者 A：中心點北方約 110 公尺（半徑內）
curl -X POST http://localhost:8001/locations -H "Content-Type: application/json" \
  -d '{"user_id": "demo_A", "latitude": 25.0640, "longitude": 121.5130}'

# 使用者 B：中心點北方約 1.1 公里（半徑外）
curl -X POST http://localhost:8001/locations -H "Content-Type: application/json" \
  -d '{"user_id": "demo_B", "latitude": 25.0730, "longitude": 121.5130}'
```

兩個終端分別開 WebSocket（可用 `websocat`、Postman 或瀏覽器 console）：

```
ws://localhost:8003/ws/demo_A   # 半徑內
ws://localhost:8003/ws/demo_B   # 半徑外
```

發布事件（半徑 500 公尺）：

```bash
curl -X POST http://localhost:8002/events -H "Content-Type: application/json" \
  -d '{"title":"圖書館沒位子","message":"3F 全滿","latitude":25.0630,"longitude":121.5130,"severity":"warning","radius_meters":500,"duration_minutes":30}'
```

**預期**：A 的連線立即收到 JSON 通知（含 `distance_meters`）；B 完全沒動靜。
回應中的 `nearby_user_count` / `active_user_count` / `delivered_count` 可順帶解釋三段過濾。

## 3. 心跳與斷線重連

1. 前端連線後，DevTools → Network → Offline 切斷網路。
2. 觀察右上角連線狀態轉為「連線中斷，重試中...」（指數退避重連）。
3. 恢復網路 → 狀態回到「即時同步中」；期間他人發布的新事件，重連後照樣可從地圖查到。

服務端心跳參數（`backend/notification-service/app/main.py`）：
Ping 每 30 秒、Pong 逾時 10 秒即斷線，避免幽靈連線佔用資源。

## 4. 壓力測試與 HPA 自動擴展（K8s）

```bash
# metrics-server 若顯示 <unknown>，先套用 insecure-tls patch（詳見 k8s/README.md）
kubectl patch deployment metrics-server -n kube-system \
  --type json -p "$(cat k8s/patches/metrics-server-insecure-tls.json)"

# 另一個終端盯著 HPA
kubectl -n realtime-map-notice get hpa -w

# 施壓（持續 180 秒，觀察 replica 上升）
python simulator/simulate_users.py --users 500 --target http://localhost:8001 --interval 1
# 或負載持續版：
python simulator/main.py --users 1000 --duration 180
```

## 5. 端到端推播延遲量化（報告圖表來源）

```bash
pip install -r simulator/requirements.txt
python simulator/measure_latency.py --users 100 --events 10
# 進階：--users 300 --events 20 --interval 0.5
```

輸出 P50 / P95 / P99 / 最大 / 平均延遲與送達率，截圖即可放進報告
「即時性量化」段落。延遲定義：`POST /events` 送出 → 使用者 WS 收到通知。

## 6. 資料自動清理

- Location Service 內建背景清理（預設每 120 秒）：`last_seen` 過期的成員會被移出
  GEO 索引，壓測留下的數千個 `sim_user_*` 不會永久殘留。
  可用 `GEO_CLEANUP_INTERVAL_SECONDS` 環境變數調整。
- 徹底重置：`docker compose down -v`（連 Redis 資料一起清掉）。

## 7. 報告素材備忘

- **架構決策（fanout 統一）**：Stage 5 之前 event-service 對半徑內每個使用者逐一發
  HTTP `POST /notify/{id}`；現在改為對 notification-service 的 `POST /broadcast/nearby`
  呼叫**一次**，由通知服務統一做 GEO 比對、`last_seen` 離線過濾、Redis pipeline
  批次發布。N 次 HTTP → 1 次，推播邏輯集中在通知服務。
- **已知限制**：Redis Pub/Sub 為 at-most-once，使用者在事件發布瞬間若斷線，通知不補送。
  未來可升級 Redis Streams（`XADD` + 重連續讀）做到 at-least-once 與離線補推。
- **延遲數據**：用第 5 節工具在不同人數（100 / 300 / 1000）下各測一輪，畫出延遲對照。

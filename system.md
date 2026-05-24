# System Design

`realtime_map_notice` 採用微服務架構，將高頻位置更新、事件處理與即時通知拆成不同服務，方便展示 Kubernetes 的擴展與容錯能力。

## 核心問題

這個系統的技術挑戰有兩個：

- 持續不斷的座標更新：大量使用者每秒上傳 GPS 位置。
- 瞬間的區域推播：事件發生後，需要快速找出 500 公尺內使用者並通知。
- 地圖畫面更新：使用者位置、事件 marker、通知位置需要在前端保持同步。

因此系統不適合每次都把即時座標寫入傳統關聯式資料庫。初步設計使用 Redis GEO 儲存目前位置，讓後端可以快速執行附近查詢。

即時性與地圖地點更新的詳細資料欄位、更新頻率與驗收標準，請參考 [docs/realtime-location-requirements.md](./docs/realtime-location-requirements.md)。

## 系統元件

Web App:

- 使用瀏覽器前端框架建立介面。
- 使用地圖元件顯示校園地圖、使用者定位與事件插旗。
- 使用 browser Geolocation API 取得目前位置。
- 定期上傳目前 GPS 座標。
- 透過 WebSocket 接收附近事件通知。
- 需要處理定位被拒絕、API 失敗、WebSocket 斷線重連與空狀態。

Location Service:

- 接收 `POST /locations`。
- 將使用者目前座標寫入 Redis GEO。
- 是主要高併發入口，也是 HPA 自動擴展展示對象。
- 不負責長期保存歷史軌跡，主要保存「目前位置」。

Event Service:

- 接收 `POST /events`。
- 使用事件座標查詢半徑內使用者。
- 呼叫 Notification Service 發送通知。
- 是區域推播的主要商業邏輯位置。

Notification Service:

- 維護 WebSocket 連線。
- 接收指定 user_id 的通知請求。
- 使用 Redis Pub/Sub 支援多副本推播。
- 需要在未來補上心跳、重連配合與離線通知策略。

Redis:

- 使用 GEOADD 儲存使用者目前位置。
- 使用 GEOSEARCH 查詢指定座標附近使用者。
- 使用 Pub/Sub 協助 Notification Service 多副本同步通知。
- Demo 階段可接受資料暫存在記憶體；正式產品需規劃資料持久化與備份。

Kubernetes:

- 使用 Deployment 管理每個微服務。
- 使用 Service 提供穩定內部網路入口。
- 使用 HPA 讓 Location Service 依 CPU 自動擴展。
- 使用多副本 Notification Service 展示容錯。

## API Contract

### `POST /locations`

用途：Web App 定期上傳使用者目前位置。

Request:

```json
{
  "user_id": "u-0001",
  "latitude": 25.0173,
  "longitude": 121.5397
}
```

正式版本建議擴充 `accuracy_meters`、`client_timestamp`、`sequence`、`source` 等欄位，用來處理定位精度、舊資料覆蓋新資料、模擬器資料與真實 GPS 資料的區分。

Response:

```json
{
  "status": "accepted",
  "user_id": "u-0001"
}
```

### `GET /locations/nearby`

用途：依指定座標查詢半徑內使用者。

Query:

```text
latitude=25.0173
longitude=121.5397
radius_meters=500
```

Response:

```json
{
  "users": ["u-0001", "u-0002"]
}
```

### `POST /events`

用途：建立事件並推播給附近使用者。

Request:

```json
{
  "title": "Library seats",
  "message": "3F has seats near windows",
  "latitude": 25.0173,
  "longitude": 121.5397,
  "severity": "info",
  "radius_meters": 500
}
```

Response:

```json
{
  "event_id": "uuid",
  "nearby_user_count": 2,
  "delivered_count": 2,
  "delivered_to": ["u-0001", "u-0002"]
}
```

### `WS /ws/{user_id}`

用途：Web App 建立指定使用者的即時通知連線。

Message:

```json
{
  "event_id": "uuid",
  "title": "Urgent notice",
  "message": "Road blocked near library",
  "latitude": 25.0173,
  "longitude": 121.5397,
  "severity": "urgent",
  "distance_meters": 120.0
}
```

## Redis 資料設計

建議 key：

| Key | 類型 | 用途 |
|-----|------|------|
| `realtime_map_notice:user:locations` | GEO set | 儲存使用者目前座標 |
| `realtime_map_notice:user:last_seen:{user_id}` | String with TTL | 記錄使用者最後上傳時間 |
| `realtime_map_notice:user:{user_id}:notifications` | Pub/Sub channel | 指定使用者通知 channel |

位置資料的 TTL 策略：

- GEO set 本身沒有針對單一 member 的 TTL。
- 可用 `last_seen` 輔助判斷使用者是否仍在線。
- Event Service 查到附近使用者後，應檢查 last_seen 是否仍有效，避免通知太久沒上線的人。
- Demo 建議 last_seen TTL 設為 60 秒；正式版本可依電量、移動速度與隱私需求調整。

## 非功能需求

效能：

- Location Service 需承受大量短請求。
- 壓測目標為 3,000 位虛擬使用者每秒更新一次座標。
- Event Service 發布事件時，500 位附近使用者的通知延遲目標小於 2 秒。

可靠性：

- Notification Service 至少 2-3 個 replicas。
- 刪除任一 Notification Pod 後，系統仍可接受新的 WebSocket 連線。
- Redis 若失效，位置查詢與通知都會受影響，Demo 前需確認 Redis Pod 狀態。

安全與隱私：

- Demo 階段使用假 user_id，不收集真實個資。
- 正式版本需加入認證、授權與位置資料保存期限。
- 位置資料不應長期保存，除非使用者明確同意。

## 資料流

位置更新流程：

```text
Web App -> Location Service -> Redis GEO
```

事件推播流程：

```text
Web App -> Event Service -> Redis GEO nearby query
Event Service -> Notification Service -> Redis Pub/Sub -> WebSocket -> Web App
```

## 區域推播邏輯

1. 使用者發布事件，包含標題、內容、座標、嚴重程度與推播半徑。
2. Event Service 使用 Redis GEO 查詢事件座標 500 公尺內的使用者。
3. Event Service 對每個附近使用者呼叫 Notification Service。
4. Notification Service 將通知發布到該使用者的 Redis Pub/Sub channel。
5. 持有該使用者 WebSocket 連線的 Notification Service Pod 收到訊息並推送到 Web App。

## Kubernetes 展示點

Auto-scaling:

- 使用 Python 腳本模擬 3,000 位使用者。
- 大量請求打到 Location Service。
- HPA 偵測 CPU 使用率上升後，將 Pod 從 1 個擴展到最多 5 個。

Fault tolerance:

- Notification Service 設定多副本。
- Demo 時手動刪除其中一個 Pod。
- Kubernetes 會自動重建 Pod。
- Service 會持續把流量導向健康 Pod。

Observability:

- 使用 `kubectl get pods -w` 觀察 Pod 狀態。
- 使用 `kubectl get hpa -w` 觀察自動擴展。
- 使用服務健康檢查 `/healthz` 判斷容器是否正常。

## 已確認的改善項目

### CORS

目前三個後端服務都沒有設定 CORS middleware。前端開發伺服器（如 Vite port 5173）與後端（port 8001-8003）不同 origin，瀏覽器會直接阻擋跨來源請求。第一階段必須加入 `fastapi.middleware.cors.CORSMiddleware`，否則 Web App 無法串接 API。

### WebSocket 心跳

Notification Service 目前沒有 ping/pong 機制。當使用者因為網路問題斷線時，服務端不會發現，導致 ghost connection 持續佔用資源。需補上 WebSocket 心跳：

- 伺服器定時發送 ping frame。
- 客戶端回覆 pong。
- 逾時未回應則主動關閉連線並清理 pubsub subscription。

### Event Service 同步通知瓶頸

目前 Event Service 對每個附近使用者發送一次 HTTP POST 給 Notification Service。若半徑內有 500 位使用者，Event Service 需要發送 500 次 HTTP 請求，且是序列執行（透過 `async for`），可能導致事件發布延遲數秒。

考量方向：

- 改用 `asyncio.gather` 批次發送，而不是逐個 await。
- 或讓 Event Service 直接發布 Redis Pub/Sub，跳過 HTTP 層，減少中間跳數。

### Event Service 多副本冪等性

Kubernetes 中 event-service 設為 2 個 replica。當多個副本同時收到同一事件時，目前沒有冪等機制，可能導致同一通知重複發送。Event Service 需要實作事件去重，或在通知流程中加入請求 ID 比對。

## 初步限制

- 尚未設計正式使用者帳號與權限。
- 即時位置目前只保留短期用途，不作長期軌跡分析。
- WebSocket 推播為初步架構，正式產品需要補上斷線重連、訊息確認與離線通知。
- 500 公尺為預設 Demo 半徑，未來可依事件類型調整。

# 即時性與地圖地點更新需求

這份文件說明 `realtime_map_notice` 要做到「即時」與「地圖地點更新」需要哪些技術、資料欄位、更新頻率與驗收標準。它補足一個關鍵問題：系統不是只把事件存在地圖上，而是要讓使用者位置、事件位置與附近通知能在短時間內同步更新。

## 即時性的定義

本專題中的「即時」不是毫秒級金融交易，而是校園情境下使用者能感受到資訊接近現況。

建議目標：

| 項目 | 目標 |
|------|------|
| 使用者位置上傳頻率 | 每 1-3 秒一次，Demo 預設每 1 秒 |
| Web App 地圖使用者位置更新 | 收到新定位後 1 秒內更新畫面 |
| Location Service API 延遲 | 單次 `POST /locations` 目標小於 200ms |
| 附近查詢延遲 | `GEOSEARCH 500m` 目標小於 100ms |
| 緊急事件推播延遲 | 發布事件後 1-2 秒內通知附近使用者 |
| WebSocket 重連時間 | 首次重連 1 秒，之後 exponential backoff |
| 使用者在線有效期限 | last_seen 超過 60 秒視為離線或不可靠 |

Demo 時可以說明：只要使用者在校園中移動，系統會持續更新 Redis 中的目前位置；當事件發生時，後端查到的是接近當下的使用者座標，而不是很久以前的資料。

## 地圖地點更新包含什麼

地圖上的「地點更新」分成三種：

1. 使用者目前位置更新。
2. 地圖事件標記更新。
3. 通知事件位置更新。

### 使用者目前位置更新

來源：browser Geolocation API。

流程：

```text
Browser Geolocation -> Web App state -> POST /locations -> Redis GEO -> Map marker update
```

Web App 需要做：

- 使用 `navigator.geolocation.watchPosition` 或定時 `getCurrentPosition`。
- 取得新座標後更新畫面上的使用者 marker。
- 將座標送到 Location Service。
- 顯示定位精度，例如 accuracy circle。
- 定位失敗時提供手動選點或預設座標。

### 地圖事件標記更新

來源：使用者發布事件，或 WebSocket 收到附近事件通知。

流程：

```text
POST /events -> Event Service -> Notification Service -> WebSocket -> Web App adds marker
```

Web App 需要做：

- 發布事件成功後，在地圖上新增事件 marker。
- 收到 WebSocket 通知後，在地圖上新增或更新事件 marker。
- 根據事件嚴重程度改變 marker 樣式。
- 緊急事件 marker 應更醒目，並可搭配通知 Banner。

### 通知事件位置更新

來源：Notification Service WebSocket message。

流程：

```text
Redis Pub/Sub -> Notification Service -> WebSocket -> Notification Banner -> Map flyTo event
```

Web App 需要做：

- 收到緊急事件後顯示 Banner。
- Banner 顯示事件標題、距離與時間。
- 使用者點擊「查看位置」後，地圖移動到事件座標。
- 通知關閉後，事件仍保留在事件列表與地圖 marker 中。

## 前端需要的技術

| 技術 | 用途 |
|------|------|
| React + Vite | 建立互動式 Web App |
| browser Geolocation API | 取得使用者目前經緯度 |
| Leaflet / MapLibre GL JS / Google Maps | 顯示地圖、marker、路徑與事件點 |
| WebSocket client | 接收附近事件通知 |
| Fetch API | 呼叫 Location Service 與 Event Service |
| State management | 保存目前位置、事件列表、連線狀態 |
| reconnect with exponential backoff | WebSocket 斷線後自動恢復 |
| throttling / debouncing | 控制位置上傳頻率，避免過度請求 |

建議前端狀態：

```typescript
type UserLocation = {
  userId: string;
  latitude: number;
  longitude: number;
  accuracyMeters?: number;
  headingDegrees?: number;
  speedMetersPerSecond?: number;
  updatedAt: string;
  source: "gps" | "manual" | "simulator";
};

type MapEvent = {
  eventId: string;
  title: string;
  message: string;
  category: "seat" | "crowd" | "activity" | "lost_found" | "traffic" | "safety" | "other";
  severity: "info" | "important" | "urgent";
  latitude: number;
  longitude: number;
  radiusMeters: number;
  createdAt: string;
  distanceMeters?: number;
};
```

## 後端需要的技術

| 技術 | 用途 |
|------|------|
| FastAPI | 提供 Location/Event/Notification API |
| Redis GEO | 儲存與查詢使用者即時位置 |
| Redis string TTL | 保存 last_seen，判斷位置是否仍有效 |
| Redis Pub/Sub | 多副本 Notification Service 的通知同步 |
| WebSocket | 對前端主動推送附近事件 |
| asyncio | 批次通知大量附近使用者 |
| Kubernetes HPA | Location Service 高流量時自動擴展 |

## 位置更新資料欄位

目前最小欄位：

```json
{
  "user_id": "u-0001",
  "latitude": 25.0173,
  "longitude": 121.5397
}
```

建議正式欄位：

```json
{
  "user_id": "u-0001",
  "latitude": 25.0173,
  "longitude": 121.5397,
  "accuracy_meters": 15,
  "heading_degrees": 180,
  "speed_mps": 1.2,
  "client_timestamp": "2026-05-24T10:15:30Z",
  "sequence": 42,
  "source": "gps"
}
```

欄位說明：

| 欄位 | 必要 | 說明 |
|------|------|------|
| `user_id` | 是 | Demo 階段可用假 ID，例如 `u-0001` |
| `latitude` | 是 | 緯度，範圍 -90 到 90 |
| `longitude` | 是 | 經度，範圍 -180 到 180 |
| `accuracy_meters` | 建議 | 瀏覽器定位精度，地圖可用圓形範圍呈現 |
| `heading_degrees` | 選擇 | 使用者移動方向，可用於方向箭頭 |
| `speed_mps` | 選擇 | 移動速度，可用於過濾不合理跳動 |
| `client_timestamp` | 建議 | 前端取得座標時間 |
| `sequence` | 建議 | 避免舊位置覆蓋新位置 |
| `source` | 建議 | `gps`、`manual`、`simulator` |

## Redis 需要保存的資料

### 即時位置

Key:

```text
realtime_map_notice:user:locations
```

Redis type:

```text
GEO set
```

內容：

```text
member = user_id
longitude = longitude
latitude = latitude
```

操作：

```text
GEOADD realtime_map_notice:user:locations longitude latitude user_id
GEOSEARCH realtime_map_notice:user:locations FROMLONLAT longitude latitude BYRADIUS 500 m
```

### 最後上線時間

Key:

```text
realtime_map_notice:user:last_seen:{user_id}
```

Redis type:

```text
String with TTL
```

內容：

```json
{
  "updated_at": "2026-05-24T10:15:30Z",
  "accuracy_meters": 15,
  "sequence": 42
}
```

用途：

- 判斷查到的 nearby user 是否仍在線。
- 過濾太久沒有更新位置的使用者。
- Demo 時可說明不是所有 Redis GEO 中的 user 都一定會收到通知，還要看 last_seen 是否有效。

### 使用者通知 channel

Key pattern:

```text
realtime_map_notice:user:{user_id}:notifications
```

Redis type:

```text
Pub/Sub channel
```

用途：

- Event Service 或 Notification Service 發布指定使用者通知。
- 持有該使用者 WebSocket 連線的 Notification Service Pod 訂閱 channel。

## 地圖事件資料欄位

事件最小欄位：

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

建議正式欄位：

```json
{
  "event_id": "uuid",
  "title": "Library seats",
  "message": "3F has seats near windows",
  "category": "seat",
  "severity": "info",
  "latitude": 25.0173,
  "longitude": 121.5397,
  "radius_meters": 500,
  "created_by": "u-0001",
  "created_at": "2026-05-24T10:15:30Z",
  "expires_at": "2026-05-24T10:45:30Z"
}
```

需要 `expires_at` 的原因：

- 座位、人潮、活動都具有時效性。
- 地圖不應永久保留過期事件。
- Demo 可以設定 30 分鐘過期，避免地圖越來越亂。

## 即時更新流程

### 使用者位置更新

```text
1. Web App 取得 GPS 座標。
2. Web App 更新地圖上的目前位置 marker。
3. Web App 呼叫 POST /locations。
4. Location Service 驗證座標範圍。
5. Location Service 寫入 Redis GEO。
6. Location Service 更新 last_seen TTL。
7. Event Service 未來查詢附近使用者時使用這份最新資料。
```

### 緊急事件附近推播

```text
1. 使用者在 Web App 上發布 urgent 事件。
2. Event Service 收到事件座標與 radius_meters。
3. Event Service 使用 Redis GEOSEARCH 查詢附近 user_id。
4. Event Service 檢查 last_seen，過濾離線或過期使用者。
5. Event Service 建立 notification payload。
6. Notification Service 發布到 Redis Pub/Sub channel。
7. 對應 WebSocket 連線收到通知。
8. Web App 顯示 Banner，並在地圖上新增事件 marker。
```

## 更新頻率策略

位置更新太慢會不即時，太快會造成不必要流量。建議策略：

| 情境 | 更新頻率 |
|------|----------|
| Demo 壓測 | 每 1 秒 |
| 一般使用者靜止 | 每 5-10 秒或位置變化超過 10m |
| 一般使用者移動 | 每 2-3 秒 |
| 發布事件前 | 立即取得一次最新位置 |
| WebSocket 斷線 | 不影響位置上傳，但通知狀態需顯示重連中 |

前端可加入條件：

- 若距離上次位置小於 5-10 公尺，可以只更新地圖，不一定上傳。
- 若 accuracy 大於 100 公尺，提示定位精度不足。
- 若 sequence 小於伺服器已知 sequence，不應覆蓋新位置。

## 即時性風險與處理

| 風險 | 影響 | 處理方式 |
|------|------|----------|
| 瀏覽器定位被拒絕 | 無法取得目前位置 | 手動選點或預設校園座標 |
| GPS 漂移 | 使用者位置跳動 | 顯示 accuracy circle，過濾不合理跳動 |
| 前端上傳太頻繁 | 後端壓力過大 | throttling、位置變化門檻 |
| Redis GEO 無 per-member TTL | 查到離線使用者 | 搭配 last_seen TTL |
| WebSocket 斷線 | 收不到即時通知 | reconnect with exponential backoff |
| 多副本 Notification Service | 使用者連在不同 Pod | Redis Pub/Sub 同步通知 |
| 壓測流量太高 | 本機卡住或 HPA 未觸發 | 先用 300/1000 人，再展示 3000 人設定 |

## 驗收標準

前端：

- 地圖上目前位置會隨定位更新。
- 定位失敗時可用手動選點或預設座標。
- WebSocket 斷線會顯示重連狀態。
- 收到通知後，地圖會新增事件 marker。
- 點擊通知可移動地圖到事件座標。

後端：

- `POST /locations` 能持續接收高頻座標更新。
- Redis GEO 中 user_id 座標會更新為最新位置。
- last_seen 可用來判斷使用者是否仍在線。
- `GEOSEARCH 500m` 能查出正確附近使用者。
- 緊急事件通知可在 1-2 秒內送達附近使用者。

Kubernetes:

- 壓測期間 Location Service 可水平擴展。
- Pod 重啟後新請求仍可被服務。
- Notification Service 多副本下仍可正確推播。


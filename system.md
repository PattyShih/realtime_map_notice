# System Design

`realtime_map_notice` 採用微服務架構，將高頻位置更新、事件處理與即時通知拆成不同服務，方便展示 Kubernetes 的擴展與容錯能力。

## 核心問題

這個系統的技術挑戰有兩個：

- 持續不斷的座標更新：大量使用者每秒上傳 GPS 位置。
- 瞬間的區域推播：事件發生後，需要快速找出 500 公尺內使用者並通知。

因此系統不適合每次都把即時座標寫入傳統關聯式資料庫。初步設計使用 Redis GEO 儲存目前位置，讓後端可以快速執行附近查詢。

## 系統元件

Mobile App:

- 使用 SwiftUI 建立介面。
- 使用 MapKit 顯示地圖與事件。
- 定期上傳目前 GPS 座標。
- 透過 WebSocket 接收附近事件通知。

Location Service:

- 接收 `POST /locations`。
- 將使用者目前座標寫入 Redis GEO。
- 是主要高併發入口，也是 HPA 自動擴展展示對象。

Event Service:

- 接收 `POST /events`。
- 使用事件座標查詢半徑內使用者。
- 呼叫 Notification Service 發送通知。

Notification Service:

- 維護 WebSocket 連線。
- 接收指定 user_id 的通知請求。
- 使用 Redis Pub/Sub 支援多副本推播。

Redis:

- 使用 GEOADD 儲存使用者目前位置。
- 使用 GEOSEARCH 查詢指定座標附近使用者。
- 使用 Pub/Sub 協助 Notification Service 多副本同步通知。

Kubernetes:

- 使用 Deployment 管理每個微服務。
- 使用 Service 提供穩定內部網路入口。
- 使用 HPA 讓 Location Service 依 CPU 自動擴展。
- 使用多副本 Notification Service 展示容錯。

## 資料流

位置更新流程：

```text
iOS App -> Location Service -> Redis GEO
```

事件推播流程：

```text
iOS App -> Event Service -> Redis GEO nearby query
Event Service -> Notification Service -> Redis Pub/Sub -> WebSocket -> iOS App
```

## 區域推播邏輯

1. 使用者發布事件，包含標題、內容、座標、嚴重程度與推播半徑。
2. Event Service 使用 Redis GEO 查詢事件座標 500 公尺內的使用者。
3. Event Service 對每個附近使用者呼叫 Notification Service。
4. Notification Service 將通知發布到該使用者的 Redis Pub/Sub channel。
5. 持有該使用者 WebSocket 連線的 Notification Service Pod 收到訊息並推送到 App。

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

## 初步限制

- 尚未設計正式使用者帳號與權限。
- 即時位置目前只保留短期用途，不作長期軌跡分析。
- WebSocket 推播為初步架構，正式產品需要補上斷線重連、訊息確認與離線通知。
- 500 公尺為預設 Demo 半徑，未來可依事件類型調整。


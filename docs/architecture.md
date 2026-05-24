# 架構說明

## 核心資料流

```mermaid
flowchart LR
    App["iOS App<br/>SwiftUI + MapKit"] -->|POST /locations| Location["Location Service"]
    Location -->|GEOADD| Redis[("Redis GEO")]
    App -->|POST /events| Event["Event Service"]
    Event -->|GEOSEARCH 500m| Redis
    Event -->|POST /notify/{user_id}| Notify["Notification Service"]
    Notify -->|PUBLISH user channel| Redis
    Redis -->|SUBSCRIBE user channel| Notify
    Notify -->|WebSocket| App
```

## 微服務職責

Location Service:

- 高頻接收使用者 GPS 更新
- 將座標寫入 Redis GEO index
- 是 K8s HPA 的主要展示對象

Event Service:

- 接收插旗事件
- 根據事件座標查詢 500 公尺內使用者
- 呼叫 Notification Service 推播

Notification Service:

- 維護手機 App 的 WebSocket 連線
- 使用 Redis Pub/Sub 解決多副本時的連線分散問題
- 對指定 user_id 推送事件通知
- 可用多副本展示 Pod 被刪除後仍可服務

Redis:

- 使用 GEOADD / GEOSEARCH 暫存即時位置
- 適合高頻率、低延遲的座標查詢

## K8s 展示重點

- Deployment: 微服務容器化部署
- Service: 穩定內部 DNS 與流量導向
- HPA: Location Service 依 CPU 使用率從 1 擴展到 5
- Readiness/Liveness Probe: 自動偵測服務健康狀態
- Replica: Notification Service 多副本容錯

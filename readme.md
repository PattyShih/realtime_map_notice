# realtime_map_notice

`realtime_map_notice` 是一個專屬校園或特定街區使用的「即時動態地圖 App」專題初步架構。使用者可以在地圖上插旗回報突發狀況，例如圖書館座位、學餐排隊、人潮、免費活動、遺失物或緊急事件。

專案核心亮點是：當有人發布緊急事件時，系統只通知目前位於該座標 500 公尺內的使用者，減少傳統論壇或群組常見的資訊延遲與無關通知。

## 專題目標

- 建立一個能展示即時地圖、即時定位與區域推播的 App 架構。
- 使用微服務拆分位置更新、事件發布與通知推播。
- 使用 Redis 暫存即時座標，支援快速查詢附近使用者。
- 使用 WebSocket 讓伺服器主動推播事件到使用者端。
- 使用 Kubernetes 展示高併發、自動擴展與容錯能力。
- 使用 Python 腳本模擬 3,000 名虛擬使用者持續移動與上傳 GPS 座標。

## 使用情境

一般事件：

- 圖書館 3 樓目前有空位。
- 學餐某攤排隊人潮很長。
- 校園廣場有免費活動。
- 某棟大樓附近有遺失物。

緊急事件：

- 路上有走失的狗狗。
- 某區域施工或封路。
- 天橋或走道臨時無法通行。
- 校內突發安全提醒。

緊急事件會依照事件座標查詢半徑 500 公尺內的使用者，再透過 WebSocket 推播。

## 初步專案結構

```text
realtime_map_notice/
├── backend/
│   ├── location-service/        # 接收 GPS 座標更新
│   ├── event-service/           # 發布事件與查詢附近使用者
│   ├── notification-service/    # WebSocket 即時推播
│   └── shared/                  # 共用 schema、設定與 Redis client
├── mobile-ios/                  # SwiftUI / MapKit App 草稿
├── simulator/                   # 3,000 虛擬使用者壓測腳本
├── k8s/                         # Kubernetes Deployment、Service、HPA
├── docs/                        # 補充文件
├── docker-compose.yml           # 本機開發環境
├── README.md                    # 專案總覽
├── DEVELOPMENT.md               # 開發與 Demo 流程
└── SYSTEM.md                    # 系統架構設計
```

## 技術選型

- Mobile App: SwiftUI, MapKit
- Backend API: Python FastAPI
- Realtime: WebSocket
- Realtime Location Store: Redis GEO
- Container: Docker
- Orchestration: Kubernetes
- Autoscaling: Horizontal Pod Autoscaler
- Load Simulation: Python asyncio + httpx

## 四人分工

- 成員 A：iOS App、SwiftUI、MapKit、UI/UX。
- 成員 B：後端 API、事件發布、商業邏輯。
- 成員 C：Redis GEO、WebSocket、即時推播。
- 成員 D：Docker、Kubernetes、HPA、壓測與 Demo。

## 相關文件

- [DEVELOPMENT.md](./DEVELOPMENT.md)：開發環境、執行方式、Demo 流程。
- [SYSTEM.md](./SYSTEM.md)：系統架構、服務職責、資料流與 K8s 展示重點。


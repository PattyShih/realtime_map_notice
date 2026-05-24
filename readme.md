# realtime_map_notice

`realtime_map_notice` 是一個專屬校園或特定街區使用的「即時動態地圖 Web App」專題初步架構。使用者可以在地圖上插旗回報突發狀況，例如圖書館座位、學餐排隊、人潮、免費活動、遺失物或緊急事件。

專案核心亮點是：當有人發布緊急事件時，系統只通知目前位於該座標 500 公尺內的使用者，減少傳統論壇或群組常見的資訊延遲與無關通知。

## 專題目標

- 建立一個能展示即時地圖、即時定位與區域推播的 Web App 架構。
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
├── web-app/                     # Web 前端草稿
├── simulator/                   # 3,000 虛擬使用者壓測腳本
├── k8s/                         # Kubernetes Deployment、Service、HPA
├── docs/                        # 補充文件
├── docker-compose.yml           # 本機開發環境
├── readme.md                    # 專案總覽
├── development.md               # 開發與 Demo 流程
└── system.md                    # 系統架構設計
```

## 技術選型

- Web App: React + Vite, browser Geolocation API, map library（待決定 Leaflet / MapLibre GL JS / Google Maps）
- Backend API: Python FastAPI
- CORS: fastapi.middleware.cors.CORSMiddleware（各服務需加入）
- Realtime: WebSocket（需補上 ping/pong 心跳）
- Realtime Location Store: Redis GEO
- Container: Docker
- Orchestration: Kubernetes
- Autoscaling: Horizontal Pod Autoscaler
- Load Simulation: Python asyncio + httpx
- Testing（待補）: pytest, httpx.AsyncClient, fakeredis

## 四人分工

- 成員 A：Web App、地圖介面、瀏覽器定位、UI/UX。
- 成員 B：後端 API、事件發布、商業邏輯。
- 成員 C：Redis GEO、WebSocket、即時推播。
- 成員 D：Docker、Kubernetes、HPA、壓測與 Demo。

## 專案階段（十週計畫）

詳細每週進度表請見 [docs/project-plan.md](./docs/project-plan.md) 的「十週進度表」章節。

第一階段（第 1-2 週）：先完成可展示的系統骨架：後端三個微服務、Redis GEO、WebSocket、Docker Compose、K8s YAML 與壓測腳本。

第二階段（第 3-5 週）：完成 Web App 與後端整合：地圖顯示、瀏覽器定位、事件插旗、附近事件通知、基本錯誤處理與 Demo 資料。

第三階段（第 4-6 週）：即時推播整合與後端優化：多副本通知正確性、WebSocket 心跳、批次推送、冪等性。

第四階段（第 6-8 週）：K8s 部署、HPA 自動擴展、Pod 容錯、3,000 人壓測。

第五階段（第 8-10 週）：報告、架構圖、Demo 演練與最終展示。

## 相關文件

- [development.md](./development.md)：開發環境、執行方式、Demo 流程。
- [system.md](./system.md)：系統架構、服務職責、資料流與 K8s 展示重點。
- [docs/project-plan.md](./docs/project-plan.md)：詳細開發計畫、分工、里程碑與驗收標準。

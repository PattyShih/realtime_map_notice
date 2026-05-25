# realtime_map_notice

`realtime_map_notice` 是一個專屬校園或特定街區使用的「即時動態地圖 Web App」專題初步架構。使用者可以在地圖上插旗回報突發狀況，例如圖書館座位、學餐排隊、人潮、免費活動、遺失物或緊急事件。

專案核心亮點是：當有人發布緊急事件時，系統只通知目前位於該座標 500 公尺內的使用者，減少傳統論壇或群組常見的資訊延遲與無關通知。

## 專題目標

- 建立一個能展示即時地圖、即時定位與區域推播的 Web App 架構。
- 使用微服務拆分位置更新、事件發布與通知推播。
- 使用 Redis 暫存即時座標，支援快速查詢附近使用者。
- 定義即時位置更新資料、更新頻率與地圖標記同步策略。
- 使用 WebSocket 讓伺服器主動推播事件到使用者端。
- 使用 Kubernetes 展示高併發、自動擴展與容錯能力。
- 使用 Python 腳本模擬初期 500-1,000 名虛擬使用者持續移動與上傳 GPS 座標，進階展示可挑戰 3,000 人。

## 目前狀態

目前 repo 已完成專題初步骨架與文件規劃：

- 已建立三個後端服務的目錄與初版 FastAPI 程式。
- 已建立 Redis GEO 位置儲存與 WebSocket 通知的基本方向。
- 已建立 Dockerfile、docker-compose 與 Kubernetes YAML。
- 已建立壓測腳本，用來模擬大量虛擬使用者上傳座標。
- 已建立 Web App 前端方向文件，但尚未實作完整 React + Vite 前端。
- 已補上專案計畫、系統設計、測試計畫、Web App UI/UX 設計說明與 K8s 使用說明。

後續開發的優先順序是：補 `.dockerignore`、完成 Web App、測試與 K8s Demo。CORS middleware 已先加入三個後端服務。

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
├── web-app/                     # Web 前端（僅有 README，尚未實作）
├── simulator/                   # 500-1,000 虛擬使用者壓測腳本，進階可調到 3,000
├── k8s/                         # Kubernetes Deployment、Service、HPA
├── docs/                        # 補充文件
├── docker-compose.yml           # 本機開發環境
├── readme.md                    # 專案總覽
├── development.md               # 開發與 Demo 流程
└── system.md                    # 系統架構設計
```

## 技術選型

- Web App: React + Vite, browser Geolocation API, map library（初期建議 Leaflet；也可選 MapLibre GL JS / Google Maps）
- Backend API: Python FastAPI
- CORS: fastapi.middleware.cors.CORSMiddleware（已加入各後端服務，可用 `CORS_ALLOW_ORIGINS` 設定）
- Realtime: WebSocket（需補上 ping/pong 心跳）
- Realtime Location Store: Redis GEO
- Container: Docker
- Orchestration: Kubernetes
- Autoscaling: Horizontal Pod Autoscaler
- Load Simulation: Python asyncio + httpx
- Testing Plan: pytest, httpx.AsyncClient, fakeredis, Vitest, MSW, WebSocket tests

## 核心 API 摘要

| 服務 | Endpoint | 用途 |
|------|----------|------|
| Location Service | `POST /locations` | 接收使用者目前 GPS 座標並寫入 Redis GEO |
| Location Service | `GET /locations/nearby` | 查詢指定座標半徑內的使用者 |
| Event Service | `POST /events` | 建立事件並觸發附近使用者通知 |
| Notification Service | `GET /healthz` | 健康檢查 |
| Notification Service | `POST /notify/{user_id}` | 對指定使用者發布通知 |
| Notification Service | `WS /ws/{user_id}` | 前端 WebSocket 即時通知連線 |

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

第四階段（第 6-8 週）：K8s 部署、HPA 自動擴展、Pod 容錯、500-1,000 人壓測；進階展示再挑戰 3,000 人。

第五階段（第 8-10 週）：報告、架構圖、Demo 演練與最終展示。

## 相關文件

- [development.md](./development.md)：開發環境、執行方式、Demo 流程。
- [system.md](./system.md)：系統架構、API、即時位置、容量規劃、瓶頸與 K8s 展示重點。
- [docs/README.md](./docs/README.md)：文件導覽與閱讀順序。
- [docs/project-plan.md](./docs/project-plan.md)：詳細開發計畫、Demo 目標、四人分工、里程碑與驗收標準。
- [docs/test-plan.md](./docs/test-plan.md)：後端、前端、WebSocket 與跨服務測試規劃。
- [k8s/README.md](./k8s/README.md)：Kubernetes 部署、HPA 與故障復原操作。
- [web-app/README.md](./web-app/README.md)：Web App 前端開發方向、地圖服務、UI/UX 與 API key。

# 專案進度追蹤表

本文件用來即時更新 `realtime_map_notice` 的開發進度。`project-plan.md` 是原始計畫，這份 `progress.md` 是目前實際狀態。

最後更新：2026-05-26  
目前分支：`dev`  
目前定位：第 7 週末 / 第 8 週初  
整體進度估計：78%

## 狀態標記

| 標記 | 意義 |
|------|------|
| Done | 已完成並至少有基本驗證 |
| Partial | 已有實作，但仍缺整合測試、細節打磨或截圖 |
| Blocked | 因環境或相依條件卡住 |
| Pending | 尚未開始 |

## 總覽

| 階段 | 計畫週次 | 狀態 | 完成度 | 目前證據 | 下一步 |
|------|----------|------|--------|----------|--------|
| 第 1 階段：後端骨架 | 1-2 | Partial | 85% | 三個 FastAPI service、shared module、Dockerfile、docker-compose、CORS、`.dockerignore` 已存在 | 使用 Docker 實際跑 `docker compose up --build` |
| 第 2 階段：Web App 前端 | 3-5 | Partial | 75% | React + Vite + Leaflet 可 build，地圖 smoke test 可開啟 | 串接真實後端服務並測事件發布與通知 |
| 第 3 階段：即時資料與推播整合 | 4-6 | Partial | 80% | Redis GEO、last_seen 過濾、WebSocket Pub/Sub、heartbeat、fan-out limit、client_event_id 去重已實作 | 補跨服務整合測試與 Docker 實測 |
| 第 4 階段：Kubernetes 與壓測 | 6-8 | Partial | 80% | K8s YAML、HPA、resources、readiness/liveness probes、simulator、`scripts/k8s-*.ps1` 已存在 | Docker/K8s 環境可用後跑實機部署、HPA、500-1,000 人壓測 |
| 跨階段：自動化測試 | 7-8 | Partial | 35% | `tests/unit` 目前 23 個 unit tests 通過 | 補 API integration、Redis、WebSocket、前端測試 |
| 第 5 階段：報告與展示整理 | 8-10 | Partial | 30% | project-plan、system、demo 腳本初稿已存在 | 產出實測截圖、壓測數據、Demo 錄影或備案素材 |

## 必做功能進度

| 功能 | 狀態 | 完成度 | 備註 |
|------|------|--------|------|
| Web App 顯示地圖 | Done | 90% | Leaflet + OpenStreetMap 已可顯示；仍需更多 responsive QA |
| 使用者在地圖發布事件 | Partial | 70% | 前端表單與 Event Service 已有；尚未完成 docker-compose 真實整合測試 |
| 使用者位置定期上傳 | Partial | 75% | 前端定時上傳、後端 `POST /locations` 已有；尚未與 Redis 真實環境完整測 |
| 地圖 marker 隨資料更新 | Partial | 70% | local events 與 WS events 可顯示；仍需真實後端測試 |
| Redis GEO 即時位置 | Partial | 80% | GEOADD/GEOSEARCH 與 last_seen 過濾已實作；缺實體 Redis 整合測試 |
| 500 公尺區域通知 | Partial | 80% | Event Service 查 nearby + 通知 active users 已實作；缺端到端測試 |
| WebSocket 主動推播 | Partial | 80% | Pub/Sub + WebSocket + heartbeat 已實作；缺真實多 pod 測試 |
| 500-1,000 人 simulator | Partial | 70% | 腳本存在；尚未在 Docker/K8s 環境壓測 |
| K8s Location Service HPA | Partial | 80% | YAML 與觀察腳本已存在；尚未實際部署與截圖 |
| K8s Notification Pod 容錯 | Partial | 80% | 多副本 YAML 與刪 Pod 腳本已存在；尚未實際刪 Pod 驗證 |

## 測試與驗證

| 類別 | 狀態 | 最近結果 | 缺口 |
|------|------|----------|------|
| Python unit tests | Done | `python -m pytest tests/unit -v`，23 passed | 尚未加入 coverage 報告 |
| Python syntax check | Done | `python -m py_compile ...` 通過 | 無 |
| Frontend lint | Done | `npm run lint` 通過 | 無 |
| Frontend build | Done | `npm run build` 通過 | 無 |
| Web App smoke test | Done | `http://127.0.0.1:5173` 可開，地圖載入 | 仍需串後端 |
| Docker Compose | Blocked | 目前 shell 找不到 `docker` 指令 | 安裝/修正 Docker CLI PATH |
| API integration tests | Pending | 尚未建立 | Location/Event/Notification 真實 API 測試 |
| WebSocket integration tests | Pending | 尚未建立 | 連線、通知、heartbeat、斷線重連 |
| K8s deployment test | Partial | Repo 交付物完成；尚未實機跑 | Pod Running、Service、HPA、port-forward 截圖 |
| Load test | Partial | `scripts/k8s-load-test.ps1` 已建立；尚未實測 | 500、1,000 users 結果與截圖 |

## 目前阻塞

| 阻塞 | 影響 | 解法 | 優先級 |
|------|------|------|--------|
| Docker CLI 不可用 | 無法跑 docker-compose、Redis 實體整合測試、K8s image build | 確認 Docker Desktop 已安裝，並修正 PowerShell PATH | P0 |
| 尚未跑真實 Redis | 區域推播只靠 unit test，尚未驗證真實 GEO/PubSub 行為 | Docker 可用後先跑 docker-compose | P0 |
| 尚未跑 K8s | 無法展示 HPA 和 Pod 容錯截圖 | Docker/K8s 環境就緒後部署 | P1 |
| API/WebSocket integration tests 尚未建立 | 改動後缺少端到端回歸保障 | 補 `tests/integration` | P1 |

## 接下來建議工作順序

| 順序 | 工作 | 預期產出 | 負責角色 |
|------|------|----------|----------|
| 1 | 修好 Docker CLI / Docker Desktop 環境 | `docker --version` 可執行 | D |
| 2 | 跑 `docker compose up --build` | 三個後端服務 + Redis 全部健康 | B、C、D |
| 3 | 手動測完整資料流 | 位置寫入、事件建立、WebSocket 通知成功 | A、B、C |
| 4 | 補 API integration tests | Location/Event/Notification 基礎整合測試 | B、C |
| 5 | 補 WebSocket integration tests | 連線、通知、heartbeat、斷線情境 | C |
| 6 | K8s 部署與 HPA 驗證 | Pod/HPA 截圖、容錯截圖 | D |
| 7 | 500-1,000 人壓測 | 壓測結果與 Demo 截圖 | D |
| 8 | Demo 演練與報告素材整理 | 8-10 分鐘 Demo 可跑完 | 全員 |

## 更新紀錄

| 日期 | 更新內容 | 驗證 |
|------|----------|------|
| 2026-05-26 | 新增 Event Service fan-out concurrency limit 與選填 `client_event_id` 去重 | 23 unit tests、frontend lint/build 通過 |
| 2026-05-26 | 完成第 4 階段 repo 交付物：K8s probes/resources/env、HPA、壓測與 Demo 腳本、K8s 文件 | unit tests、frontend lint/build、Markdown 連結檢查通過；Docker/K8s 實機待環境可用 |
| 2026-05-26 | 擴充後端 unit tests，涵蓋 schema、active user 過濾、event handler、notification helper | 17 unit tests 通過 |
| 2026-05-25 | 改善即時通知流程：Event fan-out 併發、WebSocket heartbeat、last_seen 過濾 | unit tests、frontend lint/build 通過 |
| 2026-05-25 | 建立 Web App React + Vite + Leaflet 基礎 | frontend lint/build 通過 |
| 2026-05-25 | 擴充 `CLAUDE.md` agent 指引 | 文件提交至 dev |

## 每次更新檢查清單

- 更新「最後更新」日期。
- 更新階段總覽的狀態與完成度。
- 若完成或新增測試，更新「測試與驗證」。
- 若遇到環境問題，更新「目前阻塞」。
- 若完成重要功能，新增一筆「更新紀錄」。
- 若進度影響 Demo 腳本或架構描述，同步更新 [project-plan.md](./project-plan.md)、[../system.md](../system.md) 或 [../development.md](../development.md)。

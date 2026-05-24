# 容量規劃、動態資源調整與瓶頸

這份文件說明 `realtime_map_notice` 在少量使用、中量使用與大量使用時，系統需要如何調整 Kubernetes resources、replicas、HPA 與資料服務設定，以及各階段可能遇到的瓶頸。

## 使用量分級

本專題先用「虛擬使用者每秒上傳位置」作為主要容量指標。實際系統還會受到 WebSocket 連線數、事件發布頻率、附近使用者數量與 Redis 效能影響。

| 等級 | 虛擬使用者 | 位置更新頻率 | 約略位置更新量 | 目標 |
|------|------------|--------------|----------------|------|
| 少量使用 | 1-100 人 | 每 1-3 秒 | 30-100 req/s | 功能驗證、本機開發 |
| 中量使用 | 500-1,000 人 | 每 1 秒 | 500-1,000 req/s | 初期 Demo 與 HPA 展示 |
| 大量使用 | 3,000+ 人 | 每 1 秒 | 3,000+ req/s | 進階壓測與架構討論 |

初期目標是穩定展示 500-1,000 人。3,000 人是進階挑戰，不作為第一版必要成功標準。

## 動態調整原則

流量上升時，不是所有服務都需要一起放大。每個服務的壓力來源不同：

| 元件 | 主要壓力來源 | 擴展方式 |
|------|--------------|----------|
| Location Service | 高頻 `POST /locations` | HPA 增加 replicas |
| Event Service | 事件發布與附近查詢 | 增加 replicas、批次通知 |
| Notification Service | WebSocket 連線數、Pub/Sub 訊息量 | 增加 replicas、連線分散 |
| Redis | GEO 寫入、GEOSEARCH、Pub/Sub | 提高資源、獨立部署、必要時叢集化 |
| Web App | 地圖 marker 數量、通知渲染 | marker clustering、前端節流 |

## 少量使用：1-100 人

適用場景：

- 本機開發。
- API 功能測試。
- Demo 前基本流程確認。

建議設定：

| 元件 | replicas | CPU request | Memory request |
|------|----------|-------------|----------------|
| Location Service | 1 | 100m | 128Mi |
| Event Service | 1 | 100m | 128Mi |
| Notification Service | 1 | 100m | 128Mi |
| Redis | 1 | 100m | 128Mi |

可能瓶頸：

- 通常不會遇到後端效能瓶頸。
- 比較常遇到 CORS、環境變數、Redis 連線或 WebSocket 連線問題。
- 前端定位權限與地圖 API key 也可能比效能更容易出錯。

調整策略：

- 先確保 `/healthz` 正常。
- 用 10-100 人壓測確認 Location Service 沒有例外。
- 不急著開 HPA，先確認功能正確。

## 中量使用：500-1,000 人

適用場景：

- 初期 Demo 目標。
- HPA 自動擴展展示。
- 驗證 Redis GEO 是否足以支援即時查詢。

建議設定：

| 元件 | replicas | CPU request | Memory request | 調整重點 |
|------|----------|-------------|----------------|----------|
| Location Service | 1-5 | 100m-250m | 128Mi-256Mi | 啟用 HPA |
| Event Service | 2 | 100m-250m | 128Mi-256Mi | 避免單點處理事件 |
| Notification Service | 2-3 | 100m-250m | 128Mi-256Mi | 分散 WebSocket 連線 |
| Redis | 1 | 250m-500m | 256Mi-512Mi | 觀察 CPU 與記憶體 |

HPA 建議：

```yaml
minReplicas: 1
maxReplicas: 5
targetCPUUtilizationPercentage: 60
```

可能瓶頸：

- Location Service CPU 上升，因為每秒大量 HTTP request。
- Redis GEO 寫入量增加。
- Event Service 發布緊急事件時，如果半徑內有很多人，通知可能變慢。
- Notification Service 需要維持更多 WebSocket 連線。
- 本機 Docker Desktop 或 minikube 資源不足，導致 Pod scheduling 或 HPA 指標不穩。

調整策略：

- Location Service 使用 HPA 擴展。
- Event Service 通知改成 `asyncio.gather` 批次發送，避免逐一 await。
- Notification Service 至少 2 個 replicas。
- Redis 給足 memory request，避免被系統壓縮或重啟。
- 壓測時先從 500 人開始，再提高到 1,000 人。

## 大量使用：3,000+ 人

適用場景：

- 進階壓測。
- 報告中討論系統可擴展方向。
- 展示 Kubernetes 架構價值。

建議設定：

| 元件 | replicas | CPU request | Memory request | 調整重點 |
|------|----------|-------------|----------------|----------|
| Location Service | 3-10 | 250m-500m | 256Mi-512Mi | HPA maxReplicas 提高 |
| Event Service | 3-5 | 250m-500m | 256Mi-512Mi | 批次通知、冪等 |
| Notification Service | 3-6 | 250m-500m | 256Mi-512Mi | WebSocket 分散 |
| Redis | 1 或 managed Redis | 500m+ | 512Mi-1Gi+ | 觀察是否成為單點瓶頸 |

可能瓶頸：

- Redis 可能成為主要瓶頸，因為所有位置更新、附近查詢與 Pub/Sub 都依賴 Redis。
- Location Service replicas 增加後，Redis 寫入壓力也會同步增加。
- Event Service 如果對每位附近使用者發 HTTP request，會造成大量 fan-out。
- Notification Service 的單 Pod WebSocket 連線數太高時，記憶體與 event loop 壓力上升。
- Kubernetes node 本身 CPU/Memory 不足，HPA 想擴也排不上 Pod。

調整策略：

- 將 Redis 部署到資源較充足的節點或改用 managed Redis。
- 分離 Redis GEO 與 Redis Pub/Sub，避免互相影響。
- Event Service 直接發布 Redis Pub/Sub，減少 HTTP fan-out。
- 使用 queue 或 stream，例如 Redis Streams / Kafka，處理大量通知事件。
- Location Service 加入 rate limit 或 batch update，避免異常 client 打爆服務。
- WebSocket 連線採 sticky session 或集中連線層設計，視正式架構需求決定。

## 主要瓶頸分析

### 1. Location Service

瓶頸來源：

- 每個使用者定期上傳位置。
- HTTP request 數量與使用者數量線性成長。

症狀：

- CPU 使用率升高。
- API latency 增加。
- HPA replicas 增加。

處理方式：

- 啟用 HPA。
- 降低位置上傳頻率，例如靜止時 5-10 秒才上傳。
- 前端加入移動距離門檻，例如移動超過 10 公尺才上傳。
- 後端只做輕量驗證與 Redis 寫入，不做複雜計算。

### 2. Redis

瓶頸來源：

- `GEOADD` 寫入量高。
- `GEOSEARCH` 查詢頻繁。
- Pub/Sub 同時承擔通知分發。

症狀：

- Redis CPU 飆高。
- Location Service latency 增加。
- Event Service 查詢附近使用者變慢。
- Notification delivery delay 增加。

處理方式：

- 提高 Redis CPU/Memory。
- 分離 location Redis 與 notification Redis。
- 使用 managed Redis 或 Redis Cluster。
- 避免把長期歷史資料也塞進同一個 Redis。
- 對附近查詢半徑與頻率做限制。

### 3. Event Service

瓶頸來源：

- 一次事件需要通知很多附近使用者。
- 目前流程若逐一 HTTP POST 到 Notification Service，fan-out 成本高。

症狀：

- `POST /events` 回應變慢。
- delivered_count 計算耗時。
- 大量通知時 Event Service CPU 與 network usage 上升。

處理方式：

- 使用 `asyncio.gather` 批次發送。
- 改成 Event Service 發布到 Redis Pub/Sub 或 Redis Streams。
- 將事件建立與通知發送拆成非同步背景任務。
- 加入 idempotency key，避免重複通知。

### 4. Notification Service

瓶頸來源：

- WebSocket 長連線數。
- Redis Pub/Sub 訊息量。
- 每個 Pod 需要維護多個 client 狀態。

症狀：

- 記憶體上升。
- WebSocket 斷線增加。
- 通知延遲或漏送。

處理方式：

- 增加 replicas。
- 實作 ping/pong 心跳與斷線清理。
- 控制單 Pod 最大連線數。
- 使用 Redis Pub/Sub 讓任一 Pod 都能收到通知。
- 正式架構可考慮獨立 realtime gateway。

### 5. Web App

瓶頸來源：

- 地圖 marker 太多。
- 頻繁重新 render。
- 通知與事件列表過長。

症狀：

- 瀏覽器卡頓。
- 地圖拖曳不順。
- 手機瀏覽器耗電。

處理方式：

- 只顯示目前視窗範圍內的事件。
- 使用 marker clustering。
- 限制事件列表數量。
- 對位置更新做 throttling。
- 緊急事件優先顯示，一般事件低干擾更新。

## 動態調整指標

建議觀察：

| 指標 | 用途 |
|------|------|
| `kubectl top pods` | 查看 Pod CPU/Memory |
| HPA current/target CPU | 判斷是否需要擴展 |
| Location Service latency | 判斷位置更新是否延遲 |
| Redis CPU/Memory | 判斷 Redis 是否成為瓶頸 |
| WebSocket connection count | 判斷 Notification Service 壓力 |
| Notification delivery latency | 判斷事件推播是否即時 |
| Error rate | 判斷是否有服務過載 |

Demo 可用指令：

```powershell
kubectl -n realtime-map-notice get hpa -w
kubectl -n realtime-map-notice get pods -w
kubectl -n realtime-map-notice top pods
kubectl -n realtime-map-notice describe hpa location-service-hpa
```

## 資源調整建議表

| 狀況 | 可能原因 | 調整 |
|------|----------|------|
| Location Service CPU 高 | 位置更新流量上升 | 提高 maxReplicas、降低 target CPU、增加 CPU request |
| Redis CPU 高 | GEOADD/GEOSEARCH 太多 | 提高 Redis resources、分離 Redis、降低更新頻率 |
| Event Service 回應慢 | 通知 fan-out 太多 | 批次發送、背景任務、Redis Streams |
| Notification 記憶體高 | WebSocket 連線多 | 增加 replicas、心跳清理、限制單 Pod 連線數 |
| HPA 不擴展 | metrics-server 或 CPU request 問題 | 檢查 `kubectl top pods`、調整 requests |
| 前端卡頓 | marker 太多 | clustering、viewport filtering、限制列表數量 |

## 報告可說明重點

- 少量使用重點是功能正確。
- 中量使用重點是 HPA 能根據 Location Service 壓力自動擴展。
- 大量使用重點是找出瓶頸，尤其 Redis、Event fan-out 與 WebSocket 連線管理。
- 微服務的價值在於不同服務可以依照自己的壓力來源獨立調整。
- Kubernetes 的價值不只是部署，而是能用 HPA、replica、resource requests/limits 做動態調整。


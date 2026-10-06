# ops-dashboard:壓測觸發與容器擴展可視化

給「K8s/Docker 應用」demo 用的輕量運維頁:一顆按鈕模擬大量使用者湧入,即時看到
各服務 CPU 曲線、location-service 副本數擴展(1→3)與自動擴展事件紀錄。

## 啟動(本機,需 Node ≥ 18 與 Docker)

```bash
# 先確認後端已在跑:docker compose up -d
node ops-dashboard/server.js
# 開啟 http://localhost:8090
```

零 npm 依賴;PORT 以 `OPS_PORT` 環境變數調整。

## 兩種模式(啟動時自動偵測)

| | compose 模式(預設) | k8s 模式 |
|---|---|---|
| 偵測條件 | 無 `realtime-map-notice` 命名空間 | `kubectl get ns realtime-map-notice` 成功 |
| 壓測 | 一次性容器跑 `simulator/simulate_users.py` | `load-generator` Job(叢集內) |
| 分流 | ops 內建 round-robin proxy(等效 K8s Service) | kube-proxy |
| 擴展 | ops 模擬 HPA(見下) | 真 HPA |
| 指標 | `docker stats` | `kubectl top pods` + HPA status |

### compose 模式的模擬 HPA 規則(門檻可用環境變數調整)

- location-service 平均 CPU ≥ **25%**(`OPS_SCALE_UP_CPU`,連續 2 次確認)→ 增加 1 副本(最多 **3**)
- 平均 CPU ≤ **8%**(`OPS_SCALE_DOWN_CPU`)連續 **3 次**(9 秒)→ 移除 1 副本
- 額外副本名稱 `ops-location-r2` / `ops-location-r3`,發布到主機 `:18001` / `:18002`
- 壓測流量路徑:模擬容器 → `host.docker.internal:8090/fwd/location/*` → ops 輪詢轉發到各副本
- 模擬人數 > 800 時自動拆成 2 個 worker 容器、> 1600 拆 3 個——單一 asyncio 模擬程序
  約 800 人後自身飽和(與 k8s/README.md 的教訓一致),多 worker 才推得動後端 CPU

### k8s 模式

- 狀態:`kubectl get pods`、`kubectl top pods`、`kubectl get hpa`
- 壓測:更新 `simulator-code` ConfigMap → 重建 load-generator Job(`--users` 由按鈕帶入)
- 擴縮完全交給叢集內 HPA,儀表板顯示 `currentReplicas / desiredReplicas / CPU%`

## 已知限制

- 本機 demo 用途,勿部署到對外環境(ops 具備啟停容器/Job 的能力,無鑑別)
- compose 模式的副本「擴展」是真實容器 + 真實分流,但 HPA 判斷由 ops 模擬;
  要展示真 HPA,請在 Docker Desktop 啟用 Kubernetes 後重新啟動本服務(自動切 k8s 模式)
- 單一模擬程序約 1500 人後自身飽和(見 k8s/README.md),demo 建議 300–1000 人

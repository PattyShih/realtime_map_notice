# ops-dashboard:壓測觸發與容器擴展可視化

給「K8s/Docker 應用」demo 用的輕量運維頁:一顆按鈕模擬大量使用者湧入,即時看到
location-service 的 CPU、HPA 副本數擴展(1→5)與自動擴展事件紀錄。

- 零 npm 依賴(Chart.js 已放在 `static/vendor/`),不需要 `npm install`
- 啟動時自動偵測模式:有 K8s 命名空間 `realtime-map-notice` → **k8s 模式(真 HPA)**,否則 → compose 模式(模擬 HPA)
- 字級隨視窗縮放:投影全螢幕、半螢幕都能看

---

## 在新電腦上第一次使用(k8s 模式)

以下指令都在 **PowerShell、專案根目錄** 執行。只要看儀表板與壓測,做完 1–6 即可;
地圖網站(Google 登入)是另外的選配步驟。

### 0. 需要先安裝

| 軟體 | 用途 | 備註 |
|---|---|---|
| Git | 拉程式碼 | |
| Docker Desktop | 跑 K8s | Settings → Kubernetes → 勾選啟用;`kubectl` 會一起裝好 |
| Node.js ≥ 18 | 跑儀表板(地圖網站也需要) | |
| 網路 | 建 image、壓測 Pod 啟動時要下載 Python 映像與套件 | demo 場地也要有網路 |

### 1. 切到分支

```powershell
git fetch origin
git checkout feat/ops-dashboard-v2
git pull
```

### 2. 確認 kubectl 指向 Docker Desktop

```powershell
kubectl config use-context docker-desktop
kubectl get nodes
```

### 3. 建 image(每台電腦都要自己 build,image 不會跟著 git 走)

tag 必須與 `k8s/*.yaml` 一致(location `v2`、event `v3`,其他 `latest`):

```powershell
docker build -t realtime-map-notice/location-service:v2 -f backend/location-service/Dockerfile .
docker build -t realtime-map-notice/event-service:v3 -f backend/event-service/Dockerfile .
docker build -t realtime-map-notice/notification-service:latest -f backend/notification-service/Dockerfile .
docker build -t realtime-map-notice/ai-service:latest -f backend/ai-service/Dockerfile .
```

> 為什麼不用 `:latest`:節點會快取舊的 latest,程式碼更新後 Pod 仍跑舊版。改了程式要重 build 時,
> 換新 tag(例如 v4)並同步修改對應的 `k8s/*.yaml`。

### 4. 部署服務

```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/redis.yaml -f k8s/location-service.yaml -f k8s/event-service.yaml -f k8s/notification-service.yaml -f k8s/ai-service.yaml
```

**不要** 直接 `kubectl apply -f k8s/`——會連壓測 Job 一起啟動。

ai-service 需要 Secret `gemini-key`,沒有會卡在 `CreateContainerConfigError`
(只影響事件的 AI 審核,儀表板與壓測照常)。向負責後端的組員拿 key,
**把整段換成真正的 key,不要保留 `<` `>`**:

```powershell
kubectl -n realtime-map-notice create secret generic gemini-key --from-literal=keys='AIza...你的金鑰'
```

### 5. metrics-server(沒有的話 CPU 顯示 `?`、HPA 不會擴展)

先確認有沒有安裝:

```powershell
kubectl -n kube-system get deploy metrics-server
```

出現 `not found` 就先安裝:

```powershell
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

再補 `--kubelet-insecure-tls`(Docker Desktop 的 kubelet 憑證不被信任)。**補丁不能重複套用**,這行會先檢查:

```powershell
if (-not (kubectl -n kube-system get deploy metrics-server -o yaml | Select-String 'kubelet-insecure-tls')) { kubectl -n kube-system patch deploy metrics-server --type=json --patch-file k8s/patches/metrics-server-insecure-tls.json }
```

### 6. 等 Pod 就緒,啟動儀表板

```powershell
kubectl -n realtime-map-notice wait --for=condition=Ready pod --all --timeout=180s
node ops-dashboard/server.js
```

啟動訊息要看到「**偵測到 K8s 命名空間 → k8s 模式(真 HPA)**」,開啟 http://localhost:8090 。
若顯示 compose 模式,代表 K8s 還沒好就啟動了:確認 `kubectl get ns realtime-map-notice` 有結果後重開。

儀表板不需要 port-forward,也不需要登入或 Gemini key。

### 7.(選配)地圖網站

地圖網站要 Google 登入,前端與後端要填**同一個** Client ID(向組員拿,格式 `xxxx.apps.googleusercontent.com`)。

```powershell
# 前端:建立 web-app/.env.local(不進版控)
Set-Content web-app\.env.local "VITE_GOOGLE_CLIENT_ID=你的ClientID"

# 後端:設給 K8s 裡的 event-service(會重啟 event-service)
kubectl -n realtime-map-notice set env deploy/event-service GOOGLE_CLIENT_ID=你的ClientID
```

> 指令裡的「你的ClientID」要換成真的 ID。設定沒寫進 yaml,之後重跑步驟 4 的 apply 會被蓋回空值,要再設一次。

接著開三個 PowerShell 視窗做 port-forward(地圖網站靠這三個連進 K8s),再開一個跑地圖網站:

```powershell
kubectl -n realtime-map-notice port-forward svc/location-service 8001:8000
kubectl -n realtime-map-notice port-forward svc/event-service 8002:8000
kubectl -n realtime-map-notice port-forward svc/notification-service 8003:8000
```

```powershell
cd web-app
npm install   # 第一次才需要
npm run dev   # 開啟 http://localhost:5173
```

Pod 重啟(例如設定 GOOGLE_CLIENT_ID 後)對應的 port-forward 會斷,重跑那一行即可。

---

## 操作與 demo 建議

頂部輸入 **模擬人數** 與 **每 N 秒回報**,按「⚡ 開始模擬」;流量 ≈ 人數 ÷ 間隔(次/秒)。

| 設定 | 流量 | 參考結果(4 核心 Docker Desktop) |
|---|---|---|
| 800 人、每 10 秒 | 約 80 次/秒 | 實測:擴到 5 個副本,平均 CPU 降回 40% 門檻以下 ✅ |
| 300 人、每 10 秒 | 約 30 次/秒 | 估計:擴到約 2–3 個副本 |
| 600 人、每 5 秒 | 約 120 次/秒 | 估計:5 個副本都高於門檻(展示「已達上限」) |

- **每台電腦效能不同,demo 前務必在那台電腦彩排一次**,依結果調整人數或間隔
- 筆電請插電並設為最佳效能,否則 CPU 降頻、數字會變
- 第一次開始模擬要下載 Python 映像與套件,約 30–60 秒後才有流量
- 按「⏹ 停止並清空」:壓測 Pod 立即刪除、模擬使用者與地圖事件數秒內清空;
  HPA 約 1 分鐘後開始縮減(每 30 秒最多少 1 個副本)
- `kubectl top nodes` 接近 100% 代表電腦 CPU 已滿,此時調高副本上限沒有幫助

### 數字怎麼看

- **CPU%** 以 Pod 的 CPU requests(location-service 為 100m)為基準,與 HPA 相同:
  用了 40m 就是 40%;可以超過 100%(上限 limits 為 500m)
- **HPA 門檻 40%**、副本 1–5 個,設定在 `k8s/location-service.yaml`;
  需要的副本數 ≈ 目前副本數 × 平均 CPU ÷ 門檻
- 「即時在線」只算 60 秒內回報過位置的使用者

### 壓測產生器的設計(為什麼這樣做)

- **每 400 人一個模擬 Pod**(Indexed Job,上限 8 個,人數平均分配):單一模擬程序人多會飽和
- **每 50 人共用一個 httpx client**:httpx 每次請求都掃過整個連線池,單一 client 開數百條連線時 CPU 暴增、吞吐量崩落
- **每約 20 次請求輪替一次連線**:kube-proxy 只在新連線時分流,keep-alive 長連線會讓 HPA 擴出的新 Pod 分不到流量
- 模擬器每 5 秒在日誌輸出 `req/s`、成功率、逾時與錯誤數:

```powershell
kubectl -n realtime-map-notice logs -l app=load-generator --tail=2
```

## 常見問題

| 症狀 | 原因與處理 |
|---|---|
| Pod 卡在 `ErrImageNeverPull` / `ImagePullBackOff` | image tag 與 yaml 對不上,回到步驟 3 重 build |
| ai-service 卡在 `CreateContainerConfigError` | 少了 `gemini-key`,見步驟 4 |
| CPU 顯示 `?`、HPA 不擴展 | metrics-server 未安裝或未補丁,見步驟 5 |
| 儀表板顯示 compose 模式 | K8s 未就緒時就啟動了,確認命名空間存在後重開 |
| 地圖登入顯示 `Missing required parameter: client_id` | 前端沒設 `VITE_GOOGLE_CLIENT_ID`,見步驟 7,改完要重開 `npm run dev` |
| 地圖登入顯示「Google 登入驗證失敗」 | 前後端 Client ID 不一致;`kubectl -n realtime-map-notice exec deploy/event-service -- printenv GOOGLE_CLIENT_ID` 比對 |
| 在線人數一直跳動 | 看模擬器日誌的 `req/s`;偏低代表電腦 CPU 不夠,減少人數或拉長間隔 |

---

## compose 模式(沒有 K8s 時)

先 `docker compose up -d` 啟動後端,再 `node ops-dashboard/server.js`。

| | compose 模式 | k8s 模式 |
|---|---|---|
| 偵測條件 | 無 `realtime-map-notice` 命名空間 | `kubectl get ns realtime-map-notice` 成功 |
| 壓測 | 一次性容器跑 `simulator/simulate_users.py` | `load-generator` Indexed Job(叢集內) |
| 分流 | ops 內建 round-robin proxy(等效 K8s Service) | kube-proxy |
| 擴展 | ops 模擬 HPA | 真 HPA |
| 指標 | `docker stats` | `kubectl top pods` + HPA status |

compose 模式的模擬 HPA:

- location-service 平均 CPU ≥ **25%**(`OPS_SCALE_UP_CPU`)連續 2 秒 → 增加 1 副本(最多 **5**)
- 壓測進行中不縮減;停止壓測後縮回 1 副本
- 額外副本發布到主機 `:18001`–`:18004`;壓測流量經 `host.docker.internal:8090/fwd/location/*` 由 ops 輪詢轉發
- 模擬人數 > 400 拆 2 個 worker 容器、> 800 拆 3 個

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `OPS_PORT` | `8090` | 儀表板埠號 |
| `OPS_SIM_INTERVAL` | `10` | 預設回報間隔(秒),頁面上可再調整 |
| `OPS_SCALE_UP_CPU` | `25` | compose 模式的模擬擴展門檻(%) |

## 已知限制

- 本機 demo 用途,勿部署到對外環境(ops 具備啟停容器/Job 的能力,無鑑別)
- 壓測用完若沒透過儀表板停止,要手動清 Job(不會自己停):
  `kubectl -n realtime-map-notice delete job load-generator event-gen --ignore-not-found`

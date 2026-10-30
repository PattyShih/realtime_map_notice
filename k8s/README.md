# Kubernetes 使用方式

這份文件描述如何把 `realtime_map_notice` 的後端服務部署到 Kubernetes，並展示 HPA 自動擴展與 Pod 容錯。所有指令預設在專案根目錄執行。

少量、中量、大量使用時的 resource 調整與瓶頸分析，請參考 [../system.md](../system.md)。

## 前置需求

- Docker Desktop Kubernetes 或 minikube。
- `kubectl` 已連到正確 cluster。
- metrics-server 已安裝或啟用，否則 HPA 會顯示 `<unknown>`。
- 已在本機建立三個服務的 Docker image。

確認目前 cluster：

```powershell
kubectl config current-context
kubectl get nodes
```

## 建立本機 Image

若使用 Docker Desktop Kubernetes：

```powershell
docker build -t realtime-map-notice/location-service:latest -f backend/location-service/Dockerfile .
docker build -t realtime-map-notice/event-service:latest -f backend/event-service/Dockerfile .
docker build -t realtime-map-notice/notification-service:latest -f backend/notification-service/Dockerfile .
```

若使用 minikube，先執行：

```powershell
minikube image load realtime-map-notice/location-service:latest
minikube image load realtime-map-notice/event-service:latest
minikube image load realtime-map-notice/notification-service:latest
```

## 部署

```powershell
kubectl apply -f k8s/
kubectl -n realtime-map-notice get pods
```

等待所有 Pod 就緒：

```powershell
kubectl -n realtime-map-notice wait --for=condition=Ready pod --all --timeout=180s
```

查看服務：

```powershell
kubectl -n realtime-map-notice get svc
```

## Port Forward

```powershell
kubectl -n realtime-map-notice port-forward svc/location-service 8001:8000
kubectl -n realtime-map-notice port-forward svc/event-service 8002:8000
kubectl -n realtime-map-notice port-forward svc/notification-service 8003:8000
```

建議分三個 PowerShell 視窗分別執行 port-forward，避免單一終端機被阻塞後不好操作。

健康檢查：

```powershell
Invoke-RestMethod http://localhost:8001/healthz
Invoke-RestMethod http://localhost:8002/healthz
Invoke-RestMethod http://localhost:8003/healthz
```

## 觀察 HPA

```powershell
kubectl -n realtime-map-notice get hpa -w
```

HPA 需要 metrics-server。若 HPA 顯示 unknown，請先安裝或啟用 metrics-server。

壓測時可以同時觀察：

```powershell
kubectl -n realtime-map-notice get pods -w
kubectl -n realtime-map-notice top pods
kubectl -n realtime-map-notice describe hpa location-service-hpa
```

### 叢集內壓測（建議）

壓測請從**叢集內部**對 service 發起；從主機經 `kubectl port-forward` 打會被單一通道卡住，流量根本進不了 pod。負載產生器以 Kubernetes Job 執行，模擬腳本掛 ConfigMap：

```bash
kubectl -n realtime-map-notice create configmap simulator-code \
  --from-file=simulate_users.py=simulator/simulate_users.py --dry-run=client -o yaml | kubectl apply -f -
kubectl -n realtime-map-notice delete job load-generator --ignore-not-found
kubectl apply -f k8s/load-generator-job.yaml
kubectl -n realtime-map-notice get hpa -w   # 觀察 location-service 1 → N 副本
kubectl -n realtime-map-notice delete job load-generator   # 停止壓測
```

注意：單一 Python asyncio 程序大約在 1500-3000 人後會先成為瓶頸（事件循環飽和、有效請求數不增反減），這是壓測工具本身的極限；正式分散式壓測應改用 k6 / Locust 多 worker。

## Pod 容錯 Demo

刪除一個 Notification Service Pod：

```powershell
$pod = kubectl -n realtime-map-notice get pod -l app=notification-service -o jsonpath="{.items[0].metadata.name}"
kubectl -n realtime-map-notice delete pod $pod
```

觀察 Kubernetes 自動補回：

```powershell
kubectl -n realtime-map-notice get pods -w
```

預期結果：

- 被刪除的 Pod 進入 Terminating。
- ReplicaSet 建立新的 Pod。
- 新 Pod 從 Pending 變成 Running。
- Service 仍保留穩定 DNS 名稱 `notification-service`。

## 常見問題

### HPA 顯示 unknown

可能原因：

- metrics-server 尚未啟用。
- Pod 沒有設定 CPU requests。
- metrics-server 無法讀取 node 指標。

先檢查：

```powershell
kubectl top nodes
kubectl top pods -n realtime-map-notice
```

### Pod 一直 ImagePullBackOff

可能原因：

- 本機 image 名稱與 YAML 不一致。
- minikube 沒有載入本機 image。
- `imagePullPolicy` 設定導致 cluster 嘗試從遠端 registry 拉 image。

檢查：

```powershell
kubectl -n realtime-map-notice describe pod <pod-name>
```

### Service 無法連線

可能原因：

- Pod 尚未 Ready。
- port-forward 指令未執行。
- Service selector 與 Pod label 不一致。

檢查：

```powershell
kubectl -n realtime-map-notice get endpoints
kubectl -n realtime-map-notice describe svc location-service
```

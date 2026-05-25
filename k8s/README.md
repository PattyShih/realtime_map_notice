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
.\scripts\k8s-build-images.ps1
```

若使用 minikube，先執行：

```powershell
.\scripts\k8s-build-images.ps1 -LoadToMinikube
```

## 部署

```powershell
.\scripts\k8s-deploy.ps1
```

等待所有 Pod 就緒：

```powershell
kubectl -n realtime-map-notice wait --for=condition=Ready pod --all --timeout=180s
```

查看服務：

```powershell
.\scripts\k8s-status.ps1
```

## Port Forward

```powershell
.\scripts\k8s-port-forward.ps1
```

建議分三個 PowerShell 視窗分別執行 port-forward，避免單一終端機被阻塞後不好操作。

健康檢查：

```powershell
.\scripts\k8s-health-check.ps1
```

## 500-1,000 人壓測

先確認已經執行 port-forward，讓本機 `http://localhost:8001` 可以連到 K8s 中的 Location Service。

初期 Demo 目標：

```powershell
.\scripts\k8s-load-test.ps1 -Users 500 -Interval 1
```

進階目標：

```powershell
.\scripts\k8s-load-test.ps1 -Users 1000 -Interval 1
```

若需要觀察極限或準備截圖，可再嘗試：

```powershell
.\scripts\k8s-load-test.ps1 -Users 3000 -Interval 1
```

壓測時建議同時開另一個 PowerShell 視窗：

```powershell
kubectl -n realtime-map-notice get hpa -w
kubectl -n realtime-map-notice get pods -w
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

## Pod 容錯 Demo

刪除一個 Notification Service Pod：

```powershell
.\scripts\k8s-delete-notification-pod.ps1
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

## 第四階段 Demo 截圖清單

建議至少準備下列截圖，避免現場網路或 K8s 環境不穩時沒有備案：

| 截圖 | 指令 |
|------|------|
| 所有 Pod Running | `kubectl -n realtime-map-notice get pods -o wide` |
| Service 與 HPA | `kubectl -n realtime-map-notice get svc,hpa` |
| HPA 擴展前 | `kubectl -n realtime-map-notice get hpa` |
| HPA 擴展中 | `kubectl -n realtime-map-notice get hpa -w` |
| Pod 容錯前 | `kubectl -n realtime-map-notice get pods` |
| 刪除 Notification Pod 後自動重建 | `.\scripts\k8s-delete-notification-pod.ps1` |

## 第四階段完成條件

Repo 交付物已包含：

- Redis、Location Service、Event Service、Notification Service 的 K8s YAML。
- Location Service HPA。
- 所有服務的 resource requests/limits。
- Redis、Location Service、Event Service、Notification Service 的 readiness/liveness probe。
- 500-1,000 人壓測腳本入口。
- Pod 容錯 Demo 腳本。
- HPA / Pod / Service 觀察指令。

實機完成條件：

- `.\scripts\k8s-build-images.ps1` 成功。
- `.\scripts\k8s-deploy.ps1` 成功，所有 Pod Running。
- `.\scripts\k8s-port-forward.ps1` 後 `.\scripts\k8s-health-check.ps1` 成功。
- `.\scripts\k8s-load-test.ps1 -Users 500` 可執行，HPA 有擴展跡象。
- `.\scripts\k8s-delete-notification-pod.ps1` 後 Kubernetes 自動補回 Pod。

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

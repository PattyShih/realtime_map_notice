# Kubernetes 使用方式

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

## Port Forward

```powershell
kubectl -n realtime-map-notice port-forward svc/location-service 8001:8000
kubectl -n realtime-map-notice port-forward svc/event-service 8002:8000
kubectl -n realtime-map-notice port-forward svc/notification-service 8003:8000
```

## 觀察 HPA

```powershell
kubectl -n realtime-map-notice get hpa -w
```

HPA 需要 metrics-server。若 HPA 顯示 unknown，請先安裝或啟用 metrics-server。

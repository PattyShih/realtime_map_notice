$ErrorActionPreference = "Stop"

kubectl apply -f k8s/namespace.yaml
kubectl get namespace realtime-map-notice | Out-Host

kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/notification-service.yaml
kubectl apply -f k8s/location-service.yaml
kubectl apply -f k8s/event-service.yaml

kubectl -n realtime-map-notice rollout status deployment/redis --timeout=180s
kubectl -n realtime-map-notice rollout status deployment/location-service --timeout=180s
kubectl -n realtime-map-notice rollout status deployment/event-service --timeout=180s
kubectl -n realtime-map-notice rollout status deployment/notification-service --timeout=180s
kubectl -n realtime-map-notice get pods
kubectl -n realtime-map-notice get hpa

Write-Host "Kubernetes deployment is ready."

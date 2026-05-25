$ErrorActionPreference = "Stop"

kubectl apply -f k8s/
kubectl -n realtime-map-notice rollout status deployment/redis --timeout=180s
kubectl -n realtime-map-notice rollout status deployment/location-service --timeout=180s
kubectl -n realtime-map-notice rollout status deployment/event-service --timeout=180s
kubectl -n realtime-map-notice rollout status deployment/notification-service --timeout=180s
kubectl -n realtime-map-notice get pods
kubectl -n realtime-map-notice get hpa

Write-Host "Kubernetes deployment is ready."

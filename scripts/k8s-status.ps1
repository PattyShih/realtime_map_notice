$ErrorActionPreference = "Stop"

kubectl -n realtime-map-notice get pods -o wide
kubectl -n realtime-map-notice get svc
kubectl -n realtime-map-notice get hpa
kubectl -n realtime-map-notice get deploy

Write-Host ""
Write-Host "If HPA metrics are unknown, check metrics-server:"
Write-Host "kubectl top nodes"
Write-Host "kubectl top pods -n realtime-map-notice"

$ErrorActionPreference = "Stop"

$pod = kubectl -n realtime-map-notice get pod -l app=notification-service -o jsonpath="{.items[0].metadata.name}"
if ([string]::IsNullOrWhiteSpace($pod)) {
    throw "No notification-service pod found."
}

Write-Host "Deleting notification-service pod: $pod"
kubectl -n realtime-map-notice delete pod $pod
kubectl -n realtime-map-notice rollout status deployment/notification-service --timeout=180s
kubectl -n realtime-map-notice get pods -l app=notification-service

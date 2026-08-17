$ErrorActionPreference = "Stop"

$commands = @(
    "kubectl -n realtime-map-notice port-forward svc/location-service 8001:8000",
    "kubectl -n realtime-map-notice port-forward svc/event-service 8002:8000",
    "kubectl -n realtime-map-notice port-forward svc/notification-service 8003:8000"
)

foreach ($command in $commands) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $command
}

Write-Host "Port-forward windows opened:"
Write-Host "Location Service: http://localhost:8001"
Write-Host "Event Service: http://localhost:8002"
Write-Host "Notification Service: http://localhost:8003"

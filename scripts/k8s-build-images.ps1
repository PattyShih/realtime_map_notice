param(
    [switch]$LoadToMinikube
)

$ErrorActionPreference = "Stop"

docker build -t realtime-map-notice/location-service:latest -f backend/location-service/Dockerfile .
docker build -t realtime-map-notice/event-service:latest -f backend/event-service/Dockerfile .
docker build -t realtime-map-notice/notification-service:latest -f backend/notification-service/Dockerfile .
docker build -t realtime-map-notice/simulator:latest -f simulator/Dockerfile .

if ($LoadToMinikube) {
    minikube image load realtime-map-notice/location-service:latest
    minikube image load realtime-map-notice/event-service:latest
    minikube image load realtime-map-notice/notification-service:latest
    minikube image load realtime-map-notice/simulator:latest
}

Write-Host "Images are ready."

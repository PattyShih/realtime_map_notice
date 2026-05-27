$ErrorActionPreference = "Stop"

$env:VITE_LOCATION_SERVICE_URL = "https://map.avision-gb10.org/api/location"
$env:VITE_EVENT_SERVICE_URL = "https://map.avision-gb10.org/api/events"
$env:VITE_NOTIFICATION_WS_URL = "wss://map.avision-gb10.org"

Push-Location web-app
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

Write-Host "Web App build is ready at web-app/dist."

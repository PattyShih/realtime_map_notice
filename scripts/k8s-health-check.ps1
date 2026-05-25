$ErrorActionPreference = "Stop"

$services = @(
    "http://localhost:8001/healthz",
    "http://localhost:8002/healthz",
    "http://localhost:8003/healthz"
)

foreach ($service in $services) {
    Write-Host "Checking $service"
    Invoke-RestMethod $service
}

Write-Host "All port-forwarded services are healthy."

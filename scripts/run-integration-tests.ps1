param(
    [switch]$SkipComposeUp,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

function Wait-Healthy {
    param(
        [string]$Name,
        [string]$Uri,
        [int]$Retries = 30
    )

    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        try {
            $response = Invoke-RestMethod $Uri
            if ($response.status -eq "ok") {
                Write-Host "PASS $Name health"
                return
            }
        } catch {
            if ($attempt -eq $Retries) {
                throw "$Name health check failed after $Retries attempts. $($_.Exception.Message)"
            }
        }

        Start-Sleep -Seconds 2
    }
}

if (-not $SkipComposeUp) {
    Write-Host "Starting Docker Compose services..."
    docker compose up --build -d | Out-Host
}

try {
    Wait-Healthy "Location Service" "http://localhost:8001/healthz"
    Wait-Healthy "Event Service" "http://localhost:8002/healthz"
    Wait-Healthy "Notification Service" "http://localhost:8003/healthz"

    Write-Host "Running cross-service integration tests..."
    $env:RUN_CROSS_SERVICE_TESTS = "1"
    python -m pytest tests/integration/cross_service -v
    $exitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:\RUN_CROSS_SERVICE_TESTS -ErrorAction SilentlyContinue
    if (-not $KeepRunning -and -not $SkipComposeUp) {
        Write-Host "Stopping Docker Compose services..."
        docker compose down | Out-Host
    }
}

exit $exitCode

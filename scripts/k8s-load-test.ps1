param(
    [int]$Users = 500,
    [double]$Interval = 1.0,
    [string]$Target = "http://localhost:8001",
    [int]$DurationSeconds = 0,
    [double]$TimeoutSeconds = 5.0
)

$ErrorActionPreference = "Stop"

Write-Host "Starting simulator: users=$Users interval=$Interval target=$Target durationSeconds=$DurationSeconds timeoutSeconds=$TimeoutSeconds"

try {
    $health = Invoke-RestMethod "$Target/healthz"
    if ($health.status -ne "ok") {
        throw "Unexpected health response: $($health | ConvertTo-Json -Compress)"
    }
} catch {
    throw "Location Service is not reachable at $Target. Run .\scripts\k8s-port-forward.ps1 first, or pass -Target to a reachable Location Service URL. $($_.Exception.Message)"
}

if ($DurationSeconds -gt 0) {
    python simulator/simulate_users.py --users $Users --interval $Interval --target $Target --duration $DurationSeconds --timeout $TimeoutSeconds
} else {
    python simulator/simulate_users.py --users $Users --interval $Interval --target $Target --timeout $TimeoutSeconds
}

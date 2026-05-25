param(
    [int]$Users = 500,
    [double]$Interval = 1.0,
    [string]$Target = "http://localhost:8001"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting simulator: users=$Users interval=$Interval target=$Target"
python simulator/simulate_users.py --users $Users --interval $Interval --target $Target

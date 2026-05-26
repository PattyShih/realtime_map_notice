$ErrorActionPreference = "Stop"

$token = [Environment]::GetEnvironmentVariable("CLOUDFLARE_TUNNEL_TOKEN", "User")
if ([string]::IsNullOrWhiteSpace($token)) {
    $token = [Environment]::GetEnvironmentVariable("CLOUDFLARE_TUNNEL_TOKEN", "Process")
}

if ([string]::IsNullOrWhiteSpace($token)) {
    throw "CLOUDFLARE_TUNNEL_TOKEN is not set. Set it in your PowerShell session or User environment before running this script."
}

Write-Host "Starting cloudflared tunnel from token..."
docker run --rm --name realtime-map-notice-cloudflared cloudflare/cloudflared:latest tunnel --no-autoupdate run --token $token

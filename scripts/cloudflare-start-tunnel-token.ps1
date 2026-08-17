$ErrorActionPreference = "Stop"

$token = [Environment]::GetEnvironmentVariable("CLOUDFLARE_TUNNEL_TOKEN", "User")
if ([string]::IsNullOrWhiteSpace($token)) {
    $token = [Environment]::GetEnvironmentVariable("CLOUDFLARE_TUNNEL_TOKEN", "Process")
}

if ([string]::IsNullOrWhiteSpace($token)) {
    throw "CLOUDFLARE_TUNNEL_TOKEN is not set. Set it in your PowerShell session or User environment before running this script."
}

$token = $token.Trim()

if ($token.StartsWith("cfut_")) {
    throw "CLOUDFLARE_TUNNEL_TOKEN looks like a Cloudflare API token. Use the Zero Trust Tunnel connector token from the Docker connector command instead."
}

if (-not $token.StartsWith("eyJ")) {
    throw "CLOUDFLARE_TUNNEL_TOKEN does not look like a Cloudflare Tunnel connector token. It usually starts with 'eyJ'."
}

$env:CLOUDFLARE_TUNNEL_TOKEN = $token

Write-Host "Starting public demo stack with cloudflared tunnel token..."
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml --profile cloudflare-token up --build

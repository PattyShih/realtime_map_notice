$ErrorActionPreference = "Stop"

Push-Location web-app
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

Write-Host "Web App build is ready at web-app/dist."

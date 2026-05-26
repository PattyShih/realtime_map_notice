param(
    [string]$LocationServiceUrl = "http://localhost:8001",
    [string]$EventServiceUrl = "http://localhost:8002",
    [string]$NotificationServiceUrl = "http://localhost:8003",
    [switch]$SkipComposeUp
)

$ErrorActionPreference = "Stop"

function Invoke-JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Body
    )

    Invoke-RestMethod `
        -Method Post `
        -Uri $Uri `
        -ContentType "application/json" `
        -Body ($Body | ConvertTo-Json -Compress)
}

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
                return $response
            }
        } catch {
            if ($attempt -eq $Retries) {
                throw "$Name health check failed after $Retries attempts. $($_.Exception.Message)"
            }
        }

        Start-Sleep -Seconds 2
    }
}

function Assert-Equal {
    param(
        [object]$Actual,
        [object]$Expected,
        [string]$Message
    )

    if ($Actual -ne $Expected) {
        throw "$Message Expected=$Expected Actual=$Actual"
    }
}

function Assert-Contains {
    param(
        [object[]]$Actual,
        [object]$Expected,
        [string]$Message
    )

    if ($Actual -notcontains $Expected) {
        throw "$Message Missing=$Expected Actual=$($Actual -join ',')"
    }
}

$runId = [guid]::NewGuid().ToString("N").Substring(0, 8)
$userOne = "smoke-u1-$runId"
$userTwo = "smoke-u2-$runId"
$latitude = 25.0173
$longitude = 121.5397

if (-not $SkipComposeUp) {
    Write-Host "Starting Docker Compose services..."
    docker compose up --build -d | Out-Host
}

Write-Host "== Compose smoke test =="
Write-Host "Location:     $LocationServiceUrl"
Write-Host "Event:        $EventServiceUrl"
Write-Host "Notification: $NotificationServiceUrl"

Write-Host "`n[1/5] Checking health endpoints..."
$locationHealth = Wait-Healthy "Location Service" "$LocationServiceUrl/healthz"
$eventHealth = Wait-Healthy "Event Service" "$EventServiceUrl/healthz"
$notificationHealth = Wait-Healthy "Notification Service" "$NotificationServiceUrl/healthz"

Write-Host "`n[2/5] Uploading nearby user locations..."
$firstLocation = Invoke-JsonPost "$LocationServiceUrl/locations" @{
    user_id = $userOne
    latitude = $latitude
    longitude = $longitude
}
$secondLocation = Invoke-JsonPost "$LocationServiceUrl/locations" @{
    user_id = $userTwo
    latitude = 25.0180
    longitude = 121.5400
}
Assert-Equal $firstLocation.status "accepted" "First location update failed."
Assert-Equal $secondLocation.status "accepted" "Second location update failed."
Write-Host "PASS location uploads"

Write-Host "`n[3/5] Querying nearby users..."
$nearbyUri = "$LocationServiceUrl/locations/nearby?latitude=$latitude&longitude=$longitude&radius_meters=500"
$nearby = Invoke-RestMethod $nearbyUri
Assert-Contains $nearby.users $userOne "Nearby query did not include first user."
Assert-Contains $nearby.users $userTwo "Nearby query did not include second user."
Write-Host "PASS nearby query users=$($nearby.users -join ',')"

Write-Host "`n[4/5] Creating urgent event and checking fan-out..."
$event = Invoke-JsonPost "$EventServiceUrl/events" @{
    client_event_id = "smoke-$runId"
    title = "Compose smoke urgent event"
    message = "Docker Compose smoke test"
    latitude = $latitude
    longitude = $longitude
    severity = "urgent"
    radius_meters = 500
}
Assert-Equal $event.status "created" "Event creation failed."
if ($event.nearby_user_count -lt 2) {
    throw "Expected at least two nearby users. Actual=$($event.nearby_user_count)"
}
if ($event.delivered_count -lt 2) {
    throw "Expected at least two delivered notifications. Actual=$($event.delivered_count)"
}
Write-Host "PASS event fan-out event_id=$($event.event_id) delivered=$($event.delivered_count)"

Write-Host "`n[5/5] Checking idempotency for duplicate client_event_id..."
$duplicateEvent = Invoke-JsonPost "$EventServiceUrl/events" @{
    client_event_id = "smoke-$runId"
    title = "Compose smoke urgent event"
    message = "Docker Compose smoke test"
    latitude = $latitude
    longitude = $longitude
    severity = "urgent"
    radius_meters = 500
}
Assert-Equal $duplicateEvent.status "duplicate" "Duplicate event was not detected."
Assert-Equal $duplicateEvent.event_id $event.event_id "Duplicate event did not return the original event id."
Write-Host "PASS duplicate event idempotency"

Write-Host "`nCOMPOSE SMOKE TEST PASSED"

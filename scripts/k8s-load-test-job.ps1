param(
    [int]$Users = 500,
    [double]$Interval = 1.0,
    [int]$DurationSeconds = 60,
    [double]$TimeoutSeconds = 5.0,
    [switch]$KeepJob
)

$ErrorActionPreference = "Stop"

$jobName = "location-load-$((Get-Date).ToString('yyyyMMddHHmmss'))"
$waitTimeout = [Math]::Max($DurationSeconds + 180, 240)

$manifest = @"
apiVersion: batch/v1
kind: Job
metadata:
  name: $jobName
  namespace: realtime-map-notice
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: simulator
          image: realtime-map-notice/simulator:latest
          imagePullPolicy: IfNotPresent
          command:
            - python
            - simulator/simulate_users.py
          args:
            - --users
            - "$Users"
            - --interval
            - "$Interval"
            - --duration
            - "$DurationSeconds"
            - --timeout
            - "$TimeoutSeconds"
            - --target
            - http://location-service:8000
"@

Write-Host "Creating in-cluster load test job: $jobName"
$manifest | kubectl apply -f -

try {
    $deadline = (Get-Date).AddSeconds($waitTimeout)
    while ((Get-Date) -lt $deadline) {
        $succeeded = kubectl -n realtime-map-notice get "job/$jobName" -o jsonpath="{.status.succeeded}"
        $failed = kubectl -n realtime-map-notice get "job/$jobName" -o jsonpath="{.status.failed}"

        if ($succeeded -eq "1") {
            break
        }

        if (-not [string]::IsNullOrWhiteSpace($failed) -and [int]$failed -gt 0) {
            throw "Load test job failed."
        }

        Start-Sleep -Seconds 5
    }

    $finalSucceeded = kubectl -n realtime-map-notice get "job/$jobName" -o jsonpath="{.status.succeeded}"
    if ($finalSucceeded -ne "1") {
        throw "Load test job did not complete before timeout ${waitTimeout}s."
    }

    kubectl -n realtime-map-notice logs "job/$jobName"
} catch {
    kubectl -n realtime-map-notice logs "job/$jobName" | Out-Host
    throw
} finally {
    if (-not $KeepJob) {
        kubectl -n realtime-map-notice delete "job/$jobName" --ignore-not-found | Out-Host
    }
}

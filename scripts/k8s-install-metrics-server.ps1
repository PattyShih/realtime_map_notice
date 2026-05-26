param(
    [switch]$SkipInsecureTlsPatch
)

$ErrorActionPreference = "Stop"

Write-Host "Installing metrics-server..."
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

if (-not $SkipInsecureTlsPatch) {
    Write-Host "Patching metrics-server for local Docker Desktop/minikube kubelet TLS..."
    kubectl -n kube-system patch deployment metrics-server --type=json -p='[
      {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}
    ]'
}

kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s

Write-Host "Waiting for Metrics API..."
for ($attempt = 1; $attempt -le 30; $attempt++) {
    $topOutput = kubectl top nodes 2>&1
    if ($LASTEXITCODE -eq 0) {
        $topOutput | Out-Host
        Write-Host "metrics-server is ready."
        exit 0
    }

    if ($attempt -eq 30) {
        $topOutput | Out-Host
        throw "Metrics API was not ready after 30 attempts. Check: kubectl -n kube-system logs deployment/metrics-server"
    }

    Start-Sleep -Seconds 5
}

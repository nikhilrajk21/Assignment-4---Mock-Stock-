param([switch]$LeaveRunning)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $root 'frontend'
$backendUrl = 'http://127.0.0.1:8000/api/health'
$frontendUrl = 'http://127.0.0.1:5173/api/health'
$backend = $null
$frontend = $null
$passed = $false

function Start-Backend {
    Start-Process -FilePath (Get-Command python).Source -ArgumentList '-B','-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $root -WindowStyle Hidden -PassThru
}

function Stop-ServiceProcess($process) {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id
        $process.WaitForExit()
    }
}

function Read-Response($url) {
    Invoke-WebRequest -Uri $url -TimeoutSec 3 -SkipHttpErrorCheck
}

function Wait-ForHealth($url, $process) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($process.HasExited) { throw "Service exited before $url was ready." }
        $response = $null
        try { $response = Read-Response $url } catch { }
        if ($response -and $response.StatusCode -eq 200) { return $response }
        Start-Sleep -Milliseconds 250
    }
    throw "Timed out waiting for $url."
}

function Show-Response($url, $response) {
    $body = if ($response.Content.Length) { $response.Content } else { '<empty>' }
    Write-Host "$url HTTP $($response.StatusCode) $body"
}

foreach ($port in 8000, 5173) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing service before running this check."
    }
}

try {
    $backend = Start-Backend
    $frontend = Start-Process -FilePath (Get-Command node).Source -ArgumentList 'node_modules/vite/bin/vite.js' -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru
    $direct = Wait-ForHealth $backendUrl $backend
    $proxied = Wait-ForHealth $frontendUrl $frontend
    Show-Response $backendUrl $direct
    Show-Response $frontendUrl $proxied
    if ($direct.Content -cne '{"status":"ok"}' -or $proxied.Content -cne $direct.Content) {
        throw 'Direct and proxied health JSON must match the expected body.'
    }

    Stop-ServiceProcess $backend
    $down = Read-Response $frontendUrl
    Show-Response $frontendUrl $down
    if ($down.StatusCode -lt 500 -or $down.StatusCode -ge 600) { throw 'Expected a proxy error with FastAPI stopped.' }

    $backend = Start-Backend
    $null = Wait-ForHealth $backendUrl $backend
    $recovered = Read-Response $frontendUrl
    Show-Response $frontendUrl $recovered
    if ($recovered.StatusCode -ne 200 -or $recovered.Content -cne $direct.Content) {
        throw 'Proxy did not recover after FastAPI restarted.'
    }
    $passed = $true
} finally {
    if ($passed -and $LeaveRunning) {
        Write-Host "Frontend PID $($frontend.Id), backend PID $($backend.Id)"
        Write-Host "Stop-Process -Id $($frontend.Id),$($backend.Id)"
    } else {
        Stop-ServiceProcess $frontend
        Stop-ServiceProcess $backend
    }
}

# ============================================================
#   Gangstar Remote Server -- VPS (Otimizado WebSocket Turbo)
# ============================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Gangstar Remote Server -- VPS" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

Write-Host "[1/4] Parando processos anteriores..." -ForegroundColor Yellow
taskkill /F /IM python.exe 2>$null
Start-Sleep -Seconds 2

Write-Host "[2/4] Configurando ambiente..." -ForegroundColor Yellow
$env:PYTHONOPTIMIZE = "2"
$env:PYTHONASYNCIODEBUG = "0"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUNBUFFERED = "1"
$env:FRAME_TTL_SECONDS = "60"
$env:HIERARCHY_TTL_SECONDS = "30"
$env:DASHBOARD_QUEUE_SIZE = "10"
$env:GANGSTAR_UVICORN_WORKERS = "1"
$env:PUBLIC_IP = "179.0.179.195"
$env:GANGSTAR_PORT = "5000"

if (Test-Path ".env.vps") {
    Get-Content ".env.vps" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "=") {
            $k, $v = $line -split "=", 2
            Set-Item -Path "env:$($k.Trim())" -Value $v.Trim().Trim('"').Trim("'")
        }
    }
}

if (-not $env:SERVER_URL) {
    $env:SERVER_URL = "http://179.0.179.195:5000"
}
if (-not $env:SERVER_WS_URL) {
    $env:SERVER_WS_URL = "ws://179.0.179.195:5000/ws"
}

Write-Host "[3/4] Frontend (web-dist) pronto." -ForegroundColor Yellow

Write-Host "[4/4] Iniciando servidores (Porta 5000, 80 e 8080)..." -ForegroundColor Yellow
Write-Host ("   Painel principal: " + $env:SERVER_URL) -ForegroundColor Green
Write-Host ("   WebSocket: " + $env:SERVER_WS_URL) -ForegroundColor Green
Write-Host ""

if (Test-Path "$PSScriptRoot\redirect_port80.py") {
    Write-Host "[INFO] Iniciando o redirecionador da porta 80..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList "$PSScriptRoot\redirect_port80.py" -WindowStyle Hidden
    Write-Host "[OK] Redirecionador da porta 80 iniciado." -ForegroundColor Green
}

if (Test-Path "$PSScriptRoot\projeto_bypass\launch_8080.py") {
    Write-Host "[INFO] Iniciando o servidor Bypass na porta 8080..." -ForegroundColor Yellow
    Start-Process -FilePath "python" -ArgumentList "$PSScriptRoot\projeto_bypass\launch_8080.py" -WindowStyle Hidden
    Write-Host "[OK] Servidor Bypass iniciado em segundo plano." -ForegroundColor Green
}

python -m uvicorn main:app --host 0.0.0.0 --port 5000 --workers 1 --http httptools --ws auto --ws-max-size 16777216 --ws-ping-interval 60 --ws-ping-timeout 120 --timeout-keep-alive 120 --limit-concurrency 5000 --backlog 2048

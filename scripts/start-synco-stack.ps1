# Автозапуск стека Synco Law на этом ПК (регистрируется в Планировщике).
# Идемпотентен: уже запущенные части пропускает. Лог: %TEMP%\synco-stack.log
#
# Что делает:
#   1) Docker Desktop + контейнеры (postgres/redis/minio/elasticsearch)
#   2) Бэкенд uvicorn на :8000
#   3) Туннель cloudflared на :8000; при смене URL сам обновляет
#      BACKEND_URL и NEXT_PUBLIC_UPLOAD_API_URL на Vercel и деплоит фронт.

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Log = Join-Path $env:TEMP "synco-stack.log"
$ToolsDir = Join-Path $env:USERPROFILE ".synco"
$Cloudflared = Join-Path $ToolsDir "cloudflared.exe"
$TunnelLog = Join-Path $ToolsDir "cloudflared.log"
$LastUrlFile = Join-Path $ToolsDir "tunnel-url.txt"
$Vercel = Join-Path $env:APPDATA "npm\vercel.cmd"

function Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Tee-Object -FilePath $Log -Append
}

function Test-PortListening($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

Log "=== запуск стека Synco ==="
New-Item -ItemType Directory -Force $ToolsDir | Out-Null

# --- 1. Docker + контейнеры ---
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Log "стартую Docker Desktop"
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    $deadline = (Get-Date).AddMinutes(6)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        docker info 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    }
}
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Log "ОШИБКА: docker daemon не поднялся"; exit 1 }

Set-Location $Root
docker compose up -d postgres redis minio 2>&1 | Out-Null
docker compose --profile search up -d elasticsearch 2>&1 | Out-Null
Log "контейнеры подняты"

# ждём postgres
$deadline = (Get-Date).AddMinutes(2)
while ((Get-Date) -lt $deadline) {
    $ready = docker exec ai-legal-workspace-postgres-1 pg_isready -U legal_user 2>$null
    if ($ready -match "accepting") { break }
    Start-Sleep -Seconds 3
}

# --- 2. Бэкенд ---
if (-not (Test-PortListening 8000)) {
    Log "стартую uvicorn :8000"
    Start-Process -WindowStyle Hidden -WorkingDirectory (Join-Path $Root "backend") `
        -FilePath (Join-Path $Root "backend\.venv\Scripts\python.exe") `
        -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000"
    $deadline = (Get-Date).AddMinutes(2)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        try {
            $health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 5
            if ($health.StatusCode -eq 200) { break }
        } catch {}
    }
} else { Log "uvicorn уже слушает :8000" }

# --- 3. Туннель ---
$tunnelAlive = Get-Process cloudflared -ErrorAction SilentlyContinue
if (-not $tunnelAlive) {
    if (-not (Test-Path $Cloudflared)) { Log "ОШИБКА: нет $Cloudflared"; exit 1 }
    Log "стартую cloudflared"
    if (Test-Path $TunnelLog) { Remove-Item $TunnelLog -Force }
    Start-Process -WindowStyle Hidden -FilePath $Cloudflared `
        -ArgumentList "tunnel","--url","http://localhost:8000" `
        -RedirectStandardError $TunnelLog
    # ждём URL в логе
    $url = $null
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-Path $TunnelLog) {
            $m = Select-String -Path $TunnelLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -AllMatches |
                 Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value; break }
        }
    }
    if (-not $url) { Log "ОШИБКА: URL туннеля не появился"; exit 1 }
    Log "туннель: $url"

    $lastUrl = if (Test-Path $LastUrlFile) { (Get-Content $LastUrlFile -Raw).Trim() } else { "" }
    if ($url -ne $lastUrl) {
        Log "URL сменился ($lastUrl -> $url): обновляю Vercel"
        Set-Location (Join-Path $Root "frontend")
        & $Vercel env rm BACKEND_URL production --yes 2>&1 | Out-Null
        $url | & $Vercel env add BACKEND_URL production 2>&1 | Out-Null
        & $Vercel env rm NEXT_PUBLIC_UPLOAD_API_URL production --yes 2>&1 | Out-Null
        $url | & $Vercel env add NEXT_PUBLIC_UPLOAD_API_URL production 2>&1 | Out-Null
        & $Vercel deploy --prod --yes 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Set-Content -Path $LastUrlFile -Value $url -Encoding ascii
            Log "Vercel обновлён и задеплоен"
        } else {
            Log "ОШИБКА деплоя Vercel — URL не сохранён, повторится при следующем запуске"
        }
    } else { Log "URL не менялся — Vercel трогать не нужно" }
} else { Log "cloudflared уже работает" }

Log "=== стек готов ==="

# Start Dama AN1/AN2 FastAPI app (local or LAN / container-style bind).
# Optional: copy .env.example → .env — an1_app loads .env on startup (does not override existing env vars).
param(
    [switch]$Diy,
    [switch]$Global
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (Test-Path ".venv\Scripts\Activate.ps1") {
    & .\.venv\Scripts\Activate.ps1
}

$port = if ($env:PORT) { $env:PORT } else { 8000 }

if ($Diy) {
    if (-not $env:DAMA_DIY_AUTH) { $env:DAMA_DIY_AUTH = "1" }
    if (-not $env:DAMA_SESSION_SECRET) {
        $env:DAMA_SESSION_SECRET = "local-dev-only-change-in-production"
    }
    # Plain HTTP (localhost / LAN): cookie must not be Secure-only.
    if (-not $env:DAMA_SESSION_HTTPS_ONLY) { $env:DAMA_SESSION_HTTPS_ONLY = "0" }
}

$hostBind = if ($Global) { "0.0.0.0" } else { "127.0.0.1" }

Write-Host "uvicorn an1_app:app --reload --host $hostBind --port $port"
if ($Diy) { Write-Host "  DIY auth: DAMA_DIY_AUTH=1  (landing at /, chat at /app after login)" }
if ($Global) { Write-Host "  Listening on all interfaces — use http://<this-machine>:$port/" }

uvicorn an1_app:app --reload --host $hostBind --port $port

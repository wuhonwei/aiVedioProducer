# AIVP one-click start: backend :8000 + frontend :5173
# Usage: .\scripts\start-dev.ps1  or double-click start-dev.bat

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "backend\pyproject.toml"))) {
    $Root = $PSScriptRoot
}
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Command not found: $Name. Install it and add to PATH."
    }
}

Assert-Command python
Assert-Command npm

Write-Host "==> Preparing backend deps..." -ForegroundColor Cyan
Push-Location $Backend
try {
    if ((-not (Test-Path ".env")) -and (Test-Path ".env.example")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example" -ForegroundColor DarkGray
    }
    python -m pip install -e ".[dev]" -q
}
finally {
    Pop-Location
}

Write-Host "==> Preparing frontend deps..." -ForegroundColor Cyan
Push-Location $Frontend
try {
    if (-not (Test-Path "node_modules")) {
        npm install
    }
}
finally {
    Pop-Location
}

$backendCmd = @(
    "Set-Location -LiteralPath '$Backend'"
    "`$Host.UI.RawUI.WindowTitle = 'AIVP Backend :8000'"
    "Write-Host 'Backend  http://127.0.0.1:8000' -ForegroundColor Green"
    "python -m uvicorn aivp.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000"
) -join "; "

$frontendCmd = @(
    "Set-Location -LiteralPath '$Frontend'"
    "`$Host.UI.RawUI.WindowTitle = 'AIVP Frontend :5173'"
    "Write-Host 'Frontend http://127.0.0.1:5173' -ForegroundColor Green"
    "npm run dev -- --host 127.0.0.1 --port 5173"
) -join "; "

Write-Host "==> Starting backend window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", $backendCmd
)

Start-Sleep -Seconds 1

Write-Host "==> Starting frontend window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", $frontendCmd
)

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:5173"

Write-Host ""
Write-Host "Started:" -ForegroundColor Green
Write-Host "  Frontend  http://127.0.0.1:5173"
Write-Host "  Backend   http://127.0.0.1:8000"
Write-Host "Close those PowerShell windows to stop services."
# Start project-only ComfyUI on 127.0.0.1:8190
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Comfy = Join-Path $Root "tools\ComfyUI"
$Main = Join-Path $Comfy "main.py"
$Python = Join-Path $Comfy ".venv\Scripts\python.exe"

if (-not (Test-Path $Main)) {
    Write-Error "ComfyUI not found at $Comfy. See scripts\setup-comfy.md"
}

if (-not (Test-Path $Python)) {
    Write-Error "Comfy venv python not found: $Python"
}

$listening = Get-NetTCPConnection -LocalPort 8190 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "Port 8190 already in use — ComfyUI may already be running."
    Write-Host "Open http://127.0.0.1:8190"
    exit 0
}

Set-Location $Comfy
Write-Host "Starting project ComfyUI at http://127.0.0.1:8190 ..."
Write-Host "If SAC blocks a .pyd: scripts\patch-comfy-sac-stubs.ps1"
try {
    & $Python $Main --listen 127.0.0.1 --port 8190 @args
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host ""
        Write-Host "ComfyUI exited with code $code" -ForegroundColor Red
        Write-Host "If error was '应用程序控制策略已阻止此文件', run:"
        Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\patch-comfy-sac-stubs.ps1"
        Read-Host "Press Enter to close"
    }
    exit $code
} catch {
    Write-Host ""
    Write-Host "FAILED: $_" -ForegroundColor Red
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\patch-comfy-sac-stubs.ps1"
    Read-Host "Press Enter to close"
    exit 1
}

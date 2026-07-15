# Start project-only ComfyUI on 127.0.0.1:8190
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Comfy = Join-Path $Root "tools\ComfyUI"
$Main = Join-Path $Comfy "main.py"

if (-not (Test-Path $Main)) {
    Write-Error "ComfyUI not found at $Comfy. See scripts\setup-comfy.md and clone a fresh install there."
}

$Python = Join-Path $Comfy ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Set-Location $Comfy
Write-Host "Starting project ComfyUI at http://127.0.0.1:8190 ..."
& $Python $Main --listen 127.0.0.1 --port 8190 @args

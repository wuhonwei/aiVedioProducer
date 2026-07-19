# Bypass Windows Smart App Control blocks that prevent ComfyUI from starting
# (unsigned PyAV / SciPy .pyd). Safe for image-only workflows on port 8190.
param(
    [string]$ComfyRoot = (Join-Path $PSScriptRoot "..\tools\ComfyUI")
)
$ErrorActionPreference = "Stop"
$ComfyRoot = (Resolve-Path $ComfyRoot).Path
$venvPython = Join-Path $ComfyRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Comfy venv not found: $venvPython"
}

Write-Host "1/2  PyAV stub (if needed)..."
& $venvPython (Join-Path $PSScriptRoot "install_comfy_av_stub.py") --comfy-root $ComfyRoot

Write-Host "2/2  SciPy SAC stub..."
& $venvPython (Join-Path $PSScriptRoot "install_comfy_sac_stubs.py") --comfy-root $ComfyRoot

Write-Host ""
Write-Host "Done. Start Comfy with: .\start-comfy.bat"

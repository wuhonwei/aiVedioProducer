# Prefer the combined SAC patch (PyAV + SciPy):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\patch-comfy-sac-stubs.ps1
param(
    [string]$ComfyRoot = (Join-Path $PSScriptRoot "..\tools\ComfyUI")
)
$ErrorActionPreference = "Stop"
$ComfyRoot = (Resolve-Path $ComfyRoot).Path
$venvPython = Join-Path $ComfyRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Comfy venv not found: $venvPython"
}
$helper = Join-Path $PSScriptRoot "install_comfy_av_stub.py"
& $venvPython $helper --comfy-root $ComfyRoot
& $venvPython (Join-Path $PSScriptRoot "install_comfy_sac_stubs.py") --comfy-root $ComfyRoot

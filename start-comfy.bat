@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-comfy.ps1" %*
if errorlevel 1 (
  echo.
  echo ComfyUI start failed. See scripts\setup-comfy.md
  pause
)

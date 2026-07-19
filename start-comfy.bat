@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  AIVP project ComfyUI  ^(port 8190^)
echo ========================================
echo.

set "COMFY=%~dp0tools\ComfyUI"
set "PY=%COMFY%\.venv\Scripts\python.exe"
set "MAIN=%COMFY%\main.py"

if not exist "%MAIN%" (
  echo [ERROR] 找不到 ComfyUI: %MAIN%
  echo 请先按 scripts\setup-comfy.md 安装。
  goto :fail
)

if not exist "%PY%" (
  echo [ERROR] 找不到 venv Python: %PY%
  echo 请先在 tools\ComfyUI 里创建 .venv 并安装依赖。
  goto :fail
)

REM Port already in use?
netstat -ano | findstr ":8190" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [INFO] 端口 8190 已被占用 —— ComfyUI 可能已经在运行。
  echo        浏览器打开: http://127.0.0.1:8190
  echo.
  echo 若其实没开成功，请先结束占用 8190 的进程再重试。
  goto :end
)

echo 正在启动: http://127.0.0.1:8190
echo 若报「应用程序控制策略已阻止此文件」，先运行:
echo   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\patch-comfy-sac-stubs.ps1
echo.
echo 关闭本窗口即停止 ComfyUI。
echo ----------------------------------------

cd /d "%COMFY%"
"%PY%" "%MAIN%" --listen 127.0.0.1 --port 8190 %*
set "EC=%ERRORLEVEL%"

echo.
if not "%EC%"=="0" (
  echo [ERROR] ComfyUI 退出码 %EC%
  echo.
  echo 常见原因:
  echo   1^) Smart App Control 拦截了 scipy/PyAV 的 .pyd
  echo      修复: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\patch-comfy-sac-stubs.ps1
  echo   2^) 杀毒/Defender 拦截了 python.exe 或 torch 相关 DLL
  echo   3^) 依赖损坏 —— 见 scripts\setup-comfy.md
  echo.
  goto :fail
)
goto :end

:fail
echo.
pause
exit /b 1

:end
echo.
pause
exit /b 0

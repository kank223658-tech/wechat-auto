@echo off
rem Convert benchmark videos (in input_videos\, or drag one video onto this bat) to script drafts.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Double-click "1-安装依赖.bat" first.
  pause
  exit /b 1
)

if "%~1"=="" (
  ".venv\Scripts\python.exe" video2script.py input_videos
) else (
  ".venv\Scripts\python.exe" video2script.py %*
)

echo.
echo [DONE] See output\ folder. Open report.md for items to confirm manually.
pause

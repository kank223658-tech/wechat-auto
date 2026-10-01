@echo off
rem One-time dependency installer. Run this first on a new computer.
rem Creates a project-local venv (video2script\.venv) and installs OCR/vision deps.
setlocal
cd /d "%~dp0"
set "PIP_INDEX=-i https://pypi.tuna.tsinghua.edu.cn/simple"

rem 用 --version 实测，避免命中 Windows 商店的 python.exe 占位符（where 能找到但跑不起来）
python --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH. Install Python 3.10+ first: https://www.python.org/downloads/
  echo         Remember to check "Add Python to PATH" during install.
  pause
  exit /b 1
)

rem 若 .venv 是从别的电脑/别的盘符拷来的，里面的 python.exe 会指向不存在的路径。
rem 检测到已失效就删掉重建，否则后面所有 pip 命令都会失败。
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if errorlevel 1 (
    echo [INFO] 现有 .venv 已失效（多为换电脑/换盘符导致），正在重建 ...
    rmdir /s /q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment at .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
)

echo [2/3] Upgrading pip ...
".venv\Scripts\python.exe" -m pip install %PIP_INDEX% --upgrade pip

echo [3/3] Installing dependencies (opencv / rapidocr / numpy / pillow) ...
".venv\Scripts\python.exe" -m pip install %PIP_INDEX% -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed. Check network / proxy and retry.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -c "import cv2, rapidocr_onnxruntime, numpy, PIL; print('DEPS_OK')"
if errorlevel 1 (
  echo [ERROR] Dependency check failed.
  pause
  exit /b 1
)

echo.
echo [OK] Dependencies installed. Now drag a video onto "2-视频转脚本.bat"
pause

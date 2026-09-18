@echo off
rem One-time dependency installer. Run this first on a new computer.
rem Creates a project-local venv (video2script\.venv) and installs OCR/vision deps.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH. Install Python 3.10+ first: https://www.python.org/downloads/
  echo         Remember to check "Add Python to PATH" during install.
  pause
  exit /b 1
)

echo [1/2] Creating virtual environment at .venv ...
python -m venv .venv
if errorlevel 1 (
  echo [ERROR] Failed to create venv.
  pause
  exit /b 1
)

echo [2/2] Installing dependencies (opencv / rapidocr / numpy / pillow) ...
".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade pip
".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
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

@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ==========================================
echo   微信自动化录屏 - 一键启动
echo ==========================================
echo.
echo   start_all.bat             双击默认：启动工作流编辑器（自动打开网页）
echo   start_all.bat editor      启动工作流编辑器（同上）
echo   start_all.bat scene       启动并打开独立场景编辑器
echo   start_all.bat record      开始执行剧本并录制视频（可附加 --headless 等参数）
echo.

:: ---- 1. 选择 Python 启动器（优先 py，其次 python）----
set "PY_CMD=py"
py --version >nul 2>&1
if errorlevel 1 (
    set "PY_CMD=python"
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到 Python，请先安装 Python 3.10 及以上版本。
        pause
        exit /b 1
    )
)

:: ---- 2. 安装缺失的依赖包 ----
%PY_CMD% -c "import playwright, imageio_ffmpeg, pypinyin" >nul 2>&1
if errorlevel 1 (
    echo [依赖] 正在安装 playwright / imageio-ffmpeg / pypinyin ...
    %PY_CMD% -m pip install playwright imageio-ffmpeg pypinyin -q
)

:: ---- 3. 确保 Chromium 内核已下载（已装则跳过，不再每次都检查安装）----
set "PW_BROWSER_DIR=%LOCALAPPDATA%\ms-playwright"
dir /b "%PW_BROWSER_DIR%\chromium-*" >nul 2>&1
if errorlevel 1 (
    echo [依赖] 首次运行，正在下载 Chromium 内核（约 100MB，只需一次）...
    %PY_CMD% -m playwright install chromium
)

:: ---- 4. 根据参数分发 ----
if /i "%1"=="record" goto run_record
if /i "%1"=="scene" goto run_scene

:: 默认 / editor 参数都启动工作流编辑器（自动打开本地网页）
goto run_editor

:run_editor
echo.
echo [运行] 启动工作流编辑器 http://localhost:8000 ...
%PY_CMD% editor_server.py
goto :end

:run_scene
echo.
echo [运行] 启动并打开独立场景编辑器 http://localhost:8000/scene ...
%PY_CMD% editor_server.py --open-scene
goto :end

:run_record
shift
set "REC_ARGS="
:rec_loop
if "%~1"=="" goto rec_done
set "REC_ARGS=%REC_ARGS% %~1"
shift
goto rec_loop
:rec_done
if defined REC_ARGS set "REC_ARGS=%REC_ARGS:~1%"
echo.
echo [运行] 开始执行剧本（录制视频）...
%PY_CMD% main.py %REC_ARGS%
goto :end

:end
echo.
pause
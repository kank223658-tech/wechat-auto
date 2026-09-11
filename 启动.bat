@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo ==========================================
echo   微信自动化录制 - 启动
echo ==========================================
echo.
echo   直接回车 = 启动工作流编辑器（推荐）
echo   输入 scene  = 打开独立场景编辑器
echo   输入 record = 开始执行剧本并录制视频
echo.
call "%~dp0start_all.bat" %*

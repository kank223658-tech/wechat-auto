@echo off
rem Weixin-auto editor server starter
rem 项目装在 U 盘里、盘符随电脑变，所以用 %~dp0（脚本自身所在目录）而不是写死盘符
cd /d "%~dp0"
py editor_server.py
pause

@echo off
rem 候选词方案一键回滚：把 enhance/_backup/ 里最近一次备份拷回 enhance/
rem 用法：双击此文件回滚到最近备份；或传时间戳参数 py restore_candidate_backup.py 20260904_0053
cd /d "%~dp0"
chcp 65001 >nul
py restore_candidate_backup.py %*
echo.
pause
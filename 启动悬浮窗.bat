@echo off
chcp 65001 >nul 2>&1
title 积存金
cd /d "%~dp0"
echo.
echo   🏅 积存金行情悬浮窗
echo   ─────────────────
echo   招商积存金  |  浙商积存金
echo   右键 ⭐ 可管理自选列表
echo.
start "" "%~dp0积存金.exe"
timeout /t 1 >nul
exit

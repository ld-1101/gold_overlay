@echo off
chcp 65001 >nul 2>&1
title 万能弹窗
cd /d "%~dp0"
echo.
echo   🪟 万能弹窗
echo   ─────────────
echo   国际金价 | DeepSeek 余额 | 盈亏计算
echo   右键可切换模块显示
echo.
start "" "%~dp0万能弹窗.exe"
timeout /t 1 >nul
exit

@echo off
title Animation Agent
cd /d "%~dp0"

echo ========================================
echo   Animation Agent
echo ========================================
echo.
echo Starting...
echo.
echo Browser will open automatically.
echo If not, open this URL manually:
echo   http://127.0.0.1:7860
echo.
echo Close this window to stop the program.
echo ========================================
echo.

start "" cmd /c "timeout /t 5 /nobreak >nul && start http://127.0.0.1:7860"

".venv\Scripts\python.exe" "app.py"

echo.
echo Stopped.
pause
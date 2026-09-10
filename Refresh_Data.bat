@echo off
cd /d "%~dp0"
echo Refreshing wealth dashboard data (live stocks/crypto + Excel)...
python refresh_data.py
echo.
pause

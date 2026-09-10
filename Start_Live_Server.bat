@echo off
cd /d "%~dp0"
echo Starting NEXUS Wealth live data server on http://localhost:8787 ...
echo Keep this window open. Open index.html in your browser to see live ticker tape + market intel.
python live_server.py
echo.
pause

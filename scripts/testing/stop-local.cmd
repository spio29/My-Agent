@echo off
setlocal

echo [SPIO] Stopping local stack windows...
taskkill /FI "WINDOWTITLE eq SPIO API*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SPIO WORKER*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SPIO SCHEDULER*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SPIO CONNECTOR*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SPIO UI*" /F >nul 2>&1

echo [SPIO] Stop signal sent.
endlocal

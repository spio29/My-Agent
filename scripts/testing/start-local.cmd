@echo off
setlocal
set "ROOT=%~dp0"

echo [SPIO] Starting local stack...

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo [ERROR] Python venv not found at "%ROOT%.venv\Scripts\python.exe"
  echo Run this first:
  echo   cd /d %ROOT%
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -e .
  pause
  exit /b 1
)

if not exist "%ROOT%ui\node_modules" (
  echo [SPIO] Installing UI dependencies...
  pushd "%ROOT%ui"
  call npm install
  if errorlevel 1 (
    echo [ERROR] npm install failed in "%ROOT%ui"
    popd
    pause
    exit /b 1
  )
  popd
)

echo [SPIO] Opening service windows...
start "SPIO API" cmd /k "cd /d %ROOT% && .\.venv\Scripts\python.exe -m uvicorn app.services.api.main:app --host 127.0.0.1 --port 8000"
start "SPIO WORKER" cmd /k "cd /d %ROOT% && .\.venv\Scripts\python.exe -m app.services.worker.main"
start "SPIO SCHEDULER" cmd /k "cd /d %ROOT% && .\.venv\Scripts\python.exe -m app.services.scheduler.main"
start "SPIO CONNECTOR" cmd /k "cd /d %ROOT% && .\.venv\Scripts\python.exe -m app.services.connector.main"
start "SPIO UI" cmd /k "cd /d %ROOT%ui && npm run build && npm run serve"

echo.
echo [SPIO] Started.
echo API: http://127.0.0.1:8000/healthz
echo UI : http://127.0.0.1:3000
echo.
echo Keep those windows open while using the app.
endlocal

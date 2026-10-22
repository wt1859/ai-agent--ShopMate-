@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo ERROR: uv was not found. Install uv, then run this file again.
  goto :failed
)
if not exist "frontend\dist\index.html" (
  where npm.cmd >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Frontend build is missing. Install Node.js with npm first.
    goto :failed
  )
  echo Building frontend for first startup...
  pushd "frontend"
  call npm.cmd ci
  if errorlevel 1 (
    popd
    goto :failed
  )
  call npm.cmd run build
  if errorlevel 1 (
    popd
    goto :failed
  )
  popd
)
cd /d "%~dp0backend"
echo Preparing backend dependencies...
uv sync
if errorlevel 1 goto :failed
echo Open http://localhost:8765 in your browser.
echo Keep this window open. Press Ctrl+C to stop the demo.
uv run --no-sync uvicorn app:app --app-dir . --host 127.0.0.1 --port 8765
if errorlevel 1 goto :failed
exit /b 0

:failed
echo Demo startup failed. Read the error above before retrying.
if not defined DEMO_NO_PAUSE pause
exit /b 1

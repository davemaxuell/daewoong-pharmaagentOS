@echo off
cd /d "%~dp0..\services\api"
set "APP_ENV=development"
set "DATABASE_URL=sqlite+aiosqlite:///./data/integration.db"
set "OBJECT_STORE_PATH=./data/integration-objects"
set "DEV_AUTH_ENABLED=true"
set "EMBEDDED_WORKER_ENABLED=true"
set "PYTHON_EXE=.venv313\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Backend Python environment is missing. Create services\api\.venv first. 1>&2
  exit /b 1
)
if not exist "data\integration.db" (
  "%PYTHON_EXE%" -m app.cli init-db || exit /b 1
  "%PYTHON_EXE%" -m app.cli seed-demo || exit /b 1
)
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

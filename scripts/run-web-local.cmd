@echo off
cd /d "%~dp0..\apps\web"
set "API_BASE_URL=http://127.0.0.1:8000"
set "API_DEV_USER=portal-dev"
set "API_DEV_ROLES=viewer,reviewer,admin"
node.exe "node_modules\next\dist\bin\next" dev --hostname 127.0.0.1 --port 3000

@echo off
chcp 65001 >nul
cd /d "%~dp0"

call .venv\Scripts\activate.bat

start "web-server" cmd /k python -m app.server

timeout /t 3 /nobreak >nul

start "" "C:\Program Files\Naver\Naver Whale\Application\whale.exe" "http://localhost:8000"

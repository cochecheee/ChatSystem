@echo off
REM =====================================================================
REM stop.bat — Kill chat-system dev processes
REM
REM Stop uvicorn (port 8000), vite (port 5173), ngrok.
REM Run start.bat again to restart.
REM =====================================================================

echo.
echo === Stopping chat-system processes ===
echo.

REM --- Kill anything on port 8000 (backend) ---
echo [*] Backend (port 8000)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo     killing PID %%a
  taskkill /F /PID %%a >nul 2>&1
)

REM --- Kill anything on port 5173 (vite) ---
echo [*] Frontend (port 5173)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
  echo     killing PID %%a
  taskkill /F /PID %%a >nul 2>&1
)

REM --- Kill ngrok (matches by image name) ---
echo [*] ngrok
taskkill /F /IM ngrok.exe >nul 2>&1
if %errorlevel%==0 (echo     ngrok stopped) else (echo     ngrok not running)

echo.
echo Done.

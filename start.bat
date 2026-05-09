@echo off
REM =====================================================================
REM start.bat — Launch chat-system dev stack (backend + frontend + ngrok)
REM
REM Mở 3 console window:
REM   - Backend  (uvicorn, port 8000)
REM   - Frontend (vite, port 5173)
REM   - ngrok    (tunnel public to :8000)
REM
REM Dùng:
REM   start.bat            — chạy cả 3
REM   start.bat backend    — chỉ backend
REM   start.bat frontend   — chỉ frontend
REM   start.bat ngrok      — chỉ ngrok
REM   start.bat stack      — backend + frontend (không ngrok, dev local)
REM =====================================================================

setlocal
cd /d "%~dp0"

set NGROK_PATH=D:\School\DoAnTotNghiep\ngrok-v3-stable-windows-amd64\ngrok.exe
set MODE=%1
if "%MODE%"=="" set MODE=all

echo.
echo === chat-system dev launcher ===
echo Mode: %MODE%
echo.

if /i "%MODE%"=="backend"  goto :backend
if /i "%MODE%"=="frontend" goto :frontend
if /i "%MODE%"=="ngrok"    goto :ngrok
if /i "%MODE%"=="stack"    goto :stack
if /i "%MODE%"=="all"      goto :all
echo Unknown mode: %MODE%
echo Valid: all ^| backend ^| frontend ^| ngrok ^| stack
exit /b 1

:backend
call :launch_backend
goto :done

:frontend
call :launch_frontend
goto :done

:ngrok
call :launch_ngrok
goto :done

:stack
call :launch_backend
call :launch_frontend
goto :done

:all
call :launch_backend
call :launch_frontend
call :launch_ngrok
goto :done

:launch_backend
echo [+] Backend  -> http://localhost:8000  (Swagger /docs)
start "chat-system: backend (uvicorn :8000)" cmd /k ^
  "cd /d %~dp0mcp && call .venv\Scripts\activate.bat && uvicorn src.main:app --reload --port 8000"
exit /b

:launch_frontend
echo [+] Frontend -> http://localhost:5173
start "chat-system: frontend (vite :5173)" cmd /k ^
  "cd /d %~dp0dashboard && npm run dev"
exit /b

:launch_ngrok
if not exist "%NGROK_PATH%" (
  echo [!] ngrok khong tim thay tai %NGROK_PATH%
  echo     Skip — sua bien NGROK_PATH trong start.bat neu can.
  exit /b
)
echo [+] ngrok    -> tunnel http 8000  (URL hien o console ngrok)
start "chat-system: ngrok tunnel" cmd /k "%NGROK_PATH% http 8000"
exit /b

:done
echo.
echo Done. Close ben console nao de stop service tuong ung.
echo Hoac chay: stop.bat
endlocal

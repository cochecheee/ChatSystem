@echo off
REM =====================================================================
REM dev.bat — Convenience wrappers for common dev tasks
REM
REM Dung:
REM   dev.bat test         — pytest backend (200 cases)
REM   dev.bat smoke        — smoke test 7 endpoint (backend phai dang chay)
REM   dev.bat build        — vite build production (tsc -b && vite build)
REM   dev.bat e2e          — playwright e2e
REM   dev.bat migrate      — chay migration v2 (idempotent)
REM   dev.bat reset        — reset DB (xoa hot findings + artifacts)
REM   dev.bat clean        — cleanup orphan failed artifacts
REM   dev.bat lint         — lint GitHub Actions workflows + composite
REM =====================================================================

setlocal
cd /d "%~dp0"

set CMD=%1
if "%CMD%"=="" goto :help

if /i "%CMD%"=="test"    goto :test
if /i "%CMD%"=="smoke"   goto :smoke
if /i "%CMD%"=="build"   goto :build
if /i "%CMD%"=="e2e"     goto :e2e
if /i "%CMD%"=="migrate" goto :migrate
if /i "%CMD%"=="reset"   goto :reset
if /i "%CMD%"=="clean"   goto :clean
if /i "%CMD%"=="lint"    goto :lint
goto :help

:test
echo [pytest] Running 200 backend tests...
cd mcp
call .venv\Scripts\activate.bat
python -m pytest tests/ -q
goto :done

:smoke
echo [smoke] 7-endpoint live check (backend must be running)...
cd mcp
call .venv\Scripts\activate.bat
python -m scripts.smoke_test
goto :done

:build
echo [build] tsc -b ^&^& vite build ...
cd dashboard
call npm run build
goto :done

:e2e
echo [e2e] Playwright (need backend ^+ frontend running)...
cd dashboard
call npx playwright test
goto :done

:migrate
echo [migrate] Adding multi-tenant Project columns + backfill from .env ...
cd mcp
call .venv\Scripts\activate.bat
python -m scripts.migrate_v2
goto :done

:reset
echo [reset] WIPE all findings + artifacts? Press Ctrl+C to abort, or
pause
cd mcp
call .venv\Scripts\activate.bat
python -m scripts.reset_db --apply
goto :done

:clean
echo [clean] Removing orphan failed artifacts (findings preserved)...
cd mcp
call .venv\Scripts\activate.bat
python -m scripts.cleanup_db --apply
goto :done

:lint
echo [lint] Checking GitHub Actions workflows + composite actions...
cd mcp
call .venv\Scripts\activate.bat
python -m scripts.lint_workflows
goto :done

:help
echo.
echo Usage: dev.bat ^<command^>
echo.
echo   test     Run 200 backend pytest cases
echo   smoke    Run 7-endpoint smoke test (backend must be up)
echo   build    Vite production build (tsc + vite)
echo   e2e      Playwright E2E tests
echo   migrate  Add multi-tenant columns + backfill from .env
echo   reset    Wipe findings + artifacts (DESTRUCTIVE — confirms first)
echo   clean    Remove orphan failed artifacts (safe, findings preserved)
echo   lint     Lint GitHub Actions workflows + composite actions
echo.

:done
endlocal

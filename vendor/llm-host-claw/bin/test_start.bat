@echo off
:: Set console encoding to UTF-8
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: Get project root directory (absolute path of parent directory of this script)
pushd "%~dp0.."
set "PROJECT_ROOT=%CD%"
popd

:: Clean old test directory
echo Cleaning old test directory...
if exist "%PROJECT_ROOT%\.cache\userspace" (
    rmdir /s /q "%PROJECT_ROOT%\.cache\userspace"
)

:: Create test directory structure
echo Creating test directory structure...
mkdir "%PROJECT_ROOT%\.cache\userspace\sessions" 2>nul

:: Generate session ID (using powershell to generate UUID)
for /f "delims=" %%i in ('powershell -Command "[guid]::NewGuid().ToString()"') do set "SESSION_ID=%%i"

set "SESSION_DIR=%PROJECT_ROOT%\.cache\userspace\sessions\%SESSION_ID%"
mkdir "%SESSION_DIR%\runs" 2>nul
mkdir "%SESSION_DIR%\skills" 2>nul
mkdir "%SESSION_DIR%\tools" 2>nul
mkdir "%SESSION_DIR%\subagents" 2>nul
mkdir "%SESSION_DIR%\todo" 2>nul

:: Set environment variables
echo Setting environment variables...
set "USERSPACE=%PROJECT_ROOT%\.cache\userspace"
set "SESSIONSPACE=%PROJECT_ROOT%\.cache\userspace\sessions"
set "WORKSPACE=%SESSION_DIR%"
set "RUNSPACE=%SESSION_DIR%\runs"
set "USER_ID=test_user"

:: Generate record ID
for /f "delims=" %%i in ('powershell -Command "[guid]::NewGuid().ToString()"') do set "RECORD_ID=%%i"

if not defined AUTHORIZATION set "AUTHORIZATION=TEST_AUTHORIZATION"
set "TESTING=1"
set "AGNO_DEBUG=true"

:: Load test config and set ORCHESTRATOR_CONFIG
echo Loading test config...
set "PY_SCRIPT=import yaml, json; f = open(r'%PROJECT_ROOT%\tests\test_config.yaml', 'r', encoding='utf-8'); config = yaml.safe_load(f); print(json.dumps(config)); f.close()"
for /f "delims=" %%j in ('python -c "%PY_SCRIPT%"') do set "ORCHESTRATOR_CONFIG=%%j"

:: Print environment info
echo.
echo ============================================================
echo Local test environment set up successfully
echo ============================================================
echo Userspace:    %USERSPACE%
echo Sessionspace: %SESSIONSPACE%
echo Workspace:    %WORKSPACE%
echo Runspace:     %RUNSPACE%
echo Session ID:   %SESSION_ID%
echo User ID:      %USER_ID%
echo Record ID:    %RECORD_ID%
echo ============================================================
echo.

:: Start API Server
echo Starting API Server...
echo API Docs: http://localhost:8000/docs
echo Health Check: http://localhost:8000/health
echo Press Ctrl+C to stop the server
echo.

:: Change directory to src and start the server
cd /d "%PROJECT_ROOT%\src"
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

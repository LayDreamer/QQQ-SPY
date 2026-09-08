@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"

set "VENV_PYTHON=.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [Setup] Creating Python virtual environment...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3.12 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto :failed
)

"%VENV_PYTHON%" -c "import pandas, numpy, httpx, dotenv, pytest" >nul 2>nul
if errorlevel 1 (
    echo [Setup] Installing required packages...
    "%VENV_PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

if "%~1"=="" (
    echo [Run] Starting daily sync, scoring, and report generation...
    "%VENV_PYTHON%" main.py daily
) else (
    echo [Run] python main.py %*
    "%VENV_PYTHON%" main.py %*
)

if errorlevel 1 goto :failed
echo.
echo [Done] Command completed successfully.
set "RUN_EXIT=0"
goto :finish

:failed
echo.
echo [Error] Command failed. Review the messages above.
set "RUN_EXIT=1"

:finish
popd
if not defined INVESTMENT_NO_PAUSE pause
exit /b %RUN_EXIT%

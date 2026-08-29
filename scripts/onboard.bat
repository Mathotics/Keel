@echo off
REM Onboard a local Keel development environment (venv + dependencies).
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0.."

set "MIN_PY=3.12"
set "PY_EXE="
set "PY_EXTRA="

if defined PYTHON (
    "%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo error: PYTHON=%PYTHON% is not Python %MIN_PY% or newer 1>&2
        exit /b 1
    )
    set "PY_EXE=%PYTHON%"
    goto :have_python
)

where python3.12 >nul 2>&1
if not errorlevel 1 (
    python3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=python3.12"
        goto :have_python
    )
)

where python3 >nul 2>&1
if not errorlevel 1 (
    python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=python3"
        goto :have_python
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=python"
        goto :have_python
    )
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=py"
        set "PY_EXTRA=-3.12"
        goto :have_python
    )
)

echo error: Python %MIN_PY% or newer is required ^(set PYTHON to a suitable interpreter^) 1>&2
exit /b 1

:have_python
echo Using Python: %PY_EXE% %PY_EXTRA%
if defined PY_EXTRA (
    "%PY_EXE%" %PY_EXTRA% -m venv .venv
) else (
    "%PY_EXE%" -m venv .venv
)
if errorlevel 1 exit /b 1

set "VENV_PY="
if exist ".venv\Scripts\python.exe" set "VENV_PY=.venv\Scripts\python.exe"
if not defined VENV_PY if exist ".venv\bin\python" set "VENV_PY=.venv\bin\python"
if not defined VENV_PY (
    echo error: virtual environment Python was not created 1>&2
    exit /b 1
)

echo Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 exit /b 1

echo Installing package and development dependencies...
"%VENV_PY%" -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

set "VENV_POE="
if exist ".venv\Scripts\poe.exe" set "VENV_POE=.venv\Scripts\poe.exe"
if not defined VENV_POE if exist ".venv\bin\poe" set "VENV_POE=.venv\bin\poe"
if not defined VENV_POE (
    echo error: poe was not installed into the virtual environment 1>&2
    exit /b 1
)

echo Configuring Poe...
"%VENV_POE%" _list
if errorlevel 1 exit /b 1

echo Configuring pre-commit (git hooks and environments)...
"%VENV_POE%" hooks
if errorlevel 1 exit /b 1

echo Checking isort and mypy...
"%VENV_POE%" isort-check
if errorlevel 1 exit /b 1
"%VENV_POE%" mypy
if errorlevel 1 exit /b 1

if not exist ".env" if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
    echo Created .env from .env.example
)

echo.
echo Onboarding complete.
echo.
echo Activate the virtual environment:
echo   Windows PowerShell:  .\.venv\Scripts\Activate.ps1
echo   Windows cmd:         .venv\Scripts\activate.bat
echo   Unix / Git Bash:     source .venv/bin/activate
echo.
echo Then run: poe serve
exit /b 0

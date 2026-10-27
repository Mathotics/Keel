@echo off
REM Create a git worktree for a new branch, onboard it, and optionally run an agent.
REM Usage:
REM   scripts\deploy-worktree.bat <branch>
REM       [--skip-main-check] [--stash-switch]
REM       [--agent-command <cmd>] [--commit-when-done <msg>] [--push-when-done]
setlocal EnableExtensions EnableDelayedExpansion

REM Capture script location before any SHIFT (SHIFT can corrupt %~dp0).
set "SCRIPT_DIR=%~dp0"
set "BRANCH_NAME="
set "SKIP_MAIN_CHECK=0"
set "STASH_SWITCH=0"
set "AGENT_COMMAND="
set "COMMIT_WHEN_DONE="
set "PUSH_WHEN_DONE=0"
set "HAVE_AGENT=0"
set "HAVE_COMMIT=0"
set "PREVIOUS_BRANCH="
set "DID_STASH=0"
set "STASH_MESSAGE=deploy-worktree:auto-stash"
set "DEFAULT_BRANCH=main"
set "WORKTREE_PATH="
set "MAIN_REPO="
set "ORIGINAL_CD=%CD%"

goto :parse_args

:usage
echo Usage: scripts\deploy-worktree.bat ^<branch^> [options]
echo.
echo Required:
echo   ^<branch^>                  Name of the new branch / worktree directory
echo.
echo Options:
echo   --skip-main-check         Skip verifying the main checkout is on the default branch
echo   --stash-switch            If not on the default branch: stash, checkout default, then restore after
echo   --agent-command ^<cmd^>     After onboard, activate .venv and run: agent ^<cmd^>
echo   --commit-when-done ^<msg^>  In the worktree: git add --all ^&^& git commit -m ^<msg^>
echo   --push-when-done          In the worktree: git push -u origin HEAD
echo   -h, --help                Show this help
exit /b 0

:fail
echo error: %~1 1>&2
call :restore_and_return
exit /b 1

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="-h" goto :usage
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="--skip-main-check" (
    set "SKIP_MAIN_CHECK=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--stash-switch" (
    set "STASH_SWITCH=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--push-when-done" (
    set "PUSH_WHEN_DONE=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--agent-command" (
    if "%~2"=="" (
        echo error: --agent-command requires a value 1>&2
        exit /b 1
    )
    set "AGENT_COMMAND=%~2"
    set "HAVE_AGENT=1"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--commit-when-done" (
    if "%~2"=="" (
        echo error: --commit-when-done requires a value 1>&2
        exit /b 1
    )
    set "COMMIT_WHEN_DONE=%~2"
    set "HAVE_COMMIT=1"
    shift
    shift
    goto :parse_args
)
echo %~1| findstr /b /c:"--" >nul
if not errorlevel 1 (
    echo error: unknown option: %~1 1>&2
    exit /b 1
)
if defined BRANCH_NAME (
    echo error: unexpected argument: %~1 1>&2
    exit /b 1
)
set "BRANCH_NAME=%~1"
shift
goto :parse_args

:args_done
if not defined BRANCH_NAME (
    call :usage
    echo error: branch name is required 1>&2
    exit /b 1
)
if "%SKIP_MAIN_CHECK%"=="1" if "%STASH_SWITCH%"=="1" (
    echo error: --skip-main-check and --stash-switch cannot be used together 1>&2
    exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
    echo error: git is required 1>&2
    exit /b 1
)

cd /d "%SCRIPT_DIR%.."
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo error: deploy-worktree must run inside the Keel git repository 1>&2
    exit /b 1
)

for /f "delims=" %%I in ('git rev-parse --git-common-dir') do set "GIT_COMMON=%%I"
pushd "%GIT_COMMON%\.."
set "MAIN_REPO=%CD%"
popd
for /f "delims=" %%I in ('git rev-parse --show-toplevel') do set "TOP_LEVEL_RAW=%%I"
pushd "%TOP_LEVEL_RAW%"
set "TOP_LEVEL=%CD%"
popd
if /i not "%TOP_LEVEL%"=="%MAIN_REPO%" (
    echo error: run this script from the main repository checkout ^(%MAIN_REPO%^), not a linked worktree 1>&2
    exit /b 1
)
cd /d "%MAIN_REPO%"

for /f "delims=" %%I in ('git symbolic-ref refs/remotes/origin/HEAD 2^>nul') do (
    set "ORIGIN_HEAD=%%I"
)
if defined ORIGIN_HEAD (
    set "DEFAULT_BRANCH=!ORIGIN_HEAD:refs/remotes/origin/=!"
)

REM Step 0 / 0a / 0b
if "%SKIP_MAIN_CHECK%"=="0" (
    for /f "delims=" %%I in ('git branch --show-current') do set "CURRENT_BRANCH=%%I"
    if not defined CURRENT_BRANCH (
        call :fail "detached HEAD; check out '%DEFAULT_BRANCH%' (or pass --skip-main-check / --stash-switch)"
        exit /b 1
    )
    if /i not "!CURRENT_BRANCH!"=="!DEFAULT_BRANCH!" (
        if "%STASH_SWITCH%"=="0" (
            call :fail "main checkout is on '!CURRENT_BRANCH!', expected '!DEFAULT_BRANCH!' (use --stash-switch or --skip-main-check)"
            exit /b 1
        )
        echo Not on '!DEFAULT_BRANCH!' ^(on '!CURRENT_BRANCH!'^); stashing and switching...
        set "PREVIOUS_BRANCH=!CURRENT_BRANCH!"
        set "STASH_OUT="
        for /f "delims=" %%I in ('git stash push -u -m "%STASH_MESSAGE%" 2^>^&1') do (
            set "STASH_OUT=!STASH_OUT! %%I"
        )
        if errorlevel 1 (
            call :fail "git stash failed"
            exit /b 1
        )
        echo !STASH_OUT! | findstr /c:"No local changes to save" >nul
        if errorlevel 1 set "DID_STASH=1"
        git checkout "!DEFAULT_BRANCH!"
        if errorlevel 1 (
            call :fail "git checkout !DEFAULT_BRANCH! failed"
            exit /b 1
        )
    )
)

REM Step 1
echo Fetching and updating '!DEFAULT_BRANCH!'...
git fetch origin
if errorlevel 1 (
    call :fail "git fetch failed"
    exit /b 1
)
git pull --ff-only origin !DEFAULT_BRANCH!
if errorlevel 1 (
    call :fail "git pull --ff-only origin !DEFAULT_BRANCH! failed"
    exit /b 1
)

REM Step 2
set "WORKTREES_PARENT=%MAIN_REPO%.worktrees"
set "WORKTREE_PATH=%WORKTREES_PARENT%\%BRANCH_NAME%"
if exist "%WORKTREE_PATH%" (
    call :fail "worktree path already exists: %WORKTREE_PATH%"
    exit /b 1
)
if not exist "%WORKTREES_PARENT%" mkdir "%WORKTREES_PARENT%"
echo Creating worktree at %WORKTREE_PATH% ^(branch '%BRANCH_NAME%'^)...
git worktree add "%WORKTREE_PATH%" -b "%BRANCH_NAME%"
if errorlevel 1 (
    call :fail "git worktree add failed"
    exit /b 1
)

REM Steps 3-7
cd /d "%WORKTREE_PATH%"

echo Running onboard...
call "%WORKTREE_PATH%\scripts\onboard.bat"
if errorlevel 1 (
    call :fail "onboard.bat failed"
    exit /b 1
)

if "%HAVE_AGENT%"=="1" (
    echo Activating virtual environment...
    if not exist "%WORKTREE_PATH%\.venv\Scripts\activate.bat" (
        call :fail "venv activate script not found"
        exit /b 1
    )
    call "%WORKTREE_PATH%\.venv\Scripts\activate.bat"
    echo Running agent: agent %AGENT_COMMAND%
    call agent %AGENT_COMMAND%
    if errorlevel 1 (
        call :fail "agent command failed"
        exit /b 1
    )
)

if "%HAVE_COMMIT%"=="1" (
    echo Committing worktree changes...
    git add --all
    if errorlevel 1 (
        call :fail "git add failed"
        exit /b 1
    )
    git commit -m "%COMMIT_WHEN_DONE%"
    if errorlevel 1 (
        call :fail "git commit failed"
        exit /b 1
    )
)

if "%PUSH_WHEN_DONE%"=="1" (
    echo Pushing worktree branch...
    git push -u origin HEAD
    if errorlevel 1 (
        call :fail "git push failed"
        exit /b 1
    )
)

call :restore_and_return
echo.
echo Worktree ready: %WORKTREE_PATH%
echo Branch: %BRANCH_NAME%
exit /b 0

:restore_and_return
cd /d "%MAIN_REPO%" 2>nul
if defined PREVIOUS_BRANCH if not "%PREVIOUS_BRANCH%"=="" (
    echo Restoring branch '%PREVIOUS_BRANCH%'...
    git checkout "%PREVIOUS_BRANCH%"
    if errorlevel 1 (
        echo warning: failed to checkout previous branch '%PREVIOUS_BRANCH%' 1>&2
    ) else if "%DID_STASH%"=="1" (
        echo Restoring stashed changes...
        git stash pop
        if errorlevel 1 echo warning: git stash pop failed; stash may still be on the stack 1>&2
    )
)
cd /d "%ORIGINAL_CD%" 2>nul
exit /b 0

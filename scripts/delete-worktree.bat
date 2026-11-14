@echo off
REM Remove a git worktree and its local branch created by deploy-worktree.
REM Usage:
REM   scripts\delete-worktree.bat <branch> [--force]
setlocal EnableExtensions EnableDelayedExpansion

REM Capture script location before any SHIFT (SHIFT can corrupt %~dp0).
set "SCRIPT_DIR=%~dp0"
set "BRANCH_NAME="
set "FORCE=0"
set "DEFAULT_BRANCH=main"
set "MAIN_REPO="
set "ORIGINAL_CD=%CD%"

goto :parse_args

:usage
echo Usage: scripts\delete-worktree.bat ^<branch^> [options]
echo.
echo Required:
echo   ^<branch^>                  Name of the branch / worktree directory to remove
echo.
echo Options:
echo   --force                   Discard uncommitted changes and delete the branch
echo                             even if it is not fully merged
echo   -h, --help                Show this help
echo.
echo The worktree path is ^<repository^>.worktrees\^<branch^>, the same place
echo deploy-worktree creates it. The local branch is deleted with the worktree.
echo A remote branch is left in place. Run this script from the main checkout.
exit /b 0

:die
echo error: %~1 1>&2
cd /d "%ORIGINAL_CD%" 2>nul
exit /b 1

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="-h" goto :usage
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="--force" (
    set "FORCE=1"
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

set "GIT_BRANCH=!BRANCH_NAME:\=/!"
if not defined GIT_BRANCH (
    echo error: invalid branch name: %BRANCH_NAME% 1>&2
    exit /b 1
)
set "BAD_NAME=0"
if "!GIT_BRANCH:~0,1!"=="/" set "BAD_NAME=1"
if "!GIT_BRANCH:~0,1!"=="-" set "BAD_NAME=1"
if "!GIT_BRANCH:~0,1!"=="." set "BAD_NAME=1"
if "!GIT_BRANCH:~-1!"=="/" set "BAD_NAME=1"
set "STRIPPED=!GIT_BRANCH:..=!"
if not "!GIT_BRANCH!"=="!STRIPPED!" set "BAD_NAME=1"
set "STRIPPED=!GIT_BRANCH://=!"
if not "!GIT_BRANCH!"=="!STRIPPED!" set "BAD_NAME=1"
set "STRIPPED=!GIT_BRANCH:/./=!"
if not "!GIT_BRANCH!"=="!STRIPPED!" set "BAD_NAME=1"
if "!GIT_BRANCH:~-2!"=="/." set "BAD_NAME=1"
for %%C in ("<" ">" ":" "|" "?" "*") do (
    set "STRIPPED=!GIT_BRANCH:%%~C=!"
    if not "!GIT_BRANCH!"=="!STRIPPED!" set "BAD_NAME=1"
)
if "!BAD_NAME!"=="1" (
    echo error: invalid branch name: %BRANCH_NAME% 1>&2
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
    call :die "delete-worktree must run inside the Keel git repository"
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
    call :die "run this script from the main repository checkout %MAIN_REPO%, not a linked worktree"
    exit /b 1
)
cd /d "%MAIN_REPO%"

for /f "delims=" %%I in ('git symbolic-ref refs/remotes/origin/HEAD 2^>nul') do set "ORIGIN_HEAD=%%I"
if defined ORIGIN_HEAD (
    set "DEFAULT_BRANCH=!ORIGIN_HEAD:refs/remotes/origin/=!"
)
if /i "!GIT_BRANCH!"=="!DEFAULT_BRANCH!" (
    call :die "refusing to delete the default branch '!DEFAULT_BRANCH!'"
    exit /b 1
)

set "CURRENT_BRANCH="
for /f "delims=" %%I in ('git branch --show-current') do set "CURRENT_BRANCH=%%I"
if /i "!CURRENT_BRANCH!"=="!GIT_BRANCH!" (
    call :die "branch '!GIT_BRANCH!' is checked out in the main repository"
    exit /b 1
)

set "WORKTREES_PARENT=%MAIN_REPO%.worktrees"
set "RELATIVE=!GIT_BRANCH:/=\!"
set "WORKTREE_PATH=%WORKTREES_PARENT%\!RELATIVE!"
set "BRANCH_REF=refs/heads/!GIT_BRANCH!"

set "MATCHED=0"
set "MATCH_BRANCH="
set "MATCH_DETACHED=0"
set "CHECKOUT_PATH="
set "CUR_PATH="
set "CUR_BRANCH="
set "CUR_DETACHED=0"

for /f "delims=" %%L in ('git worktree list --porcelain') do (
    set "LINE=%%L"
    if /i "!LINE:~0,9!"=="worktree " (
        call :consider_worktree
        set "CUR_PATH=!LINE:~9!"
        set "CUR_PATH=!CUR_PATH:/=\!"
        set "CUR_BRANCH="
        set "CUR_DETACHED=0"
    )
    if /i "!LINE:~0,7!"=="branch " set "CUR_BRANCH=!LINE:~7!"
    if /i "!LINE!"=="detached" set "CUR_DETACHED=1"
)
call :consider_worktree

git show-ref --verify --quiet "refs/heads/!GIT_BRANCH!" 2>nul
if errorlevel 1 (
    set "BRANCH_EXISTS=0"
) else (
    set "BRANCH_EXISTS=1"
)

if "!MATCHED!"=="1" (
    if "!MATCH_DETACHED!"=="1" (
        call :die "worktree at !WORKTREE_PATH! is detached; expected branch '!GIT_BRANCH!'"
        exit /b 1
    )
    if not "!MATCH_BRANCH!"=="!BRANCH_REF!" (
        set "OTHER=!MATCH_BRANCH:refs/heads/=!"
        call :die "worktree at !WORKTREE_PATH! is on '!OTHER!', not '!GIT_BRANCH!'"
        exit /b 1
    )
    if "!FORCE!"=="0" (
        set "DIRTY=0"
        for /f "delims=" %%I in ('git -C "!WORKTREE_PATH!" status --porcelain') do set "DIRTY=1"
        if "!DIRTY!"=="1" (
            call :die "worktree has uncommitted changes; re-run with --force to discard them"
            exit /b 1
        )
    )
    if "!BRANCH_EXISTS!"=="1" if "!FORCE!"=="0" (
        call :branch_merged
        if "!MERGED!"=="0" (
            call :die "branch '!GIT_BRANCH!' is not fully merged; re-run with --force to delete it"
            exit /b 1
        )
    )
    echo Removing worktree at !WORKTREE_PATH!...
    if "!FORCE!"=="1" (
        git worktree remove --force -- "!WORKTREE_PATH!"
    ) else (
        git worktree remove -- "!WORKTREE_PATH!"
    )
    if errorlevel 1 (
        call :die "git worktree remove failed"
        exit /b 1
    )
    set "REMOVED_WORKTREE=1"
    goto :delete_branch
)

if exist "!WORKTREE_PATH!" (
    call :die "path exists but is not a registered git worktree: !WORKTREE_PATH!"
    exit /b 1
)
if defined CHECKOUT_PATH (
    call :die "branch '!GIT_BRANCH!' is checked out at !CHECKOUT_PATH!, not at !WORKTREE_PATH!"
    exit /b 1
)
if "!BRANCH_EXISTS!"=="0" (
    call :die "no worktree or local branch named '!GIT_BRANCH!'"
    exit /b 1
)
if "!FORCE!"=="0" (
    call :branch_merged
    if "!MERGED!"=="0" (
        call :die "branch '!GIT_BRANCH!' is not fully merged; re-run with --force to delete it"
        exit /b 1
    )
)
echo Worktree path already absent: !WORKTREE_PATH!
set "REMOVED_WORKTREE=0"

:delete_branch
if "!BRANCH_EXISTS!"=="1" (
    echo Deleting local branch '!GIT_BRANCH!'...
    if "!FORCE!"=="1" (
        git branch -D -- "!GIT_BRANCH!"
    ) else (
        git branch -d -- "!GIT_BRANCH!"
    )
    if errorlevel 1 (
        call :die "git branch delete failed"
        exit /b 1
    )
)

if exist "!WORKTREES_PARENT!" rmdir "!WORKTREES_PARENT!" 2>nul

echo.
if "!REMOVED_WORKTREE!"=="1" echo Worktree removed: !WORKTREE_PATH!
if "!BRANCH_EXISTS!"=="1" echo Branch deleted: !GIT_BRANCH!
echo Remote branches were left in place.
cd /d "%ORIGINAL_CD%" 2>nul
exit /b 0

:consider_worktree
if not defined CUR_PATH exit /b 0
if /i "!CUR_PATH!"=="!WORKTREE_PATH!" (
    set "MATCHED=1"
    set "MATCH_BRANCH=!CUR_BRANCH!"
    set "MATCH_DETACHED=!CUR_DETACHED!"
)
if /i "!CUR_BRANCH!"=="!BRANCH_REF!" set "CHECKOUT_PATH=!CUR_PATH!"
exit /b 0

:branch_merged
set "MERGED=0"
git merge-base --is-ancestor -- "!GIT_BRANCH!" HEAD
if not errorlevel 1 (
    set "MERGED=1"
    exit /b 0
)
set "UPSTREAM="
for /f "delims=" %%I in ('git rev-parse --abbrev-ref -- "!GIT_BRANCH!@{upstream}" 2^>nul') do set "UPSTREAM=%%I"
if not defined UPSTREAM exit /b 0
git merge-base --is-ancestor -- "!GIT_BRANCH!" "!UPSTREAM!"
if not errorlevel 1 set "MERGED=1"
exit /b 0

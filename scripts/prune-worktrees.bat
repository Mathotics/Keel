@echo off
REM Remove merged and stale git worktrees and their local branches.
REM Usage:
REM   scripts\prune-worktrees.bat [--dry-run] [--stale] [--force]
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "ORIGINAL_CD=%CD%"
set "DRY_RUN=0"
set "VERBOSE=0"
set "FORCE=0"
set "INCLUDE_STALE=0"
set "SKIP_MERGED=0"
set "WORKTREES_ONLY=0"
set "STALE_DAYS=90"
set "DEFAULT_BRANCH=main"
set "ORIGIN_DEFAULT="
set "FAILED=0"
set "REMOVED_WORKTREES=0"
set "REMOVED_BRANCHES=0"
set "SKIPPED=0"
set "WT_COUNT=0"
set "MAIN_REPO="
set "START_TOP="
set "SCRIPT_TOP="

goto :parse_args

:usage
echo Usage: scripts\prune-worktrees.bat [options]
echo.
echo With no options, remove every managed worktree whose branch is merged
echo into the default branch, and every local branch that is merged into the
echo default branch and is not checked out. A managed worktree lives under
echo ^<repository^>.worktrees, the directory deploy-worktree creates.
echo.
echo A branch counts as merged when its tip is contained in the local default
echo branch, or in origin/^<default^> when that remote-tracking ref exists.
echo Squash merges are not detected. Remote branches are left in place.
echo.
echo The default branch and the main checkout are never removed. A worktree
echo this command was started from is left in place. Run it from any checkout.
echo.
echo Options:
echo   --stale                   Also select worktrees and branches whose tip
echo                             commit is at least --stale-days old
echo   --stale-days ^<days^>       Age threshold for --stale ^(default: 90^).
echo                             Passing this turns --stale on
echo   --skip-merged             Do not remove items only because they are merged
echo   --worktrees-only          Do not delete local branches that have no
echo                             managed worktree
echo   --force                   Discard uncommitted changes, unlock a locked
echo                             worktree, and delete an unmerged branch selected
echo                             by --stale
echo   -n, --dry-run             Print what would be removed and change nothing
echo   -v, --verbose             Explain why each worktree and branch was kept
echo   -h, --help                Show this help
exit /b 0

:die
echo error: %~1 1>&2
cd /d "%ORIGINAL_CD%" 2>nul
exit /b 1

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="-h" goto :usage
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="-n" goto :set_dry
if /i "%~1"=="--dry-run" goto :set_dry
if /i "%~1"=="-v" goto :set_verbose
if /i "%~1"=="--verbose" goto :set_verbose
if /i "%~1"=="--force" goto :set_force
if /i "%~1"=="--stale" goto :set_stale
if /i "%~1"=="--skip-merged" goto :set_skip_merged
if /i "%~1"=="--worktrees-only" goto :set_worktrees_only
if /i "%~1"=="--stale-days" goto :set_stale_days
echo %~1| findstr /b /c:"--" >nul
if not errorlevel 1 (
    echo error: unknown option: %~1 1>&2
    exit /b 1
)
echo error: unexpected argument: %~1 1>&2
exit /b 1

:set_dry
set "DRY_RUN=1"
shift
goto :parse_args

:set_verbose
set "VERBOSE=1"
shift
goto :parse_args

:set_force
set "FORCE=1"
shift
goto :parse_args

:set_stale
set "INCLUDE_STALE=1"
shift
goto :parse_args

:set_skip_merged
set "SKIP_MERGED=1"
shift
goto :parse_args

:set_worktrees_only
set "WORKTREES_ONLY=1"
shift
goto :parse_args

:set_stale_days
if "%~2"=="" (
    echo error: --stale-days requires a value 1>&2
    exit /b 1
)
set "RAW_DAYS=%~2"
set "BAD="
for /f "delims=0123456789" %%X in ("!RAW_DAYS!") do set "BAD=1"
if defined BAD (
    echo error: --stale-days must be a positive integer 1>&2
    exit /b 1
)
set "STRIP="
for /f "tokens=* delims=0" %%Z in ("!RAW_DAYS!") do set "STRIP=%%Z"
if not defined STRIP set "STRIP=0"
if "!STRIP!"=="0" (
    echo error: --stale-days must be a positive integer 1>&2
    exit /b 1
)
set "STALE_DAYS=!STRIP!"
set "INCLUDE_STALE=1"
shift
shift
goto :parse_args

:args_done
if "!SKIP_MERGED!"=="1" if "!INCLUDE_STALE!"=="0" (
    echo error: --skip-merged removes nothing unless --stale is set 1>&2
    exit /b 1
)
where git >nul 2>&1
if errorlevel 1 (
    echo error: git is required 1>&2
    exit /b 1
)

git rev-parse --show-toplevel >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%I in ('git rev-parse --show-toplevel') do set "START_TOP=%%I"
)

cd /d "%SCRIPT_DIR%.."
set "SCRIPT_TOP=%CD%"
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    call :die "prune-worktrees must run inside a git repository"
    exit /b 1
)

for /f "delims=" %%I in ('git rev-parse --git-common-dir') do set "GIT_COMMON=%%I"
pushd "%GIT_COMMON%\.."
set "MAIN_REPO=%CD%"
popd
cd /d "%MAIN_REPO%"

for /f "delims=" %%I in ('git symbolic-ref refs/remotes/origin/HEAD 2^>nul') do set "ORIGIN_HEAD=%%I"
if defined ORIGIN_HEAD set "DEFAULT_BRANCH=!ORIGIN_HEAD:refs/remotes/origin/=!"
git show-ref --verify --quiet "refs/heads/!DEFAULT_BRANCH!"
if errorlevel 1 (
    call :die "default branch '!DEFAULT_BRANCH!' does not exist locally"
    exit /b 1
)
git show-ref --verify --quiet "refs/remotes/origin/!DEFAULT_BRANCH!"
if not errorlevel 1 set "ORIGIN_DEFAULT=origin/!DEFAULT_BRANCH!"

for /f %%T in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "NOW=%%T"
set "WORKTREES_PARENT=!MAIN_REPO!.worktrees"
set "PLAN=%TEMP%\prune-worktrees-%RANDOM%-%RANDOM%.plan"
set "CHECKED=%TEMP%\prune-checked-%RANDOM%-%RANDOM%.txt"
set "CLAIMED=%TEMP%\prune-claimed-%RANDOM%-%RANDOM%.txt"
type nul > "%PLAN%"
type nul > "%CHECKED%"
type nul > "%CLAIMED%"

set "CUR_PATH="
set "CUR_BRANCH="
set "CUR_HEAD="
set "CUR_LOCKED=0"
for /f "delims=" %%L in ('git worktree list --porcelain') do (
    set "LINE=%%L"
    call :on_line
)
call :save_worktree

set /a I=0
:checked_loop
set /a I+=1
if !I! GTR !WT_COUNT! goto :select_worktrees
call :load_wt !I!
call :short_branch
if defined SHORT >>"%CHECKED%" echo !SHORT!
goto :checked_loop

:select_worktrees
set /a I=0
:select_wt_loop
set /a I+=1
if !I! GTR !WT_COUNT! goto :select_branches
call :load_wt !I!
call :short_branch
call :select_worktree
goto :select_wt_loop

:select_branches
if "!WORKTREES_ONLY!"=="1" goto :run_plan
set "REF_FMT=%%(refname:short)"
for /f "delims=" %%B in ('git for-each-ref --format^=!REF_FMT! refs/heads') do (
    call :select_branch "%%B"
)

:run_plan
for /f "usebackq tokens=1-6 delims=|" %%A in ("%PLAN%") do (
    call :do_action "%%A" "%%B" "%%C" "%%D" "%%E" "%%F"
)
call :clean_dirs
call :summary
del "%PLAN%" "%CHECKED%" "%CLAIMED%" 2>nul
cd /d "%ORIGINAL_CD%"
if "!FAILED!"=="1" exit /b 1
exit /b 0

:on_line
if not defined LINE exit /b 0
if /i "!LINE:~0,9!"=="worktree " (
    call :save_worktree
    set "CUR_PATH=!LINE:~9!"
    set "CUR_BRANCH="
    set "CUR_HEAD="
    set "CUR_LOCKED=0"
    exit /b 0
)
if /i "!LINE:~0,5!"=="HEAD " (
    set "CUR_HEAD=!LINE:~5!"
    exit /b 0
)
if /i "!LINE:~0,7!"=="branch " (
    set "CUR_BRANCH=!LINE:~7!"
    exit /b 0
)
if /i "!LINE!"=="detached" exit /b 0
if /i "!LINE:~0,6!"=="locked" set "CUR_LOCKED=1"
exit /b 0

:save_worktree
if not defined CUR_PATH exit /b 0
set /a WT_COUNT+=1
set "WT_PATH_%WT_COUNT%=!CUR_PATH!"
set "WT_BRANCH_%WT_COUNT%=!CUR_BRANCH!"
set "WT_HEAD_%WT_COUNT%=!CUR_HEAD!"
set "WT_LOCKED_%WT_COUNT%=!CUR_LOCKED!"
set "CUR_PATH="
exit /b 0

:load_wt
set "IDX=%~1"
call set "THIS_PATH=%%WT_PATH_%IDX%%%"
call set "THIS_BRANCH=%%WT_BRANCH_%IDX%%%"
call set "THIS_HEAD=%%WT_HEAD_%IDX%%%"
call set "THIS_LOCKED=%%WT_LOCKED_%IDX%%%"
exit /b 0

:short_branch
set "SHORT=!THIS_BRANCH!"
if /i "!SHORT:~0,11!"=="refs/heads/" set "SHORT=!SHORT:~11!"
exit /b 0

:is_same
set "SAME=0"
set "LEFT=%~1"
set "RIGHT=%~2"
set "LEFT=!LEFT:/=\!"
set "RIGHT=!RIGHT:/=\!"
if /i "!LEFT!"=="!RIGHT!" set "SAME=1"
exit /b 0

:is_inside
set "INSIDE=0"
set "PARENT_N=%~1"
set "CHILD_N=%~2"
set "PARENT_N=!PARENT_N:/=\!"
set "CHILD_N=!CHILD_N:/=\!"
if /i "!CHILD_N!"=="!PARENT_N!" exit /b 0
set "PREFIX=!PARENT_N!\"
call set "STRIPPED=%%CHILD_N:!PREFIX!=%%"
if /i "!PREFIX!!STRIPPED!"=="!CHILD_N!" set "INSIDE=1"
exit /b 0

:is_merged
set "MERGED=0"
set "REV=%~1"
git merge-base --is-ancestor -- "!REV!" "!DEFAULT_BRANCH!" >nul 2>&1
if not errorlevel 1 (
    set "MERGED=1"
    exit /b 0
)
if not defined ORIGIN_DEFAULT exit /b 0
git merge-base --is-ancestor -- "!REV!" "!ORIGIN_DEFAULT!" >nul 2>&1
if not errorlevel 1 set "MERGED=1"
exit /b 0

:read_epoch
set "EPOCH="
set "REV=%~1"
for /f %%T in ('git log -1 --format^=%%ct "!REV!"') do set "EPOCH=%%T"
exit /b 0

:mark_stale
set "IS_STALE=0"
set "AGE_DAYS="
call :read_epoch "%~1"
if not defined EPOCH exit /b 0
set /a AGE_SEC=!NOW!-!EPOCH!
set /a AGE_DAYS=!AGE_SEC!/86400
if !AGE_DAYS! LSS 0 set "AGE_DAYS=0"
set /a LIMIT=!STALE_DAYS!*86400
if !AGE_SEC! GEQ !LIMIT! set "IS_STALE=1"
exit /b 0

:is_dirty
set "DIRTY=0"
for /f "delims=" %%L in ('git -C "%~1" status --porcelain') do set "DIRTY=1"
exit /b 0

:listed_in
set "LISTED=0"
findstr /x /l /c:"%~1" "%~2" >nul 2>&1
if not errorlevel 1 set "LISTED=1"
exit /b 0

:select_worktree
call :is_same "!THIS_PATH!" "!MAIN_REPO!"
if "!SAME!"=="1" (
    if "!VERBOSE!"=="1" echo keep worktree !THIS_PATH!: main checkout
    exit /b 0
)
call :is_inside "!WORKTREES_PARENT!" "!THIS_PATH!"
if "!INSIDE!"=="0" (
    if "!VERBOSE!"=="1" echo keep worktree !THIS_PATH!: outside !WORKTREES_PARENT!
    exit /b 0
)
if defined START_TOP (
    call :is_same "!THIS_PATH!" "!START_TOP!"
    if "!SAME!"=="1" (
        if "!VERBOSE!"=="1" echo keep worktree !THIS_PATH!: this command was started here
        exit /b 0
    )
)
if /i not "!SCRIPT_TOP!"=="!MAIN_REPO!" (
    call :is_same "!THIS_PATH!" "!SCRIPT_TOP!"
    if "!SAME!"=="1" (
        if "!VERBOSE!"=="1" echo keep worktree !THIS_PATH!: this command was started here
        exit /b 0
    )
)
set "REV=!SHORT!"
if not defined REV set "REV=!THIS_HEAD!"
if not defined REV exit /b 0
if /i "!SHORT!"=="!DEFAULT_BRANCH!" (
    if "!VERBOSE!"=="1" echo keep worktree !THIS_PATH!: default branch
    exit /b 0
)
call :is_merged "!REV!"
call :mark_stale "!REV!"
set "REASON="
if "!SKIP_MERGED!"=="0" if "!MERGED!"=="1" set "REASON=merged into !DEFAULT_BRANCH!"
if not defined REASON if "!INCLUDE_STALE!"=="1" if "!IS_STALE!"=="1" set "REASON=stale, !AGE_DAYS! days"
if not defined REASON exit /b 0
call :is_dirty "!THIS_PATH!"
set "BLOCKERS="
if "!DIRTY!"=="1" set "BLOCKERS=uncommitted changes"
if "!THIS_LOCKED!"=="1" (
    if defined BLOCKERS (
        set "BLOCKERS=!BLOCKERS!, locked"
    ) else (
        set "BLOCKERS=locked"
    )
)
if "!MERGED!"=="0" (
    if defined BLOCKERS (
        set "BLOCKERS=!BLOCKERS!, not merged into !DEFAULT_BRANCH!"
    ) else (
        set "BLOCKERS=not merged into !DEFAULT_BRANCH!"
    )
)
if defined BLOCKERS if "!FORCE!"=="0" (
    set "LABEL=!SHORT!"
    if not defined LABEL set "LABEL=detached"
    echo skip: worktree !THIS_PATH! branch !LABEL!: !BLOCKERS!; re-run with --force
    set /a SKIPPED+=1
    exit /b 0
)
set "ACT_BRANCH=!SHORT!"
if not defined ACT_BRANCH set "ACT_BRANCH=."
if defined SHORT >>"%CLAIMED%" echo !SHORT!
call :append_action worktree "!THIS_PATH!" "!ACT_BRANCH!" "!REASON!" "!MERGED!" "!THIS_LOCKED!"
exit /b 0

:select_branch
set "NAME=%~1"
if not defined NAME exit /b 0
call :listed_in "!NAME!" "%CLAIMED%"
if "!LISTED!"=="1" exit /b 0
if /i "!NAME!"=="!DEFAULT_BRANCH!" exit /b 0
call :listed_in "!NAME!" "%CHECKED%"
if "!LISTED!"=="1" exit /b 0
call :is_merged "!NAME!"
call :mark_stale "!NAME!"
set "REASON="
if "!SKIP_MERGED!"=="0" if "!MERGED!"=="1" set "REASON=merged into !DEFAULT_BRANCH!"
if not defined REASON if "!INCLUDE_STALE!"=="1" if "!IS_STALE!"=="1" set "REASON=stale, !AGE_DAYS! days"
if not defined REASON exit /b 0
if "!MERGED!"=="0" if "!FORCE!"=="0" (
    echo skip: branch !NAME!: not merged into !DEFAULT_BRANCH!; re-run with --force
    set /a SKIPPED+=1
    exit /b 0
)
call :append_action branch "." "!NAME!" "!REASON!" "!MERGED!" "0"
exit /b 0

:append_action
>>"%PLAN%" echo %~1^|%~2^|%~3^|%~4^|%~5^|%~6
exit /b 0

:do_action
set "KIND=%~1"
set "ACT_PATH=%~2"
set "ACT_BRANCH=%~3"
set "ACT_REASON=%~4"
set "ACT_MERGED=%~5"
set "ACT_LOCKED=%~6"
if "!ACT_BRANCH!"=="." set "ACT_BRANCH="
if /i "!KIND!"=="worktree" goto :do_worktree
goto :do_branch

:do_worktree
if "!DRY_RUN!"=="1" goto :dry_worktree
echo Removing worktree !ACT_PATH! - !ACT_REASON!...
if "!FORCE!"=="1" if "!ACT_LOCKED!"=="1" (
    git worktree unlock -- "!ACT_PATH!"
    if errorlevel 1 (
        echo error: git worktree unlock failed for !ACT_PATH! 1>&2
        set "FAILED=1"
        exit /b 0
    )
)
if "!FORCE!"=="1" (
    git worktree remove --force -- "!ACT_PATH!"
) else (
    git worktree remove -- "!ACT_PATH!"
)
if errorlevel 1 (
    echo error: git worktree remove failed for !ACT_PATH! 1>&2
    set "FAILED=1"
    exit /b 0
)
set /a REMOVED_WORKTREES+=1
if not defined ACT_BRANCH exit /b 0
goto :do_branch

:dry_worktree
echo dry-run: remove worktree !ACT_PATH! - !ACT_REASON!
set /a REMOVED_WORKTREES+=1
if not defined ACT_BRANCH exit /b 0
goto :do_branch

:do_branch
if not defined ACT_BRANCH exit /b 0
if "!DRY_RUN!"=="1" goto :dry_branch
echo Deleting branch !ACT_BRANCH! - !ACT_REASON!...
if "!ACT_MERGED!"=="1" (
    git branch -d -- "!ACT_BRANCH!" >nul 2>&1
    if errorlevel 1 git branch -D -- "!ACT_BRANCH!" >nul 2>&1
) else (
    git branch -D -- "!ACT_BRANCH!" >nul 2>&1
)
if errorlevel 1 (
    echo error: git branch delete failed for !ACT_BRANCH! 1>&2
    set "FAILED=1"
    exit /b 0
)
set /a REMOVED_BRANCHES+=1
exit /b 0

:dry_branch
echo dry-run: delete branch !ACT_BRANCH! - !ACT_REASON!
set /a REMOVED_BRANCHES+=1
exit /b 0

:clean_dirs
if "!DRY_RUN!"=="1" exit /b 0
if not exist "!WORKTREES_PARENT!" exit /b 0
for /f "delims=" %%D in ('dir /s /b /ad "!WORKTREES_PARENT!" 2^>nul ^| sort /r') do rmdir "%%D" 2>nul
rmdir "!WORKTREES_PARENT!" 2>nul
exit /b 0

:summary
echo.
if "!REMOVED_WORKTREES!"=="0" if "!REMOVED_BRANCHES!"=="0" (
    echo Nothing to remove.
    goto :summary_skip
)
call :phrase !REMOVED_WORKTREES! worktree worktrees
set "WORKTREE_PHRASE=!PHRASE!"
call :phrase !REMOVED_BRANCHES! branch branches
set "BRANCH_PHRASE=!PHRASE!"
if "!DRY_RUN!"=="1" (
    echo Would remove !WORKTREE_PHRASE! and !BRANCH_PHRASE!.
) else (
    echo Removed !WORKTREE_PHRASE! and !BRANCH_PHRASE!.
)
:summary_skip
if not "!SKIPPED!"=="0" (
    call :phrase !SKIPPED! item items
    echo Skipped !PHRASE!.
)
echo Remote branches were left in place.
exit /b 0

:phrase
if "%~1"=="1" (
    set "PHRASE=1 %~2"
) else (
    set "PHRASE=%~1 %~3"
)
exit /b 0

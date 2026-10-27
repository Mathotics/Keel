# Create a git worktree for a new branch, onboard it, and optionally run an agent.
# Usage:
#   .\scripts\deploy-worktree.ps1 <branch>
#       [--skip-main-check] [--stash-switch]
#       [--agent-command <cmd>] [--commit-when-done <msg>] [--push-when-done]
$ErrorActionPreference = "Stop"

function Write-Usage {
    Write-Host @"
Usage: .\scripts\deploy-worktree.ps1 <branch> [options]

Required:
  <branch>                  Name of the new branch / worktree directory

Options:
  --skip-main-check         Skip verifying the main checkout is on the default branch
  --stash-switch            If not on the default branch: stash, checkout default, then restore after
  --agent-command <cmd>     After onboard, activate .venv and run: agent <cmd>
  --commit-when-done <msg>  In the worktree: git add --all && git commit -m <msg>
  --push-when-done          In the worktree: git push -u origin HEAD
  -h, --help                Show this help
"@
}

function Exit-Error([string]$Message) {
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

function Fail([string]$Message) {
    # Thrown inside try so finally can restore stash/branch before exit.
    throw "error: $Message"
}

$BranchName = $null
$SkipMainCheck = $false
$StashSwitch = $false
$AgentCommand = $null
$CommitWhenDone = $null
$PushWhenDone = $false

$argv = [System.Collections.Generic.List[string]]::new()
foreach ($a in $args) { [void]$argv.Add([string]$a) }

$i = 0
while ($i -lt $argv.Count) {
    $arg = $argv[$i]
    switch -Wildcard ($arg) {
        { $_ -in @("-h", "--help") } {
            Write-Usage
            exit 0
        }
        "--skip-main-check" {
            $SkipMainCheck = $true
            $i++
        }
        "--stash-switch" {
            $StashSwitch = $true
            $i++
        }
        "--push-when-done" {
            $PushWhenDone = $true
            $i++
        }
        "--agent-command" {
            if ($i + 1 -ge $argv.Count) { Exit-Error "--agent-command requires a value" }
            $AgentCommand = $argv[$i + 1]
            $i += 2
        }
        "--commit-when-done" {
            if ($i + 1 -ge $argv.Count) { Exit-Error "--commit-when-done requires a value" }
            $CommitWhenDone = $argv[$i + 1]
            $i += 2
        }
        "--*" {
            Exit-Error "unknown option: $arg"
        }
        default {
            if ($null -ne $BranchName) { Exit-Error "unexpected argument: $arg" }
            $BranchName = $arg
            $i++
        }
    }
}

if ([string]::IsNullOrWhiteSpace($BranchName)) {
    Write-Usage
    Exit-Error "branch name is required"
}
if ($SkipMainCheck -and $StashSwitch) {
    Exit-Error "--skip-main-check and --stash-switch cannot be used together"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Exit-Error "git is required"
}

$ScriptRoot = $PSScriptRoot
$OriginalLocation = (Get-Location).Path
Set-Location (Split-Path -Parent $ScriptRoot)

git rev-parse --git-dir 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Exit-Error "deploy-worktree must run inside the Keel git repository"
}

$GitCommon = (git rev-parse --git-common-dir).Trim()
if (-not [System.IO.Path]::IsPathRooted($GitCommon)) {
    $GitCommon = (Resolve-Path -LiteralPath $GitCommon).Path
}
$MainRepo = (Resolve-Path -LiteralPath (Join-Path $GitCommon "..")).Path
$TopLevel = (Resolve-Path -LiteralPath (git rev-parse --show-toplevel).Trim()).Path
if ($TopLevel -ne $MainRepo) {
    Exit-Error "run this script from the main repository checkout ($MainRepo), not a linked worktree"
}
Set-Location $MainRepo

$DefaultBranch = "main"
$OriginHead = git symbolic-ref refs/remotes/origin/HEAD 2>$null
if ($LASTEXITCODE -eq 0 -and $OriginHead) {
    $DefaultBranch = ($OriginHead.Trim() -replace '^refs/remotes/origin/', '')
}

$PreviousBranch = $null
$DidStash = $false
$StashMessage = "deploy-worktree:auto-stash"

function Restore-MainCheckout {
    if ($null -eq $PreviousBranch) { return }
    Write-Host "Restoring branch '$PreviousBranch'..."
    git checkout $PreviousBranch
    if ($LASTEXITCODE -ne 0) {
        Write-Host "warning: failed to checkout previous branch '$PreviousBranch'" -ForegroundColor Yellow
        return
    }
    if ($DidStash) {
        Write-Host "Restoring stashed changes..."
        git stash pop
        if ($LASTEXITCODE -ne 0) {
            Write-Host "warning: git stash pop failed; stash may still be on the stack" -ForegroundColor Yellow
        }
    }
}

$WorktreePath = $null
try {
    # Step 0 / 0a / 0b
    if (-not $SkipMainCheck) {
        $CurrentBranch = (git branch --show-current).Trim()
        if ([string]::IsNullOrWhiteSpace($CurrentBranch)) {
            Fail "detached HEAD; check out '$DefaultBranch' (or pass --skip-main-check / --stash-switch)"
        }
        if ($CurrentBranch -ne $DefaultBranch) {
            if (-not $StashSwitch) {
                Fail "main checkout is on '$CurrentBranch', expected '$DefaultBranch' (use --stash-switch or --skip-main-check)"
            }
            Write-Host "Not on '$DefaultBranch' (on '$CurrentBranch'); stashing and switching..."
            $PreviousBranch = $CurrentBranch
            $stashOut = git stash push -u -m $StashMessage 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) { Fail "git stash failed: $stashOut" }
            if ($stashOut -notmatch "No local changes to save") {
                $DidStash = $true
            }
            git checkout $DefaultBranch
            if ($LASTEXITCODE -ne 0) { Fail "git checkout $DefaultBranch failed" }
        }
    }

    # Step 1: update default branch from remote
    Write-Host "Fetching and updating '$DefaultBranch'..."
    git fetch origin
    if ($LASTEXITCODE -ne 0) { Fail "git fetch failed" }
    git pull --ff-only origin $DefaultBranch
    if ($LASTEXITCODE -ne 0) { Fail "git pull --ff-only origin $DefaultBranch failed" }

    # Step 2: create worktree + branch
    $WorktreesParent = $MainRepo + ".worktrees"
    $WorktreePath = Join-Path $WorktreesParent $BranchName
    if (Test-Path -LiteralPath $WorktreePath) {
        Fail "worktree path already exists: $WorktreePath"
    }
    New-Item -ItemType Directory -Force -Path $WorktreesParent | Out-Null
    Write-Host "Creating worktree at $WorktreePath (branch '$BranchName')..."
    git worktree add $WorktreePath -b $BranchName
    if ($LASTEXITCODE -ne 0) { Fail "git worktree add failed" }

    # Steps 3–7 in the worktree
    Set-Location $WorktreePath

    Write-Host "Running onboard..."
    & "$WorktreePath\scripts\onboard.ps1"
    if ($LASTEXITCODE -ne 0) { Fail "onboard.ps1 failed" }

    if ($null -ne $AgentCommand) {
        Write-Host "Activating virtual environment..."
        $ActivatePs1 = Join-Path $WorktreePath ".venv\Scripts\Activate.ps1"
        if (-not (Test-Path -LiteralPath $ActivatePs1)) {
            Fail "venv activate script not found at $ActivatePs1"
        }
        . $ActivatePs1
        Write-Host "Running agent: agent $AgentCommand"
        Invoke-Expression "agent $AgentCommand"
        if ($LASTEXITCODE -ne 0) { Fail "agent command failed" }
    }

    if ($null -ne $CommitWhenDone) {
        Write-Host "Committing worktree changes..."
        git add --all
        if ($LASTEXITCODE -ne 0) { Fail "git add failed" }
        git commit -m $CommitWhenDone
        if ($LASTEXITCODE -ne 0) { Fail "git commit failed" }
    }

    if ($PushWhenDone) {
        Write-Host "Pushing worktree branch..."
        git push -u origin HEAD
        if ($LASTEXITCODE -ne 0) { Fail "git push failed" }
    }
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    # Step 8: return to original directory (main repo if we started there)
    Set-Location $MainRepo
    # Step 9: restore previous branch + stash if 0b ran
    Restore-MainCheckout
    Set-Location $OriginalLocation
}

Write-Host ""
Write-Host "Worktree ready: $WorktreePath"
Write-Host "Branch: $BranchName"

# Remove a git worktree and its local branch created by deploy-worktree.
# Usage:
#   .\scripts\delete-worktree.ps1 <branch> [--force]
$ErrorActionPreference = "Stop"

function Write-Usage {
    Write-Host @"
Usage: .\scripts\delete-worktree.ps1 <branch> [options]

Required:
  <branch>                  Name of the branch / worktree directory to remove

Options:
  --force                   Discard uncommitted changes and delete the branch
                            even if it is not fully merged
  -h, --help                Show this help

The worktree path is <repository>.worktrees\<branch>, the same place
deploy-worktree creates it. The local branch is deleted with the worktree.
A remote branch is left in place. Run this script from the main checkout.
"@
}

function Fail([string]$Message) {
    # Thrown inside try so finally can restore the original directory.
    throw "error: $Message"
}

function Test-SafeBranchName([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name)) { return $false }
    if ($Name.StartsWith("-")) { return $false }
    $invalid = @('<', '>', ':', '"', '|', '?', '*')
    foreach ($char in $invalid) {
        if ($Name.Contains($char)) { return $false }
    }
    $slash = @([char]'/', [char]'\')
    if ($slash -contains $Name[0]) { return $false }
    if ($Name.EndsWith("/") -or $Name.EndsWith("\")) { return $false }
    if ($Name.Contains("//") -or $Name.Contains("\\") -or $Name.Contains("/\") -or $Name.Contains("\/")) {
        return $false
    }
    $segments = $Name.Split($slash)
    foreach ($segment in $segments) {
        if ($segment -eq "." -or $segment -eq "..") { return $false }
    }
    return $true
}

function ConvertTo-ComparablePath([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Test-SamePath([string]$Left, [string]$Right) {
    $a = ConvertTo-ComparablePath $Left
    $b = ConvertTo-ComparablePath $Right
    return [string]::Equals($a, $b, [System.StringComparison]::OrdinalIgnoreCase)
}

function Test-IsInside([string]$Parent, [string]$Child) {
    $parentFull = ConvertTo-ComparablePath $Parent
    $childFull = ConvertTo-ComparablePath $Child
    $prefix = $parentFull + [System.IO.Path]::DirectorySeparatorChar
    return $childFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-WorktreeRecords {
    $records = New-Object System.Collections.Generic.List[object]
    $current = $null
    foreach ($line in @(git worktree list --porcelain)) {
        if ([string]::IsNullOrEmpty($line)) { continue }
        if ($line.StartsWith("worktree ")) {
            if ($null -ne $current) { $records.Add($current) }
            $current = [pscustomobject]@{
                Path     = $line.Substring(9)
                Branch   = ""
                Detached = $false
            }
        }
        elseif ($null -ne $current -and $line.StartsWith("branch ")) {
            $current.Branch = $line.Substring(7)
        }
        elseif ($null -ne $current -and $line -eq "detached") {
            $current.Detached = $true
        }
    }
    if ($null -ne $current) { $records.Add($current) }
    return $records
}

function Test-LocalBranch([string]$Name) {
    git show-ref --verify --quiet -- ("refs/heads/" + $Name) 2>$null
    return $LASTEXITCODE -eq 0
}

function Test-BranchMerged([string]$Name) {
    # Same rule as git branch -d: merged into HEAD, or into its upstream.
    git merge-base --is-ancestor -- $Name HEAD
    if ($LASTEXITCODE -eq 0) { return $true }
    if ($LASTEXITCODE -ne 1) { Fail "git merge-base failed" }
    $upstream = git rev-parse --abbrev-ref -- ($Name + '@{upstream}') 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }
    $upstream = "$upstream".Trim()
    if ([string]::IsNullOrWhiteSpace($upstream)) { return $false }
    git merge-base --is-ancestor -- $Name $upstream
    if ($LASTEXITCODE -eq 0) { return $true }
    if ($LASTEXITCODE -ne 1) { Fail "git merge-base failed" }
    return $false
}

function Remove-EmptyWorktreesParent([string]$Parent) {
    if (-not (Test-Path -LiteralPath $Parent)) { return }
    $items = @(Get-ChildItem -Force -LiteralPath $Parent -ErrorAction SilentlyContinue)
    if ($items.Count -eq 0) {
        Remove-Item -LiteralPath $Parent -Force -ErrorAction SilentlyContinue
    }
}

$BranchName = $null
$Force = $false

foreach ($arg in $args) {
    switch -Wildcard ($arg) {
        { $_ -in @("-h", "--help") } {
            Write-Usage
            exit 0
        }
        "--force" {
            $Force = $true
        }
        "--*" {
            Write-Host "error: unknown option: $arg" -ForegroundColor Red
            exit 1
        }
        default {
            if ($null -ne $BranchName) {
                Write-Host "error: unexpected argument: $arg" -ForegroundColor Red
                exit 1
            }
            $BranchName = [string]$arg
        }
    }
}

if ([string]::IsNullOrWhiteSpace($BranchName)) {
    Write-Usage
    Write-Host "error: branch name is required" -ForegroundColor Red
    exit 1
}
if (-not (Test-SafeBranchName $BranchName)) {
    Write-Host "error: invalid branch name: $BranchName" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "error: git is required" -ForegroundColor Red
    exit 1
}

$GitBranch = $BranchName -replace '\\', '/'
$BranchRef = "refs/heads/" + $GitBranch
$OriginalLocation = (Get-Location).Path

try {
    Set-Location (Split-Path -Parent $PSScriptRoot)

    git rev-parse --git-dir 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail "delete-worktree must run inside the Keel git repository"
    }

    $GitCommon = (git rev-parse --git-common-dir).Trim()
    if (-not [System.IO.Path]::IsPathRooted($GitCommon)) {
        $GitCommon = (Resolve-Path -LiteralPath $GitCommon).Path
    }
    $MainRepo = (Resolve-Path -LiteralPath (Join-Path $GitCommon "..")).Path
    $TopLevel = (Resolve-Path -LiteralPath (git rev-parse --show-toplevel).Trim()).Path
    if ($TopLevel -ne $MainRepo) {
        Fail "run this script from the main repository checkout ($MainRepo), not a linked worktree"
    }
    Set-Location $MainRepo

    $DefaultBranch = "main"
    $OriginHead = git symbolic-ref refs/remotes/origin/HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $OriginHead) {
        $DefaultBranch = ($OriginHead.Trim() -replace '^refs/remotes/origin/', '')
    }
    if ($GitBranch -eq $DefaultBranch) {
        Fail "refusing to delete the default branch '$DefaultBranch'"
    }

    $CurrentBranch = "$(git branch --show-current)".Trim()
    if ($CurrentBranch -eq $GitBranch) {
        Fail "branch '$GitBranch' is checked out in the main repository"
    }

    $WorktreesParent = $MainRepo + ".worktrees"
    $Relative = $GitBranch -replace '/', [System.IO.Path]::DirectorySeparatorChar
    $WorktreePath = Join-Path $WorktreesParent $Relative
    if (-not (Test-IsInside $WorktreesParent $WorktreePath)) {
        Fail "refusing to touch a path outside $WorktreesParent"
    }

    $records = Get-WorktreeRecords
    if ($LASTEXITCODE -ne 0) { Fail "git worktree list failed" }

    $Match = $null
    $CheckoutPath = $null
    foreach ($record in $records) {
        if (Test-SamePath $record.Path $WorktreePath) { $Match = $record }
        if ($record.Branch -eq $BranchRef) { $CheckoutPath = $record.Path }
    }

    $BranchExists = Test-LocalBranch $GitBranch
    $RemovedWorktree = $false

    if ($null -ne $Match) {
        if ($Match.Detached -or [string]::IsNullOrWhiteSpace($Match.Branch)) {
            Fail "worktree at $WorktreePath is detached; expected branch '$GitBranch'"
        }
        if ($Match.Branch -ne $BranchRef) {
            $other = $Match.Branch -replace '^refs/heads/', ''
            Fail "worktree at $WorktreePath is on '$other', not '$GitBranch'"
        }
        $dirty = @(git -C $WorktreePath status --porcelain)
        if ($LASTEXITCODE -ne 0) { Fail "git status failed in $WorktreePath" }
        $dirty = @($dirty | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        if (-not $Force -and $dirty.Count -gt 0) {
            Fail "worktree has uncommitted changes; re-run with --force to discard them"
        }
        if ($BranchExists -and -not $Force -and -not (Test-BranchMerged $GitBranch)) {
            Fail "branch '$GitBranch' is not fully merged; re-run with --force to delete it"
        }
        Write-Host "Removing worktree at $WorktreePath..."
        if ($Force) {
            git worktree remove --force -- $WorktreePath
        }
        else {
            git worktree remove -- $WorktreePath
        }
        if ($LASTEXITCODE -ne 0) { Fail "git worktree remove failed" }
        $RemovedWorktree = $true
    }
    else {
        if (Test-Path -LiteralPath $WorktreePath) {
            Fail "path exists but is not a registered git worktree: $WorktreePath"
        }
        if ($null -ne $CheckoutPath) {
            Fail "branch '$GitBranch' is checked out at $CheckoutPath, not at $WorktreePath"
        }
        if (-not $BranchExists) {
            Fail "no worktree or local branch named '$GitBranch'"
        }
        if (-not $Force -and -not (Test-BranchMerged $GitBranch)) {
            Fail "branch '$GitBranch' is not fully merged; re-run with --force to delete it"
        }
        Write-Host "Worktree path already absent: $WorktreePath"
    }

    if ($BranchExists) {
        Write-Host "Deleting local branch '$GitBranch'..."
        if ($Force) {
            git branch -D -- $GitBranch
        }
        else {
            git branch -d -- $GitBranch
        }
        if ($LASTEXITCODE -ne 0) { Fail "git branch delete failed" }
    }

    Remove-EmptyWorktreesParent $WorktreesParent

    Write-Host ""
    if ($RemovedWorktree) {
        Write-Host "Worktree removed: $WorktreePath"
    }
    if ($BranchExists) {
        Write-Host "Branch deleted: $GitBranch"
    }
    Write-Host "Remote branches were left in place."
}
catch {
    $msg = $_.Exception.Message
    if ($msg -notlike "error:*") { $msg = "error: $msg" }
    Write-Host $msg -ForegroundColor Red
    exit 1
}
finally {
    Set-Location $OriginalLocation
}

# Remove merged and stale git worktrees and their local branches.
# Usage:
#   .\scripts\prune-worktrees.ps1 [--dry-run] [--stale] [--force]
$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

function Write-Usage {
    Write-Host @"
Usage: .\scripts\prune-worktrees.ps1 [options]

With no options, remove every managed worktree whose branch is merged
into the default branch, and every local branch that is merged into the
default branch and is not checked out. A managed worktree lives under
<repository>.worktrees, the directory deploy-worktree creates.

A branch counts as merged when its tip is contained in the local default
branch, or in origin/<default> when that remote-tracking ref exists.
Squash merges are not detected. Remote branches are left in place.

The default branch and the main checkout are never removed. A worktree
this command was started from is left in place. Run it from any checkout.

Options:
  --stale                   Also select worktrees and branches whose tip
                            commit is at least --stale-days old
  --stale-days <days>       Age threshold for --stale (default: 90).
                            Passing this turns --stale on
  --skip-merged             Do not remove items only because they are merged
  --worktrees-only          Do not delete local branches that have no
                            managed worktree
  --force                   Discard uncommitted changes, unlock a locked
                            worktree, and delete an unmerged branch selected
                            by --stale
  -n, --dry-run             Print what would be removed and change nothing
  -v, --verbose             Explain why each worktree and branch was kept
  -h, --help                Show this help
"@
}

function Fail([string]$Message) {
    throw "error: $Message"
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

function Format-Count([int]$Count, [string]$Singular, [string]$Plural) {
    if ($Count -eq 1) { return "1 $Singular" }
    return "$Count $Plural"
}

function Get-WorktreeRecords {
    $records = New-Object System.Collections.Generic.List[object]
    $current = $null
    $lines = @(git worktree list --porcelain)
    if ($LASTEXITCODE -ne 0) { Fail "git worktree list failed" }
    foreach ($line in $lines) {
        if ([string]::IsNullOrEmpty($line)) { continue }
        if ($line.StartsWith("worktree ")) {
            if ($null -ne $current) { $records.Add($current) }
            $current = [pscustomobject]@{
                Path     = $line.Substring(9)
                Branch   = ""
                Head     = ""
                Detached = $false
                Locked   = $false
            }
        }
        elseif ($null -ne $current -and $line.StartsWith("HEAD ")) {
            $current.Head = $line.Substring(5).Trim()
        }
        elseif ($null -ne $current -and $line.StartsWith("branch ")) {
            $current.Branch = $line.Substring(7).Trim()
        }
        elseif ($null -ne $current -and $line -eq "detached") {
            $current.Detached = $true
        }
        elseif ($null -ne $current -and $line.StartsWith("locked")) {
            $current.Locked = $true
        }
    }
    if ($null -ne $current) { $records.Add($current) }
    return $records
}

function Get-ShortBranch([string]$Ref) {
    if ([string]::IsNullOrWhiteSpace($Ref)) { return "" }
    if ($Ref.StartsWith("refs/heads/")) { return $Ref.Substring(11) }
    return $Ref
}

function Test-ContainedInDefault([string]$Rev) {
    git merge-base --is-ancestor -- $Rev $DefaultBranch 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return $true }
    if ($LASTEXITCODE -ne 1) { return $false }
    if ([string]::IsNullOrWhiteSpace($script:OriginDefault)) { return $false }
    git merge-base --is-ancestor -- $Rev $script:OriginDefault 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Get-TipEpoch([string]$Rev) {
    $raw = git log -1 --format=%ct $Rev 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $text = "$raw".Trim()
    if ($text -notmatch '^\d+$') { return $null }
    return [int64]$text
}

function Get-AgeDays([int64]$Epoch) {
    $age = [int64](($script:NowEpoch - $Epoch) / 86400)
    if ($age -lt 0) { return 0 }
    return [int]$age
}

function Test-WorktreeDirty([string]$Path) {
    $dirty = @(git -C $Path status --porcelain 2>$null)
    if ($LASTEXITCODE -ne 0) { Fail "git status failed in $Path" }
    $dirty = @($dirty | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    return $dirty.Count -gt 0
}

function Remove-EmptyWorktreeDirs([string]$Parent) {
    if (-not (Test-Path -LiteralPath $Parent)) { return }
    $dirs = @(Get-ChildItem -Directory -Recurse -Force -LiteralPath $Parent -ErrorAction SilentlyContinue)
    $dirs = @($dirs | Sort-Object { $_.FullName.Length } -Descending)
    foreach ($dir in $dirs) {
        $items = @(Get-ChildItem -Force -LiteralPath $dir.FullName -ErrorAction SilentlyContinue)
        if ($items.Count -eq 0) {
            Remove-Item -LiteralPath $dir.FullName -Force -ErrorAction SilentlyContinue
        }
    }
    $left = @(Get-ChildItem -Force -LiteralPath $Parent -ErrorAction SilentlyContinue)
    if ($left.Count -eq 0) {
        Remove-Item -LiteralPath $Parent -Force -ErrorAction SilentlyContinue
    }
}

$DryRun = $false
$Verbose = $false
$Force = $false
$IncludeStale = $false
$SkipMerged = $false
$WorktreesOnly = $false
$StaleDays = 90
$SawStaleDays = $false

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
        { $_ -in @("-n", "--dry-run") } {
            $DryRun = $true
            $i++
            break
        }
        { $_ -in @("-v", "--verbose") } {
            $Verbose = $true
            $i++
            break
        }
        "--force" {
            $Force = $true
            $i++
            break
        }
        "--stale" {
            $IncludeStale = $true
            $i++
            break
        }
        "--skip-merged" {
            $SkipMerged = $true
            $i++
            break
        }
        "--worktrees-only" {
            $WorktreesOnly = $true
            $i++
            break
        }
        "--stale-days" {
            if ($i + 1 -ge $argv.Count) {
                Write-Host "error: --stale-days requires a value" -ForegroundColor Red
                exit 1
            }
            $rawDays = $argv[$i + 1]
            if ($rawDays -notmatch '^\d+$' -or [int]$rawDays -lt 1) {
                Write-Host "error: --stale-days must be a positive integer" -ForegroundColor Red
                exit 1
            }
            $StaleDays = [int]$rawDays
            $SawStaleDays = $true
            $IncludeStale = $true
            $i += 2
            break
        }
        "--*" {
            Write-Host "error: unknown option: $arg" -ForegroundColor Red
            exit 1
        }
        default {
            Write-Host "error: unexpected argument: $arg" -ForegroundColor Red
            exit 1
        }
    }
}

if ($SkipMerged -and -not $IncludeStale) {
    Write-Host "error: --skip-merged removes nothing unless --stale is set" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "error: git is required" -ForegroundColor Red
    exit 1
}

$OriginalLocation = (Get-Location).Path
$StartTop = $null
$StartCommon = $null
Push-Location $OriginalLocation
try {
    $rawTop = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $rawTop) {
        $StartTop = (Resolve-Path -LiteralPath ($rawTop | Select-Object -First 1).ToString().Trim()).Path
        $rawCommon = git rev-parse --git-common-dir 2>$null
        if ($LASTEXITCODE -eq 0 -and $rawCommon) {
            $commonText = ($rawCommon | Select-Object -First 1).ToString().Trim()
            if (-not [System.IO.Path]::IsPathRooted($commonText)) {
                $commonText = Join-Path $StartTop $commonText
            }
            $StartCommon = (Resolve-Path -LiteralPath $commonText).Path
        }
    }
}
finally {
    Pop-Location
}

$RemovedWorktrees = 0
$RemovedBranches = 0
$Skipped = 0
$Failed = $false
$DefaultBranch = "main"
$OriginDefault = ""
$NowEpoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

try {
    Set-Location (Split-Path -Parent $PSScriptRoot)

    git rev-parse --git-dir 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail "prune-worktrees must run inside a git repository"
    }

    $GitCommon = (git rev-parse --git-common-dir).Trim()
    if (-not [System.IO.Path]::IsPathRooted($GitCommon)) {
        $GitCommon = (Resolve-Path -LiteralPath $GitCommon).Path
    }
    else {
        $GitCommon = (Resolve-Path -LiteralPath $GitCommon).Path
    }
    $MainRepo = (Resolve-Path -LiteralPath (Join-Path $GitCommon "..")).Path
    if ($null -ne $StartCommon -and -not (Test-SamePath $StartCommon $GitCommon)) {
        $StartTop = $null
    }
    Set-Location $MainRepo

    $OriginHead = git symbolic-ref refs/remotes/origin/HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $OriginHead) {
        $DefaultBranch = (($OriginHead | Select-Object -First 1).ToString().Trim() -replace '^refs/remotes/origin/', '')
    }
    git show-ref --verify --quiet -- "refs/heads/$DefaultBranch"
    if ($LASTEXITCODE -ne 0) {
        Fail "default branch '$DefaultBranch' does not exist locally"
    }
    git show-ref --verify --quiet -- "refs/remotes/origin/$DefaultBranch"
    if ($LASTEXITCODE -eq 0) {
        $OriginDefault = "origin/$DefaultBranch"
    }

    $WorktreesParent = $MainRepo + ".worktrees"
    $records = @(Get-WorktreeRecords)
    if ($LASTEXITCODE -ne 0) { Fail "git worktree list failed" }

    $CheckedOut = New-Object 'System.Collections.Generic.HashSet[string]'
    $Claimed = New-Object 'System.Collections.Generic.HashSet[string]'
    $Actions = New-Object System.Collections.Generic.List[object]

    foreach ($record in $records) {
        $short = Get-ShortBranch $record.Branch
        if (-not [string]::IsNullOrWhiteSpace($short)) {
            [void]$CheckedOut.Add($short)
        }
    }

    foreach ($record in $records) {
        $short = Get-ShortBranch $record.Branch
        $managed = Test-IsInside $WorktreesParent $record.Path
        $startedHere = $null -ne $StartTop -and (Test-SamePath $record.Path $StartTop)
        if (Test-SamePath $record.Path $MainRepo) {
            if ($Verbose) { Write-Host "keep worktree $($record.Path): main checkout" }
            continue
        }
        if (-not $managed) {
            if ($Verbose) { Write-Host "keep worktree $($record.Path): outside $WorktreesParent" }
            continue
        }
        if ($startedHere) {
            if ($Verbose) { Write-Host "keep worktree $($record.Path): this command was started here" }
            continue
        }

        $rev = $short
        if ([string]::IsNullOrWhiteSpace($rev)) { $rev = $record.Head }
        if ([string]::IsNullOrWhiteSpace($rev)) {
            if ($Verbose) { Write-Host "keep worktree $($record.Path): no branch or commit" }
            continue
        }
        if ($short -eq $DefaultBranch) {
            if ($Verbose) { Write-Host "keep worktree $($record.Path): default branch" }
            continue
        }

        $merged = Test-ContainedInDefault $rev
        $epoch = Get-TipEpoch $rev
        $ageDays = $null
        $isStale = $false
        if ($null -ne $epoch) {
            $ageDays = Get-AgeDays $epoch
            $isStale = $ageDays -ge $StaleDays
        }
        $reason = $null
        if (-not $SkipMerged -and $merged) {
            $reason = "merged into $DefaultBranch"
        }
        elseif ($IncludeStale -and $isStale) {
            $reason = "stale, $ageDays days"
        }
        if ($null -eq $reason) {
            if ($Verbose) {
                $ageText = "unknown age"
                if ($null -ne $ageDays) { $ageText = "last commit $ageDays days ago" }
                $mergedText = "not merged"
                if ($merged) { $mergedText = "merged into $DefaultBranch" }
                Write-Host "keep worktree $($record.Path) branch ${short}: $mergedText, $ageText"
            }
            continue
        }

        $dirty = Test-WorktreeDirty $record.Path
        $blockers = New-Object System.Collections.Generic.List[string]
        if ($dirty) { $blockers.Add("uncommitted changes") }
        if ($record.Locked) { $blockers.Add("locked") }
        if (-not $merged) { $blockers.Add("not merged into $DefaultBranch") }
        if ($blockers.Count -gt 0 -and -not $Force) {
            $label = $short
            if ([string]::IsNullOrWhiteSpace($label)) { $label = "detached" }
            Write-Host "skip: worktree $($record.Path) branch ${label}: $($blockers -join ', '); re-run with --force"
            $Skipped++
            continue
        }

        if (-not [string]::IsNullOrWhiteSpace($short)) {
            [void]$Claimed.Add($short)
        }
        $Actions.Add([pscustomobject]@{
            Kind    = "worktree"
            Path    = $record.Path
            Branch  = $short
            Reason  = $reason
            Merged  = [bool]$merged
            Locked  = [bool]$record.Locked
        })
    }

    if (-not $WorktreesOnly) {
        $branchNames = @(git for-each-ref --format="%(refname:short)" refs/heads)
        if ($LASTEXITCODE -ne 0) { Fail "git for-each-ref failed" }
        foreach ($nameRaw in $branchNames) {
            $name = "$nameRaw".Trim()
            if ([string]::IsNullOrWhiteSpace($name)) { continue }
            if ($Claimed.Contains($name)) { continue }
            if ($name -eq $DefaultBranch) {
                if ($Verbose) { Write-Host "keep branch ${name}: default branch" }
                continue
            }
            if ($CheckedOut.Contains($name)) {
                if ($Verbose) { Write-Host "keep branch ${name}: checked out" }
                continue
            }
            $merged = Test-ContainedInDefault $name
            $epoch = Get-TipEpoch $name
            $ageDays = $null
            $isStale = $false
            if ($null -ne $epoch) {
                $ageDays = Get-AgeDays $epoch
                $isStale = $ageDays -ge $StaleDays
            }
            $reason = $null
            if (-not $SkipMerged -and $merged) {
                $reason = "merged into $DefaultBranch"
            }
            elseif ($IncludeStale -and $isStale) {
                $reason = "stale, $ageDays days"
            }
            if ($null -eq $reason) {
                if ($Verbose) {
                    $ageText = "unknown age"
                    if ($null -ne $ageDays) { $ageText = "last commit $ageDays days ago" }
                    $mergedText = "not merged"
                    if ($merged) { $mergedText = "merged into $DefaultBranch" }
                    Write-Host "keep branch ${name}: $mergedText, $ageText"
                }
                continue
            }
            if (-not $merged -and -not $Force) {
                Write-Host "skip: branch ${name}: not merged into $DefaultBranch; re-run with --force"
                $Skipped++
                continue
            }
            $Actions.Add([pscustomobject]@{
                Kind    = "branch"
                Path    = ""
                Branch  = $name
                Reason  = $reason
                Merged  = [bool]$merged
                Locked  = $false
            })
        }
    }

    foreach ($action in $Actions) {
        if ($action.Kind -eq "worktree") {
            if ($DryRun) {
                Write-Host "dry-run: remove worktree $($action.Path) - $($action.Reason)"
            }
            else {
                Write-Host "Removing worktree $($action.Path) - $($action.Reason)..."
                if ($Force -and $action.Locked) {
                    git worktree unlock -- $action.Path
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "error: git worktree unlock failed for $($action.Path)" -ForegroundColor Red
                        $Failed = $true
                        continue
                    }
                }
                if ($Force) {
                    git worktree remove --force -- $action.Path
                }
                else {
                    git worktree remove -- $action.Path
                }
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "error: git worktree remove failed for $($action.Path)" -ForegroundColor Red
                    $Failed = $true
                    continue
                }
            }
            $RemovedWorktrees++
            if ([string]::IsNullOrWhiteSpace($action.Branch)) { continue }
        }

        $branchName = $action.Branch
        if ($DryRun) {
            Write-Host "dry-run: delete branch $branchName - $($action.Reason)"
            $RemovedBranches++
            continue
        }
        Write-Host "Deleting branch $branchName - $($action.Reason)..."
        if ($action.Merged) {
            git branch -d -- $branchName
            if ($LASTEXITCODE -ne 0) {
                git branch -D -- $branchName
            }
        }
        else {
            git branch -D -- $branchName
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "error: git branch delete failed for $branchName" -ForegroundColor Red
            $Failed = $true
            continue
        }
        $RemovedBranches++
    }

    if (-not $DryRun) {
        Remove-EmptyWorktreeDirs $WorktreesParent
    }

    Write-Host ""
    $worktreePhrase = Format-Count $RemovedWorktrees "worktree" "worktrees"
    $branchPhrase = Format-Count $RemovedBranches "branch" "branches"
    if ($RemovedWorktrees -eq 0 -and $RemovedBranches -eq 0) {
        Write-Host "Nothing to remove."
    }
    elseif ($DryRun) {
        Write-Host "Would remove $worktreePhrase and $branchPhrase."
    }
    else {
        Write-Host "Removed $worktreePhrase and $branchPhrase."
    }
    if ($Skipped -gt 0) {
        $skipPhrase = Format-Count $Skipped "item" "items"
        Write-Host "Skipped $skipPhrase."
    }
    if ($SawStaleDays -and $Verbose) {
        Write-Host "Stale threshold: $StaleDays days."
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

if ($Failed) { exit 1 }
exit 0

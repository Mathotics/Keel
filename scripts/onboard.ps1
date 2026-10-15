# Onboard a local Keel development environment (venv + dependencies).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Configuring local git aliases..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "error: git is required" -ForegroundColor Red
    exit 1
}
git rev-parse --git-dir 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "error: onboard must run inside the Keel git repository" -ForegroundColor Red
    exit 1
}
$GitAliases = [ordered]@{
    graph             = "log --oneline --decorate --graph"
    unstage           = "reset HEAD --"
    last              = "log -1 HEAD"
    compare           = "diff --no-index --color-words"
    "unique-commits"  = "log main.. --format='%C(green)%as %C(yellow)%h %C(cyan)%an %C(white)%s'"
    "missing-commits" = "log ..main --format='%C(green)%as %C(yellow)%h %C(cyan)%an %C(white)%s'"
    conflicts         = "diff --name-only --diff-filter=U"
    oops              = "reset --soft HEAD~1"
    purge             = "clean -fdx -e .venv/ -e venv/ -e user/"
}
foreach ($name in $GitAliases.Keys) {
    git config --local "alias.$name" $GitAliases[$name]
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$MinPy = "3.12"

function Test-Python312 {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Exe,
        [string[]]$ExtraArgs = @()
    )
    & $Exe @ExtraArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$PyExe = $null
$PyExtra = @()

if ($env:PYTHON) {
    if (-not (Test-Python312 -Exe $env:PYTHON)) {
        Write-Host "error: PYTHON=$($env:PYTHON) is not Python $MinPy or newer" -ForegroundColor Red
        exit 1
    }
    $PyExe = $env:PYTHON
} else {
    $found = $false
    foreach ($candidate in @("python3.12", "python3", "python")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $cmd -and (Test-Python312 -Exe $cmd.Source)) {
            $PyExe = $cmd.Source
            $found = $true
            break
        }
    }
    if (-not $found) {
        $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($null -ne $pyLauncher -and (Test-Python312 -Exe $pyLauncher.Source -ExtraArgs @("-3.12"))) {
            $PyExe = $pyLauncher.Source
            $PyExtra = @("-3.12")
            $found = $true
        }
    }
    if (-not $found) {
        Write-Host "error: Python $MinPy or newer is required (set PYTHON to a suitable interpreter)" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Using Python: $PyExe $($PyExtra -join ' ')".Trim()
& $PyExe @PyExtra -m venv .venv

$VenvPy = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $VenvPy = (Resolve-Path ".venv\Scripts\python.exe").Path
} elseif (Test-Path ".venv/bin/python") {
    $VenvPy = (Resolve-Path ".venv/bin/python").Path
} else {
    Write-Host "error: virtual environment Python was not created" -ForegroundColor Red
    exit 1
}

Write-Host "Upgrading pip..."
& $VenvPy -m pip install --upgrade pip setuptools wheel

Write-Host "Installing package and development dependencies..."
& $VenvPy -m pip install -e '.[dev]'

$VenvPoe = $null
if (Test-Path ".venv\Scripts\poe.exe") {
    $VenvPoe = (Resolve-Path ".venv\Scripts\poe.exe").Path
} elseif (Test-Path ".venv/bin/poe") {
    $VenvPoe = (Resolve-Path ".venv/bin/poe").Path
} else {
    Write-Host "error: poe was not installed into the virtual environment" -ForegroundColor Red
    exit 1
}

Write-Host "Configuring Poe..."
& $VenvPoe _list_tasks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Configuring pre-commit (git hooks and environments)..."
& $VenvPoe hooks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Checking isort and mypy..."
& $VenvPoe isort-check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPoe mypy
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

Write-Host ""
Write-Host "Onboarding complete."
Write-Host ""
Write-Host "Activate the virtual environment:"
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "  Windows PowerShell:  .\.venv\Scripts\Activate.ps1"
}
if (Test-Path ".venv\Scripts\activate.bat") {
    Write-Host "  Windows cmd:         .venv\Scripts\activate.bat"
}
if (Test-Path ".venv\Scripts\activate") {
    Write-Host "  Git Bash:            source .venv/Scripts/activate"
}
if (Test-Path ".venv/bin/activate") {
    Write-Host "  Unix:                source .venv/bin/activate"
}
Write-Host ""
Write-Host "Then run: poe serve"

# Onboard a local Keel development environment (venv + dependencies).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

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
& $VenvPoe _list
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

Write-Host @"

Onboarding complete.

Activate the virtual environment:
  Windows PowerShell:  .\.venv\Scripts\Activate.ps1
  Windows cmd:         .venv\Scripts\activate.bat
  Unix / Git Bash:     source .venv/bin/activate

Then run: poe serve
"@

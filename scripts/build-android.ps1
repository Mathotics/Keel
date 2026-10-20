# Build a signed Keel Android release APK and copy it to %LOCALAPPDATA%\Keel\keel-shell.apk.
# Signing values are read from %LOCALAPPDATA%\Keel\android-signing.env and are never printed.
param(
    [switch]$NoBump
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Mobile = Join-Path $Root "mobile"
$AppJson = Join-Path $Mobile "app.json"
$SigningEnv = Join-Path $env:LOCALAPPDATA "Keel\android-signing.env"
$DestApk = Join-Path $env:LOCALAPPDATA "Keel\keel-shell.apk"

function Fail([string]$Message) {
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $AppJson)) {
    Fail "mobile/app.json was not found. Run this from the Keel repository."
}
if (-not (Test-Path -LiteralPath $SigningEnv)) {
    Fail "signing file not found at $SigningEnv"
}

Get-Content -LiteralPath $SigningEnv | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim().Trim('"')
    }
}
foreach ($name in @(
        "KEEL_ANDROID_KEYSTORE_PATH",
        "KEEL_ANDROID_KEYSTORE_PASSWORD",
        "KEEL_ANDROID_KEY_ALIAS",
        "KEEL_ANDROID_KEY_PASSWORD"
    )) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if (-not $value) {
        Fail "$name is missing from the signing file"
    }
}
if (-not (Test-Path -LiteralPath $env:KEEL_ANDROID_KEYSTORE_PATH)) {
    Fail "keystore file is missing"
}

if (-not $env:JAVA_HOME) {
    $jdk = "C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot"
    if (-not (Test-Path -LiteralPath $jdk)) {
        Fail "JDK 17 was not found. Set JAVA_HOME."
    }
    $env:JAVA_HOME = $jdk
}
if (-not $env:ANDROID_HOME) {
    $sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    if (-not (Test-Path -LiteralPath $sdk)) {
        Fail "Android SDK was not found. Set ANDROID_HOME."
    }
    $env:ANDROID_HOME = $sdk
}

$appText = [System.IO.File]::ReadAllText($AppJson)
$versionMatch = [regex]::Match($appText, '"versionCode"\s*:\s*(\d+)')
if (-not $versionMatch.Success) {
    Fail "versionCode was not found in mobile/app.json"
}
$versionCode = [int]$versionMatch.Groups[1].Value
if (-not $NoBump) {
    $versionCode += 1
    $appText = [regex]::Replace($appText, '("versionCode"\s*:\s*)\d+', "`${1}$versionCode", 1)
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($AppJson, $appText, $utf8)
}
Write-Host "Android version code: $versionCode"

Push-Location $Mobile
try {
    # A bare `npx expo` with no local install downloads the newest Expo, which is not this app's SDK.
    if (-not (Test-Path -LiteralPath "node_modules\expo\package.json")) {
        Write-Host "Installing mobile dependencies..."
        npm ci
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & node ".\node_modules\expo\bin\cli" prebuild --platform android --clean --no-install
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & .\android\gradlew.bat -p android assembleRelease --no-daemon
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}

$built = Join-Path $Mobile "android\app\build\outputs\apk\release\app-release.apk"
if (-not (Test-Path -LiteralPath $built)) {
    Fail "Gradle did not produce $built"
}
$apksigner = Get-ChildItem -Path (Join-Path $env:ANDROID_HOME "build-tools") -Recurse -Filter apksigner.bat |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if ($null -eq $apksigner) {
    Fail "apksigner was not found under ANDROID_HOME"
}
$cert = & $apksigner.FullName verify --print-certs $built 2>&1 | Out-String
if ($cert -notmatch 'CN=Keel') {
    Fail "APK is not signed with the Keel certificate"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DestApk) | Out-Null
Copy-Item -LiteralPath $built -Destination $DestApk -Force
$item = Get-Item -LiteralPath $DestApk
$link = "file:///" + ($DestApk -replace '\\', '/')

Write-Host ""
Write-Host "Signed with the Keel certificate."
Write-Host "APK:  $($item.FullName)"
Write-Host "Size: $([math]::Round($item.Length / 1MB, 1)) MB"
Write-Host "Link: $link"

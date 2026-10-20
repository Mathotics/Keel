@echo off
REM Build a signed Keel Android release APK. Pass -NoBump to keep the current version code.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-android.ps1" %*
exit /b %ERRORLEVEL%

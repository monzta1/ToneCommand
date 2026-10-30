@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\mk1\Install.ps1"
if errorlevel 1 pause

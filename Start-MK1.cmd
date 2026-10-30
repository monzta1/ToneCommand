@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\mk1\Start.ps1"
if errorlevel 1 pause

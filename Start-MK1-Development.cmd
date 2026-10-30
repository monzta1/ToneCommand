@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\mk1-ai\Development.ps1"
if errorlevel 1 pause

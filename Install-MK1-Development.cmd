@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\mk1-ai\Install.ps1" -Development
if errorlevel 1 pause

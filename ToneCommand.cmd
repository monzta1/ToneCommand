@echo off
setlocal
cd /d "%~dp0"
if /I "%~1"=="install" goto install
if /I "%~1"=="test" goto test
if /I "%~1"=="mk1" goto mk1
if /I "%~1"=="mk2" goto mk2
if not "%~1"=="" goto usage
echo ToneCommand Unofficial - one checkout for Axe-Fx III MK1 and MK2
echo 1. Install dependencies and run offline MK1 checks
echo 2. Start MK1 experimental development
echo 3. Start the full FX3 workspace for MK2
echo 4. Run offline regression checks
echo Q. Quit
choice /c 1234Q /n /m "Choose: "
if errorlevel 5 exit /b 0
if errorlevel 4 goto test
if errorlevel 3 goto mk2
if errorlevel 2 goto mk1
goto install
:install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\mk1-ai\Install.ps1" -Development
exit /b %errorlevel%
:test
if not exist "%~dp0.venv\Scripts\python.exe" goto missing
set TONECOMMAND_SIM=1
"%~dp0.venv\Scripts\python.exe" -m pytest tests/test_device_handle.py tests/test_capability_gates.py tests/test_ui_warning.py tests/test_axefx3_profile.py tests/test_axefx3_navigation.py tests/test_mk1_development.py tests/test_mk1_ai_trial.py tests/test_mk1_tester.py -q
exit /b %errorlevel%
:mk1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\mk1-ai\Development.ps1"
exit /b %errorlevel%
:mk2
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_tonecommand.ps1"
exit /b %errorlevel%
:missing
echo Run ToneCommand.cmd install first. No device was opened.
exit /b 1
:usage
echo Usage: ToneCommand.cmd [install^|test^|mk1^|mk2]
exit /b 2

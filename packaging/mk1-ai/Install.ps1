param([switch]$Development)
$ErrorActionPreference = 'Stop'
$trialRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $trialRoot
$trialPython = Join-Path $trialRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $trialPython -PathType Leaf)) {
    & py -3.12 -m venv (Join-Path $trialRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Install official Python3.12 64-bit first. No firmware/driver update is needed.' }
}
& $trialPython -c "import struct,sys; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
if ($LASTEXITCODE -ne 0) { throw 'Extract into a new folder and use Python3.12 64-bit. Do not reuse another app environment.' }
& $trialPython -m pip install --disable-pip-version-check -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; do not connect the unit.' }
$env:PYTHONUTF8='1'
$env:TONECOMMAND_SIM='1'
$trialTests = @('tests/test_mk1_ai_trial.py', 'tests/test_mk1_tester.py')
if ($Development) { $trialTests += 'tests/test_mk1_development.py' }
& $trialPython -m pytest @trialTests -q
if ($LASTEXITCODE -ne 0) { throw 'Offline safety tests failed. Do not start the hardware trial.' }
if ($Development) {
    Write-Host 'Offline checks passed. Use ToneCommand.cmd in the shared checkout, or Start-MK1-Development.cmd. No hardware was accessed.'
} else {
    Write-Host 'Offline checks passed. Run Start-MK1-AI-Trial.cmd. No hardware was accessed by this installer.'
}

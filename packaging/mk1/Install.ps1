$ErrorActionPreference = 'Stop'
$kitRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $kitRoot
Write-Host 'Unofficial ToneCommand MK1 read-only tester setup'
Write-Host 'No drivers, firmware, global Python packages or Fractal memory are changed.'
$kitPython = Join-Path $kitRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $kitPython -PathType Leaf)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -c "import struct,sys; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
        if ($LASTEXITCODE -ne 0) { throw 'Install Python3.12 64-bit first. See docs/MK1-TESTER-GUIDE.md.' }
        & py -3.12 -m venv (Join-Path $kitRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import struct,sys; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
        if ($LASTEXITCODE -ne 0) { throw 'Install Python3.12 64-bit first. Do not substitute Python3.14.' }
        & python -m venv (Join-Path $kitRoot '.venv')
    } else { throw 'Python3.12 is missing. Install the official 64-bit Windows Python3.12 distribution first.' }
    if ($LASTEXITCODE -ne 0) { throw 'Creating the private virtual environment failed.' }
}
& $kitPython -c "import struct,sys; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"
if ($LASTEXITCODE -ne 0) { throw 'This .venv is not 64-bit Python3.12. Extract into a new folder; do not reuse another app environment.' }
& $kitPython -m pip install --disable-pip-version-check -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Keep the console error; do not start a partial installation.' }
& $kitPython -m pytest tests/test_mk1_tester.py tests/test_language_packs.py -q
if ($LASTEXITCODE -ne 0) { throw 'Offline safety tests failed. Do not connect the unit.' }
Write-Host 'Setup and offline safety tests passed. Run Start-MK1.cmd next.'
Write-Host 'Never start server.py directly for this MK1 evaluation.'

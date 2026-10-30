$ErrorActionPreference = 'Stop'
$kitRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $kitRoot
$kitPython = Join-Path $kitRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $kitPython -PathType Leaf)) { throw 'Run Install-MK1.cmd first.' }
if (Get-NetTCPConnection -LocalPort 8909 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port8909 is already in use. Close the other TC normally. This package will not kill or replace it.'
}
$env:PYTHONUTF8 = '1'
Write-Host 'Close Axe-Edit before connecting. Keep external monitoring muted.'
Write-Host 'Leave this console open. Press Ctrl+C here to stop TC normally.'
& $kitPython -m tools.mk1_tester serve
if ($LASTEXITCODE -ne 0) { throw 'The MK1 tester stopped with an error. No automatic restart.' }

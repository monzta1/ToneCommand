$ErrorActionPreference = 'Stop'
$developmentRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $developmentRoot
if (Get-NetTCPConnection -LocalPort 8909 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Close the other TC normally first. No process is killed or replaced.'
}
$developmentPython = Join-Path $developmentRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $developmentPython -PathType Leaf)) {
    throw 'Run Install-MK1-Development.cmd in this clone first.'
}
$env:PYTHONUTF8 = '1'
Write-Host 'UNOFFICIAL MK1 DEVELOPMENT. No ZIP manifest required. Local modifications are NOT a validated release.'
Write-Host 'Close Axe-Edit and mute external monitoring before SEND. No Store/NAM/global writes.'
& $developmentPython -m tools.mk1_development
if ($LASTEXITCODE -ne 0) { throw 'Stopped. No automatic restart or write retry. Read the error above.' }

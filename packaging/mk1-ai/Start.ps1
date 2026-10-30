$ErrorActionPreference = 'Stop'
$trialRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Set-Location -LiteralPath $trialRoot
if (Get-NetTCPConnection -LocalPort 8909 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Close the other TC normally first. No process is killed or replaced.'
}
$trialPython = Join-Path $trialRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $trialPython -PathType Leaf)) { throw 'Run Install-MK1-AI-Trial.cmd first.' }
$env:PYTHONUTF8='1'
Write-Host 'EXPERIMENTAL MK1 AI BUILDER. Close Axe-Edit. Mute external monitoring before SEND.'
Write-Host 'Uses only your manually selected empty preset. No Store/NAM/User2/controllers/global or firmware writes.'
& $trialPython -m tools.mk1_ai_trial
if ($LASTEXITCODE -ne 0) { throw 'TC stopped with an error. No automatic restart or write retry.' }

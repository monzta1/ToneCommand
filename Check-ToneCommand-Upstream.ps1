[CmdletBinding()]
param([switch]$Fetch, [switch]$Json)

# This checks Git only. It never starts TC or opens the Fractal's MIDI port.
$ErrorActionPreference = 'Stop'
$tcCheckPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $tcCheckPython)) {
    throw 'Install the project virtual environment before checking upstream.'
}
$tcCheckArgs = @('-X', 'utf8', 'tools/upstream_status.py')
if ($Fetch) { $tcCheckArgs += '--fetch' }
if ($Json) { $tcCheckArgs += '--json' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $tcCheckPython @tcCheckArgs
    if ($LASTEXITCODE -ne 0) { throw 'Upstream check failed. No application update was applied.' }
} finally {
    Pop-Location
}

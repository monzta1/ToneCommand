param(
    [ValidateRange(1024,65535)][int]$Port = 8910,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$controllerRoot = Split-Path -Parent $PSScriptRoot
$controllerPython = Join-Path $controllerRoot '.venv\Scripts\python.exe'
$controllerUrl = "http://127.0.0.1:$Port/controllers"
if (-not (Test-Path -LiteralPath $controllerPython)) {
    throw "Python environment missing: $controllerPython"
}
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $existing = Invoke-WebRequest -Uri $controllerUrl -UseBasicParsing -TimeoutSec 3
    if ($existing.Content -notmatch 'controllers.js' -or $existing.Content -notmatch 'ToneCommand') {
        throw "Port $Port belongs to another application. Choose a different -Port."
    }
} else {
    $controllerLogs = Join-Path $controllerRoot 'backups\controller-workspace'
    New-Item -ItemType Directory -Path $controllerLogs -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $previousSim = $env:TONECOMMAND_SIM
    $previousUtf8 = $env:PYTHONUTF8
    try {
        $env:TONECOMMAND_SIM = '0'
        $env:PYTHONUTF8 = '1'
        $started = Start-Process -FilePath $controllerPython -WorkingDirectory $controllerRoot `
            -ArgumentList @('-m','uvicorn','server:app','--host','127.0.0.1','--port',"$Port") `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $controllerLogs "$stamp-out.log") `
            -RedirectStandardError (Join-Path $controllerLogs "$stamp-error.log")
    } finally {
        $env:TONECOMMAND_SIM = $previousSim
        $env:PYTHONUTF8 = $previousUtf8
    }
    $controllerDeadline = [DateTime]::UtcNow.AddSeconds(20)
    $ready = $false
    while ([DateTime]::UtcNow -lt $controllerDeadline) {
        if ($started.HasExited) { throw "Server exited. Check $controllerLogs" }
        try {
            $response = Invoke-WebRequest -Uri $controllerUrl -UseBasicParsing -TimeoutSec 2
            $ready = $response.StatusCode -eq 200 -and $response.Content -match 'controllers.js'
        } catch [System.Net.WebException] { $ready = $false }
        if ($ready) { break }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw "Server not ready yet. Check $controllerLogs before starting another instance." }
}
Write-Host "Controller workspace: $controllerUrl"
Write-Host 'Close Axe-Edit and other TC MIDI sessions, then connect explicitly in this page. Nothing is sent automatically.'
if (-not $NoBrowser) {
    $controllerChrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if (Test-Path -LiteralPath $controllerChrome) {
        Start-Process -FilePath $controllerChrome -ArgumentList $controllerUrl
    } else {
        Write-Host 'Chrome was not found at its standard path. Open the URL above in your browser.'
    }
}

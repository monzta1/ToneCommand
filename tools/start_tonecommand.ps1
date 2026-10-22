param(
    [ValidateSet(8909)][int]$Port = 8909,
    [string]$SettingsDirectory = '',
    [switch]$Connect,
    [ValidateSet('','mk1','mk2')][string]$AxeFxVariant = '',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$tcSource = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$tcPython = Join-Path $tcSource '.venv\Scripts\python.exe'
$tcUrl = "http://127.0.0.1:$Port/axefx3"
$tcStateUrl = "http://127.0.0.1:$Port/api/axefx3/state"
if (-not (Test-Path -LiteralPath $tcPython)) { throw "Python environment missing: $tcPython" }
$tcFiles = @('server.py','fm9/planner.py','fm9/protocol.py','fm9/device.py',
    'fm9/language.py','ui/languages/i18next.min.js','ui/languages/tc-language.js',
    'ui/languages/en.json','ui/languages/template.json','ui/languages/manifest.json',
    'ui/axefx3.js','ui/axefx3.html','ui/index.html','devices/axefx3/data/fw33_amp_models.json',
    'devices/axefx3/data/fw33_cab_models.json','devices/axefx3/data/fw33_cab_probe.json',
    'devices/axefx3/data/fw33_drive_probe.json','devices/axefx3/data/fw33_effect_calibration.json',
    'devices/axefx3/data/fw33_zero_tempo_calibration.json',
    'devices/axefx3/data/fw33_inherited_controls.json',
    'devices/axefx3/data/fw33_legacy_zeros.json',
    'devices/axefx3/data/fw33_effect_models.json') + @(
    Get-ChildItem -LiteralPath (Join-Path $tcSource 'devices\axefx3') -File -Filter '*.py' |
        ForEach-Object { 'devices/axefx3/' + $_.Name })
function Assert-TcWorkspace($State, $Listener) {
    if ($State.workspace.contract -ne 'fx3-workspace-20261012' -or
        $State.workspace.source_root -ne $tcSource -or
        $State.workspace.pid -ne $Listener.OwningProcess) {
        throw "Port $Port belongs to another or older TC checkout. Close that TC normally first. No second instance or automatic termination."
    }
    if (@($State.workspace.files.psobject.Properties).Count -ne $tcFiles.Count) {
        throw 'TC source-file set changed. Restart normally; do not reuse a partial update.'
    }
    foreach ($tcFile in $tcFiles) {
        $tcHash = (Get-FileHash -LiteralPath (Join-Path $tcSource $tcFile) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($State.workspace.files.$tcFile -ne $tcHash) {
            throw 'TC is running older imported code. Restart it normally before opening the updated workspace.'
        }
    }
}
if (Get-NetTCPConnection -LocalPort 8910 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8910 is occupied. Close the other TC normally first; this launcher never starts or reuses a second workspace.'
}
$tcListener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($tcListener.Count -gt 1) { throw "Ambiguous listeners on port $Port. Nothing started." }
if ($tcListener.Count -eq 1) {
    try { $tcState = Invoke-RestMethod -Uri $tcStateUrl -TimeoutSec 5 }
    catch [System.Net.WebException] { throw "Port $Port is occupied by an older TC or another application. Close it normally first; nothing started." }
    Assert-TcWorkspace $tcState $tcListener[0]
} else {
    $tcLogs = Join-Path $tcSource 'backups\tc-runtime'
    New-Item -ItemType Directory -Path $tcLogs -Force | Out-Null
    $tcStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
    $tcSavedEnv = @{}
    foreach ($tcKey in @('TONECOMMAND_SIM','PYTHONUTF8','TONECOMMAND_PORT','TONECOMMAND_DEVICE',
        'TONECOMMAND_AI_SETTINGS','TONECOMMAND_STORE_SLOTS_FILE','TONECOMMAND_USER_CABS')) {
        $tcSavedEnv[$tcKey] = [Environment]::GetEnvironmentVariable($tcKey,'Process')
    }
    try {
        $env:TONECOMMAND_SIM = '0'
        $env:PYTHONUTF8 = '1'
        $env:TONECOMMAND_PORT = [string]$Port
        # Device choice/connection belongs to the GUI, not legacy FM9 startup.
        [Environment]::SetEnvironmentVariable('TONECOMMAND_DEVICE',$null,'Process')
        if ($SettingsDirectory) {
            $tcSettings = (Resolve-Path -LiteralPath $SettingsDirectory).Path
            foreach ($tcSetting in @(
                @('TONECOMMAND_AI_SETTINGS','ai_settings.json'),
                @('TONECOMMAND_STORE_SLOTS_FILE','store_slots.json'))) {
                $tcPath = Join-Path $tcSettings $tcSetting[1]
                if (-not (Test-Path -LiteralPath $tcPath -PathType Leaf)) {
                    throw "Existing settings file missing: $tcPath. Nothing copied or guessed."
                }
                [Environment]::SetEnvironmentVariable($tcSetting[0],$tcPath,'Process')
            }
            $tcOptionalNames = Join-Path $tcSettings 'user_cabs.json'
            [Environment]::SetEnvironmentVariable('TONECOMMAND_USER_CABS',
                $(if (Test-Path -LiteralPath $tcOptionalNames -PathType Leaf) { $tcOptionalNames } else { $null }), 'Process')
        }
        $tcProcess = Start-Process -FilePath $tcPython -ArgumentList @('-m','server') `
            -WorkingDirectory $tcSource -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $tcLogs "$tcStamp-out.log") `
            -RedirectStandardError (Join-Path $tcLogs "$tcStamp-error.log")
    } finally {
        foreach ($tcKey in $tcSavedEnv.Keys) {
            [Environment]::SetEnvironmentVariable($tcKey,$tcSavedEnv[$tcKey],'Process')
        }
    }
    $tcDeadline = [DateTime]::UtcNow.AddSeconds(25)
    $tcReady = $false
    while ([DateTime]::UtcNow -lt $tcDeadline) {
        if ($tcProcess.HasExited) { throw "TC exited. Inspect $tcLogs; do not start another instance." }
        try {
            $tcState = Invoke-RestMethod -Uri $tcStateUrl -TimeoutSec 2
            $tcReady = $true
        } catch [System.Net.WebException] { $tcReady = $false }
        if ($tcReady) { break }
        Start-Sleep -Milliseconds 200
    }
    if (-not $tcReady) { throw "TC readiness unknown. Inspect $tcLogs; no retry or second instance." }
    $tcListener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($tcListener.Count -ne 1) { throw 'Single runtime listener not verified.' }
    Assert-TcWorkspace $tcState $tcListener[0]
}
Write-Host "TC FX3 $($tcState.workspace.revision): $tcSource"
Write-Host "Single workspace: $tcUrl (PID $($tcState.workspace.pid)). No hardware writes or automatic AI/build/Store."
if ($Connect) {
    if (Get-Process -Name 'Axe-Edit III' -ErrorAction SilentlyContinue) {
        throw 'TC is running, but Axe-Edit owns MIDI. Close Axe-Edit normally and connect in TC; no forced handoff.'
    }
    if (-not $tcState.connected) {
        $tcConnected = Invoke-RestMethod "http://127.0.0.1:$Port/api/controllers/connect" -Method Post -TimeoutSec 20
        if (-not $tcConnected.connected) { throw 'Read-only MIDI connection not verified. TC remains running; nothing sent.' }
        $tcState = Invoke-RestMethod -Uri $tcStateUrl -TimeoutSec 20
    }
    if ($AxeFxVariant -and $tcState.profile.variant -ne $AxeFxVariant) {
        $tcProfile = Invoke-RestMethod "http://127.0.0.1:$Port/api/axefx3/profile" -Method Post -TimeoutSec 10 `
            -ContentType 'application/json' -Body (ConvertTo-Json @{variant=$AxeFxVariant} -Compress)
        if ($tcProfile.hardware_written) { throw 'Unexpected hardware write from local profile choice.' }
    }
}
if (-not $NoBrowser) {
    $tcChrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    if (Test-Path -LiteralPath $tcChrome) {
        Start-Process -FilePath $tcChrome -ArgumentList $tcUrl -WindowStyle Hidden
    } else { Write-Host "Chrome not found. Open $tcUrl in your browser." }
}

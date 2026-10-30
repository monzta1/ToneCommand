"""Checkout identity and Windows launcher tests never open MIDI or real servers."""
import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import Mock

import pytest
from devices.axefx3 import runtime, album_planning

ROOT = Path(__file__).resolve().parents[1]


def test_identity_pins_files_and_contains_no_account_settings(tmp_path, monkeypatch):
    for name in runtime.FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic source', encoding='utf-8')
    monkeypatch.setattr(runtime.subprocess, 'run', Mock(side_effect=OSError('no git')))
    info = runtime.identity(tmp_path)
    assert info['contract'] == 'fx3-workspace-20261012'
    assert info['source_root'] == str(tmp_path.resolve()) and info['pid'] > 0
    assert info['revision'] == '' and set(info['files']) == set(runtime.FILES)
    first = dict(info['files'])
    (tmp_path / 'ui/axefx3.js').write_text('changed source', encoding='utf-8')
    assert info['files'] == first  # Existing runtime cannot claim new imported code.
    assert runtime.identity(tmp_path)['files']['ui/axefx3.js'] != first['ui/axefx3.js']
    assert 'settings' not in json.dumps(info)


@pytest.mark.parametrize('prompt', [
    'Zoek een geschikte CAB in de usercab bibliotheek',
    'Use a user cab', 'kies usercabs', 'USER 1 slot 28', 'U2.0050 exact',
])
def test_explicit_user_ir_intent_never_silently_uses_factory(prompt):
    assert album_planning.user_cab_requested(prompt)


def test_measured_factory_request_is_not_a_user_ir_request():
    assert not album_planning.user_cab_requested('Metallica albums AMP CAB met Factory2')


PS = shutil.which('powershell')


@pytest.mark.skipif(not PS, reason='Windows PowerShell launcher')
@pytest.mark.parametrize('case', ['reuse', 'reuse-connect', 'wrong-root', 'stale-code',
                                 'stale-inventory', 'stale-drive-probe', 'stale-effect-inventory','stale-zero-tempo','stale-inherited-controls',
                                 'stale-controllers', 'stale-reviewed-edit', 'occupied-old', 'new', 'new-settings', 'second-port'])
def test_launcher_reuses_only_exact_runtime_and_never_kills_or_writes(tmp_path, case):
    source = tmp_path / 'checkout with spaces'
    (source / 'tools').mkdir(parents=True)
    (source / '.venv/Scripts').mkdir(parents=True)
    (source / '.venv/Scripts/python.exe').touch()
    for name in runtime.FILES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('source', encoding='utf-8')
    launcher = source / 'tools/start_tonecommand.ps1'
    shutil.copyfile(ROOT / 'tools/start_tonecommand.ps1', launcher)
    info = runtime.identity(source)
    info['pid'] = 1234
    if case == 'wrong-root':
        info['source_root'] = str(tmp_path / 'other checkout')
    if case == 'stale-code':
        info['files']['devices/axefx3/album_build.py'] = 'stale'
    if case == 'stale-inventory':
        info['files']['devices/axefx3/data/fw33_amp_models.json'] = 'stale'
    if case == 'stale-drive-probe':
        info['files']['devices/axefx3/data/fw33_drive_probe.json'] = 'stale'
    if case == 'stale-effect-inventory':
        info['files']['devices/axefx3/data/fw33_effect_models.json'] = 'stale'
    if case == 'stale-zero-tempo':
        info['files']['devices/axefx3/data/fw33_zero_tempo_calibration.json'] = 'stale'
    if case=='stale-inherited-controls':
        info['files']['devices/axefx3/data/fw33_inherited_controls.json']='stale'
    if case=='stale-controllers':
        info['files']['ui/controllers.js']='stale'
    if case=='stale-reviewed-edit':
        info['files']['ui/axefx3-reviewed-edit.js']='stale'
    state = json.dumps(dict(connected=case=='reuse-connect', profile={'variant':'mk2'}, workspace=info))
    extra = '-Connect -AxeFxVariant mk2' if case=='reuse-connect' else ''
    if case=='new-settings':
        settings=tmp_path / 'existing settings'
        settings.mkdir()
        for name in ('ai_settings.json','store_slots.json'):
            (settings / name).write_text('{}',encoding='utf-8')
        extra="-SettingsDirectory '"+str(settings).replace("'","''")+"'"
    # The test replaces OS/process/network boundaries. No real server, browser,
    # MIDI or termination operation is reachable.
    command = '''
$ErrorActionPreference='Stop'
$global:started=$false
$global:posts=0
$global:tcCase='%s'
function Get-NetTCPConnection {
 param($LocalPort,$State,$ErrorAction)
 if ($global:tcCase -eq 'second-port') { if ($LocalPort -eq 8910) { [pscustomobject]@{OwningProcess=999} }; return }
 if ($LocalPort -eq 8910) { return }
 if ($global:tcCase.StartsWith('new') -and -not $global:started) { return }
 [pscustomobject]@{OwningProcess=1234}
}
function Invoke-RestMethod {
 param($Uri,$TimeoutSec,$Method)
 if ($Method -and $Method -ne 'GET') { $global:posts++; throw 'No POST allowed' }
 if ($global:tcCase -eq 'occupied-old') { throw [System.Net.WebException]::new('404') }
 '%s' | ConvertFrom-Json
}
function Start-Process {
 param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,[switch]$PassThru,$RedirectStandardOutput,$RedirectStandardError)
 if ($global:started -or $WindowStyle -ne 'Hidden') { throw 'Second/visible process' }
 if ($ArgumentList.Count -ne 2 -or $ArgumentList[0] -ne '-m' -or $ArgumentList[1] -ne 'server') { throw 'Wrong source command' }
 $global:started=$true
 [pscustomobject]@{HasExited=$false}
}
function Get-FileHash { throw 'Module-discovered Get-FileHash is unavailable in this host' }
function Stop-Process { throw 'Never terminate existing process' }
function Get-Process { param($Name,$ErrorAction); return }
$env:TONECOMMAND_DEVICE='sentinel'
$env:TONECOMMAND_AI_SETTINGS='sentinel-ai'
$env:TONECOMMAND_STORE_SLOTS_FILE='sentinel-policy'
try { & '%s' -NoBrowser %s; $ok=$true } catch { $ok=$false;$failure=$_.Exception.Message }
@{ok=$ok;started=$global:started;posts=$global:posts;device=$env:TONECOMMAND_DEVICE;ai=$env:TONECOMMAND_AI_SETTINGS;policy=$env:TONECOMMAND_STORE_SLOTS_FILE;failure=$failure} | ConvertTo-Json -Compress
''' % (case, state.replace("'", "''"), str(launcher).replace("'", "''"),extra)
    result = subprocess.run([PS, '-NoProfile', '-Command', command], capture_output=True,
                            encoding='utf-8', errors='replace', timeout=35, check=True)
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed['ok'] == (case in ('reuse', 'reuse-connect', 'new', 'new-settings')), result.stdout + result.stderr
    assert observed['started'] == case.startswith('new')
    assert observed['posts'] == 0 and observed['device'] == 'sentinel'
    assert observed['ai']=='sentinel-ai' and observed['policy']=='sentinel-policy'

"""Passive discovery metadata and the shipped FX3 choice painter, no MIDI."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

import server


def test_device_metadata_discovery_does_not_open_or_change_a_context(monkeypatch):
    before = server.device_context()
    detected = [{'kind': 'axefx3', 'label': 'Axe-Fx III', 'supported': True}]
    monkeypatch.setattr(server, 'detected_devices', lambda: detected)
    monkeypatch.setattr(server, 'get_fm9', lambda: pytest.fail('Discovery opened MIDI'))
    monkeypatch.setattr(server, '_build_context', lambda *_: pytest.fail('Discovery connected'))
    with TestClient(server.app) as client:
        result = client.get('/api/device')
    assert result.status_code == 200
    assert result.json()['detected'] == detected
    assert server.device_context() is before


@pytest.mark.parametrize('kinds,connected,wanted', [
    ([], False, ['']), (['axefx3'], False, ['axefx3']),
    (['fm9'], False, ['fm9']), (['fm9', 'axefx3'], False, ['axefx3', 'fm9']),
    (['fm9', 'fm9'], False, ['fm9']), (['ir2', 'unknown'], False, ['']),
    ([], True, ['axefx3']), (['fm9'], True, ['axefx3', 'fm9']),
])
def test_absent_devices_are_omitted_without_selecting_or_connecting(kinds, connected, wanted):
    node = shutil.which('node')
    if not node:
        if os.environ.get('CI'):
            pytest.fail('Node is required for the shipped UI regression')
        pytest.skip('Node is required for the shipped UI regression')
    code = (Path(__file__).resolve().parents[1] / 'ui/axefx3.js').read_text(encoding='utf-8')
    body = code.split('function renderDeviceChoices(info, connected=!!state?.connected) {', 1)[1].split('\n}', 1)[0]
    script = "const assert=require('node:assert/strict'); const tcText=x=>x; const busy=false;\n" + (
        "const choice={value:'',options:[],replaceChildren(...items){this.options=items},"
        "append(item){this.options.push(item)}}; const variant={hidden:false};\n"
        "const el=id=>id==='deviceChoice'?choice:variant;\n"
        "function Option(label,value){this.label=label;this.value=value};\n"
        "const fetch=()=>{throw Error('Painter performed IO')};\n"
        'function renderDeviceChoices(info, connected) {' + body + '\n}\n'
        f'renderDeviceChoices({json.dumps(dict(detected=[dict(kind=k) for k in kinds]))},{json.dumps(connected)});\n'
        f'assert.deepEqual(choice.options.map(o=>o.value),{json.dumps(wanted)});\n'
        f'assert.equal(choice.disabled,{json.dumps(wanted == [""])});\n'
        'assert.equal(variant.hidden,choice.value!=="axefx3");\n'
    )
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stderr

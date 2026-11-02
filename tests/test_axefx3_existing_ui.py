"""Run the shipped addon with independent DOM/HTTP/clock fixtures."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('scenario',['lifecycle','scan-consent','question','confirm-consent',
    'late-plan','late-state','unsafe-result','arm-expiry','legacy','text-only','rescan'])
def test_shipped_existing_edit_controls(scenario):
    node=shutil.which('node')
    if not node:
        if os.environ.get('CI'):
            pytest.fail('Node is required for the existing-preset UI regression check')
        pytest.skip('Node is not installed')
    result=subprocess.run([node,str(ROOT/'tests/axefx3_existing_ui.cjs'),
        str(ROOT/'ui/axefx3-existing-edit.js'),scenario],capture_output=True,text=True,
        encoding='utf-8',timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_addon_has_no_keyboard_send_or_html_injection_path():
    source=(ROOT/'ui/axefx3-existing-edit.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in source and 'keydown' not in source
    html=(ROOT/'ui/index.html').read_text(encoding='utf-8')
    assert html.index('<script src="/axefx3-existing-edit.js"></script>')<html.index('<script>')
    assert html.index('window.AFX3Existing = window.installAFX3Existing();')<html.index("$('bootfail')?.remove();")

"""Execute the shipped opt-in controller with isolated DOM, clock and HTTP."""
import os
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_new_design_guard_includes_in_flight_reviewed_edit():
    node = shutil.which('node')
    if not node:
        if os.environ.get('CI'):
            pytest.fail('Node is required for the new-design guard regression')
        pytest.skip('Node is not installed')
    source = (ROOT / 'ui/index.html').read_text(encoding='utf-8')
    start = source.index('function newDesignBusy() {')
    function = source[start:source.index('\n}',start)+2]
    code = '''
const assert=require('node:assert/strict'),vm=require('node:vm');
const fn=%s;
for(const key of ['chatBusy','srcWork','planSending','reviewed']){
 const c={chatBusy:false,srcWork:false,planSending:false,window:{}};
 if(key==='reviewed')c.window.AFX3ReviewedEdit={working:()=>true};else c[key]=true;
 assert.equal(vm.runInNewContext(fn+';newDesignBusy()',c),true,key);
}
for(const api of [undefined,{working:()=>false}]){
 const c={chatBusy:false,srcWork:false,planSending:false,window:{AFX3ReviewedEdit:api}};
 assert.equal(vm.runInNewContext(fn+';newDesignBusy()',c),false);
}
console.log('passed');
''' % json.dumps(function)
    result = subprocess.run([node,'-e',code],capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert result.returncode==0,result.stderr
    assert 'passed' in result.stdout


@pytest.mark.parametrize('scenario', ['lifecycle', 'consent', 'timeout', 'queued-discard',
    'late-proposal', 'late-state', 'target', 'uncertain', 'dirty-input'])
def test_reviewed_edit_controller(scenario):
    node = shutil.which('node')
    if not node:
        if os.environ.get('CI'):
            pytest.fail('Node is required for the reviewed-edit UI regression check')
        pytest.skip('Node is not installed')
    result = subprocess.run([node, str(ROOT / 'tests/axefx3_reviewed_edit_ui.cjs'),
        str(ROOT / 'ui/axefx3-reviewed-edit.js'), scenario], capture_output=True,
        text=True, encoding='utf-8', timeout=15)
    assert result.returncode == 0, result.stderr
    assert '"passed":true' in result.stdout


def test_main_plan_has_no_iii_sweep_undo_or_unrun_tone_check():
    node = shutil.which('node')
    if not node:
        if os.environ.get('CI'):
            pytest.fail('Node is required for the plan-stage regression check')
        pytest.skip('Node is not installed')
    result = subprocess.run([node,str(ROOT / 'tests/axefx3_reviewed_plan_ui.cjs'),
        str(ROOT / 'ui/index.html'),str(ROOT / 'ui/axefx3-reviewed-edit.js')],
        capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert result.returncode == 0, result.stderr
    assert '"passed":true' in result.stdout

"""MK1 package guard/GUI contracts use fake ports, never a real unit or account."""
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import runpy
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

from fastapi.testclient import TestClient
import mido
import pytest

import server
from devices.axefx3 import protocol, grid, nam_slots
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from fm9 import protocol as shared
from tools import mk1_tester as kit, build_mk1_tester as builder


READS = [protocol.envelope(8, []), protocol.envelope(0x13, []),
    protocol.envelope(0x0d, [127,127]), protocol.envelope(0x0d, [0,0]),
    protocol.envelope(0x0c, [127]), protocol.envelope(0x0e, [127]),
    protocol.envelope(0x0e, [7]), protocol.envelope(0x0a, [58,0,127]),
    protocol.envelope(0x0b, [58,0,127]),
    grid.reframe(shared.build_request_grid_layout())]
WRITES = [protocol.envelope(0x0c, [0]), protocol.envelope(0x0a, [58,0,0]),
    protocol.envelope(0x0b, [58,0,1]), protocol.param_frame(58,1,5,opcode=9),
    protocol.param_frame(58,0,0,opcode=0x52), protocol.display_query(58,1),
    protocol.envelope(0x1f, [58,0]), nam_slots.name_request(1),
    nam_slots.memory_request(256), grid.reframe(shared.build_select_grid_cell(1,1)),
    grid.reframe(shared.build_set_grid_cell(1,1,58)), protocol.envelope(3,[0,0]),
    shared.envelope(8, []), protocol.envelope(0x0d,[0,4])]


@pytest.mark.parametrize('frame',READS)
def test_only_explicit_read_shapes_pass(frame):
    raw=Mock(); output=kit.ReadOnlyOutput(raw)
    assert kit.read_query(frame)
    output.send(mido.Message('sysex',data=frame[1:-1]))
    raw.send.assert_called_once()


@pytest.mark.parametrize('frame',WRITES)
def test_unsafe_or_unproven_frames_never_reach_port(frame):
    raw=Mock(); output=kit.ReadOnlyOutput(raw)
    assert not kit.read_query(frame)
    with pytest.raises(PermissionError):output.send(mido.Message('sysex',data=frame[1:-1]))
    raw.send.assert_not_called()
    assert output.rejected==1


@pytest.mark.parametrize('message',[mido.Message('control_change',control=0,value=2),
    mido.Message('program_change',program=5),mido.Message('note_on',note=60),mido.Message('clock')])
def test_non_sysex_is_blocked_even_outside_adapter_send(message):
    raw=Mock(); output=kit.ReadOnlyOutput(raw)
    with pytest.raises(PermissionError):output.send(message)
    raw.send.assert_not_called()


def test_corrupt_foreign_and_malformed_frames_fail_closed():
    frame=protocol.envelope(8,[]);frame[-2]^=1
    for bad in (None,[],[0xf0],frame,protocol.envelope(8,[0]),
                protocol.envelope(0x0c,[8]),protocol.envelope(0x0e,[8])):
        assert not kit.read_query(bad)


def test_subclass_discloses_readonly_and_does_not_open_native_ports(monkeypatch):
    raw=Mock();inp=Mock()
    monkeypatch.setattr(AxeFxIII,'firmware_label',lambda self:'33.99')
    monkeypatch.setattr(AxeFxIII,'current_preset',lambda self:(12,'private'))
    dev=kit.ReadOnlyAxeFxIII((inp,raw))
    assert dev.reg.hardware_variant=='mk1'
    assert not dev.capabilities().verifies_writes
    assert not dev.capabilities().can_rename
    with pytest.raises(PermissionError):dev._check_edit_target()
    with pytest.raises(PermissionError):dev.outp.send(mido.Message('program_change',program=0))
    raw.send.assert_not_called()
    dev.close();inp.close.assert_called_once();raw.close.assert_called_once()


class FakeDevice:
    def __init__(self):
        self._lock=threading.RLock()
        self.reg=Registry('33.99')
        self.firmware_reply_sha256='a'*64
        self.current_preset=Mock(return_value=(12,'PRIVATE PRESET NAME'))
        self.current_scene=Mock(return_value=1)
        self.firmware_label=Mock(return_value='33.99')
        self.status_dump=Mock(return_value=[shared.BlockStatus(58,False,0,4)])
        self.read_grid=Mock(return_value=[shared.GridCell(0,0,58,False,0)])
        self.scene_name=lambda scene:(scene,'PRIVATE SCENE NAME')
        self.close=Mock()
        self.outp=SimpleNamespace(queries=Counter({'08':2}),rejected=1)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(server,'_context',server._context)
    dev=FakeDevice()
    return kit.create_app(server,factory=lambda:dev),dev


HEADERS={'X-ToneCommand':'1'}


@pytest.mark.parametrize('path',[
    '/api/axefx3/send','/api/axefx3/plan','/api/axefx3/store/send',
    '/api/controllers/send','/api/device/select','/api/apply',
    '/api/axefx3/nam/install/commit','/api/axefx3/navigation/select',
    '/api/axefx3/tone3000/key'])
def test_http_writes_blocked_before_reaching_tc(app,path):
    application,dev=app
    with TestClient(application) as client:
        result=client.post(path,json={},headers=HEADERS)
    assert result.status_code==423
    dev.current_preset.assert_not_called()


def test_unrecognized_get_endpoints_cannot_open_accounts_or_memory(app):
    application,dev=app
    with TestClient(application) as client:
        for path in ('/api/tone3000/login','/api/axefx3/nam/slots','/api/controllers/state'):
            assert client.get(path).status_code==423
    dev.current_preset.assert_not_called()


def test_connection_requires_local_action_and_chassis_cannot_be_changed(app):
    application,dev=app
    with TestClient(application) as client:
        assert client.post('/api/controllers/connect',json={}).status_code==403
        assert client.post('/api/controllers/connect',json={},headers={**HEADERS,'Origin':'https://foreign.example'}).status_code==403
        assert client.post('/api/controllers/connect',json={},headers=HEADERS).status_code==200
        assert client.post('/api/axefx3/profile',json={'variant':'mk2'},headers=HEADERS).status_code==422
        response=client.get('/api/axefx3/state')
        assert response.status_code==200
        state=response.json()
        assert state['read_only'] and not state['navigation_supported']
        assert state['profile']['variant']=='mk1'
        assert not state['profile']['write_supported'] and not state['profile']['nam_writes']


def test_language_assets_are_available_without_relaxing_readonly_boundary(app):
    application,dev=app
    with TestClient(application) as client:
        for asset in ('en.json','template.json','manifest.json','i18next.min.js','tc-language.js'):
            assert client.get('/language/'+asset).status_code==200
        assert client.post('/language/en.json',json={},headers=HEADERS).status_code in (405,423)
        assert client.post('/api/axefx3/send',json={},headers=HEADERS).status_code==423
        assert not client.get('/api/mk1-test/status').json()['connected']


def test_observation_export_is_sanitized_and_survives_disconnect(app):
    application,dev=app
    with TestClient(application) as client:
        client.post('/api/controllers/connect',json={},headers=HEADERS)
        assert client.post('/api/mk1-test/observe',json={},headers=HEADERS).status_code==400
        got=client.post('/api/mk1-test/observe',json={'consent':True,'label':'baseline'},headers=HEADERS).json()
        assert got['observation']['coherent']
        assert got['local_view']['name']=='PRIVATE PRESET NAME'
        client.post('/api/controllers/disconnect',json={},headers=HEADERS)
        report=client.get('/api/mk1-test/report').json()
    dev.close.assert_called_once()
    assert report['queries']=={'08':2} and report['rejected_messages']==1
    assert report['observations'][0]['block_count']==1
    text=json.dumps(report)
    for forbidden in ('PRIVATE PRESET','PRIVATE SCENE','source_root','access_token','raw_sysex'):
        assert forbidden not in text
    assert not report['hardware_written'] and not report['mk1_write_release']


def test_changed_or_incomplete_state_is_not_reported_as_success():
    dev=FakeDevice();dev.current_scene.side_effect=[1,2]
    assert not kit.snapshot(dev)['coherent']
    dev=FakeDevice();dev.read_grid.return_value=None
    assert 'grid' in kit.snapshot(dev)['read_errors']


def test_environment_has_no_owner_accounts_or_storage_permissions(monkeypatch,tmp_path):
    env={'TONECOMMAND_STORE_SLOTS':'1-511','PLANNER_API_KEY':'private',
         'TONECOMMAND_TONE3000_DIR':'private-account','PATH':'retained'}
    monkeypatch.setattr(kit.os,'environ',env)
    kit.configure_environment(tmp_path)
    assert 'PLANNER_API_KEY' not in env
    assert env['TONECOMMAND_STORE_SLOTS']==env['TONECOMMAND_CAB_SLOTS']==env['TONECOMMAND_NAM_SLOTS']==''
    assert Path(env['TONECOMMAND_TONE3000_DIR']).is_relative_to(tmp_path)
    assert env['PATH']=='retained'


def test_workspace_and_shortcuts_use_only_test_launcher():
    root=Path(__file__).resolve().parents[1]
    workspace=json.loads((root/'MK1-Tester.code-workspace').read_text(encoding='utf-8'))
    launch=workspace['launch']['configurations'][0]
    assert launch['module']=='tools.mk1_tester' and launch['args']==['serve']
    start=(root/'packaging/mk1/Start.ps1').read_text(encoding='utf-8')
    assert 'tools.mk1_tester serve' in start
    assert 'Stop-Process' not in start and 'Start-Process' not in start
    assert 'Set-ExecutionPolicy' not in start
    site=(root/'.github/workflows/site.yml').read_text(encoding='utf-8')
    assert "if: github.repository == 'monzta1/ToneCommand'" in site


def test_example_scenario_uses_only_guarded_server_and_prints_summary(monkeypatch,capsys):
    path=Path(__file__).resolve().parents[1]/'packaging/mk1/example_scenario.py'
    module=runpy.run_path(str(path))
    calls=[]
    def local(endpoint,payload=None):
        calls.append((endpoint,payload))
        if endpoint.endswith('/status'):
            return dict(version=kit.VERSION,read_only=True,connected=True)
        return dict(observation={'label':'example'},local_view={'name':'PRIVATE NAME'})
    module['main'].__globals__['request_local']=local
    with pytest.raises(SystemExit):module['main']([])
    assert calls==[]
    assert module['main'](['--confirm-monitoring-muted','--label','example'])==0
    assert [call[0] for call in calls]==['/api/mk1-test/status','/api/mk1-test/observe']
    assert 'PRIVATE NAME' not in capsys.readouterr().out


def synthetic_archive(extra=None):
    names=['tools/mk1_tester.py','tests/test_mk1_tester.py',
        'docs/MK1-TESTER-GUIDE.md','packaging/mk1/welcome.html',
        'packaging/mk1/Install.ps1','packaging/mk1/Start.ps1',
        'packaging/mk1/example_scenario.py','packaging/mk1/SCENARIO-CHECKLIST.txt',
        'Install-MK1.cmd','Start-MK1.cmd','MK1-Tester.code-workspace',
        'pyproject.toml','server.py','LICENSE','START-HERE-MK1.txt']
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive:
        for name in names:archive.writestr(name,'public example')
        for name,content in (extra or {}).items():archive.writestr(name,content)
    return data.getvalue()


def fake_git(monkeypatch,archive):
    monkeypatch.setattr(builder.subprocess,'check_output',
        lambda args,**kwargs: b'a'*40 if args[1]=='rev-parse' else archive)


def test_builder_exports_only_committed_public_files_with_integrity(monkeypatch,tmp_path):
    fake_git(monkeypatch,synthetic_archive())
    path=builder.build(destination=tmp_path)
    with zipfile.ZipFile(path) as archive:
        root='ToneCommand-MK1-Tester-'+kit.VERSION+'/'
        manifest=json.loads(archive.read(root+'MK1-PACKAGE.json'))
        assert manifest['source_commit']=='a'*40 and manifest['read_only']
        assert not manifest['mk1_hardware_accepted']
        assert len(manifest['files'])==15
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    assert checksum in path.with_suffix('.sha256').read_text(encoding='ascii')
    with pytest.raises(FileExistsError):builder.build(destination=tmp_path)


@pytest.mark.parametrize('path',['.env','test-results/private/report.json','notes/private.txt',
                               'models/private.nam','../escape.txt'])
def test_builder_refuses_secrets_results_payloads_and_traversal(monkeypatch,tmp_path,path):
    fake_git(monkeypatch,synthetic_archive({path:'private'}))
    with pytest.raises(ValueError):builder.build(destination=tmp_path)
    assert not list(tmp_path.glob('*.zip'))


def test_cli_export_is_local_only_and_refuses_another_app(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(kit,'ROOT',tmp_path)
    monkeypatch.setattr(kit,'request_local',lambda *a,**k:{'read_only':False})
    with pytest.raises(SystemExit):kit.main(['export'])
    assert not (tmp_path/'test-results').exists()
    expected=dict(read_only=True,version=kit.VERSION,observations=[])
    monkeypatch.setattr(kit,'request_local',lambda *a,**k:expected)
    assert kit.main(['export'])==0
    files=list((tmp_path/'test-results/share').glob('*.zip'))
    assert len(files)==1
    with zipfile.ZipFile(files[0]) as bundle:
        assert bundle.namelist()==['report.json']
        assert json.loads(bundle.read('report.json'))==expected

from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
import threading
import json
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from devices.axefx3 import nam_file, nam_install, nam_memory, fw33_profile, tone3000 as t3
from devices.axefx3 import fw33
from tests.test_axefx3_fw33 import fake
from fm9 import protocol as p
from tests.test_axefx3_nam_conversion import source, compile_source
import server

@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(nam_install, '_platform_supported', lambda: True)
    t3.client.configure('public-client')
    selected = {'tone': {'id': 123, 'gear': 'amp-cab', 'title': 'Synthetic', 'creator': {},
                         'description': '', 'format': 'nam', 'url': 'https://www.tone3000.com/tones/123'},
                'model': {'id': 456, 'name': 'Synthetic'}, 'installed': False}
    t3.client._save_session({'access_token': 'test', 'selected': selected})
    raw = json.dumps(source()).encode()
    monkeypatch.setattr(t3.client, 'download', lambda model_id: (raw, 'synthetic.nam'))
    old = compile_source('Before')
    before = nam_memory.parse_export(old.frames())
    device = Mock(model=16, _injected_ports=False)
    device.edit_session.side_effect = lambda **kw: nullcontext()
    device.firmware_label.return_value = fw33_profile.KEY
    device.current_preset.return_value = (326, '<EMPTY>')
    device.read_grid.return_value = []
    device.read_nam_slot.return_value = before
    device.export_nam_slot.return_value = (before, old.frames())
    device.install_nam_slot.side_effect = lambda slot, model, sha: nam_memory.parse_export(model.frames(slot),slot=slot)
    policy = {'device': 'axe-fx-iii', 'firmware': fw33_profile.KEY, 'variant': 'mk2',
              'simulated': False, 'gig_locked': False, 'allowed_presets': {326}}
    service = nam_install.Installer(threading.RLock(), lambda: device, lambda: policy)
    monkeypatch.setattr(server._afx3_nam_installer,'prepare',service.prepare)
    monkeypatch.setattr(server._afx3_nam_installer,'commit',service.commit)
    return service, device, policy, before, tmp_path


def test_prepare_is_readonly_commit_is_explicit_and_full_backup_exists(setup):
    service, device, _policy, before, _tmp = setup
    preview = service.prepare(456, 326, 1)
    device.install_nam_slot.assert_not_called()
    assert preview['readonly'] and preview['existing_name'] == 'Before'
    result = service.commit(preview['prepared_id'], True, True, True)
    assert result['ok'] and result['bytes_verified'] == 65536 and not result['preset_stored']
    assert Path(result['backup']).read_bytes() == b''.join(compile_source('Before').frames())
    assert t3.client.status()['selected']['installed'] is True
    context = t3.client.planner_context()
    assert 'NOT fresh device authorization' in context
    assert result['backup'] not in context and 'access_token' not in context
    with pytest.raises(t3.ToneError):
        service.commit(preview['prepared_id'], True, True, True)
    assert device.install_nam_slot.call_count == 1


@pytest.mark.parametrize('source_name,expected',[
    ('puppet','puppet'),
    ('Marshall JTM45+cab led zeppelin whole lotte love setting','Marshall JTM45+cab led zepp'),
    ('Crème Brûlée\nRock','Creme Brulee Rock'),
    ('  Rock   Tone  ','Rock Tone'),
    ('EMPTY','NAM 456'),('', 'NAM 456'),
    ('\x00\x01','NAM 456')])
def test_catalog_label_maps_to_strict_header_without_changing_weights(setup,source_name,expected):
    service,device,_policy,_before,_tmp=setup
    with t3.client.lock:
        session=t3.client._session()
        session['selected']['model']['name']=source_name
        t3.client._save_session(session)
    preview=service.prepare(456,326,1)
    assert preview['name']==expected
    assert preview['source_name']==source_name
    assert preview['name_adjusted']==(expected!=source_name)
    assert 1<=len(preview['name'])<=27
    assert preview['source_sha256']==compile_source().source_sha256
    assert service.pending['compiled'].payload[28:]==compile_source().payload[28:]
    device.install_nam_slot.assert_not_called()


@pytest.mark.parametrize('fault', ['firmware', 'mk1', 'fm9', 'sim', 'gig', 'preset', 'grid', 'allowlist'])
def test_policy_and_device_guards_prevent_writes(setup, fault):
    service, device, policy, _before, _tmp = setup
    if fault == 'firmware': device.firmware_label.return_value = '33.01'
    if fault == 'mk1': policy['variant'] = 'mk1'
    if fault == 'fm9': policy['device'] = 'fm9'
    if fault == 'sim': policy['simulated'] = True
    if fault == 'gig': policy['gig_locked'] = True
    if fault == 'preset': device.current_preset.return_value = (327, '<EMPTY>')
    if fault == 'grid': device.read_grid.return_value = [p.GridCell(2, 0, 206, False, 0)]
    if fault == 'allowlist': policy['allowed_presets'] = set()
    with pytest.raises(t3.ToneError):
        service.prepare(456, 326, 1)
    device.install_nam_slot.assert_not_called()


@pytest.mark.parametrize('acks', [(False, True, True), (True, False, True), (True, True, False),
                                 ('true', True, True), (1, True, True)])
def test_acknowledgements_cannot_be_inferred_or_coerced(setup, acks):
    service, device, _policy, _before, _tmp = setup
    preview = service.prepare(456, 326, 1)
    with pytest.raises(t3.ToneError): service.commit(preview['prepared_id'], *acks)
    device.install_nam_slot.assert_not_called()


@pytest.mark.parametrize('fault', ['token', 'expired', 'selection', 'memory', 'export', 'backup', 'readback'])
def test_changed_evidence_and_failed_recovery_stop_install(setup, monkeypatch, fault):
    service, device, _policy, before, _tmp = setup
    preview = service.prepare(456, 326, 1)
    token = preview['prepared_id']
    if fault == 'token': token = 'bad-token'
    if fault == 'expired': service.pending['expires'] = 0
    if fault == 'selection': t3.client.clear_selection()
    if fault == 'memory': device.export_nam_slot.return_value = (replace(before, payload_sha256='bad'), compile_source('Before').frames())
    if fault == 'export': device.export_nam_slot.return_value = (before, compile_source('Before').frames()[:-1])
    if fault == 'backup':
        monkeypatch.setattr(t3, '_write_private', Mock(side_effect=OSError('private location')))
    if fault == 'readback': device.install_nam_slot.return_value = before; device.install_nam_slot.side_effect = None
    with pytest.raises((t3.ToneError, ValueError)):
        service.commit(token, True, True, True)
    assert device.install_nam_slot.call_count == (1 if fault == 'readback' else 0)


def test_local_routes_use_two_phase_body_and_csrf_protection(setup):
    _service, device, _policy, _before, _tmp = setup
    client = TestClient(server.app, base_url='http://127.0.0.1:8909', headers={'X-ToneCommand': '1'})
    body = {'model_id': 456, 'expected_preset': 326, 'slot': 1}
    assert client.post('/api/axefx3/tone3000/install/prepare', json=body, headers={'Origin': 'https://evil.test'}).status_code == 403
    assert client.post('/api/axefx3/tone3000/install/prepare', json={**body, 'slot': 257}).status_code == 422
    preview = client.post('/api/axefx3/tone3000/install/prepare', json=body)
    assert preview.status_code == 200
    token = preview.json()['prepared_id']
    assert client.post('/api/axefx3/tone3000/install', json={'prepared_id': token}).status_code == 403
    assert client.post('/api/axefx3/tone3000/install', json={'prepared_id': token, 'external_audio_muted': 'true'}).status_code == 422
    result = client.post('/api/axefx3/tone3000/install', json={'prepared_id': token, 'external_audio_muted': True,
        'confirm_permanent_write': True, 'confirm_overwrite': True})
    assert result.status_code == 200 and result.json()['ok']
    assert device.install_nam_slot.call_count == 1


def test_front_panel_preset_change_during_backup_stops_install(setup):
    service, device, _policy, _before, _tmp = setup
    preview = service.prepare(456, 326, 1)
    device.current_preset.side_effect = [(326, '<EMPTY>'), (327, '<EMPTY>')]
    with pytest.raises(t3.ToneError, match='target preset changed'):
        service.commit(preview['prepared_id'], True, True, True)
    device.install_nam_slot.assert_not_called()


def test_identical_reconnected_device_invalidates_install_preview(setup):
    service,device,_policy,_before,_tmp=setup
    preview=service.prepare(456,326,1)
    replacement=Mock(model=16,_injected_ports=False)
    replacement.firmware_label.return_value=fw33_profile.KEY
    replacement.current_preset.return_value=(326,'<EMPTY>')
    replacement.read_grid.return_value=[]
    service.get_device=lambda:replacement
    with pytest.raises(t3.ToneError,match='connection changed'):
        service.commit(preview['prepared_id'],True,True,True)
    replacement.export_nam_slot.assert_not_called()
    replacement.install_nam_slot.assert_not_called()
    device.install_nam_slot.assert_not_called()


def test_unmeasured_platform_is_refused(setup, monkeypatch):
    service, device, _policy, _before, _tmp = setup
    monkeypatch.setattr(nam_install, '_platform_supported', lambda: False)
    with pytest.raises(t3.ToneError):
        service.prepare(456, 326, 1)
    device.install_nam_slot.assert_not_called()


def test_native_frame_sequence_is_separately_guarded_and_fully_verified(monkeypatch):
    dev=fake();dev._injected_ports=False
    before=nam_memory.parse_export(compile_source('Before').frames())
    compiled=compile_source();after=nam_memory.parse_export(compiled.frames())
    dev.read_nam_slot.side_effect=[before,after]
    dev._nam_install_permit=(1,compiled.source_sha256,before.payload_sha256)
    monkeypatch.setattr(fw33,'platform_supported',lambda:True)
    monkeypatch.setattr(fw33.time,'sleep',lambda _:None)
    assert fw33.install(dev,compiled,before.payload_sha256)==after
    frames=tuple(bytes([240,*c.args[0].data,247]) for c in dev.outp.send.call_args_list)
    assert frames==compiled.frames() and len(frames)==130
    from devices.axefx3.adapter import AxeFxIII
    for fn in (0x54,0x55,0x56):
        with pytest.raises(Exception):AxeFxIII.guard.check(fn)


@pytest.mark.parametrize('fault',['hash','variant','firmware','source','payload','target'])
def test_native_installer_refuses_changed_or_forged_input_without_writes(monkeypatch,fault):
    dev=fake();dev._injected_ports=False
    before=nam_memory.parse_export(compile_source('Before').frames())
    dev.read_nam_slot.return_value=before;compiled=compile_source()
    sha=before.payload_sha256
    dev._nam_install_permit=(1,compiled.source_sha256,sha)
    monkeypatch.setattr(fw33,'platform_supported',lambda:True)
    if fault=='hash':sha='bad'
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='firmware':dev.reg.firmware='33.01'
    if fault=='source':compiled=replace(compiled,source_sha256='bad')
    if fault=='payload':compiled=replace(compiled,payload=b'x'*65536)
    if fault=='target':dev._check_edit_target.side_effect=PermissionError('target changed')
    with pytest.raises(PermissionError):fw33.install(dev,compiled,sha)
    dev.outp.send.assert_not_called()


def test_every_ported_broad_handler_has_an_explicit_disposition():
    import ast
    import server
    from tests.test_capability_gates import _except_exception_blocks
    from pathlib import Path
    root=Path(server.__file__).parent
    entries=json.loads((root/'tests/data/broad_except_audit.json').read_text(encoding='utf8'))['fx3_blocks']
    actual={}
    for module in ('nam_install.py','tone3000_routes.py'):
        path='devices/axefx3/'+module
        actual.update({(path,*key):block for key,block in _except_exception_blocks(ast.parse((root/path).read_text(encoding='utf8'))).items()})
    listed={(e['file'],e['function'],e['ordinal']):e['disposition'] for e in entries}
    assert set(actual)==set(listed)
    assert all(len(reason)>50 for reason in listed.values())

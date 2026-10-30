"""Experimental pipeline acceptance on an independent memory device, never MIDI."""
from copy import deepcopy
from dataclasses import replace
import threading
import time
import hashlib
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import mido
import pytest

from devices.axefx3 import mk1_trial as t, protocol, row_fixture
from devices.axefx3 import amp_inventory, fw33_profile, firmware_identity
from fm9 import protocol as p
from tools import mk1_ai_trial as ui

HEADERS = {'X-ToneCommand': '1'}
SAMPLE = dict(name='AI Pink Floyd', summary='A spacious album-inspired lead, not a measured match.',
    amp='Hipower Brilliant', cab='Greenback', gain=3.5, bass=4., mid=6., treble=5.,
    master=5., presence=4., depth=2., chorus=True, chorus_rate=.4, chorus_depth=30.,
    chorus_mix=15., delay=True, delay_ms=440., delay_feedback=25., delay_mix=24.,
    reverb=True, reverb_seconds=1.8, reverb_mix=12.)


@pytest.fixture(autouse=True)
def immediate_memory_device(monkeypatch):
    # Only these fake-state tests. Production readback settle intervals remain.
    monkeypatch.setattr(t.time, 'sleep', lambda _: None)


class MemoryDevice(t.Device):
    """Decode actual transmitted frames, independent of Execution.matches()."""
    def __init__(self):
        self._lock = threading.RLock()
        self.uncertain = False
        self.outp = t.Output(SimpleNamespace(send=self.transmit, close=lambda: None))
        self.preset, self.scene = (99, '<EMPTY>'), 1
        self.names = [(i, '') for i in range(1, 9)]
        self.cells, self.blocks, self.words, self.display = {}, {}, {}, {}
        self.modifiers = {i: [0]*25 for i in range(3, 35)}
        self.cursor = None
        self.serialized = []
        self.closed = False
        self.fault = ''

    def identity(self):
        if self.uncertain or self.fault == 'identity':
            raise PermissionError('Identity mismatch')
        return t.FINGERPRINT

    def current_preset(self): return self.preset
    def current_scene(self): return self.scene
    def scene_name(self, scene): return self.names[scene-1]
    def status_dump(self): return list(self.blocks.values())
    def read_grid(self):
        return [p.GridCell(row-1, col-1, eid, shunt, mask)
                for (row, col), (eid, shunt, mask) in self.cells.items()]
    def bulk_read(self, eid, timeout=1.5): return deepcopy(self.modifiers.get(eid, self.words.get(eid)))
    def read_display_text(self, eid, pid): return self.display.get((eid, pid))
    def close(self): self.closed = True

    def transmit(self, message):
        assert type(message) is mido.Message
        wire = message.bytes()
        self.serialized.append(wire)
        if self.fault == 'transport':
            raise OSError('Port may have sent it')
        fn, data = wire[5], wire[6:-2]
        if fn == 0x0a:
            eid = p.decode14(*data[:2])
            self.blocks[eid] = replace(self.blocks[eid], bypassed=bool(data[2]))
        elif data[:2] == [0x30, 0]:
            position = sum(v << (7*i) for i, v in enumerate(data[6:11]))
            self.cursor = (position % 6 + 1, position // 6 + 1)
        elif data[:2] == [0x32, 0]:
            eid = p.decode14(*data[2:4])
            self.cells[self.cursor] = (eid, False, 0)
            self.blocks[eid] = p.BlockStatus(eid, False, 0, 1 if eid == 37 else 4)
            self.words[eid] = [0] * (4*t.STRIDES.get(eid, 20))
            if self.fault == 'tempo' and eid == 70:
                self.words[eid][9] = 14
        elif data[:2] == [0x35, 0]:
            col = next(c for c in range(1, 7) if wire == row_fixture.connect(1, c))
            eid, shunt, _ = self.cells[1, col+1]
            self.cells[1, col+1] = (eid, shunt, 2)
        elif data[:2] in ([0x28, 0], [0x2b, 0]):
            name = p.unpack_chunked(wire[21:-2], 32).decode('ascii').strip()
            if data[0] == 0x28:
                self.preset = (99, name)
            else:
                self.names[0] = (1, name)
        elif data[:2] == [9, 0]:
            eid, pid = p.decode14(*data[2:4]), p.decode14(*data[4:6])
            value = p.decode_f32_septets(data[6:11])
            if (pid == 0 and eid in (58, 78, 70, 66)) or (eid == 62 and pid in (0, 4)):
                self.words[eid][pid] = int(value)
                if self.fault == 'spill' and eid == 58:
                    self.words[58][142] = 77
            else:
                if eid == 58:
                    shown, lo, hi, suffix = (value*10, 0, 10, '') if pid != 21 else (value, -80, 20, ' dB')
                elif eid == 42:
                    shown, lo, hi, suffix = value, -80, 20, ' dB'
                elif eid == 62 and pid >= 24:
                    self.words[eid][pid] = int(value)
                    self.display[eid, pid] = '--' if value == 0 else 'MUTE'
                    return
                elif eid == 62:
                    shown, lo, hi, suffix = value, -40, 0, ' dB'
                elif eid == 78:
                    spec = {2: (value, .1, 10, ' Hz'), 4: (value*100, 0, 100, '%'),
                            10: (value*100, 0, 100, '%'), 11: (value, -80, 20, ' dB')}
                    shown, lo, hi, suffix = spec[pid]
                elif eid == 70:
                    spec = {2: (value*1000, 1, 16000, ' ms'), 4: (value*100, -100, 100, '%'),
                            17: (value*100, 0, 100, '%'), 18: (value, -80, 20, ' dB')}
                    shown, lo, hi, suffix = spec[pid]
                else:
                    spec = {1: (value, .1, 100, ' s'), 13: (value*100, 0, 100, '%'), 14: (value, -80, 20, ' dB')}
                    shown, lo, hi, suffix = spec[pid]
                kind = 'log10' if eid == 78 and pid == 2 else 'linear'
                self.words[eid][pid] = round(p.display_to_normalized(shown, lo, hi, kind)*65534)
                self.display[eid, pid] = str(round(shown, 5))+suffix
        else:
            pytest.fail('Unexpected frame reached the fake port')


def execution(dev=None, design=None):
    dev = dev or MemoryDevice()
    design = design or t.Design.model_validate(SAMPLE)
    return t.Execution(dev, 99, design, dev.observe(99), time.monotonic()+60)


def test_selected_ai_settings_change_the_compiled_preset():
    first = t.Design.model_validate(SAMPLE)
    second = t.Design.model_validate(dict(SAMPLE, amp='Deluxe Verb Normal', gain=1., delay=False))
    assert t.steps(first) != t.steps(second)
    assert any(s.kind == 'model' and s.value == 17 for s in t.steps(first))
    assert any(s.kind == 'model' and s.value == 224 for s in t.steps(second))


def test_complete_shared_catalog_reaches_the_mk1_design_schema():
    catalog=amp_inventory.roster(fw33_profile.KEY)
    assert len(t.AMPS)==336 and t.AMPS=={name:ordinal for ordinal,name in catalog.items()}
    assert set(t.Design.model_json_schema()['properties']['amp']['enum'])==set(t.AMPS)
    assert 'Pink Floyd' not in ui.SYSTEM
    assert '336-model' in ui.SYSTEM and 'not necessarily\na thin sound' in ui.SYSTEM


@pytest.mark.parametrize('name,ordinal',list(t.AMPS.items()))
def test_every_amp_has_an_exact_reviewed_model_frame_and_level_staging(name,ordinal):
    design=t.Design.model_validate(dict(SAMPLE,amp=name))
    sequence=t.steps(design)
    position=next(i for i,s in enumerate(sequence) if s.kind=='model' and s.eid==58)
    step=sequence[position]
    assert step.value==ordinal
    assert list(step.frame)==protocol.param_frame(58,0,ordinal,opcode=9)
    assert p.decode_f32_septets(list(step.frame[12:17]))==ordinal
    assert all(sequence[position+offset].name=='DISTORT_LEVEL' and sequence[position+offset].value==-12
               for offset in (-1,1))
    assert any(s.kind=='bypass' and s.eid==58 and s.value is True for s in sequence[:position])


@pytest.mark.parametrize('ordinal',[0,14,16,144,224,335])
def test_representative_full_builds_independently_decode_the_selected_model(ordinal):
    name=next(name for name,value in t.AMPS.items() if value==ordinal)
    run=execution(design=t.Design.model_validate(dict(SAMPLE,amp=name)))
    assert run.run(muted=True,target_confirmed=True)['verified']
    assert run.dev.words[58][0]==ordinal
    assert not run.dev.uncertain


def test_wrong_model_readback_consumes_build_without_sending_the_remaining_steps():
    class WrongModel(MemoryDevice):
        def transmit(self,message):
            super().transmit(message)
            frame=message.bytes()
            if frame[5:12]==[1,9,0,58,0,0,0]:
                self.words[58][0]=(self.words[58][0]+1)%336
    run=execution(dev=WrongModel())
    with pytest.raises(t.UncertainWrite):run.run(muted=True,target_confirmed=True)
    count=len(run.dev.serialized)
    with pytest.raises(PermissionError):run.run(muted=True,target_confirmed=True)
    assert len(run.dev.serialized)==count<len(run.sequence)


def test_broader_model_catalog_does_not_admit_the_new_mk2_beta5_identity():
    dev=object.__new__(t.Device);dev.uncertain=False
    # A response with the MK2 raw version/date is not the tester's MK1 identity.
    reply=protocol.envelope(8,[97,0,*b'Oct 26 2026 12:42:45'])[1:-1]
    dev._request=lambda *args:tuple(reply)
    assert firmware_identity.identify(reply) is None
    with pytest.raises(PermissionError):dev.identity()


def test_named_artist_request_can_select_a_non_floyd_amp_without_host_substitution(monkeypatch):
    monkeypatch.setattr(ui.planner,'_env',lambda key:'codex')
    monkeypatch.setattr(ui.planner,'candidates',lambda:['codex'])
    chosen=next(name for name in t.AMPS if name.startswith('Plexi'))
    def plan(prompt,state,reference,**kwargs):
        facts=json.loads(reference)
        assert len(facts['amps'])==336 and chosen in facts['amps']
        assert facts['amp_catalog_count']==336 and 'experimental' in facts['model_acceptance']
        assert 'Pink Floyd' not in kwargs['system']
        return kwargs['validate']({'question':None,'design':dict(SAMPLE,amp=chosen,name='AI Album Lead')})
    monkeypatch.setattr(ui.planner,'plan',plan)
    result=ui.ask('Ritchie Blackmore, Made in Japan, one expressive lead scene',{'preset':(99,'Test')})
    assert result['design']['amp']==chosen


@pytest.mark.parametrize('field,value', [('gain', 9), ('gain', True), ('amp', 'invented'),
    ('cab', 'User2'), ('delay_feedback', 95), ('delay_ms', 10000), ('chorus', 'true')])
def test_out_of_scope_ai_values_are_rejected(field, value):
    with pytest.raises(ValueError): t.Design.model_validate(dict(SAMPLE, **{field: value}))


def test_complete_request_recipe_writes_only_reviewed_chain_and_reads_back():
    run = execution()
    result = run.run(muted=True, target_confirmed=True)
    assert result['verified'] and not result['stored']
    assert result['actions'] == len(run.sequence)
    assert run.dev.cells == {(1, i): (eid, False, 0 if i == 1 else 2)
                            for i, eid in enumerate((37, 58, 62, 78, 70, 66, 42), 1)}
    assert run.dev.preset == (99, SAMPLE['name'])
    assert run.dev.scene == 1 and run.dev.names[1:] == [(i, '') for i in range(2, 9)]
    assert all(not run.dev.blocks[eid].bypassed for eid in (58, 62, 78, 70, 66, 42))
    with pytest.raises(PermissionError): run.run(muted=True, target_confirmed=True)


@pytest.mark.parametrize('fault', ['transport', 'spill', 'tempo'])
def test_uncertain_write_stops_without_retry_or_restore(fault):
    run = execution()
    run.dev.fault = fault
    with pytest.raises(t.UncertainWrite): run.run(muted=True, target_confirmed=True)
    count = len(run.dev.serialized)
    assert run.failed and run.dev.uncertain
    with pytest.raises(PermissionError): run.run(muted=True, target_confirmed=True)
    assert len(run.dev.serialized) == count
    assert all(f[5] in (1, 0x0a) for f in run.dev.serialized)


def test_expiry_changed_target_and_missing_confirmation_never_send():
    for mode in ('expired', 'target', 'consent'):
        run = execution()
        if mode == 'expired': run.expires = 0
        if mode == 'target': run.dev.preset = (100, 'Other')
        with pytest.raises((ValueError, PermissionError)):
            run.run(muted=mode != 'consent', target_confirmed=True)
        assert not run.dev.serialized


def test_output_refuses_store_nam_direct_writes_and_serialization_tricks():
    dev = MemoryDevice()
    for frame in (protocol.envelope(3, []), protocol.param_frame(206, 0, 1, opcode=9),
                  list(t.steps(t.Design.model_validate(SAMPLE))[0].frame)):
        with pytest.raises(PermissionError): dev._send(frame)
    assert not dev.serialized
    class BadMessage(mido.Message):
        def bytes(self): return [0xc0, 3]
    received = []
    output = t.Output(SimpleNamespace(send=lambda msg: received.append(msg)))
    read = protocol.envelope(8, [])
    output.send(BadMessage('sysex', data=read[1:-1]))
    assert type(received[0]) is mido.Message and received[0].bytes() == read


def test_question_and_real_selected_planner_seam(monkeypatch):
    monkeypatch.setattr(ui.planner, '_env', lambda key: 'codex')
    monkeypatch.setattr(ui.planner, 'candidates', lambda: ['codex'])
    calls = []
    def ask(prompt, state, reference, **kwargs):
        calls.append(prompt)
        return kwargs['validate']({'question': None, 'design': SAMPLE})
    monkeypatch.setattr(ui.planner, 'plan', ask)
    result = ui.ask('Pink Floyd Animals, one lead scene', {'preset': (99, 'private')})
    assert result['design']['amp'] == 'Hipower Brilliant'
    assert calls == ['Pink Floyd Animals, one lead scene']


def test_http_request_review_consent_send_and_replay(monkeypatch):
    dev = MemoryDevice()
    app = ui.create_app(factory=lambda: dev,
        ask_ai=lambda prompt, baseline: {'design': SAMPLE, 'backend': 'codex', 'model': 'fake'})
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        assert client.post('/api/connect', json={}).status_code == 403
        assert client.post('/api/connect', json={}, headers=HEADERS).status_code == 200
        response = client.post('/api/plan', json={'prompt': 'Pink Floyd lead', 'expected_preset': 99}, headers=HEADERS)
        assert response.status_code == 200 and not response.json()['sent']
        assert not dev.serialized
        payload = dict(token=response.json()['token'], expected_preset=99,
            target_confirmed=True, external_audio_muted=True, experimental_mk1_consent=True)
        result = client.post('/api/send', json=payload, headers=HEADERS)
        assert result.status_code == 200 and result.json()['verified']
        count = len(dev.serialized)
        assert client.post('/api/send', json=payload, headers=HEADERS).status_code == 409
        assert len(dev.serialized) == count
        report = client.get('/api/report').json()
        assert report['attempts'][0]['verified']
        assert 'private' not in str(report) and not report['mk1_production_write_release']
        assert client.post('/api/axefx3/tone3000/install', json={}, headers=HEADERS).status_code == 404
        assert client.post('/api/disconnect', json={}, headers=HEADERS).status_code == 200 and dev.closed


def test_http_clarification_has_no_token_or_write():
    dev = MemoryDevice()
    app = ui.create_app(factory=lambda: dev,
        ask_ai=lambda prompt, baseline: {'clarification': 'This trial has no fuzz. Continue with AMP/CAB and ambience?'})
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        client.post('/api/connect', json={}, headers=HEADERS)
        result = client.post('/api/plan', json={'prompt': 'Fuzz solo', 'expected_preset': 99}, headers=HEADERS).json()
        assert result['question'] and 'token' not in result and not dev.serialized


def test_unknown_firmware_never_becomes_a_write_profile():
    dev = object.__new__(t.Device)
    dev.uncertain = False
    dev._request = lambda *a: tuple(protocol.envelope(8, [97, 0])[1:-1])
    with pytest.raises(PermissionError, match='fingerprint'):
        dev.identity()


def test_readback_failure_and_out_of_order_frame_never_retry(monkeypatch):
    run = execution()
    wrong = list(run.sequence[-1].frame)
    run.active = True
    run.dev.outp.permit = (threading.get_ident(), tuple(wrong))
    with pytest.raises(PermissionError): run.dev._send(wrong)
    assert not run.dev.serialized
    run.active = False
    run.dev.read_display_text = lambda *a: None
    with pytest.raises(t.UncertainWrite): run.run(muted=True, target_confirmed=True)
    assert len(run.dev.serialized) == 3  # Cursor, Output insert, single level SET.


def test_package_integrity_is_required_without_changing_old_kit(tmp_path):
    files = {}
    for name in ('tools/mk1_ai_trial.py', 'devices/axefx3/mk1_trial.py',
                 'packaging/mk1-ai/index.html', 'packaging/mk1-ai/trial.js'):
        path = tmp_path/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('approved', encoding='utf-8')
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(version=ui.VERSION, experimental=True, source_commit='1'*40, files=files)
    (tmp_path/'MK1-AI-PACKAGE.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert ui.verify_package(tmp_path) == '1'*40
    path.write_text('modified', encoding='utf-8')
    with pytest.raises(ValueError): ui.verify_package(tmp_path)


def test_api_refuses_missing_consent_and_erases_review():
    dev = MemoryDevice()
    app = ui.create_app(factory=lambda: dev, ask_ai=lambda *a: {'design': SAMPLE})
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        client.post('/api/connect', json={}, headers=HEADERS)
        token = client.post('/api/plan', json={'prompt': 'Pink Floyd lead', 'expected_preset': 99}, headers=HEADERS).json()['token']
        payload = dict(token=token, expected_preset=99, target_confirmed=True,
                       external_audio_muted=True, experimental_mk1_consent=False)
        assert client.post('/api/send', json=payload, headers=HEADERS).status_code == 409
        payload['experimental_mk1_consent'] = True
        assert client.post('/api/send', json=payload, headers=HEADERS).status_code == 409
        assert not dev.serialized


def test_api_key_validation_error_does_not_echo_secret():
    app = ui.create_app(factory=MemoryDevice)
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        result = client.post('/api/settings', json={'backend': 'invalid', 'apiKey': 'DO-NOT-ECHO'}, headers=HEADERS)
        assert result.status_code == 422 and 'DO-NOT-ECHO' not in result.text

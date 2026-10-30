"""Independent developer loop and drift refusal. No physical MIDI or AI calls."""
import json
import subprocess
import time

from fastapi.testclient import TestClient
import pytest

from tools import mk1_development as dev, mk1_ai_trial as ui
from devices.axefx3 import mk1_trial as t
from test_mk1_ai_trial import MemoryDevice, SAMPLE, HEADERS


@pytest.fixture
def checkout(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path/'.gitignore').write_text('kb/\nbackups/\ntest-results/\n.venv/\n', encoding='utf-8')
    (tmp_path/'example.py').write_text('print("first")\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, check=True)
    subprocess.run(['git', '-c', 'user.name=Local test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'Fixture'], cwd=tmp_path, check=True)
    return tmp_path


def test_clean_and_edited_checkout_are_self_identified(checkout):
    clean = dev.SourcePin.capture(checkout)
    assert not clean.info['source_dirty'] and len(clean.info['source_commit']) == 40
    assert clean.info['development'] and not clean.info['validated_release']
    clean.verify()
    (checkout/'example.py').write_text('print("edited")\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Source changed'): clean.verify()
    edited = dev.SourcePin.capture(checkout)
    assert edited.info['source_dirty'] and edited.info['source_digest'] != clean.info['source_digest']
    edited.verify()  # Local edits are explicitly allowed at a fresh developer startup.
    assert str(checkout) not in json.dumps(edited.info)


@pytest.mark.parametrize('change', ['new', 'delete', 'branch', 'head'])
def test_membership_branch_and_head_changes_invalidate_pin(checkout, change):
    pin = dev.SourcePin.capture(checkout)
    if change == 'new': (checkout/'new.py').write_text('new', encoding='utf-8')
    if change == 'delete': (checkout/'example.py').unlink()
    if change == 'branch': subprocess.run(['git', 'switch', '-qc', 'other'], cwd=checkout, check=True)
    if change == 'head':
        subprocess.run(['git', '-c', 'user.name=Local test', '-c', 'user.email=test@example.invalid',
                        'commit', '--allow-empty', '-qm', 'Next'], cwd=checkout, check=True)
    with pytest.raises(ValueError, match='Source changed'): pin.verify()


def test_private_runtime_state_does_not_drift_or_leak(checkout):
    pin = dev.SourcePin.capture(checkout)
    (checkout/'test-results').mkdir()
    (checkout/'test-results/secret.json').write_text('private account data', encoding='utf-8')
    pin.verify()
    assert 'private account data' not in json.dumps(pin.info)


def test_zip_or_nested_folder_is_not_a_developer_clone(checkout):
    (checkout/'nested').mkdir()
    with pytest.raises(ValueError, match='root'): dev.SourcePin.capture(checkout/'nested')
    with pytest.raises(ValueError, match='Git source'): dev.SourcePin.capture(checkout.parent)


def test_unstable_startup_snapshot_is_refused(checkout, monkeypatch):
    original = dev.identify
    count = 0
    def changing(root):
        nonlocal count
        result = original(root)
        count += 1
        if count == 1: (checkout/'example.py').write_text('changed', encoding='utf-8')
        return result
    monkeypatch.setattr(dev, 'identify', changing)
    with pytest.raises(ValueError, match='during startup'): dev.SourcePin.capture(checkout)


def test_source_symlink_is_refused_without_reading_target(checkout):
    try:
        (checkout/'linked.py').symlink_to(checkout/'example.py')
    except OSError:
        pytest.skip('Host does not grant symlink creation')
    with pytest.raises(ValueError, match='symlinks'): dev.SourcePin.capture(checkout)


def test_http_developer_source_survives_report_and_guards_send(checkout, monkeypatch):
    monkeypatch.setattr(t.time, 'sleep', lambda _: None)
    pin = dev.SourcePin.capture(checkout)
    memory = MemoryDevice()
    app = ui.create_app(factory=lambda: memory, ask_ai=lambda *a: {'design': SAMPLE},
                        source_info=pin.info, check_source=pin.verify)
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        assert client.get('/api/state').json()['source_digest'] == pin.info['source_digest']
        assert client.post('/api/connect', json={}, headers=HEADERS).status_code == 200
        plan = client.post('/api/plan', json={'prompt': 'Floyd lead', 'expected_preset': 99}, headers=HEADERS).json()
        assert plan['source'] == pin.info
        body = dict(token=plan['token'], expected_preset=99, target_confirmed=True,
                    external_audio_muted=True, experimental_mk1_consent=True)
        (checkout/'example.py').write_text('modified after plan', encoding='utf-8')
        reply = client.post('/api/send', json=body, headers=HEADERS)
        assert reply.status_code == 409 and 'Source changed' in reply.json()['detail']
        # Even restoring files cannot revive a consumed review.
        (checkout/'example.py').write_text('print("first")\n', encoding='utf-8')
        assert client.post('/api/send', json=body, headers=HEADERS).status_code == 409
        assert not memory.serialized
        assert client.get('/api/report').json()['source_digest'] == pin.info['source_digest']
        assert client.post('/api/disconnect', json={}, headers=HEADERS).status_code == 200


def test_source_changed_during_ai_never_yields_review(checkout):
    pin = dev.SourcePin.capture(checkout)
    memory = MemoryDevice()
    def ai(*a):
        (checkout/'new.py').write_text('edited during AI', encoding='utf-8')
        return {'design': SAMPLE}
    app = ui.create_app(factory=lambda: memory, ask_ai=ai, source_info=pin.info, check_source=pin.verify)
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        client.post('/api/connect', json={}, headers=HEADERS)
        reply = client.post('/api/plan', json={'prompt': 'Floyd lead', 'expected_preset': 99}, headers=HEADERS)
        assert reply.status_code == 409 and app.state.trial['review'] is None
        assert not memory.serialized


def test_source_drift_during_send_stops_before_next_frame(checkout, monkeypatch):
    monkeypatch.setattr(t.time, 'sleep', lambda _: None)
    pin = dev.SourcePin.capture(checkout)
    memory = MemoryDevice()
    run = t.Execution(memory, 99, t.Design.model_validate(SAMPLE), memory.observe(99), time.monotonic()+60)
    def verify():
        if memory.serialized:
            (checkout/'example.py').write_text('changed after first frame', encoding='utf-8')
        pin.verify()
    with pytest.raises(t.UncertainWrite):
        run.run(muted=True, target_confirmed=True, check_source=verify)
    assert len(memory.serialized) == 1 and memory.uncertain and run.failed
    with pytest.raises(PermissionError):
        run.run(muted=True, target_confirmed=True, check_source=verify)
    assert len(memory.serialized) == 1


def test_source_drift_before_connect_never_opens_ports(checkout):
    pin = dev.SourcePin.capture(checkout)
    opened = []
    app = ui.create_app(factory=lambda: opened.append(True), source_info=pin.info, check_source=pin.verify)
    (checkout/'example.py').write_text('changed', encoding='utf-8')
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        assert client.post('/api/connect', json={}, headers=HEADERS).status_code == 409
    assert not opened


def test_release_launcher_still_requires_its_package_manifest(tmp_path):
    with pytest.raises(OSError): ui.verify_package(tmp_path)
    assert 'verify_package()' in (dev.ROOT/'tools/mk1_ai_trial.py').read_text(encoding='utf-8')
    workspace = json.loads((dev.ROOT/'MK1-Development.code-workspace').read_text(encoding='utf-8'))
    assert workspace['launch']['configurations'][0]['module'] == 'tools.mk1_development'


def test_developer_app_does_not_need_or_trust_a_zip_manifest(checkout, monkeypatch):
    monkeypatch.setattr(ui, 'ROOT', checkout)
    # A leftover ZIP manifest is irrelevant to this explicit developer mode.
    (checkout/'MK1-AI-PACKAGE.json').write_text('invalid JSON', encoding='utf-8')
    pin = dev.SourcePin.capture(checkout)
    app = ui.create_app(source_info=pin.info, check_source=pin.verify)
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        assert client.get('/api/state').json()['source_commit'] == pin.info['source_commit']
        assert client.get('/api/report').json()['development']


def test_pinned_development_http_send_still_works_without_physical_midi(checkout, monkeypatch):
    monkeypatch.setattr(t.time, 'sleep', lambda _: None)
    pin = dev.SourcePin.capture(checkout)
    memory = MemoryDevice()
    app = ui.create_app(factory=lambda: memory, ask_ai=lambda *a: {'design': SAMPLE},
                        source_info=pin.info, check_source=pin.verify)
    with TestClient(app, base_url='http://127.0.0.1:8909') as client:
        assert client.post('/api/connect', json={}, headers=HEADERS).status_code == 200
        plan = client.post('/api/plan', json={'prompt': 'Floyd lead', 'expected_preset': 99}, headers=HEADERS).json()
        result = client.post('/api/send', headers=HEADERS, json=dict(token=plan['token'], expected_preset=99,
            target_confirmed=True, external_audio_muted=True, experimental_mk1_consent=True))
        assert result.status_code == 200 and result.json()['verified']
        report = client.get('/api/report').json()
        assert report['attempts'][0]['verified'] and not report['attempts'][0]['stored']
        assert report['source_digest'] == plan['source']['source_digest']

"""Upstream read-only and the guarded workspace never share write authority."""
from types import SimpleNamespace
import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3.readonly_adapter import AxeFxIII, is_readonly_device
from devices.axefx3.registry import Registry
from tests.test_axefx3_readonly import FakePorts


def test_merged_device_catalog_has_no_duplicate_keys():
    tree = ast.parse((Path(__file__).parents[1] / 'server.py').read_text(encoding='utf-8'))
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'DEVICE_KINDS' for t in node.targets))
    keys = [ast.literal_eval(key) for key in assignment.value.keys]
    assert len(keys) == len(set(keys))
    assert server.DEVICE_KINDS['axefx3'] == 'Fractal Axe-Fx III'


@pytest.fixture
def boundary(monkeypatch):
    ports = FakePorts()
    readonly = AxeFxIII((ports.inp, ports.outp))
    monkeypatch.setattr(server, '_context', server.DeviceContext(
        'axefx3', Registry(), readonly, 'Fractal Axe-Fx III'))
    monkeypatch.setattr(server, '_selected_kind', {'kind': 'axefx3'})
    monkeypatch.setattr(server, '_gig_mode', {'on': False})
    monkeypatch.setattr(server, '_plan_revisions', {})
    monkeypatch.setattr(server, '_audition', {'open': False})
    monkeypatch.setattr(server, 'detected_devices', lambda: [{'kind': 'axefx3'}])
    server._controller_reviews.clear()
    with TestClient(server.app) as client:
        yield client, readonly, ports
    readonly.close()
    server._controller_reviews.clear()


def test_readonly_selection_keeps_the_shared_ui_and_declines_workspace_writes(boundary):
    client, readonly, ports = boundary
    before = list(ports.sent)
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 200 and 'Unofficial FX3' in response.text
    assert client.get('/api/device').json()['axefx3']['read_only'] is True
    assert client.get('/api/controllers/state').json()['connected'] is False
    assert client.get('/api/axefx3/state').status_code == 409
    assert client.post('/api/axefx3/store/prepare', json={'expected_preset': 323}).status_code == 409
    assert client.post('/api/controllers/review', json={
        'effect_id': 95, 'source': 12}).status_code == 409
    assert ports.sent == before
    assert is_readonly_device(readonly)


@pytest.mark.parametrize('path', ['/axefx3', '/controllers'])
def test_workspace_script_failure_keeps_version_and_report_available(boundary, monkeypatch, path):
    from fm9 import updates
    client, _, ports = boundary
    monkeypatch.setattr(updates, 'current_version', lambda: '1.6.2')
    before = list(ports.sent)
    response = client.get(path)
    assert response.status_code == 200
    assert 'data-server-version>v1.6.2</span>' in response.text
    assert 'id="bootfail"' in response.text and 'href="/report"' in response.text
    assert response.headers['cache-control'] == 'no-cache'
    assert ports.sent == before


def test_explicit_workspace_connect_closes_readonly_before_opening_replacement(boundary, monkeypatch):
    client, readonly, ports = boundary
    events = []
    close = readonly.close

    def close_old():
        events.append('close')
        close()

    monkeypatch.setattr(readonly, 'close', close_old)
    workspace = SimpleNamespace(reg=Registry(), close=lambda: events.append('workspace-close'))

    def open_workspace():
        assert readonly._closed and events == ['close']
        events.append('open')
        return workspace

    monkeypatch.setattr(server._controller_reviews, 'connect_device', open_workspace)
    before = list(ports.sent)
    assert client.post('/api/controllers/connect').status_code == 200
    assert events == ['close', 'open']
    assert server.device_context().adapter is workspace
    assert client.get('/', follow_redirects=False).headers['location'] == '/axefx3'
    assert client.get('/api/state').status_code == 409
    assert client.get('/api/device').json()['axefx3'] == {
        'read_only': False, 'workspace': '/axefx3'}
    assert client.post('/api/device/select', json={'kind': 'axefx3', 'chassis': 'mk2'}).status_code == 409
    assert ports.sent == before


def test_failed_workspace_handoff_never_reopens_or_reuses_the_closed_handle(boundary, monkeypatch):
    client, readonly, ports = boundary
    attempts = []

    def occupied():
        assert readonly._closed
        attempts.append('open')
        raise OSError('port occupied')

    monkeypatch.setattr(server._controller_reviews, 'connect_device', occupied)
    before = list(ports.sent)
    response = client.post('/api/controllers/connect')
    assert response.status_code == 503 and attempts == ['open']
    assert server.device_context().adapter is None
    assert client.get('/api/state').status_code == 409
    assert client.get('/report').status_code == 200
    assert ports.sent == before


def test_scriptless_report_identifies_fork_and_never_queries_workspace(boundary, monkeypatch):
    client, _, ports = boundary
    adapter = SimpleNamespace(firmware_label=lambda: pytest.fail('Unexpected MIDI read'))
    monkeypatch.setattr(server, '_context', server.DeviceContext(
        'axefx3', Registry(), adapter, 'Fractal Axe-Fx III'))
    before = list(ports.sent)
    response = client.get('/report')
    assert response.status_code == 200 and 'UNOFFICIAL FX3' in response.text
    assert '<script' not in response.text
    assert 'github.com/Axelman8/ToneCommand/issues/new' in response.text
    assert ports.sent == before

"""Shared local-only and Gig Lock controls also cover the full FX3 workspace."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3.readonly_adapter import ReadOnlyRegistry


@pytest.fixture
def workspace(monkeypatch):
    monkeypatch.setattr(server, '_context',
        server.DeviceContext('axefx3', ReadOnlyRegistry(), object(), 'Axe-Fx III'))
    monkeypatch.setattr(server, '_gig_mode', {'on': False})
    monkeypatch.setattr(server, '_plan_revisions', {})
    monkeypatch.setattr(server, '_audition', {'open': False})
    def forbidden(*a, **k):
        pytest.fail('No hardware or AI is permitted in workspace boundary tests')
    monkeypatch.setattr('fm9.midi_transport.open_ports', forbidden)
    monkeypatch.setattr(server, 'get_fm9', forbidden)
    monkeypatch.setattr(server.planner, 'plan', forbidden)
    client = TestClient(server.app, base_url='http://127.0.0.1:8909')
    try:
        yield client
    finally:
        client.close()


@pytest.mark.parametrize('path', ['/', '/api/gig', '/api/apply', '/api/axefx3/send'])
def test_foreign_host_refuses_before_full_workspace_redirect_or_gate(workspace, path):
    response = workspace.get(path, headers={'host':'attacker.example'}, follow_redirects=False)
    assert response.status_code == 403
    assert 'answers only' in response.json()['error']


@pytest.mark.parametrize('path', ['/api/axefx3/send', '/api/controllers/send',
    '/api/axefx3/edit/send', '/api/axefx3/store'])
def test_foreign_origin_refuses_before_body_validation(workspace, path):
    assert workspace.post(path, json={}, headers={'origin':'https://attacker.example'}).status_code == 403
    # A real local request reaches typed validation, not a device operation.
    assert workspace.post(path, json={}, headers={'origin':'http://127.0.0.1:8909'}).status_code == 422


def test_gig_lock_waits_for_inflight_fx3_controller_send(workspace, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls, results = [], {}
    def send(*a, **k):
        calls.append(True)
        entered.set()
        assert release.wait(5), 'Test release missing'
        return {'verified':True, 'stored':False}
    monkeypatch.setattr(server._controller_reviews, 'send', send)
    body = dict(token='test-token', external_audio_muted=True, target_confirmed=True)
    sending = threading.Thread(target=lambda:results.update(send=workspace.post('/api/controllers/send',json=body)))
    locking = threading.Thread(target=lambda:results.update(gig=workspace.post('/api/gig',json={'on':True})))
    try:
        sending.start()
        assert entered.wait(3)
        locking.start()
        deadline = time.monotonic()+3
        while not server._gig_mode['on'] and time.monotonic()<deadline:
            time.sleep(.005)
        assert server._gig_mode['on'] and locking.is_alive()
    finally:
        release.set()
        sending.join(5)
        if locking.ident is not None:
            locking.join(5)
    assert not sending.is_alive() and not locking.is_alive()
    assert results['send'].status_code == 200
    assert results['gig'].json() == {'gig_mode':True, 'settled':True}
    assert workspace.post('/api/controllers/send',json=body).status_code == 423
    assert calls == [True]

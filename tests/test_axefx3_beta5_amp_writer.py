"""Explicit Beta5 scope and registered stages; independent fake wire only."""
import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3 import edit_routes
from devices.axefx3.amp_writer import AmpEdit, AmpWriter
from devices.axefx3.beta5_amp_writer import Beta5AmpWriter
from devices.axefx3.name_writer import MK2_FW33_IDENTITY
from devices.axefx3.readonly_adapter import ReadOnlyRegistry
from fm9.device import ReadOnly
from tests.test_axefx3_amp_writer import AmpPorts
from tests.test_axefx3_edit_routes import payload
from tests.test_axefx3_firmware_identity import BETA5


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv('TONECOMMAND_AXEFX3_REVIEWED_AMP', raising=False)
    monkeypatch.delenv('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5', raising=False)
    monkeypatch.setattr('fm9.midi_transport.open_ports',
                        lambda *a, **k: pytest.fail('Physical ports forbidden'))
    monkeypatch.setattr('devices.axefx3.amp_writer.time.sleep', lambda _: None)


@pytest.fixture
def native_shape(monkeypatch):
    ports = AmpPorts()
    ports.identity, ports.amp[0] = BETA5, 0
    dev = Beta5AmpWriter((ports.inp, ports.outp))
    monkeypatch.setattr(server, '_context',
        server.DeviceContext('axefx3', ReadOnlyRegistry(), dev, 'Axe-Fx III'))
    monkeypatch.setattr(server, '_gig_mode', {'on': False})
    monkeypatch.setattr(server, '_plan_revisions', {})
    monkeypatch.setattr(server.planner, 'plan', lambda *a, **k: pytest.fail('No AI'))
    server._afx3_edit_workflow.discard()
    client = TestClient(server.app)
    yield client, dev, ports
    client.close()
    server._afx3_edit_workflow.discard()
    dev.close()


def proposal():
    return dict(actions=[dict(kind='set_param', block='amp',
        param='DISTORT_DRIVE', value=3.3)], expected_preset=320, expected_scene=1)


def arm(client):
    view = client.post('/api/axefx3/edit/prepare', json=proposal())
    assert view.status_code == 200, view.text
    view = client.post('/api/axefx3/edit/review', json=payload(view.json()))
    assert view.status_code == 200, view.text
    view = client.post('/api/axefx3/edit/confirm', json=payload(view.json(), True))
    assert view.status_code == 200, view.text
    return view.json()


def test_beta5_requires_its_own_explicit_selection(native_shape, monkeypatch):
    client, dev, ports = native_shape
    assert not client.get('/api/axefx3/edit/state').json()['configured']
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP', '1')
    assert client.post('/api/axefx3/edit/prepare', json=proposal()).status_code == 409
    monkeypatch.delenv('TONECOMMAND_AXEFX3_REVIEWED_AMP')
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5', '1')
    view = arm(client)
    assert not ports.writes
    response = client.post('/api/axefx3/edit/send', json=payload(view, True))
    assert response.status_code == 200 and response.json()['verified']
    assert len(ports.writes) == 1 and not dev.capabilities().verifies_writes
    assert client.post('/api/axefx3/edit/send', json=payload(view, True)).status_code == 409
    assert len(ports.writes) == 1


@pytest.mark.parametrize('fault', ['ignore', 'raise', 'other_channel', 'modifier', 'identity'])
def test_uncertain_beta5_result_has_no_retry(native_shape, monkeypatch, fault):
    client, dev, ports = native_shape
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5', '1')
    view = arm(client)
    ports.behavior = fault
    response = client.post('/api/axefx3/edit/send', json=payload(view, True))
    assert response.status_code == 409 and response.json()['uncertain']
    assert not response.json()['retry_allowed'] and dev._uncertain
    assert len(ports.writes) == 1
    assert client.post('/api/axefx3/edit/send', json=payload(view, True)).status_code == 409
    assert len(ports.writes) == 1


@pytest.mark.parametrize('change', ['mode', 'model', 'identity', 'modifier'])
def test_beta5_context_change_consumes_before_output(native_shape, monkeypatch, change):
    client, dev, ports = native_shape
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5', '1')
    view = arm(client)
    if change == 'mode':
        monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP', '1')
    elif change == 'model':
        ports.amp[0] = 14
    elif change == 'identity':
        ports.identity = MK2_FW33_IDENTITY
    else:
        ports.mods[34][9] = 78
    assert client.post('/api/axefx3/edit/send', json=payload(view, True)).status_code == 409
    assert not ports.writes


@pytest.mark.parametrize('writer,identity', [(AmpWriter, BETA5), (Beta5AmpWriter, MK2_FW33_IDENTITY)])
def test_identity_approval_does_not_flow_between_writers(writer, identity):
    ports = AmpPorts()
    ports.identity, ports.amp[0] = identity, 0
    dev = writer((ports.inp, ports.outp))
    try:
        with pytest.raises(ReadOnly):
            dev.review_amp(AmpEdit(320, 'gain', 3.3))
        assert not ports.writes
    finally:
        dev.close()


def test_conflicting_configuration_never_constructs_a_writer(monkeypatch):
    for key in ('TONECOMMAND_AXEFX3_REVIEWED_AMP', 'TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5'):
        monkeypatch.setenv(key, '1')
    assert not edit_routes.enabled()
    with pytest.raises(ReadOnly, match='only one'):
        edit_routes.connect('mk2')


def test_other_model_is_visibly_unavailable(native_shape, monkeypatch):
    client, dev, ports = native_shape
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5', '1')
    ports.amp[0] = 14
    state = client.get('/api/axefx3/edit/state').json()
    assert state['configured'] and not state['available'] and 'Bassguy' in state['reason']
    assert not ports.writes


@pytest.mark.parametrize('chassis', ['mk1', 'turbo'])
def test_new_flag_does_not_enable_other_chassis(monkeypatch, chassis):
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5', '1')
    with pytest.raises(ReadOnly):
        edit_routes.connect(chassis)

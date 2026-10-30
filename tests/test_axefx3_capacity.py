"""Declared read ranges, without a physical unit or any writable capability."""
from types import SimpleNamespace

import mido
import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3 import readonly_protocol as p
from devices.axefx3.readonly_adapter import AxeFxIII, ReadOnlyOutput, ReadOnlyRegistry, SlotName
from fm9 import protocol as shared
from fm9.device import FM9NotFound, ReadOnly
from tests.test_axefx3_readonly import FakePorts


class CapacityPorts(FakePorts):
    def send(self, message):
        frame = [0xF0, *message.data, 0xF7]
        assert p.allowed(frame, 'mk2'), 'The fake received a non-read'
        self.sent.append(frame)
        for data in self.reply(frame):
            self.queue.append(mido.Message('sysex', data=data))


@pytest.mark.parametrize('chassis,count', [('mk1', 512), ('mk2', 1024), ('turbo', 1024)])
def test_only_name_read_range_changes_for_the_declared_chassis(chassis, count):
    for number in range(1025):
        assert p.allowed(p.envelope(0x0D, list(shared.encode14(number))), chassis) == (number < count)
    assert p.allowed(p.envelope(0x0D, [127, 127]), chassis)
    for function, payload in [(0x0C, [0]), (0x0A, [58, 0, 0]), (0x0B, [58, 0, 2]),
                              (0x64, []), (1, [9, 0] + [0] * 13)]:
        assert not p.allowed(p.envelope(function, payload), chassis)
    raw = SimpleNamespace(send=lambda message: pytest.fail('Non-read reached the raw port'))
    with pytest.raises(ReadOnly):
        ReadOnlyOutput(raw, chassis).send(mido.Message('program_change', program=1))


@pytest.mark.parametrize('chassis,count', [('mk1', 512), ('mk2', 1024), ('turbo', 1024)])
def test_full_declared_name_scan_including_upper_boundary(chassis, count):
    ports = CapacityPorts()
    dev = AxeFxIII((ports.inp, ports.outp), chassis=chassis)
    try:
        before = (ports.preset, ports.scene)
        assert [s.number for s in dev.scan_slots()] == list(range(count))
        assert dev.slot_name(count - 1).name == 'Read Test'
        assert dev.slot_name(count - 1).editor == count - 1
        sent = list(ports.sent)
        with pytest.raises(ValueError):
            dev.slot_name(count)
        with pytest.raises(ValueError):
            list(dev.scan_slots(0, count))
        assert ports.sent == sent
        assert (ports.preset, ports.scene) == before
    finally:
        dev.close()


@pytest.mark.parametrize('bad', [None, 'auto', 'MK2', 'mk3', '', 1024, True, [], {}])
def test_invalid_chassis_is_rejected_before_opening_ports(monkeypatch, bad):
    monkeypatch.setattr('fm9.midi_transport.open_ports', lambda *a: pytest.fail('MIDI opened'))
    with pytest.raises(ValueError):
        AxeFxIII(chassis=bad)


def test_default_refuses_upper_current_preset_but_explicit_mk2_can_connect():
    ports = CapacityPorts()
    ports.preset = 1023
    with pytest.raises(FM9NotFound):
        AxeFxIII((ports.inp, ports.outp))
    assert ports.closes == ['in', 'out']
    ports = CapacityPorts()
    ports.preset = 1023
    dev = AxeFxIII((ports.inp, ports.outp), chassis='mk2')
    try:
        assert dev.current_preset() == (1023, 'Read Test')
    finally:
        dev.close()


def test_chassis_change_sends_nothing_and_updates_both_guard_boundaries():
    ports = CapacityPorts()
    dev = AxeFxIII((ports.inp, ports.outp))
    try:
        sent = list(ports.sent)
        dev.set_chassis('mk2')
        assert ports.sent == sent
        assert dev.slot_name(1023).number == 1023
        dev.set_chassis('mk1')
        sent = list(ports.sent)
        upper = p.envelope(0x0D, list(shared.encode14(512)))
        with pytest.raises(ReadOnly):
            dev._send(upper)
        with pytest.raises(ReadOnly):
            dev.outp.send(mido.Message('sysex', data=upper[1:-1]))
        assert ports.sent == sent
        assert not dev.capabilities().stores_presets and not dev.capabilities().can_verify
    finally:
        dev.close()


@pytest.fixture
def client(monkeypatch):
    ports = CapacityPorts()
    dev = AxeFxIII((ports.inp, ports.outp))
    monkeypatch.setattr(server, '_context', server.DeviceContext('axefx3', ReadOnlyRegistry(), dev))
    monkeypatch.setattr(server, '_axefx3_chassis', {'value': 'mk1'})
    monkeypatch.setattr(server, '_selected_kind', {'kind': 'axefx3'})
    monkeypatch.setattr(server, '_gig_mode', {'on': False})
    monkeypatch.setattr(server, '_plan_revisions', {})
    monkeypatch.setattr(server, '_preset_cache', {'slots': None})
    monkeypatch.setattr(server, 'detected_devices', lambda: [{'kind': 'axefx3'}])
    with TestClient(server.app) as http:
        yield http, dev, ports
    dev.close()


def test_existing_device_route_selects_chassis_without_hardware_traffic(client):
    http, dev, ports = client
    before = list(ports.sent)
    result = http.post('/api/device/select', json={'kind': 'axefx3', 'chassis': 'mk2'})
    assert result.status_code == 200
    assert result.json()['axefx3'] == dict(chassis='mk2', preset_count=1024, declared=True, read_only=True)
    assert ports.sent == before
    assert http.get('/api/device').json()['axefx3']['chassis'] == 'mk2'
    assert http.get('/api/state').json()['declared_chassis'] == 'mk2'


@pytest.mark.parametrize('bad', ['auto', 'MK2', None, True, 1024, {}, []])
def test_bad_http_choice_preserves_profile_and_sends_nothing(client, bad):
    http, dev, ports = client
    before = list(ports.sent)
    response = http.post('/api/device/select', json={'kind': 'axefx3', 'chassis': bad})
    assert response.status_code == 400
    assert dev.chassis == 'mk1' and ports.sent == before


def test_gig_lock_and_pending_plan_protect_the_selection(client, monkeypatch):
    http, dev, ports = client
    before = list(ports.sent)
    monkeypatch.setitem(server._gig_mode, 'on', True)
    assert http.post('/api/device/select', json={'kind':'axefx3', 'chassis':'mk2'}).status_code == 423
    monkeypatch.setitem(server._gig_mode, 'on', False)
    monkeypatch.setattr(server, '_plan_revisions', {'pending': object()})
    assert http.post('/api/device/select', json={'kind':'axefx3', 'chassis':'mk2'}).status_code == 409
    assert dev.chassis == 'mk1' and ports.sent == before


def test_full_http_scan_uses_capacity_and_does_not_reuse_other_device_cache(client):
    http, dev, ports = client
    server._preset_cache['slots'] = [{'number': 9999, 'name': 'Other device'}]
    response = http.get('/api/presets')
    assert len(response.json()['slots']) == 512
    assert http.get('/api/presets').json()['cached']
    http.post('/api/device/select', json={'kind': 'axefx3', 'chassis': 'mk2'})
    response = http.get('/api/presets')
    assert len(response.json()['slots']) == 1024
    assert response.json()['slots'][-1]['number'] == 1023
    assert response.json()['slots'][-1]['editor'] == 1023
    assert response.json()['slots'][-1]['label'] == '1023 (wire 1023)'
    http.post('/api/device/select', json={'kind': 'axefx3', 'chassis': 'mk1'})
    response = http.get('/api/presets')
    assert len(response.json()['slots']) == 512
    assert response.json()['slots'][-1]['number'] == 511


def test_stream_reports_1024_and_cache_stays_scoped(client):
    http, dev, ports = client
    http.post('/api/device/select', json={'kind':'axefx3', 'chassis':'turbo'})
    result = http.get('/api/presets/stream').text
    assert '"total": 1024' in result and '"number": 1023' in result
    assert '"editor": 1023' in result and '"label": "1023 (wire 1023)"' in result
    assert server._preset_cache_matches()
    dev.set_chassis('mk1')
    assert not server._preset_cache_matches()


def test_explicit_mk2_can_be_selected_before_connecting_from_another_context(client, monkeypatch):
    http, dev, ports = client
    monkeypatch.setattr(server, '_context', server._default_context)
    monkeypatch.setattr(server, 'drop_fm9', lambda: None)
    def build(kind, *, axefx3_chassis=None):
        assert kind == 'axefx3' and axefx3_chassis == 'mk2'
        dev.set_chassis(axefx3_chassis)
        return server.DeviceContext(kind, ReadOnlyRegistry(), dev)
    monkeypatch.setattr(server, '_build_context', build)
    result = http.post('/api/device/select', json={'kind':'axefx3', 'chassis':'mk2'})
    assert result.status_code == 200 and result.json()['axefx3']['preset_count'] == 1024


def test_failed_connection_preserves_previous_declared_profile(client, monkeypatch):
    http, dev, ports = client
    monkeypatch.setattr(server, '_context', server._default_context)
    def fail(kind, **kwargs):
        raise FM9NotFound('Occupied port')
    monkeypatch.setattr(server, '_build_context', fail)
    assert http.post('/api/device/select', json={'kind':'axefx3', 'chassis':'mk2'}).status_code == 503
    assert server._axefx3_chassis['value'] == 'mk1'
    assert server.device_context() is server._default_context


def test_chassis_field_cannot_be_used_for_another_device(client):
    http, dev, ports = client
    before = list(ports.sent)
    assert http.post('/api/device/select', json={'kind':'fm9', 'chassis':'mk2'}).status_code == 400
    assert ports.sent == before


@pytest.mark.parametrize('number', [0, 323, 511, 512, 1023])
def test_iii_numbering_matches_editor_without_changing_fm9(number):
    assert SlotName(number, 'Name').editor == number
    assert SlotName(number, 'Name').label == f'{number:04d} (wire {number})'
    assert shared.SlotName(number, 'Name').editor == number + 1

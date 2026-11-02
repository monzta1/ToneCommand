"""Independent synthetic port traffic; never physical hardware acceptance."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import mido
import pytest

from devices.axefx3 import protocol as p, live_observation as live
from devices.axefx3.adapter import AxeFxIII, ReadOnlyOutput
from fm9.device import ReadOnly, FM9NotFound
from fm9.safety import BrickGuardRefusal
from tests.axefx3_beta5_identity import BETA5
from tests.test_axefx3_observed_words import burst
from tests.test_axefx3_readonly import FakePorts


def grid_reply(cells):
    """Independent byte/bit fixture builder, not the production grid parser."""
    size = (46 + 14 * 6 * 32 + 6) // 7
    bits = [0] * (size * 7)
    for row, col, eid, shunt, mask in cells:
        for start, value in ((45 + col * 192 + row * 32, eid),
                             (54 + col * 192 + row * 32, 8 if shunt else 0),
                             (62 + col * 192 + row * 32, mask)):
            for n in range(8): bits[start + n] = value >> (7 - n) & 1
    septets = [sum(bits[n + b] << (6 - b) for b in range(7)) for n in range(0, len(bits), 7)]
    return p.envelope(1, [46, 0, *([0] * 342), *septets])[1:-1]


class ObservationPorts(FakePorts):
    def __init__(self):
        super().__init__()
        self.identity = BETA5
        self.preset = 323
        self.cells = [(3, 0, 58, False, 0), (3, 1, 206, False, 16), (5, 13, 0, True, 126)]
        self.words = {200: [65535] * 1525, 201: [65535] * 350,
                      58: [65535, *([7] * 567)], 206: [65535] * 44,
                      **{eid: [0] * 8 + [78, 77] + [65535] * 15 for eid in range(3, 35)}}
        self.transform = lambda wire, packets: packets

    def send(self, message):
        frame = message.bytes()
        assert p.allowed(frame, 'mk2') or live.extra_read(frame)
        self.sent.append(frame)
        for data in self.transform(frame, self.answer(frame)):
            self.queue.append(mido.Message('sysex', data=data))

    def answer(self, frame):
        if frame[5] == 8: return [list(self.identity)]
        if frame[5] == 19:
            return [p.envelope(19, [58, 0, 64, 78, 1, 64, 72, 1, 16, 73, 1, 16])[1:-1]]
        if frame[5] == 31:
            eid = frame[6] | frame[7] << 7
            return burst(eid, tuple(self.words[eid]), chunk=64)
        if tuple(frame) == live.GRID_QUERY: return [grid_reply(self.cells)]
        return super().answer(frame)


@pytest.fixture
def device(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports', lambda *a, **k: pytest.fail('No real MIDI'))
    ports = ObservationPorts()
    dev = live.LiveReader((ports.inp, ports.outp), chassis='mk2')
    yield dev, ports
    dev.close()


def test_repeated_complete_reads_retain_systems_nam_and_custom_modifiers(device):
    dev, ports = device
    result = dev.capture()
    data = result.data()
    assert data['preset'] == [323, 'Read Test'] and data['scene'] == 1
    assert data['identity'] == list(BETA5)
    assert data['bulk']['200'] == [65535] * 1525
    assert data['bulk']['201'] == [65535] * 350
    assert data['bulk']['206'] == [65535] * 44
    assert data['modifiers'][0] == [0] * 8 + [78, 77] + [65535] * 15
    assert data['grid'][1]['effect_id'] == 206 and data['grid'][2]['is_shunt']
    assert len(data['scenes']) == 8
    assert sum(f[5] == 31 for f in ports.sent) == 2 * (4 + 32)
    assert all(p.allowed(f, 'mk2') or live.extra_read(f) for f in ports.sent)


def test_extra_reads_do_not_change_normal_adapter_or_its_capabilities(device):
    dev, ports = device
    caps = dev.capabilities()
    assert not caps.can_verify and not caps.can_rename and not caps.stores_presets
    assert not caps.has_modifiers and not caps.topology
    raw = SimpleNamespace(send=lambda message: pytest.fail('Ordinary gate widened'))
    for frame in (list(live.GRID_QUERY), p.envelope(31, [58, 0])):
        assert not p.allowed(frame, 'mk2')
        with pytest.raises((ReadOnly, BrickGuardRefusal)):
            ReadOnlyOutput(raw, 'mk2').send(mido.Message('sysex', data=frame[1:-1]))
    assert AxeFxIII.bulk_read(dev, 58) is None


@pytest.mark.parametrize('fn,args', [(1, [9, 0, 58, 0, 1, 0, *([0] * 9)]),
    (1, [82, 0, 58, 0, 1, 0, *([0] * 9)]), (1, [48, 0, *([0] * 13)]),
    (1, [50, 0, *([0] * 13)]), (1, [53, 0, *([0] * 13)]),
    (1, [16, 0, 58, 0, 1, 0]), (12, [0]), (10, [58, 0, 0]),
    (11, [58, 0, 1]), (31, [0, 0]), (31, [80, 1]), (31, [58, 0, 0]),
    (100, []), (119, [0]), (125, [])])
def test_mutations_and_unobserved_forms_fail_both_output_paths(device, fn, args):
    dev, ports = device
    frame = p.envelope(fn, args)
    before = deepcopy(ports.sent)
    assert not live.extra_read(frame)
    with pytest.raises((ReadOnly, BrickGuardRefusal)): dev._send(frame)
    with pytest.raises((ReadOnly, BrickGuardRefusal)):
        dev.outp.send(mido.Message('sysex', data=frame[1:-1]))
    assert ports.sent == before


@pytest.mark.parametrize('kind', ['program_change', 'control_change', 'note_on', 'clock'])
def test_no_channel_or_realtime_output(device, kind):
    dev, ports = device
    before = len(ports.sent)
    with pytest.raises(ReadOnly): dev.outp.send(mido.Message(kind))
    assert len(ports.sent) == before


@pytest.mark.parametrize('eid', [True, 0, 208, -1, '58', 58.])
def test_bad_bulk_target_refused_before_io(device, eid):
    dev, ports = device
    before = len(ports.sent)
    with pytest.raises(ValueError): dev.broadcast(eid)
    assert len(ports.sent) == before


@pytest.mark.parametrize('timeout', [True, 0, 6, float('nan'), float('inf'), '2'])
def test_invalid_timeout_refused_before_io(device, timeout):
    dev, ports = device
    before = len(ports.sent)
    with pytest.raises(ValueError): dev.broadcast(58, timeout)
    assert len(ports.sent) == before


@pytest.mark.parametrize('fault', ['checksum', 'foreign', 'interleaved', 'double_head',
    'wrong_target', 'count', 'reserved', 'trailing', 'short', 'timeout', 'excessive'])
def test_bad_fresh_bursts_fail_without_cached_partial_values(device, fault):
    dev, ports = device
    def transform(frame, data):
        if frame[5] != 31: return data
        if fault == 'checksum': data[1][-1] ^= 1
        elif fault == 'foreign': data[1] = [*data[1][:3], 18, *data[1][4:]]
        elif fault == 'interleaved': data.insert(1, p.envelope(8, [33, 1])[1:-1])
        elif fault == 'double_head': data.insert(1, data[0])
        elif fault == 'wrong_target': data = burst(62, (1, 2))
        elif fault == 'count': data[0] = p.envelope(116, [58, 0, 1, 0])[1:-1]
        elif fault == 'reserved': data[1] = p.envelope(117, [1, 0, 0, 0, 0])[1:-1]
        elif fault == 'trailing': data.append(data[-1])
        elif fault == 'short': data = data[:1] + data[-1:]
        elif fault == 'timeout': data = []
        elif fault == 'excessive': data = [data[0]] * 1025
        return data
    ports.transform = transform
    before = len(ports.sent)
    with pytest.raises(ValueError): dev.broadcast(58, timeout=.01)
    assert len(ports.sent) == before + 1


def test_stale_pending_burst_is_discarded_before_query(device):
    dev, ports = device
    ports.queue.extend(mido.Message('sysex', data=d) for d in burst(58, (123,)))
    assert dev.broadcast(58).words == tuple(ports.words[58])


def test_excessive_stale_pending_traffic_stops_before_query(device):
    dev, ports = device
    ports.queue = [mido.Message('clock')] * 4098
    before = len(ports.sent)
    with pytest.raises(ValueError, match='pending'): dev.broadcast(58)
    assert len(ports.sent) == before


def test_partial_burst_can_arrive_in_multiple_poll_batches(device):
    dev, ports = device
    original = ports.inp.iter_pending
    def one():
        if ports.queue: yield ports.queue.pop(0)
    ports.inp.iter_pending = one
    assert dev.bulk_read(58) == ports.words[58]
    ports.inp.iter_pending = original


@pytest.mark.parametrize('target', ['identity', 'preset', 'scene', 'variant', 'status', 'grid'])
def test_drift_during_snapshot_stops_before_complete_observation(device, monkeypatch, target):
    dev, ports = device
    original = dev.broadcast
    def read(eid, *a, **k):
        value = original(eid, *a, **k)
        if eid == 34:
            if target == 'identity': ports.identity = tuple(p.envelope(8, [33, 1])[1:-1])
            elif target == 'preset': ports.preset += 1
            elif target == 'scene': ports.scene = 1
            elif target == 'variant': dev.set_chassis('mk1')
            elif target == 'grid': ports.cells[-1] = (5, 12, 0, True, 126)
            elif target == 'status':
                old = ports.answer
                ports.answer = lambda frame: [p.envelope(19, [58, 0, 66])[1:-1]] if frame[5] == 19 else old(frame)
        return value
    monkeypatch.setattr(dev, 'broadcast', read)
    with pytest.raises(ValueError, match='changed'): dev.observation()


def test_mutating_complete_passes_can_settle_but_different_target_cannot(device, monkeypatch):
    dev, ports = device
    original = dev.observation
    reads = []
    def read():
        reads.append(True)
        if len(reads) == 2: ports.words[58][1] += 1
        return original()
    monkeypatch.setattr(dev, 'observation', read)
    assert dev.capture().data()['bulk']['58'][1] == 8
    assert len(reads) == 3


@pytest.mark.parametrize('fault', ['empty_identity', 'long_identity', 'grid_timeout', 'missing_status', 'missing_name', 'no_system'])
def test_incomplete_required_surfaces_fail_not_default_fill(device, fault):
    dev, ports = device
    def transform(frame, data):
        if fault == 'empty_identity' and frame[5] == 8: return []
        if fault == 'long_identity' and frame[5] == 8: return [p.envelope(8, [1] * 260)[1:-1]]
        if fault == 'grid_timeout' and frame[5] == 1: return []
        if fault == 'missing_status' and frame[5] == 19: return []
        if fault == 'no_system' and frame[5] == 19: return [p.envelope(19, [58, 0, 64])[1:-1]]
        if fault == 'missing_name' and frame[5] == 14: return []
        return data
    ports.transform = transform
    with pytest.raises(ValueError): dev.capture()


def test_closed_reader_fails_without_new_output(device):
    dev, ports = device
    dev.close()
    before = len(ports.sent)
    with pytest.raises(FM9NotFound): dev.broadcast(58)
    assert len(ports.sent) == before


def test_grid_full_ids_and_every_row_column_survive():
    for row in range(6):
        for col in range(14):
            cells = live.parse_grid(grid_reply([(row, col, 206, False, 126)]))
            assert [asdict(c) for c in cells] == [dict(row=row, col=col,
                effect_id=206, is_shunt=False, cable_in_mask=126)]
    assert live.parse_grid(p.envelope(1, [46, 0])[1:-1]) is None


def test_each_grid_request_byte_is_pinned():
    good = list(live.GRID_QUERY)
    assert live.extra_read(good)
    for i in range(6, len(good) - 2):
        args = good[6:-2]; args[i - 6] ^= 1
        assert not live.extra_read(p.envelope(1, args))


@pytest.mark.parametrize('frame', [[], [240], [240, 247], list(live.GRID_QUERY[:-2]) + [0, 247],
    p.envelope(31, [58, 0])[:-1], [240, 0, 1, 116, 18, 31, 58, 0, 0, 247]])
def test_malformed_extra_frames_refused(frame):
    assert not live.extra_read(frame)

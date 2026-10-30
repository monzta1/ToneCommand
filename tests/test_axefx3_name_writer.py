"""Literal fake III responses; no hardware, account or application changes."""
from dataclasses import replace
import threading
from types import SimpleNamespace

import mido
import pytest

from devices.axefx3 import readonly_protocol as p
from devices.axefx3.readonly_adapter import AxeFxIII, ReadOnlyOutput, snapshot
from devices.axefx3.name_edits import NameEdit
from devices.axefx3.name_writer import (MK2_FW33_IDENTITY, NameReadbackError,
                                       NameWriter, _NameOutput)
from fm9 import protocol as shared
from fm9.device import ReadOnly
from tests.test_axefx3_readonly import FakePorts, name_field


class NamedPorts(FakePorts):
    def __init__(self):
        super().__init__()
        self.preset_name = 'Read Test'
        self.names = [f'Scene {n}' for n in range(1, 9)]
        self.identity = MK2_FW33_IDENTITY
        self.writes = []
        self.behavior = 'apply'
        self.stale_reads = 0

    def send(self, message):
        frame = message.bytes()  # Match the MIDI backend's serialization boundary.
        if frame[5] != 1:
            return super().send(message)
        self.writes.append(frame)
        self.sent.append(frame)
        if self.behavior == 'raise':
            raise OSError('Port failed after possibly sending the frame')
        if self.behavior == 'ignore':
            return
        # Independent decode of the actual wire message, not expected_after().
        assert frame[6] in (0x28, 0x2B)
        data = shared.unpack_chunked(frame[21:-2], 32)
        name = bytes(data).decode('ascii').strip()
        if frame[6] == 0x28:
            self.preset_name = name
        else:
            self.names[shared.decode14(*frame[10:12])] = name
        if self.behavior == 'move':
            self.scene = 1
        elif self.behavior == 'preset':
            self.preset = 321
        elif self.behavior == 'identity':
            self.identity = tuple(p.envelope(8, [97, 0])[1:-1])

    def answer(self, frame):
        fn, args = frame[5], frame[6:-2]
        if fn == 8:
            return [list(self.identity)]
        if fn == 0x0D:
            number = self.preset if args == [127, 127] else shared.decode14(*args)
            name = self.preset_name
            if self.writes and self.stale_reads:
                self.stale_reads -= 1
                name = 'Read Test'
            return [p.envelope(fn, [*shared.encode14(number), *name_field(name)])[1:-1]]
        if fn == 0x0E:
            scene = self.scene if args == [127] else args[0]
            return [p.envelope(fn, [scene, *name_field(self.names[scene])])[1:-1]]
        return super().answer(frame)


@pytest.fixture
def writer(monkeypatch):
    ports = NamedPorts()
    dev = NameWriter((ports.inp, ports.outp))
    monkeypatch.setattr('devices.axefx3.name_writer.time.sleep', lambda _: None)
    yield dev, ports
    dev.close()


@pytest.mark.parametrize('scene', [None, *range(1, 9)])
def test_one_review_one_exact_write_and_unchanged_observed_context(writer, scene):
    dev, ports = writer
    before = snapshot(dev)
    edit = NameEdit(320, 'New name', scene)
    review = dev.review_name(edit)
    assert not ports.writes
    assert review.preview()['executable'] is True
    result = dev.apply_name(review, external_audio_muted=True)
    assert result['verified'] and result['sent'] and not result['stored']
    assert ports.writes == [edit.frame()]
    assert edit.verify(before, result['state'])
    with pytest.raises(ReadOnly):
        dev.apply_name(review, external_audio_muted=True)
    assert len(ports.writes) == 1
    assert not dev.capabilities().can_rename  # Not a planner release.
    assert not dev.capabilities().stores_presets


@pytest.mark.parametrize('consent', [False, None, 1, 'yes', [], {}])
def test_explicit_mute_confirmation_is_not_truthiness(writer, consent):
    dev, ports = writer
    review = dev.review_name(NameEdit(320, 'New'))
    with pytest.raises(ReadOnly):
        dev.apply_name(review, external_audio_muted=consent)
    assert not ports.writes


@pytest.mark.parametrize('change', ['preset', 'scene', 'name', 'other_name',
                                    'identity', 'chassis', 'closed'])
def test_changed_review_context_refuses_before_write(writer, change):
    dev, ports = writer
    review = dev.review_name(NameEdit(320, 'New'))
    if change == 'preset': ports.preset = 321
    elif change == 'scene': ports.scene = 1
    elif change == 'name': ports.preset_name = 'Manually changed'
    elif change == 'other_name': ports.names[5] = 'Manually changed'
    elif change == 'identity': ports.identity = tuple(p.envelope(8, [33, 0])[1:-1])
    elif change == 'chassis':
        with pytest.raises(ReadOnly): dev.set_chassis('mk1')
        dev._chassis = 'mk1'  # Simulate a stale/corrupt connection, not a user API.
    elif change == 'closed': dev.close()
    with pytest.raises((ReadOnly, ValueError)):
        dev.apply_name(review, external_audio_muted=True)
    assert not ports.writes


def test_wrong_target_foreign_replaced_and_expired_review_fail_closed(writer, monkeypatch):
    dev, ports = writer
    with pytest.raises(ValueError):
        dev.review_name(NameEdit(321, 'New'))
    review = dev.review_name(NameEdit(320, 'New'))
    for bad in (None, {}, replace(review), replace(review, edit=NameEdit(320, 'Other'))):
        with pytest.raises(ReadOnly):
            dev.apply_name(bad, external_audio_muted=True)
    newer = dev.review_name(NameEdit(320, 'Newer'))
    with pytest.raises(ReadOnly): dev.apply_name(review, external_audio_muted=True)
    monkeypatch.setattr('devices.axefx3.name_writer.time.monotonic', lambda: newer._expires)
    with pytest.raises(ReadOnly): dev.apply_name(newer, external_audio_muted=True)
    assert not ports.writes


@pytest.mark.parametrize('chassis', ['mk1', 'turbo', None, '', True])
def test_unsupported_chassis_refused_before_opening_any_port(chassis, monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports', lambda *_: pytest.fail('opened MIDI'))
    with pytest.raises(ReadOnly): NameWriter(chassis=chassis)


@pytest.mark.parametrize('identity', [(), (33, 0), (97, 0),
    tuple(p.envelope(8, [97, 0])[1:-1]),
    tuple(p.envelope(8, [97, 0, 16, 1, 18])[1:-1])])
def test_ambiguous_or_unknown_identity_is_not_a_write_profile(writer, identity):
    dev, ports = writer
    # A syntactically valid different complete identity must also be refused.
    ports.identity = identity
    with pytest.raises(ReadOnly): dev.review_name(NameEdit(320, 'New'))
    assert not ports.writes


def test_stale_name_readback_retries_only_reads(writer):
    dev, ports = writer
    review = dev.review_name(NameEdit(320, 'New'))
    ports.stale_reads = 2  # First post-write snapshot sees the old name coherently.
    assert dev.apply_name(review, external_audio_muted=True)['verified']
    assert len(ports.writes) == 1


@pytest.mark.parametrize('behavior', ['ignore', 'move', 'raise', 'preset', 'identity'])
def test_uncertain_write_stops_without_retry_restore_or_reload(writer, behavior):
    dev, ports = writer
    review = dev.review_name(NameEdit(320, 'New'))
    ports.behavior = behavior
    with pytest.raises(NameReadbackError) as caught:
        dev.apply_name(review, external_audio_muted=True)
    if behavior in ('raise', 'preset', 'identity'):
        assert isinstance(caught.value.__cause__,
                          {'raise': OSError, 'preset': ValueError, 'identity': ReadOnly}[behavior])
    assert len(ports.writes) == 1
    with pytest.raises(ReadOnly): dev.review_name(NameEdit(320, 'New'))
    with pytest.raises(ReadOnly): dev.apply_name(review, external_audio_muted=True)
    assert len(ports.writes) == 1
    assert all(f[5] != 0x0C or f[6:-2] == [127] for f in ports.sent)


def test_noop_is_verified_without_a_set(writer):
    dev, ports = writer
    result = dev.apply_name(dev.review_name(NameEdit(320, 'Read Test')),
                            external_audio_muted=True)
    assert result['verified'] and not result['sent'] and not result['stored']
    assert not ports.writes


def test_explicit_scene_clear_is_one_reviewed_write(writer):
    dev, ports = writer
    result = dev.apply_name(dev.review_name(NameEdit(320, '', 8)), external_audio_muted=True)
    assert result['verified'] and ports.names[7] == '' and len(ports.writes) == 1


def test_default_adapter_does_not_gain_the_opt_in_writer():
    ports = NamedPorts()
    dev = AxeFxIII((ports.inp, ports.outp), chassis='mk2')
    try:
        assert not hasattr(dev, 'review_name')
        assert not dev.capabilities().can_rename
        with pytest.raises(ReadOnly): dev._send(NameEdit(320, 'New').frame())
        assert not ports.writes
    finally: dev.close()


def test_output_rejects_mutation_replay_other_threads_and_non_sysex():
    sent = []
    output = _NameOutput(SimpleNamespace(send=sent.append), 'mk2')
    edit = NameEdit(320, 'New')
    message = mido.Message('sysex', data=edit.frame()[1:-1])
    for msg in (message, mido.Message('control_change', control=7, value=0),
                mido.Message('program_change', program=0),
                mido.Message('sysex', data=p.envelope(0x64, [0])[1:-1])):
        with pytest.raises(ReadOnly): output.send(msg)
    with output._once(edit):
        refused = []
        def other_thread():
            try: output.send(message)
            except ReadOnly: refused.append(True)
        thread = threading.Thread(target=other_thread)
        thread.start(); thread.join()
        assert refused == [True]
        wrong = NameEdit(320, 'Wrong').frame()
        with pytest.raises(ReadOnly): output.send(mido.Message('sysex', data=wrong[1:-1]))
        with pytest.raises(ReadOnly): output.send(mido.Message('sysex', data=edit.frame()[1:-2]+[0]))
        output.send(message)
        with pytest.raises(ReadOnly): output.send(message)
    with pytest.raises(ReadOnly): output.send(message)
    assert sent == [message]


def test_final_output_consumes_permit_even_if_the_port_fails():
    sent = []
    def fail(message):
        sent.append(message)
        raise OSError('uncertain transport')
    output = _NameOutput(SimpleNamespace(send=fail), 'mk2')
    edit = NameEdit(320, 'New')
    message = mido.Message('sysex', data=edit.frame()[1:-1])
    with output._once(edit):
        with pytest.raises(OSError): output.send(message)
        with pytest.raises(ReadOnly): output.send(message)
    assert len(sent) == 1


# Fixed protocol fixtures: 32-byte space-padded name, product 0x10, scene 8
# encoded as index 7, with literal length fields, packing and checksums. Do not
# derive expected bytes from the shared builder or decode them with its unpacker.
PRESET_RENAME_WIRE = bytes.fromhex(
    'f0 00 01 74 10 01 28 00 00 00 00 00 00 00 00 00 00 00 00 20 00 '
    '27 19 2e 72 03 39 42 6d 32 48 04 02 01 00 40 20 10 08 04 02 '
    '01 00 40 20 10 08 04 02 01 00 40 20 10 08 04 02 00 68 f7'
)
SCENE_RENAME_WIRE = bytes.fromhex(
    'f0 00 01 74 10 01 2b 00 00 00 07 00 00 00 00 00 00 00 00 20 00 '
    '26 19 2c 16 21 00 5e 20 29 5b 6d 46 79 00 40 20 10 08 04 02 '
    '01 00 40 20 10 08 04 02 01 00 40 20 10 08 04 02 00 1c f7'
)


@pytest.mark.parametrize('name,scene,expected', [
    ('New name', None, PRESET_RENAME_WIRE), ('Lead / Solo', 8, SCENE_RENAME_WIRE),
])
def test_literal_rename_bytes_reach_the_port(writer, name, scene, expected):
    dev, ports = writer
    review = dev.review_name(NameEdit(320, name, scene))
    assert dev.apply_name(review, external_audio_muted=True)['verified']
    assert [bytes(frame) for frame in ports.writes] == [expected]


@pytest.mark.parametrize('boundary', ['readonly', 'writer_read', 'writer_set'])
@pytest.mark.parametrize('attack', ['subclass', 'mutation'])
def test_final_port_serializes_a_fresh_plain_checked_message(boundary, attack):
    class DifferentBytes(mido.Message):
        def bytes(self):
            return [0xC0, 1]  # Must never serialize this unreviewed program change.

    expected = (PRESET_RENAME_WIRE if boundary == 'writer_set'
                else bytes.fromhex('f0 00 01 74 10 08 1d f7'))
    cls = DifferentBytes if attack == 'subclass' else mido.Message
    original = cls('sysex', data=expected[1:-1])
    received = []

    def serialize(message):
        if attack == 'mutation':
            original.data = [0, 1, 116, 16, 0x64, 0]
        received.append(message)
        assert type(message) is mido.Message
        assert message is not original
        assert bytes(message.bytes()) == expected

    raw = SimpleNamespace(send=serialize)
    output = ReadOnlyOutput(raw, 'mk2') if boundary == 'readonly' else _NameOutput(raw, 'mk2')
    if boundary == 'writer_set':
        with output._once(NameEdit(320, 'New name')):
            output.send(original)
            with pytest.raises(ReadOnly): output.send(original)
    else:
        output.send(original)
    assert len(received) == 1


@pytest.mark.parametrize('phase', ['snapshot', 'last_identity'])
@pytest.mark.parametrize('overrun', [0.0, 0.1])
def test_review_expiring_during_preflight_never_arms_or_sends(writer, monkeypatch, phase, overrun):
    dev, ports = writer
    review = dev.review_name(NameEdit(320, 'New'))
    now = [review._expires - 0.5]
    monkeypatch.setattr('devices.axefx3.name_writer.time.monotonic', lambda: now[0])
    if phase == 'snapshot':
        def slow_snapshot(device):
            result = snapshot(device)
            now[0] = review._expires + overrun
            return result
        monkeypatch.setattr('devices.axefx3.name_writer.snapshot', slow_snapshot)
    else:
        identity, calls = dev._identity, []
        def slow_identity():
            identity()
            calls.append(True)
            if len(calls) == 2:
                now[0] = review._expires + overrun
        monkeypatch.setattr(dev, '_identity', slow_identity)
    monkeypatch.setattr(dev.outp, '_once', lambda _: pytest.fail('armed an expired permit'))
    with pytest.raises(ReadOnly, match='expired during preflight'):
        dev.apply_name(review, external_audio_muted=True)
    assert not ports.writes and not dev._uncertain
    assert dev._review is None
    assert dev.review_name(NameEdit(320, 'Fresh')).preview()['executable']


@pytest.mark.parametrize('failure', ['snapshot_error', 'incoherent_snapshot', 'settling_error'])
def test_post_send_verification_errors_are_uncertain_not_prewrite_refusals(writer, monkeypatch, failure):
    dev, ports = writer
    review = dev.review_name(NameEdit(320, 'New'))
    def failing_snapshot(device):
        result = snapshot(device)
        if ports.writes:
            if failure == 'snapshot_error':
                raise ReadOnly('Post-write read failed')
            result['connected'] = False
        return result
    if failure == 'settling_error':
        def failed_settling(_):
            raise OSError('Post-write settling failed')
        monkeypatch.setattr('devices.axefx3.name_writer.time.sleep', failed_settling)
    else:
        monkeypatch.setattr('devices.axefx3.name_writer.snapshot', failing_snapshot)
    with pytest.raises(NameReadbackError) as caught:
        dev.apply_name(review, external_audio_muted=True)
    expected_cause = {'snapshot_error': ReadOnly, 'incoherent_snapshot': ValueError,
                      'settling_error': OSError}[failure]
    assert isinstance(caught.value.__cause__, expected_cause)
    assert len(ports.writes) == 1 and dev._uncertain
    with pytest.raises(ReadOnly): dev.review_name(NameEdit(320, 'Do not retry'))
    assert len(ports.writes) == 1

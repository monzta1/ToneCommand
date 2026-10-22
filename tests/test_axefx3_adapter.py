"""Exercise the new adapter on independent scripted AFX3 ports, not FM9Sim."""
import mido
import pytest

from fm9.adapter import conformance
from fm9 import protocol as shared
from fm9.safety import BrickGuardRefusal
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3 import protocol


class Ports:
    def __init__(self):
        self.queue = []
        self.sent = []
        self.preset = 322
        self.firmware = [32, 6]
        self.channel = 0
        self.mid = 5.0
        self.tempo = "NONE"
        self.delay = 280
        self.drop_writes = False
        self.closed = False

    def iter_pending(self):
        while self.queue:
            yield self.queue.pop(0)

    def close(self):
        self.closed = True

    def reply(self, fn, payload):
        self.queue.append(mido.Message("sysex", data=protocol.envelope(fn, payload)[1:-1]))

    def display(self, eid, pid, text):
        bits = "".join(f"{b:08b}" for b in (text + "\0").encode("ascii"))
        bits += "0" * (-len(bits) % 7)
        packed = [int(bits[i:i+7], 2) for i in range(0, len(bits), 7)]
        payload = [0x10, 0, eid, 0, pid, 0] + [0] * 7
        payload += list(shared.encode14(len(packed))) + packed
        self.reply(1, payload)

    def send(self, message):
        data = list(message.data)
        self.sent.append(data)
        assert protocol.valid_reply(data)
        fn, payload = data[4], data[5:-1]
        if fn == 8:
            self.reply(8, self.firmware)
        elif fn == 0x0D:
            self.reply(fn, [*shared.encode14(self.preset), *b"Test".ljust(32, b"\0")])
        elif fn == 0x0B:
            if payload[2] != 127:
                self.channel = payload[2]
            self.reply(fn, [*payload[:2], self.channel])
        elif fn == 0x1F and payload == [70, 0]:
            words = [0] * (4 * 89)
            words[self.channel * 89 + 9] = 0 if self.tempo == "NONE" else 7
            self.reply(0x74, [70, 0, *shared.encode14(len(words))])
            packed = [b for word in words for b in (word & 127, (word >> 7) & 127, word >> 14)]
            self.reply(0x75, [0, 0, *packed])
            self.reply(0x76, [])
        elif fn == 1 and payload[:2] == [0x10, 0]:
            eid, pid = payload[2], payload[4]
            text = (f"{self.mid:g}" if (eid, pid) == (58, 3) else
                    self.tempo if (eid, pid) == (70, 9) else
                    f"{self.delay} ms" if (eid, pid) == (70, 2) else "unknown")
            self.display(eid, pid, text)
        elif fn == 1 and payload[:2] in ([9, 0], [0x52, 0]) and not self.drop_writes:
            value = shared.decode_f32_septets(payload[6:11])
            if (payload[2], payload[4]) == (58, 3):
                self.mid = round(value * 10, 2)
            elif (payload[2], payload[4]) == (70, 2):
                self.delay = round(value * 1000)
            elif (payload[2], payload[4]) == (70, 9) and payload[0] == 0x52 and value == 0:
                self.tempo = "NONE"

    def writes(self):
        return [d for d in self.sent if d[4] == 1 and d[5:7] in ([9, 0], [0x52, 0])]


@pytest.fixture
def rig():
    ports = Ports()
    dev = AxeFxIII(ports=(ports, ports))
    yield dev, ports
    dev.close()


def test_connect_is_read_only_and_conforms_to_upstream_contract(rig):
    dev, ports = rig
    assert conformance(dev) == []
    assert dev.current_preset() == (322, "Test")
    assert dev.reg.firmware == "32.06"
    assert all(d[4] in (8, 0x0D) for d in ports.sent)
    assert not dev.capabilities().stores_presets
    assert not dev.capabilities().installs_files


def test_no_write_without_explicit_session_and_no_automatic_store(rig):
    dev, ports = rig
    spec = dev.reg.find_param("DISTORT", "DISTORT_MID")
    with pytest.raises(PermissionError):
        dev.set_param_display(spec, 6)
    with pytest.raises(PermissionError):
        dev.store_preset(322)
    assert ports.writes() == []


@pytest.mark.parametrize('family,name,value,eid',[
    ('COMP','COMP_THRESH',-30,46),('GEQ','GEQ_GAIN1',-3,50),('PEQ','PEQ_FREQ1',300,54)])
def test_numeric_pid_zero_passes_canonical_parameter_gate_not_model_gate(rig,family,name,value,eid):
    dev,ports=rig
    frame=protocol.set_parameter(dev.reg,dev.reg.find_param(family,name),value)
    with dev.edit_session(external_audio_muted=True,expected_preset=322):
        dev._write(frame)
    assert ports.writes()[-1][5:11]==[9,0,eid,0,0,0]


@pytest.mark.parametrize('eid,pid,ordinal',[(118,0,0),(118,0,6),(118,0,8),(46,12,0),(46,12,13)])
def test_drive_and_comp_model_frames_use_their_captured_selector(rig,eid,pid,ordinal):
    dev,ports=rig
    frame=protocol.param_frame(eid,pid,ordinal,opcode=9)
    with pytest.raises(PermissionError):dev._send(frame)
    with dev.edit_session(external_audio_muted=True,expected_preset=322):
        dev._write(frame)
    assert ports.writes()[-1][5:11]==[9,0,eid,0,pid,0]


@pytest.mark.parametrize('eid,pid,ordinal,opcode',[(118,0,1,9),(46,12,8,9),
    (118,0,6,82),(46,12,13,82),(119,0,6,9),(47,12,13,9)])
def test_extra_model_transport_refuses_uncaptured_instances_models_and_opcodes(rig,eid,pid,ordinal,opcode):
    dev,ports=rig
    with dev.edit_session(external_audio_muted=True,expected_preset=322):
        with pytest.raises((ValueError,PermissionError)):
            dev._write(protocol.param_frame(eid,pid,ordinal,opcode=opcode))
    assert ports.writes()==[]


def test_native_modifier_allocator_requires_exact_frame_and_edit_session(rig):
    from devices.axefx3 import modifiers
    dev, ports = rig
    frame = modifiers.allocation_frame(94)
    with pytest.raises(PermissionError):
        dev._send(frame)
    with pytest.raises(PermissionError):
        dev.create_wah_modifier(94, 12)
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        dev._write(frame)
        payload = frame[6:-2]
        payload[4] = 6  # Wah Level, not Control.
        with pytest.raises(PermissionError):
            dev._write(protocol.envelope(1, payload))
        with pytest.raises(PermissionError):
            dev._write(protocol.envelope(1, frame[6:-3]))
    assert sum(d[4:7] == [1, 0x3A, 0] for d in ports.sent) == 1
    assert not dev.capabilities().has_modifiers


def test_pedal_frames_keep_exact_allowlist_and_session_gate(rig):
    from devices.axefx3 import pedal_control as pc
    dev, ports = rig
    with pytest.raises(PermissionError):
        dev.bind_pedal_control(102, 13, "Off")
    with pytest.raises(PermissionError):
        dev._send(pc.auto_frame(2, 0))
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        dev._write(pc.allocation_frame(102))
        dev._write(pc.auto_frame(2, 0))
        dev._write(pc.auto_frame(2, 6))
        bad = pc.allocation_frame(102)[6:-2]
        bad[4] = 5
        with pytest.raises(PermissionError):
            dev._write(protocol.envelope(1, bad))
        for pid, value, opcode in [(10,1,9),(10,0,0x52),(1,6,9)]:
            with pytest.raises((ValueError, PermissionError)):
                dev._write(protocol.param_frame(4,pid,value,opcode=opcode))
        with pytest.raises((ValueError, PermissionError)):
            dev._write(protocol.param_frame(102,0,1,opcode=9))
    assert len(ports.writes()) == 2
    assert not dev.capabilities().has_modifiers


def test_mid_six_is_verified_from_display_not_from_the_value_we_sent(rig):
    dev, ports = rig
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        result = dev.set_param_display(dev.reg.find_param("DISTORT", "DISTORT_MID"), 6)
    assert result.ok
    assert (result.display_before, result.display_after) == (5, 6)
    assert len(ports.writes()) == 1
    assert dev._edit_target is None


def test_dropped_write_is_failure_even_when_send_did_not_raise(rig):
    dev, ports = rig
    ports.drop_writes = True
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        result = dev.set_param_display(dev.reg.find_param("DISTORT", "DISTORT_MID"), 6)
    assert not result.ok
    assert result.display_after == 5


@pytest.mark.parametrize("muted,target", [(False, 322), ("true", 322), (True, "322"), (True, 321)])
def test_missing_mute_or_wrong_target_cannot_arm_writes(rig, muted, target):
    dev, ports = rig
    with pytest.raises(PermissionError):
        with dev.edit_session(external_audio_muted=muted, expected_preset=target):
            pytest.fail("Invalid edit session was accepted")
    assert not ports.writes()
    assert dev._edit_target is None


def test_firmware_or_preset_change_revokes_the_session(rig):
    dev, ports = rig
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        ports.firmware = [33, 0]
        with pytest.raises(PermissionError):
            dev.set_param_display(dev.reg.find_param("DISTORT", "DISTORT_MID"), 6)
    assert not ports.writes()


def test_invalid_later_batch_item_refuses_before_first_write(rig):
    dev, ports = rig
    spec = dev.reg.find_param("DISTORT", "DISTORT_MID")
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        with pytest.raises(ValueError):
            dev.set_params_batch([(spec, 6), (spec, 100)])
    assert not ports.writes()


def test_batch_stops_after_an_unverified_write(rig):
    dev, ports = rig
    spec = dev.reg.find_param("DISTORT", "DISTORT_MID")
    ports.drop_writes = True
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        results = dev.set_params_batch([(spec, 6), (spec, 7)])
    assert len(results) == 2 and not any(r.ok for r in results)
    assert len(ports.writes()) == 1


def test_tempo_sync_is_not_mistaken_for_a_millisecond_value(rig):
    dev, ports = rig
    ports.tempo = "1/4"
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        result = dev.set_param_display(dev.reg.find_param("DELAY", "DELAY_TIME"), 380)
    assert result.ok and ports.tempo == "NONE" and ports.delay == 380
    assert [d[9] for d in ports.writes()] == [9, 2]


def test_tempo_precondition_failure_never_sends_the_time_write(rig):
    dev, ports = rig
    ports.tempo = "1/4"
    ports.drop_writes = True
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        result = dev.set_param_display(dev.reg.find_param("DELAY", "DELAY_TIME"), 380)
    assert not result.ok
    assert [d[9] for d in ports.writes()] == [9]


def test_verified_none_allows_milliseconds_in_the_captured_seconds_domain(rig):
    dev, ports = rig
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        result = dev.set_param_display(dev.reg.find_param("DELAY", "DELAY_TIME"), 380)
    assert result.ok and ports.delay == 380


def test_legacy_global_restore_and_undeclared_frames_are_refused(rig):
    dev, ports = rig
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        with pytest.raises(PermissionError):
            dev._send(protocol.param_frame(1, 72, 1, opcode=9))
        with pytest.raises(BrickGuardRefusal):
            dev._send(protocol.envelope(0x77, []))
        with pytest.raises(PermissionError):
            dev._send(protocol.envelope(1, [0x26, 0]))
    assert not ports.writes()


@pytest.mark.parametrize("eid", [1, 60, 61, True, 58.5, -1, 999])
def test_reserved_or_nonexistent_block_cannot_be_switched(rig, eid):
    dev, ports = rig
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        with pytest.raises(PermissionError):
            dev.set_bypass(eid, False)
        with pytest.raises(PermissionError):
            dev.set_channel(eid, 1)
    assert not any(d[4] == 0x0A or (d[4] == 0x0B and d[-2] != 127) for d in ports.sent)


@pytest.mark.parametrize("issue", ["truncated", "overflow", "partial_word", "invalid_high_bits", "bad_end"])
def test_bulk_read_never_presents_malformed_data_as_a_complete_block(rig, issue):
    dev, ports = rig
    send = ports.send
    def damaged(message):
        if list(message.data)[4] != 0x1F:
            return send(message)
        ports.reply(0x74, [70, 0, 1, 0])
        payload = {"truncated": [0, 0], "overflow": [0, 0, 1, 0, 0, 2, 0, 0],
                   "partial_word": [0, 0, 1, 0, 0, 0], "invalid_high_bits": [0, 0, 1, 0, 4],
                   "bad_end": [0, 0, 1, 0, 0]}[issue]
        ports.reply(0x75, payload)
        ports.reply(0x76, [1] if issue == "bad_end" else [])
    ports.send = damaged
    assert dev.bulk_read(70) is None


@pytest.mark.parametrize("eid,ordinal,opcode", [(58, 0, 9), (58, 14, 0x52),
    (70, 1, 9), (94, 3, 9), (66, 78, 9), (60, 14, 9)])
def test_transport_refuses_uncaptured_model_commands_even_inside_session(rig, eid, ordinal, opcode):
    dev, ports = rig
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        with pytest.raises((PermissionError, ValueError)):
            dev._write(protocol.param_frame(eid, 0, ordinal, opcode=opcode))
    assert not ports.writes()


@pytest.mark.parametrize("eid,pid,value,opcode", [
    (62, 0, 0, 9), (62, 0, 3, 9), (62, 4, 1024, 9), (62, 4, 1.5, 9),
    (3, 0, 0, 0x52), (3, 0, 10, 9), (3, 1, .5, 9), (3, 8, 94, 9),
])
def test_transport_rejects_invalid_cab_selection_and_modifier_curve_writes(rig, eid, pid, value, opcode):
    dev, ports = rig
    with dev.edit_session(external_audio_muted=True, expected_preset=322):
        with pytest.raises((PermissionError, ValueError)):
            dev._write(protocol.param_frame(eid, pid, value, opcode=opcode))
    assert not ports.writes()


@pytest.mark.parametrize('fault', [None,'synced','display','length','channel'])
def test_chorus_rate_requires_independent_tempo_none_without_tempo_writes(rig,monkeypatch,fault):
    dev, ports = rig
    spec=dev.reg.spec('CHORUS',2)
    words=[0]*128
    if fault=='synced': words[3]=7
    if fault=='length': words.pop()
    monkeypatch.setattr(dev,'bulk_read',lambda eid:words)
    monkeypatch.setattr(dev,'read_display_text',lambda eid,pid:'1/4' if fault=='display' else 'NONE')
    monkeypatch.setattr(dev,'get_channel',lambda eid:1 if fault=='channel' else 0)
    result=dev._prepare_delay_milliseconds(spec,0)
    assert (result is None)==(fault is None)
    assert not ports.writes()

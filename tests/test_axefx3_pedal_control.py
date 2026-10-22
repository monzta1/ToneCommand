"""Captured pedal writes preserve all other records and existing parallel grids."""
from contextlib import nullcontext
from types import SimpleNamespace, MethodType
from unittest.mock import Mock
import threading

import pytest

from devices.axefx3 import pedal_control as pc, modifiers, protocol
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from fm9.protocol import decode_f32_septets


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(pc.time, "sleep", lambda _: None)
    d = Mock()
    d.reg = Registry("32.06")
    d.firmware_label.return_value = "32.06"
    d._lock = threading.RLock()
    d.edit_session.side_effect = lambda **kw: nullcontext()
    d.bind_pedal_control = MethodType(AxeFxIII.bind_pedal_control, d)
    slots = [[0] * 25 for _ in range(32)]
    slots[0] = pc.default_words(102)
    slots[0][0] = 13
    slots[1] = pc.default_words(95)
    slots[1][0], slots[1][10] = 12, 6
    d.read_modifier.side_effect = lambda slot: slots[slot - 1].copy()
    d.status_dump.return_value = [SimpleNamespace(effect_id=e, channel=0,
        channels_supported=4, bypassed=False) for e in (95, 102)]
    d.current_scene.return_value = 1
    d.current_preset.return_value = (324, "Test")
    # Opaque reference: no serial-route reconstruction or normalization.
    d.read_grid.return_value = [(3, 2, 95, 8), (3, 6, 102, 30)]
    volume = [65534,32767,2,0,0,65534,52427,0,0,0,24575,32767,32767,32767,0] * 4
    d.bulk_read.side_effect = lambda eid: volume.copy() if eid == 102 else None
    def write(frame):
        if frame[6] == 0x3A:
            slot = next(i for i, w in enumerate(slots) if w[0] == w[8] == 0)
            slots[slot] = pc.default_words(frame[8])
        else:
            slots[frame[8] - 3][frame[10]] = int(decode_f32_septets(frame[12:17]))
    d._write.side_effect = write
    return d, slots, volume


@pytest.mark.parametrize("slot,mode,hex_frame", [
    (2, 0, "f0 00 01 74 10 01 09 00 04 00 0a 00 00 00 00 00 00 00 00 00 00 13 f7"),
    (2, 6, "f0 00 01 74 10 01 09 00 04 00 0a 00 00 00 00 06 04 00 00 00 00 11 f7"),
])
def test_auto_engage_exact_captured_frames(slot, mode, hex_frame):
    assert pc.auto_frame(slot, mode) == list(bytes.fromhex(hex_frame))


def test_volume_allocation_is_parameter_zero_not_model_change():
    assert pc.allocation_frame(102) == list(bytes.fromhex(
        "f0 00 01 74 10 01 3a 00 66 00 00 00 00 00 00 00 00 00 00 00 00 48 f7"))
    with pytest.raises(ValueError):
        modifiers.allocation_frame(102)
    with pytest.raises((ValueError, KeyError)):
        Registry("32.06").spec("VOLPAN", 0, 1)


@pytest.mark.parametrize("eid,source,mode", [(95,12,"Off"), (95,13,"Fast Pos"), (102,12,"Off")])
def test_existing_binding_only_changes_requested_fields(rig, eid, source, mode):
    d, slots, volume = rig
    before = [w.copy() for w in slots]
    ctx = pc.context(d, eid, modifiers.inspect(d))
    r = d.bind_pedal_control(eid, source, mode)
    assert r.ok and "physical" in r.detail
    target = 0 if eid == 102 else 1
    before[target][0] = source
    before[target][10] = pc.MODES[mode]
    assert slots == before
    assert pc.context(d, eid, modifiers.inspect(d)) == ctx


@pytest.mark.parametrize("eid", [95,102])
def test_native_creation_before_source_preserves_every_other_record(rig, eid):
    d, slots, _ = rig
    index = 0 if eid == 102 else 1
    slots[index][0] = slots[index][8] = slots[index][9] = 0
    before = [w.copy() for w in slots]
    r = d.bind_pedal_control(eid, 13, "Off")
    assert r.ok
    before[index] = [13] + pc.default_words(eid)[1:]
    assert slots == before
    assert [c.args[0] for c in d._write.call_args_list] == [
        pc.allocation_frame(eid), modifiers.source_frame(index + 1, 13)]


def test_matching_request_has_no_writes_and_full_final_readback(rig):
    d, _, _ = rig
    assert d.bind_pedal_control(95,12,"Fast Pos").ok
    d._write.assert_not_called()
    assert d.read_modifier.call_count >= 96


@pytest.mark.parametrize("eid,source,mode", [
    (True,12,None), (96,12,None), (103,13,None), (102,13,"Fast Pos"),
    (95,6,None), (95,True,None), (95,12,[]), (95,12,"Slow Pos"),
])
def test_unverified_requests_refuse_without_writes(rig,eid,source,mode):
    d, _, _ = rig
    with pytest.raises(ValueError): d.bind_pedal_control(eid,source,mode)
    d._write.assert_not_called()


@pytest.mark.parametrize("issue", ["fw", "live_fw", "short", "duplicate", "inactive", "missing",
    "volume_curve", "volume_mode", "volume_type", "volume_level", "unassessed", "wah_mode"])
def test_unsafe_existing_state_refuses_before_writes(rig, issue):
    d, slots, volume = rig
    if issue == "fw": d.reg = Registry("33.00")
    if issue == "live_fw": d.firmware_label.return_value = "33.00"
    if issue == "short": slots[31] = [0] * 15
    if issue == "duplicate": slots[2] = slots[1].copy()
    if issue == "inactive": slots[1][0] = 0
    if issue == "missing": d.status_dump.return_value = []
    if issue == "volume_curve": slots[0][20] = 1
    if issue == "volume_mode": slots[0][10] = 6
    if issue == "volume_type": volume[17] = 3
    if issue == "volume_level": volume[6] += 1
    if issue == "unassessed": slots[0][9] = 6
    if issue == "wah_mode": slots[1][10] = 7
    with pytest.raises(ValueError): d.bind_pedal_control(95,12,"Off")
    d._write.assert_not_called()


@pytest.mark.parametrize("issue", ["drop", "collateral", "curve", "volume", "scene", "grid", "preset"])
def test_independent_readback_not_echo(rig, issue):
    d, slots, volume = rig
    original = d._write.side_effect
    def bad(frame):
        if issue == "drop": return
        original(frame)
        if issue == "collateral": slots[31][7] = 1
        if issue == "curve": slots[1][1] = 1
        if issue == "volume": volume[6] = 52426
        if issue == "scene": d.current_scene.return_value = 2
        if issue == "grid": d.read_grid.return_value = []
        if issue == "preset": d.current_preset.return_value = (325, "Test")
    d._write.side_effect = bad
    try:
        assert not d.bind_pedal_control(95,12,"Off").ok
    except ValueError:
        assert issue == "volume"
    assert d._write.call_count == 1


@pytest.mark.parametrize("issue", ["drop", "curve", "collateral"])
def test_failed_allocation_never_assigns_source(rig, issue):
    d, slots, _ = rig
    slots[0] = [0] * 25
    original = d._write.side_effect
    def bad(frame):
        if issue == "drop": return
        original(frame)
        slots[0 if issue == "curve" else 31][20] = 1
    d._write.side_effect = bad
    assert not d.bind_pedal_control(102,13,"Off").ok
    assert d._write.call_count == 1


def test_settle_retries_reads_not_writes(rig):
    d, slots, _ = rig
    original = d._write.side_effect
    pending = []
    d._write.side_effect = pending.append
    count = 0
    def read(slot):
        nonlocal count
        if pending and slot == 1:
            count += 1
            if count == 2: original(pending.pop())
        return slots[slot-1].copy()
    d.read_modifier.side_effect = read
    assert d.bind_pedal_control(95,12,"Off").ok
    assert d._write.call_count == 1


def test_pedal_only_executor_preserves_parallel_grid(rig):
    d, slots, _ = rig
    report = pc.execute(d,[dict(effect_id=95,source=12,auto_engage="Off"),
                          dict(effect_id=102,source=13,auto_engage="Off")],
                        expected_preset=324, external_audio_muted=True)
    assert report["ok"] and not report["stored"] and not report["physical_pedal_verified"]
    d.edit_session.assert_called_once_with(external_audio_muted=True,expected_preset=324)
    assert d._write.call_count == 1


def test_complete_list_preflight_prevents_partial_execution(rig):
    d, _, _ = rig
    with pytest.raises(ValueError):
        pc.execute(d,[dict(effect_id=95,source=12,auto_engage="Off"),
                      dict(effect_id=102,source=13,auto_engage="Fast Pos")],
                   expected_preset=324,external_audio_muted=True)
    d._write.assert_not_called()


def test_no_mute_no_execution(rig):
    d, _, _ = rig
    with pytest.raises(PermissionError):
        pc.execute(d,[dict(effect_id=95,source=12)],expected_preset=324,external_audio_muted=False)
    d._write.assert_not_called()


def test_failure_stops_following_requests(rig):
    d, _, _ = rig
    d._write.side_effect = OSError("disconnected")
    report = pc.execute(d,[dict(effect_id=95,source=12,auto_engage="Off"),
                          dict(effect_id=102,source=12)],expected_preset=324,external_audio_muted=True)
    assert not report["ok"] and report["skipped"] == 1 and not report["stored"]
    assert d._write.call_count == 1


def test_complete_list_reserves_enough_slots_before_any_write(rig):
    d, slots, _ = rig
    for w in slots:
        w[0], w[8], w[9] = 0, 58, 44
    slots[0] = [0] * 25
    with pytest.raises(ValueError, match="Insufficient"):
        pc.execute(d,[dict(effect_id=95,source=12),dict(effect_id=102,source=13)],
                   expected_preset=324,external_audio_muted=True)
    d._write.assert_not_called()


def test_even_noop_requires_unchanged_modifier_records(rig):
    d, slots, _ = rig
    original = d.read_modifier.side_effect
    count = 0
    def changed(slot):
        nonlocal count
        count += 1
        if count == 33: slots[31][7] = 1
        return original(slot)
    d.read_modifier.side_effect = changed
    assert not d.bind_pedal_control(95,12,"Fast Pos").ok
    d._write.assert_not_called()


def test_auto_engage_may_change_only_target_wah_bypass(rig):
    d, _, _ = rig
    original = d._write.side_effect
    def toggle(frame):
        original(frame)
        d.status_dump.return_value[0].bypassed = True
    d._write.side_effect = toggle
    assert d.bind_pedal_control(95,12,"Off").ok

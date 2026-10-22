"""Native allocator evidence is independent of physical pedal acceptance."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from devices.axefx3 import modifiers, protocol
from devices.axefx3.registry import Registry
from fm9.protocol import decode_f32_septets


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(modifiers.time, "sleep", lambda _: None)
    d = Mock()
    d.reg = Registry("32.06")
    slots = [[0] * 25 for _ in range(32)]
    # Inactive stale data is not itself a valid target and must be initialized.
    slots[0] = modifiers.native_default(0)
    slots[0][9] = 44
    d.read_modifier.side_effect = lambda slot: slots[slot - 1].copy()
    d.status_dump.return_value = [SimpleNamespace(effect_id=94)]
    d.current_scene.return_value = 1
    d.read_grid.return_value = [(3, 3, 94)]
    def write(frame):
        if frame[6] == 0x3A:
            slots[0] = modifiers.native_default(94)
        else:
            slots[0][0] = int(decode_f32_septets(frame[12:17]))
    d._write.side_effect = write
    return d, slots


@pytest.mark.parametrize("eid,hex_frame", [
    (94, "f0 00 01 74 10 01 3a 00 5e 00 05 00 00 00 00 00 00 00 00 00 00 75 f7"),
    (95, "f0 00 01 74 10 01 3a 00 5f 00 05 00 00 00 00 00 00 00 00 00 00 74 f7"),
])
def test_exact_axe_edit_frames(eid, hex_frame):
    assert modifiers.allocation_frame(eid) == list(bytes.fromhex(hex_frame))
    assert protocol.valid_reply(modifiers.allocation_frame(eid)[1:-1])


@pytest.mark.parametrize("eid", [True, 94.0, 0, 3, 58, 96, 97, 199])
def test_no_other_allocations(eid):
    with pytest.raises(ValueError):
        modifiers.allocation_frame(eid)


@pytest.mark.parametrize("source", [12, 13])
def test_device_builds_curve_then_source_only(rig, source):
    d, slots = rig
    result = modifiers.create_wah(d, 94, source)
    assert result.ok and result.display_after == 1
    assert slots[0] == [source] + modifiers.native_default(94)[1:]
    assert [c.args[0] for c in d._write.call_args_list] == [
        modifiers.allocation_frame(94), modifiers.source_frame(1, source)]
    assert "physical pedal unverified" in result.detail


@pytest.mark.parametrize("issue", ["missing", "firmware", "existing", "short", "unreadable", "full", "invalid_source"])
def test_refuse_before_allocation(rig, issue):
    d, slots = rig
    source = 12
    if issue == "missing": d.status_dump.return_value = []
    if issue == "firmware": d.reg = Registry("33.00")
    if issue == "existing": slots[0] = modifiers.native_default(94)
    if issue == "short": slots[31] = [0] * 15
    if issue == "unreadable": slots[31] = []
    if issue == "full":
        for w in slots: w[8] = 58
    if issue == "invalid_source": source = 6
    with pytest.raises(ValueError):
        modifiers.create_wah(d, 94, source)
    d._write.assert_not_called()


@pytest.mark.parametrize("issue", ["drop", "curve", "collateral", "status", "scene", "grid"])
def test_allocation_failure_never_writes_source(rig, issue):
    d, slots = rig
    def bad(frame):
        if issue == "drop": return
        slots[0] = modifiers.native_default(94)
        if issue == "curve": slots[0][20] = 1
        if issue == "collateral": slots[1][9] = 5
        if issue == "status": d.status_dump.return_value = []
        if issue == "scene": d.current_scene.return_value = 2
        if issue == "grid": d.read_grid.return_value = []
    d._write.side_effect = bad
    assert not modifiers.create_wah(d, 94, 12).ok
    assert d._write.call_count == 1


@pytest.mark.parametrize("issue", ["drop_source", "other_slot", "curve"])
def test_source_echo_is_not_success(rig, issue):
    d, slots = rig
    original = d._write.side_effect
    def bad(frame):
        if frame[6] == 0x3A: return original(frame)
        if issue == "drop_source": return
        original(frame)
        if issue == "other_slot": slots[31][7] = 1
        if issue == "curve": slots[0][13] = 0
    d._write.side_effect = bad
    assert not modifiers.create_wah(d, 94, 12).ok
    assert d._write.call_count == 2

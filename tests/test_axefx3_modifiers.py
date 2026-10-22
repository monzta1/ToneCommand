import threading
from types import MethodType
from unittest.mock import Mock

import pytest

from devices.axefx3 import modifiers
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from fm9.protocol import decode_f32_septets


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(modifiers.time, "sleep", lambda _: None)
    dev = Mock()
    dev.reg = Registry("32.06")
    dev._lock = threading.RLock()
    slots = [[0]*15 for _ in range(32)]
    slots[0] = [12, 0, 65534, 0, 32767, 65534, 32767, 1000, 94, 5, 2000, 3000, 4000, 32767, 32767]
    dev.read_modifier.side_effect = lambda slot: slots[slot - 1].copy()
    dev._write.side_effect = lambda frame: slots[0].__setitem__(0, int(decode_f32_septets(frame[12:17])))
    dev.assign_existing_modifier = MethodType(AxeFxIII.assign_existing_modifier, dev)
    return dev, slots


def test_existing_curve_is_preserved_and_physical_claim_stays_false(rig):
    dev, slots = rig
    before = slots[0].copy()
    result = dev.assign_existing_modifier(1, 94, 5, 13)
    assert result.ok and slots[0][0] == 13 and slots[0][1:] == before[1:]
    assert len(dev._write.call_args_list) == 1
    report = modifiers.inspect(dev)
    assert report[0]["source_name"] == "External 2"
    assert not report[0]["physical_pedal_verified"]


def test_empty_preset_does_not_receive_the_old_incomplete_default_curve(rig):
    dev, slots = rig
    slots[0] = [0]*15
    result = dev.assign_existing_modifier(1, 94, 5, 12)
    assert not result.ok and "device-built curve" in result.detail
    dev._write.assert_not_called()


@pytest.mark.parametrize("issue", ["dead_curve", "duplicate", "unknown_target", "level_target", "unreadable"])
def test_unknown_or_unsafe_modifier_refuses_before_writing(rig, issue):
    dev, slots = rig
    if issue == "dead_curve": slots[0][1] = slots[0][2]
    if issue == "duplicate": slots[1] = slots[0].copy()
    if issue == "unknown_target": slots[0][8] = 999
    if issue == "level_target": slots[0][9] = 6
    if issue == "unreadable": slots[31] = []
    try:
        result = dev.assign_existing_modifier(1, 94, 5, 13)
        assert not result.ok
    except ValueError:
        pass
    dev._write.assert_not_called()


@pytest.mark.parametrize("issue", ["drop", "curve"])
def test_echo_or_collateral_change_is_not_success(rig, issue):
    dev, slots = rig
    def fail(frame):
        if issue == "curve":
            slots[0][0] = 13
            slots[0][7] += 1
    dev._write.side_effect = fail
    assert not dev.assign_existing_modifier(1, 94, 5, 13).ok

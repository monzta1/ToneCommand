"""Observed labels must not become permission to write a volume modifier."""
from unittest.mock import Mock

import pytest

from devices.axefx3 import modifiers
from devices.axefx3.registry import Registry


@pytest.mark.parametrize("eid,pid,mode,name,label", [
    (95, 5, 6, "WAH_CONTROL", "Fast Pos"),
    (94, 5, 0, "WAH_CONTROL", "Off"),
    (102, 0, 0, "VOLUME_CONTROL", "Off"),
    (95, 5, 1, "WAH_CONTROL", None),
    (102, 0, 6, "VOLUME_CONTROL", None),
])
def test_only_observed_mode_names_are_reported(eid, pid, mode, name, label):
    words = modifiers.native_default(eid)
    words[9], words[10] = pid, mode
    result = modifiers.observed_target(Registry("32.06"), words)
    assert result["parameter"] == name
    assert result["auto_engage_name"] == label
    assert result["auto_engage_word"] == mode
    assert result["auto_engage_write_verified"] == (name == "WAH_CONTROL" and mode in (0, 6))
    assert not result["physical_bypass_verified"]


@pytest.mark.parametrize("firmware,eid,pid,count", [
    ("33.00", 95, 5, 25), ("32.06", 95, 5, 15),
    ("32.06", 103, 0, 25), ("32.06", 58, 0, 25),
    ("32.06", 102, 6, 25),
])
def test_no_extrapolation_to_other_firmware_layout_or_target(firmware, eid, pid, count):
    words = modifiers.native_default(eid)[:count]
    words[9] = pid
    assert modifiers.observed_target(Registry(firmware), words) is None


def test_named_volume_target_still_refuses_writes():
    dev = Mock()
    dev.reg = Registry("32.06")
    slots = [[0] * 25 for _ in range(32)]
    slots[0] = modifiers.native_default(102)
    slots[0][0], slots[0][9] = 13, 0
    dev.read_modifier.side_effect = lambda slot: slots[slot - 1].copy()
    entry = modifiers.inspect(dev)[0]
    assert entry["parameter"] == "VOLUME_CONTROL"
    assert not entry["target_in_write_registry"]
    assert not entry["assessed_target"]
    with pytest.raises(ValueError, match="unassessed target"):
        modifiers.preflight(dev)
    with pytest.raises(ValueError):
        modifiers.assign_existing(dev, 1, 102, 0, 12)
    with pytest.raises(ValueError):
        modifiers.allocation_frame(102)
    assert dev.reg.find_param("VOLUME", "VOLUME_CONTROL") is None
    dev._write.assert_not_called()

"""IR list imports are metadata; selector writes must preserve the mixer."""
import threading
from types import MethodType
from unittest.mock import Mock

import pytest

from devices.axefx3 import cab_selection, cab_mix, protocol
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.catalog import Catalog, wire_address
from devices.axefx3.registry import Registry
from fm9.protocol import decode_f32_septets, decode14


def test_unsupported_user3_export_is_explicit_and_atomic():
    reg=Registry('32.06')
    reg.import_cab_names('U1.0028 Existing', 'user')
    before=dict(reg.cab_catalog.names)
    with pytest.raises(ValueError,match='User bank 3, slot 1'):
        reg.import_cab_names('U1.0029 New\nU3.0001 Unsupported', 'user')
    assert reg.cab_catalog.names==before


def test_banks_and_one_based_slots_are_not_fm9_legacy_aliases():
    assert wire_address("user", 1, 1) == (2, 0)
    assert wire_address("user", 1, 512) == (2, 511)
    assert wire_address("user", 2, 1) == (2, 512)
    assert wire_address("user", 2, 512) == (2, 1023)
    assert wire_address("factory", 1, 1) == (0, 0)
    assert wire_address("factory", 2, 1024) == (1, 1023)


def test_catalog_imports_preserve_user_and_factory_and_refuse_ambiguous_names():
    reg = Registry("32.06")
    reg.import_cab_names("U1.0210 Test IR\nU2.0001 Other IR", "user")
    reg.import_cab_names("bank,slot,name\nF1,1,Factory IR\nF2,573,Test IR", "factory")
    assert reg.cab_rosters["2"]["209"] == "Test IR"
    assert reg.cab_rosters["2"]["512"] == "Other IR"
    assert reg.cab_catalog.resolve("Test IR", 2) == (2, 209, "Test IR")
    with pytest.raises(ValueError, match="ambiguous"):
        reg.cab_catalog.resolve("Test IR")
    reg.import_cab_names("U1.0002 New IR", "user", replace=True)
    assert reg.cab_rosters["2"] == {"1": "New IR"}
    assert reg.cab_rosters["1"]["572"] == "Test IR"
    assert reg.cab_catalog.position(2, 512) == "USER 2 slot 1"


@pytest.mark.parametrize("text,kind", [("U3.0001 Wrong", "user"), ("U1.0513 Wrong", "user"),
    ("F1.1025 Wrong", "factory"), ("U1.0001 Name\nU1.0001 Different", "user"),
    ("F1.0001 Wrong", "user"), ("U1.0001 Wrong", "factory"), ("empty", "user")])
def test_invalid_import_is_atomic(text, kind):
    catalog = Catalog()
    catalog.import_text("U1.0001 Original", "user")
    with pytest.raises(ValueError):
        catalog.import_text(text, kind, replace=True)
    assert catalog.names == {(2, 0): "Original"}


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(cab_selection.time, "sleep", lambda _: None)
    dev = Mock(model=16)
    dev.reg = Registry("32.06")
    dev._lock = threading.RLock()
    dev.get_channel.return_value = 0
    dev.firmware_label.return_value = "32.06"
    words = ([0, 1, 0, 0, 5, 572, 0, 0] + [65534]*4 + [32767]*4 + [0]*8
             + [0, 1, 1, 1] + [0]*78) * 4
    dev.bulk_read.side_effect = lambda eid: words.copy()
    def shown(eid, pid):
        word = words[dev.get_channel(eid)*106 + pid]
        if pid in range(8, 12): return f"{-40+40*word/65534:.2f} dB"
        if pid in range(12, 16): return f"{-100+200*word/65534:.1f}"
        return cab_mix.DISPLAY_MODES[word]
    dev.read_display_text.side_effect = shown
    def write(frame):
        assert protocol.valid_reply(frame[1:-1])
        pid = decode14(*frame[10:12])
        value = int(decode_f32_septets(frame[12:17]))
        assert frame == cab_selection.frame(62, pid, value)
        words[dev.get_channel(62)*106+pid] = value
    dev._write.side_effect = write
    dev.set_cab = MethodType(AxeFxIII.set_cab, dev)
    return dev, words


@pytest.mark.parametrize("channel", range(4))
@pytest.mark.parametrize("side", ["left", "right", "both"])
@pytest.mark.parametrize("bank,ordinal", [(0, 0), (1, 572), (2, 512)])
def test_only_requested_slots_change_and_muted_ir_stays_muted(rig, channel, side, bank, ordinal):
    dev, words = rig
    dev.get_channel.return_value = channel
    original = words.copy()
    result = dev.set_cab(62, bank, ordinal, side)
    assert result.ok, result.detail
    slots = [0, 1] if side == "both" else [0] if side == "left" else [1]
    permitted = {channel*106+p for s in slots for p in (s, s+4)}
    assert all(a == b or i in permitted for i, (a, b) in enumerate(zip(words, original)))
    assert words[channel*106+25] == 1
    assert "mute, level and pan unchanged" in result.detail


@pytest.mark.parametrize("issue", ["drop", "collateral", "channel", "dynacab", "firmware"])
def test_failed_or_unsafe_selection_cannot_succeed(rig, issue):
    dev, words = rig
    write = dev._write.side_effect
    if issue == "dynacab": words[31] = 1
    if issue == "firmware": dev.firmware_label.return_value = "32.04"
    def changed(frame):
        if issue != "drop": write(frame)
        if issue == "collateral": words[0] = 2  # LEFT changed during RIGHT edit
        if issue == "channel": dev.get_channel.return_value = 1
    dev._write.side_effect = changed
    result = dev.set_cab(62, 2, 209, "right")
    assert not result.ok
    if issue in ("dynacab", "firmware"):
        dev._write.assert_not_called()

"""Model reset, channel isolation and fail-closed selection regressions."""
import threading
from types import MethodType
from unittest.mock import Mock

import pytest

from devices.axefx3 import models, protocol
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from fm9.device import SetResult
from fm9.protocol import decode_f32_septets


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(models.time, "sleep", lambda _: None)
    def make(family, channel=0):
        base, _, stride, _ = models.LAYOUTS[family]
        # Synthetic amp layout tests the historical four-channel shape check;
        # it does not claim that 64 is a real firmware layout.
        stride = stride or 64
        names = models.roster(Registry("32.06"), family)
        words = [0] * (stride * 4)
        selector = models.SELECTORS[family]
        for c in range(4):
            words[c * stride + selector] = 1 if family == "DISTORT" else 3 if family == 'CHORUS' else 0
            words[c * stride + 1] = 12345
        dev = Mock()
        dev.reg = Registry("32.06")
        dev._lock = threading.RLock()
        dev._channels = {base: 4}
        dev.firmware_label.return_value = "32.06"
        dev.status_dump.return_value = [object()]
        dev.get_channel.return_value = channel
        dev.bulk_read.side_effect = lambda eid: words.copy()
        dev.get_param_display.return_value = 5 if family == 'FUZZ' else -6
        dev.get_bypass.return_value = True
        dev.set_bypass.return_value = True
        dev.set_param_display.return_value = SetResult(True, "readback", -6, -12)
        def write(frame):
            assert protocol.valid_reply(frame[1:-1])
            assert frame[4:12] == [16, 1, 9, 0, base, 0, selector, 0]
            word = int(decode_f32_septets(frame[12:17]))
            words[channel * stride + selector] = word
            # Selecting a model resets voicing in the addressed channel.
            words[channel * stride + 1] = 30000
        dev._write.side_effect = write
        dev.set_model = MethodType(AxeFxIII.set_model, dev)
        return dev, words, base, stride, names
    return make


@pytest.mark.parametrize("family,name", [("DISTORT", "Brit 800 2204 High"),
    ("WAH", "Cry Babe"), ("DELAY", "Analog Mono"), ("REVERB", "Plate: Small Plate"),
    ("CHORUS", "Analog Stereo"), ("FUZZ", "T808 OD"),
    ("FUZZ", "T808 Mod"), ("COMP", "Classic VCA Compressor")])
@pytest.mark.parametrize("channel", range(4))
def test_model_resets_only_target_channel_and_stays_bypassed(rig, family, name, channel):
    dev, words, eid, stride, _ = rig(family, channel)
    if family == 'CHORUS': words[channel*stride]=1
    before = words.copy()
    result = dev.set_model(family, eid, name)
    assert result.ok, result.detail
    assert words[channel * stride + 1] == 30000
    assert all(words[c*stride:(c+1)*stride] == before[c*stride:(c+1)*stride]
               for c in range(4) if c != channel)
    dev.set_bypass.assert_called_once_with(eid, True)
    assert dev.set_param_display.call_count == 2
    assert all(c.args[1] == (0 if family == 'FUZZ' else -12)
               for c in dev.set_param_display.call_args_list)
    dev.read_display_text.assert_not_called()
    dev._write.assert_called_once()


@pytest.mark.parametrize("family", models.LAYOUTS)
def test_selecting_same_model_never_resets_voicing_or_bypass(rig, family):
    dev, words, eid, _, names = rig(family)
    before = words.copy()
    result = dev.set_model(family, eid, names[str(words[models.SELECTORS[family]])])
    assert result.ok and words == before
    dev._write.assert_not_called()
    dev.set_bypass.assert_not_called()
    dev.set_param_display.assert_not_called()


@pytest.mark.parametrize("family,name", [("DISTORT", "59 Bassguy Bright"),
    ("WAH", "VX846"), ("DELAY", "Dual Delay"), ("REVERB", "Huge: Cavern"),
    ("PITCH", "Whammy"), ("CHORUS", "Digital Stereo"),
    ("FUZZ", "FAS Boost"), ("COMP", "JFET Studio Compressor")])
def test_read_inventory_does_not_authorize_uncaptured_models(rig, family, name):
    dev, _, eid, _, _ = rig("DISTORT" if family == "PITCH" else family)
    with pytest.raises(ValueError):
        dev.set_model(family, eid, name)
    dev._write.assert_not_called()
    dev.set_bypass.assert_not_called()


@pytest.mark.parametrize("issue", ["firmware", "layout", "channel", "missing_block",
    "unknown_model", "unknown_level", "bypass", "staging"])
def test_unsafe_starting_state_never_sends_model(rig, issue):
    dev, words, eid, _, _ = rig("WAH")
    if issue == "firmware": dev.firmware_label.return_value = "33.00"
    if issue == "layout": words.pop()
    if issue == "channel": dev.get_channel.return_value = None
    if issue == "missing_block": dev._channels = {}
    if issue == "unknown_model": words[0] = 999
    if issue == "unknown_level": dev.get_param_display.return_value = float("nan")
    if issue == "bypass": dev.set_bypass.return_value = None
    if issue == "staging": dev.set_param_display.return_value = SetResult(False, "failed", None, None)
    assert not dev.set_model("WAH", eid, "Cry Babe").ok
    dev._write.assert_not_called()
    assert not any(c.args == (eid, False) for c in dev.set_bypass.call_args_list)


@pytest.mark.parametrize("issue", ["dropped", "wrong_channel", "collateral", "post_level", "unbypassed"])
def test_failed_verification_cannot_be_reported_as_success(rig, issue):
    dev, words, eid, stride, _ = rig("WAH")
    original = dev._write.side_effect
    def write(frame):
        if issue != "dropped": original(frame)
        if issue == "wrong_channel": dev.get_channel.return_value = 1
        if issue == "collateral": words[stride + 1] = 7
        if issue == "post_level":
            dev.set_param_display.return_value = SetResult(False, "failed", None, None)
        if issue == "unbypassed": dev.get_bypass.return_value = False
    dev._write.side_effect = write
    result = dev.set_model("WAH", eid, "Cry Babe")
    assert not result.ok
    assert not any(c.args == (eid, False) for c in dev.set_bypass.call_args_list)


@pytest.mark.parametrize("family,target_name", [("WAH", "FAS Wah"),
    ("DELAY", "Digital Mono"), ("REVERB", "Room: Small Room"),
    ("FUZZ", "Rat Distortion"), ("COMP", "Modern VCA Compressor")])
def test_captured_effect_zero_is_a_model_write_not_an_assumed_get(rig, family, target_name):
    dev, words, eid, _, _ = rig(family)
    selector = models.SELECTORS[family]
    words[selector] = {'REVERB':9, 'FUZZ':6, 'COMP':13}.get(family,2)
    assert dev.set_model(family, eid, target_name).ok
    assert words[selector] == 0
    assert dev._write.call_args.args[0] == protocol.param_frame(eid, selector, 0, opcode=9)


def test_unknown_firmware_has_neither_read_nor_write_model_rosters():
    reg = Registry("33.00")
    for family in models.LAYOUTS:
        assert models.roster(reg, family) == {}
        assert models.roster(reg, family, selectable=True) == {}

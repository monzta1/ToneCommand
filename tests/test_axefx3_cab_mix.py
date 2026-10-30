"""IR bank/slot readback alone is not evidence of mixer membership."""
from unittest.mock import Mock

import pytest

from devices.axefx3 import cab_mix, protocol as p


def device(modes=(0, 1, 1, 1), *, channel=0, firmware="32.06"):
    dev = Mock(model=p.MODEL)
    dev.firmware_label.return_value = firmware
    dev.get_channel.return_value = channel
    words = [0] * (4 * cab_mix.STRIDE)
    base = channel * cab_mix.STRIDE
    words[base:base+8] = [2, 1, 0, 0, 27, 572, 0, 0]
    words[base+8:base+16] = [65534]*4 + [32767]*4
    words[base+24:base+28] = modes
    dev.bulk_read.return_value = words
    shown = {**{8+i: "0.00 dB" for i in range(4)},
             **{12+i: "0.0" for i in range(4)},
             **{24+i: cab_mix.DISPLAY_MODES[m] for i, m in enumerate(modes)}}
    dev.read_display_text.side_effect = lambda eid, pid: shown[pid]
    return dev, words, shown


def test_actual_322_regression_right_ir_selected_but_muted():
    dev, _, _ = device()
    mixer = cab_mix.inspect(dev, 62)
    assert mixer["supported"]
    left, right, *rest = mixer["slots"]
    assert left["in_mix"] and left["level_db"] == 0 and left["pan"] == 0
    assert right["bank"] == 1 and right["ordinal"] == 572
    assert right["muted"] and not right["in_mix"]
    assert all(not s["in_mix"] for s in rest)
    assert "MUTED" in cab_mix.selection_note(mixer, "right")
    assert "mute, level and pan unchanged" in cab_mix.selection_note(mixer, "both")
    dev._send.assert_not_called()


@pytest.mark.parametrize("channel", range(4))
def test_all_four_channels_use_their_own_offset(channel):
    dev, _, _ = device(channel=channel)
    assert cab_mix.inspect(dev, 62)["slots"][1]["muted"]


def test_solo_in_fourth_slot_excludes_first_two():
    dev, _, _ = device((0, 0, 1, 2))
    slots = cab_mix.inspect(dev, 62)["slots"]
    assert [s["in_mix"] for s in slots] == [False, False, False, True]
    assert slots[0]["status"] == "EXCLUDED BY SOLO"
    assert not slots[0]["muted"]


def test_independent_numeric_readback_not_assumed_bulk_law():
    dev, _, shown = device()
    shown[8], shown[9], shown[12], shown[13] = "-6.00 dB", "-12.00 dB", "-100.0", "100.0"
    slots = cab_mix.inspect(dev, 62)["slots"]
    assert (slots[0]["level_db"], slots[0]["pan"]) == (-6, -100)
    assert (slots[1]["level_db"], slots[1]["pan"]) == (-12, 100)


@pytest.mark.parametrize("pid,text", [(8,""),(8,"nan dB"),(8,"1.00 dB"),
    (8,"-41.00 dB"),(12,"101"),(12,"0 ms"),(25,"--")])
def test_bad_or_contradictory_display_is_unknown(pid, text):
    dev, _, shown = device()
    shown[pid] = text
    assert not cab_mix.inspect(dev, 62)["supported"]


@pytest.mark.parametrize("problem", ["firmware","model","mode","layout","channel","changed","exception"])
def test_no_silent_fm9_or_dynacab_fallback(problem):
    dev, words, _ = device()
    if problem == "firmware": dev.firmware_label.return_value = "33.00"
    if problem == "model": dev.model = 0x12
    if problem == "mode": words[31] = 1
    if problem == "layout": words.pop()
    if problem == "channel": dev.get_channel.side_effect = [0, 1]
    if problem == "changed":
        after = words.copy(); after[25] = 0
        dev.bulk_read.side_effect = [words, after]
    if problem == "exception": dev.get_channel.side_effect = RuntimeError("lost MIDI")
    result = cab_mix.inspect(dev, 62)
    assert not result["supported"] and result["slots"] == []
    assert "UNKNOWN" in cab_mix.describe(result)
    dev._send.assert_not_called()

"""Firmware-pinned model selection, read through passive bulk only.

Based on the original fork's amp_catalog/effect_catalog and independently
checked Axe-Edit captures. Individual hardware passes are recorded in docs;
Drive/Compressor first-instance channel A was replayed on 2026-10-06.
Inventory names are not blanket permission to write every model.
"""
from __future__ import annotations

import json
import math
import time
from importlib.resources import files

from fm9.device import SetResult
from . import protocol


# family: (first block, instances, words/channel, level parameter)
# The amp layout is checked from the reported four-channel block, as in the
# historical validated path. The narrower effect layouts were captured.
LAYOUTS = {"DISTORT": (58, 2, None, 21), "WAH": (94, 4, 25, 6),
           "DELAY": (70, 4, 89, 18), "REVERB": (66, 4, 71, 14),
           "CHORUS": (78, 1, 32, 11), "FUZZ": (118, 1, 44, 3),
           "COMP": (46, 1, 37, 4)}
# Compressor threshold is numeric pid 0, not its model selector.
SELECTORS = {family: (12 if family == 'COMP' else 0) for family in LAYOUTS}
CAPTURED = {"WAH": {"0": "FAS Wah", "1": "Clyde", "2": "Cry Babe"},
            "DELAY": {"0": "Digital Mono", "2": "Analog Mono"},
            "REVERB": {"0": "Room: Small Room", "9": "Plate: Small Plate"},
            "CHORUS": {"3": "Analog Stereo"},
            "FUZZ": {"0": "Rat Distortion", "6": "T808 OD", "8": "T808 Mod"},
            "COMP": {"0": "Modern VCA Compressor", "13": "Classic VCA Compressor"}}


def roster(reg, family, *, selectable=False):
    if reg.firmware != "32.06" or family not in LAYOUTS:
        return {}
    if family == "DISTORT":
        return reg.selectable_amp_models() if selectable else dict(reg.amp_roster)
    data = json.loads(files("devices.axefx3").joinpath("data", "axe_fx_iii_effect_models.json").read_text(
        encoding="utf-8"))
    entry = data["families"][family]
    if data["firmware"] != reg.firmware or entry["stride"] != LAYOUTS[family][2]:
        return {}
    names = entry["models"]
    if any(names.get(key) != value for key, value in CAPTURED[family].items()):
        return {}
    return dict(CAPTURED[family] if selectable else names)


def target(reg, family, effect_id, name):
    layout = LAYOUTS.get(family)
    if layout is None or type(effect_id) is not int or effect_id not in range(
            layout[0], layout[0] + layout[1]):
        raise ValueError("Model address is not in the verified Axe-Fx III family")
    ordinal = next((int(k) for k, v in roster(reg, family, selectable=True).items()
                    if v == name), None)
    if ordinal is None:
        raise ValueError("Model has no verified selection on this firmware")
    return ordinal


def read(dev, family, effect_id):
    """No active model queries, channel switches or assumptions on timeout."""
    layout = LAYOUTS.get(family)
    if layout is None or type(effect_id) is not int or effect_id not in range(
            layout[0], layout[0] + layout[1]):
        return None
    if dev.firmware_label() != dev.reg.firmware or not roster(dev.reg, family):
        return None
    blocks = dev.status_dump()
    if blocks is None or dev._channels.get(effect_id) != 4:
        return None
    channel = dev.get_channel(effect_id)
    words = dev.bulk_read(effect_id)
    if (type(channel) is not int or channel not in range(4) or not words
            or len(words) % 4 or len(words) // 4 <= layout[3]
            or (layout[2] is not None and len(words) != 4 * layout[2])
            or dev.get_channel(effect_id) != channel):
        return None
    stride = len(words) // 4
    ordinal = words[channel * stride + SELECTORS[family]]
    if type(ordinal) is not int or str(ordinal) not in roster(dev.reg, family):
        return None
    return {"channel": channel, "stride": stride, "words": words,
            "ordinal": ordinal, "name": roster(dev.reg, family)[str(ordinal)]}


def select(dev, family, effect_id, name):
    """Leave a changed model bypassed and quiet until explicitly voiced.

    External mute and full route/modifier preflight remain caller duties.
    Re-selecting an already matching model is deliberately a read-only no-op.
    No failure re-engages a block, resets another channel or tries an opcode.
    """
    ordinal = target(dev.reg, family, effect_id, name)
    before = read(dev, family, effect_id)
    fail = lambda detail: SetResult(False, detail,
                                    before["name"] if before else None, None)
    if before is None:
        return fail("Model/channel/layout unreadable; nothing written")
    if before["ordinal"] == ordinal:
        return SetResult(True, "Model already selected; all voicing preserved", name, name)
    channel, stride = before["channel"], before["stride"]
    base, _, _, level_pid = LAYOUTS[family]
    level_spec = dev.reg.spec(family, level_pid, effect_id - base + 1)
    level = dev.get_param_display(level_spec)
    if type(level) not in (float, int) or not math.isfinite(level):
        return fail("Level unreadable; model not changed")
    if dev.set_bypass(effect_id, True) is not True or dev.get_bypass(effect_id) is not True:
        return fail("Bypass unverified; model not changed")
    # Drive Level is a 0..10 knob, not dB. Its captured zero is the quiet
    # staging value; never encode a negative dB value into that knob.
    quiet = 0 if family == 'FUZZ' else min(level, -12.0)
    staged = dev.set_param_display(level_spec, quiet)
    if not staged.ok or dev.get_channel(effect_id) != channel:
        return fail("Quiet staging/channel unverified; model not changed, block left bypassed")
    # Compare against state AFTER our explicitly verified level staging.
    staged_state = read(dev, family, effect_id)
    if staged_state is None or staged_state["channel"] != channel:
        return fail("State changed during staging; model not changed")
    if staged_state["ordinal"] != before["ordinal"]:
        return fail("Model changed outside this request; stopped")
    dev._write(protocol.param_frame(effect_id, SELECTORS[family], ordinal, opcode=0x09))
    for _ in range(4):
        time.sleep(.15)
        after = read(dev, family, effect_id)
        if after is None:
            continue
        if after["channel"] != channel or len(after["words"]) != len(staged_state["words"]):
            break
        if any(after["words"][c*stride:(c+1)*stride] !=
               staged_state["words"][c*stride:(c+1)*stride]
               for c in range(4) if c != channel):
            return fail("Another model channel changed; stop and inspect, no further writes")
        if after["ordinal"] == ordinal:
            if dev.get_bypass(effect_id) is not True:
                return fail("Model changed bypass state; external mute must remain on")
            result = dev.set_param_display(level_spec, quiet)
            if not result.ok or dev.get_channel(effect_id) != channel:
                return fail("Model changed but quiet level did not verify; left bypassed")
            return SetResult(True, "Model and quiet level verified; left bypassed. "
                             "Voice this channel before explicitly engaging it.", before["name"], name)
    return fail("Model/channel readback failed; partial edit, block left bypassed")

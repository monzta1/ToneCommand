"""Axe-Fx III Legacy IR mixer inspection, independently read from the device.

Slot selection is NOT activation and slot 1/2 is NOT a stereo pan setting.
FW 32.06 cache section 11 and Axe-Edit/readback comparison, 2026-09-18.
Writes use the 2026-09-19 Axe-Edit captures, not inferred FM9 SET units.
No acoustic measurements or limiter claims.
"""
from __future__ import annotations

import math
import re
import time

from . import protocol as p
from . import evidence,fw33_profile


FIRMWARE = "32.06"
STRIDE = 106
MODES = {0: "normal", 1: "mute", 2: "solo"}
DISPLAY_MODES = {0: "--", 1: "MUTE", 2: "SOLO"}


def control_value(mixer, param_id):
    """Display value from an independently verified mixer snapshot."""
    if not mixer or not mixer.get('supported'):
        return None
    if param_id in range(8, 12):
        return mixer['slots'][param_id-8]['level_db']
    if param_id in range(12, 16):
        return mixer['slots'][param_id-12]['pan']
    if param_id in range(24, 28):
        return {v:k for k,v in MODES.items()}[mixer['slots'][param_id-24]['mode']]
    return None


def set_control(dev, spec, value, *, restore_word=None):
    """One exact Legacy mixer control, no hidden unmute/pan or enum fallback.

    Full-block reads detect changes outside the addressed word, including other
    channels. Exact zero is an editor-captured 01 09 SET for these fields.
    A failed verification is reported as a partial edit, never as success.
    """
    from fm9.device import SetResult
    from . import audio_safety
    fail = lambda detail, before=None, after=None: SetResult(False, detail, before, after)
    definition = evidence.AXE_FX_III_CAB_MIX_PARAMS.get(spec.name)
    error = audio_safety.parameter_error(spec, value)
    if error:
        return fail(error)
    if not definition or spec.family != 'CABINET':
        return fail('No verified Cab mixer control; nothing written')
    if (spec.dmin is None or spec.dmax is None or not spec.dmin <= value <= spec.dmax
            or (spec.kind == 'enum' and value != int(value))):
        return fail('Cab mixer value outside the verified range; nothing written')
    channel = dev.get_channel(spec.effect_id)
    error = dev._set_domain_guard(spec, channel)
    if error:
        return fail(error)
    before_words = dev.bulk_read(spec.effect_id)
    mixer = inspect(dev, spec.effect_id, words=before_words, channel=channel)
    if not mixer.get('supported'):
        return fail(mixer.get('reason', 'Cab mixer unavailable; nothing written'))
    before = control_value(mixer, spec.param_id)
    index = channel * STRIDE + spec.param_id
    if (before == value and (restore_word is None or before_words[index] == restore_word)):
        return SetResult(True, 'Cab mixer already matches, independently verified', before, before)
    if dev.get_channel(spec.effect_id) != channel:
        return fail('Cab channel changed; nothing written', before)
    # Actual captured SET domain: dB, signed pan fraction or integer mode.
    dev._param_echo(p.param_frame(spec.effect_id, spec.param_id,
                                          value / spec.set_divisor, opcode=0x09),
                    spec.effect_id, spec.param_id, timeout=.3)
    after = None
    for _ in range(4):
        time.sleep(.12)
        after_words = dev.bulk_read(spec.effect_id)
        result = inspect(dev, spec.effect_id, words=after_words, channel=channel)
        after = control_value(result, spec.param_id)
        if not result.get('supported') or len(after_words) != len(before_words):
            continue
        changed = {i for i,(a,b) in enumerate(zip(before_words, after_words)) if a != b}
        if changed - {index}:
            return fail('Cab state changed outside the requested control; stopped', before, after)
        if (after is not None and abs(after-value) <= (spec.display_tolerance or 0)
                and (restore_word is None or after_words[index] == restore_word)):
            return SetResult(True, 'Cab mixer verified by independent display and full-block readback. '
                             'Other IRs/channels unchanged; audible level not measured.', before, after)
    return fail('Cab mixer write did not verify; partial edit may remain', before, after)


def restore_control(dev, spec, word):
    from fm9.device import SetResult
    if type(word) is not int or not 0 <= word <= 65534:
        return SetResult(False, 'Invalid Cab restore word; nothing written', None, None)
    if spec.name not in evidence.AXE_FX_III_CAB_MIX_PARAMS:
        return SetResult(False, 'Unknown Cab restore control; nothing written', None, None)
    value = evidence.param_normalized_to_display(spec, word/65534, FIRMWARE)
    return set_control(dev, spec, value, restore_word=word)


def _number(text, unit, low, high):
    match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*" + unit + r"\s*", str(text))
    if not match:
        return None
    value = float(match[1])
    return value if math.isfinite(value) and low <= value <= high else None


def inspect(dev, effect_id, *, words=None, channel=None):
    try:
        return _inspect(dev, effect_id, words=words, channel=channel)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        return {"supported": False, "slots": [], "reason": "Cab mixer read failed; activation unknown."}


def _inspect(dev, effect_id, *, words=None, channel=None):
    """Read only the current channel, failing to UNKNOWN rather than 'active'.

    Enum words must agree with independent display text. Numeric readings
    use display text, not a guessed bulk taper. Read all four slots so a solo
    on slot 3/4 cannot be mistaken for an active slot 1/2. No model queries.
    """
    unknown = {"supported": False, "slots": [],
               "reason": "Cab mixer requires Axe-Fx III FW 32.06, a readable Legacy channel and independent display values."}
    if (getattr(dev, "model", None) != p.MODEL
            or effect_id not in range(62, 66)
            or dev.firmware_label() not in (FIRMWARE,fw33_profile.KEY)):
        return unknown
    if dev.firmware_label()==fw33_profile.KEY and (effect_id!=62 or getattr(dev.reg,'hardware_variant',None)!='mk2'):
        return unknown
    current = dev.get_channel(effect_id)
    if type(current) is not int or current not in range(4) or (channel is not None and channel != current):
        return unknown
    channel = current
    if words is None:
        words = dev.bulk_read(effect_id)
    if not words or len(words) != 4 * STRIDE:
        return unknown
    vals = words[channel * STRIDE:(channel + 1) * STRIDE]
    if vals[31] != 0:
        return dict(unknown, reason="Dyna-Cab mixer is not verified; Legacy IR controls are unavailable.")
    if any(type(vals[i]) is not int or vals[i] not in MODES for i in range(24, 28)):
        return unknown
    slots = []
    try:
        for index in range(4):
            mode = vals[24 + index]
            shown = str(dev.read_display_text(effect_id, 24 + index)).strip().upper()
            if shown != DISPLAY_MODES[mode]:
                return unknown
            level = _number(dev.read_display_text(effect_id, 8 + index), r"dB", -40, 0)
            pan = _number(dev.read_display_text(effect_id, 12 + index), r"", -100, 100)
            if level is None or pan is None:
                return unknown
            slots.append({"slot": index + 1, "bank": vals[index], "ordinal": vals[4 + index],
                          "mode": MODES[mode], "muted": mode == 1, "solo": mode == 2,
                          "level_db": level, "pan": pan})
        after = dev.bulk_read(effect_id)
        # Detect a channel or mixer/selection change during the reads. Do not
        # publish a mixture of before/after states from a busy MIDI controller.
        relevant = list(range(16)) + list(range(24, 28)) + [31]
        if (dev.get_channel(effect_id) != channel or not after or len(after) != len(words)
                or any(after[channel * STRIDE + i] != vals[i] for i in relevant)):
            return unknown
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        return unknown
    any_solo = any(slot["solo"] for slot in slots)
    for slot in slots:
        slot["in_mix"] = slot["solo"] if any_solo else not slot["muted"]
        slot["status"] = ("SOLO" if slot["solo"] else "MUTED" if slot["muted"]
                          else "EXCLUDED BY SOLO" if any_solo else "IN MIX")
    return {"supported": True, "channel": channel, "slots": slots,
            "note": "Mixer membership only: block bypass, routing and physical audio still matter. Slot numbers do not set stereo pan."}


def describe(mixer):
    if not mixer or not mixer.get("supported"):
        return "Cab mixer UNKNOWN: " + (mixer or {}).get("reason", "not read")
    return "; ".join(
        f"IR {s['slot']} {s.get('name', '')}: {s['status']}, "
        f"{s['level_db']:g} dB, pan {s['pan']:g} (-100=L, 0=center, +100=R)"
        for s in mixer["slots"])


def selection_note(mixer, side):
    """A successful bank/slot write must not claim the IR is sounding."""
    if not mixer.get("supported"):
        return "IR selected; mixer state UNKNOWN. Activation was not verified."
    wanted = {1, 2} if side == "both" else {1 if side == "left" else 2}
    slots = [s for s in mixer["slots"] if s["slot"] in wanted]
    return "Selection only; mute, level and pan unchanged. " + describe({"supported": True, "slots": slots})


def review(blocks, actions):
    """Snapshot evidence for review, NOT a prediction of the finished rig.

    No scene/channel switches are allowed just to fill this panel. Inactive
    channels and newly added blocks remain explicitly unknown.
    """
    cabs = {b["effect_id"]: b for b in blocks
            if b.get("family") == "CABINET" or "cab_mix" in b}
    cab_actions = [a for a in actions
                   if str(a.get("block", "")).upper() in {"CAB", "CABINET"}]
    for action in cab_actions:
        eid = action.get("effect_id") or 61 + int(action.get("instance") or 1)
        if eid not in cabs:
            cabs[eid] = {"effect_id": eid, "label": f"Cab {eid - 61}", "channel": "?"}
    reports = []
    for eid, block in cabs.items():
        related = [a for a in cab_actions
                   if (a.get("effect_id") or 61 + int(a.get("instance") or 1)) == eid]
        requested = sorted({"ABCD"[int(a["value"])] for a in related
                            if a.get("kind") == "set_channel" and a.get("value") in range(4)})
        reports.append({
            "effect_id": eid, "label": block.get("label", "Cab"),
            "channel": block.get("channel", "?"),
            "bypassed": block.get("bypassed"),
            "cab_mix": block.get("cab_mix") or {
                "supported": False, "slots": [], "reason": "Mixer not read; activation unknown."},
            "unread_channels": [c for c in requested if c != block.get("channel")],
            "selection_changes": any(a.get("kind") == "set_cab" for a in related),
        })
    return reports

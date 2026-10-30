"""Captured FW32.06 pedal operations, never generic scalar/model setters.

No MIDI CC/global mapping, curve writes, routing edits, channel changes or
flash stores. External muting is mandatory and is not a measured limiter.
"""
import time

from fm9.device import SetResult
from . import modifiers, protocol


TARGETS = {94: 5, 95: 5, 102: 0}
MODES = {"Off": 0, "Fast Pos": 6}


def validate(effect_id, source, auto_engage=None):
    if type(effect_id) is not int or effect_id not in TARGETS:
        raise ValueError("Only Wah 1/2 Control and Volume/Pan 1 Volume are captured")
    if type(source) is not int or source not in (12, 13):
        raise ValueError("Select External 1 or External 2 explicitly; no global CC mapping")
    if auto_engage is not None and (not isinstance(auto_engage, str) or auto_engage not in MODES):
        raise ValueError("Only captured Off/Fast Pos Auto Engage modes are enabled")
    if effect_id == 102 and auto_engage not in (None, "Off"):
        raise ValueError("Volume pedal must not use Auto Engage")


def allocation_frame(effect_id):
    validate(effect_id, 12)
    return protocol.envelope(1, [0x3A, 0, effect_id, 0, TARGETS[effect_id], 0] + [0] * 9)


def auto_frame(slot, mode):
    if type(mode) is not int or mode not in (0, 6):
        raise ValueError("Unverified Auto Engage SET")
    return protocol.param_frame(modifiers.slot_eid(slot), 10, mode, opcode=9)


def default_words(effect_id):
    words = modifiers.native_default(effect_id)
    words[9] = TARGETS[effect_id]
    return words


def entries(dev):
    if dev.reg.firmware != "32.06" or dev.firmware_label() != "32.06":
        from . import pedal_fw33
        if not pedal_fw33.supported(dev,94):
            raise ValueError("Pedal operations require an independently verified firmware/device profile")
    result = modifiers.inspect(dev)
    owners = set()
    for e in result:
        w = e["words"]
        if len(w) != 25:
            raise ValueError("All 32 full modifier records are required")
        if not e["active"]:
            continue
        address = (e["effect_id"], e["param_id"])
        if address in owners:
            raise ValueError("Duplicate modifier ownership; nothing written")
        owners.add(address)
        if address == (102, 0):
            if w[0] not in (12, 13) or w[1:] != default_words(102)[1:]:
                raise ValueError("Volume requires the captured full-range curve with Auto Engage Off")
        elif not e["assessed_target"] or not e["curve_structurally_usable"]:
            raise ValueError("Unassessed modifier target or curve; nothing written")
    return result


def context(dev, target, slots):
    preset = dev.current_preset()
    blocks, cells, scene = dev.status_dump(), dev.read_grid(), dev.current_scene()
    if preset is None or blocks is None or cells is None or scene is None or not any(b.effect_id == target for b in blocks):
        raise ValueError("Pedal target/scene/grid unreadable or absent")
    # Auto Engage/source changes may legitimately change only the target Wah
    # bypass state. No other topology, channel or block-state changes allowed.
    status = [(b.effect_id, b.channel, b.channels_supported,
               None if b.effect_id == target and target in (94, 95) else b.bypassed)
              for b in blocks]
    volume = None
    if target == 102 or any(e["active"] and e["effect_id"] == 102 for e in slots):
        volume = dev.bulk_read(102)
        if (not isinstance(volume, list) or len(volume) != 60
                or any(type(w) is not int or not 0 <= w <= 65534 for w in volume)
                or any(volume[c * 15 + 2] != 2 or volume[c * 15 + 6] != 52427 for c in range(4))):
            raise ValueError("Volume requires verified Type Volume and captured 0 dB Level on all channels")
    return preset, scene, cells, status, volume


def preflight(dev, effect_id, source, auto_engage=None):
    validate(effect_id, source, auto_engage)
    if dev.reg.firmware != '32.06':
        from . import pedal_fw33
        if not pedal_fw33.supported(dev,effect_id):
            raise ValueError('Requested Wah/Volume binding is outside the measured FW33 hardware profile')
    slots = entries(dev)
    matches = [e for e in slots if (e["effect_id"], e["param_id"]) == (effect_id, TARGETS[effect_id])]
    if len(matches) > 1 or (matches and not matches[0]["active"]):
        raise ValueError("Existing inactive/duplicate target must be reviewed, not overwritten")
    if matches and (matches[0]["source"] not in (12, 13)
                    or matches[0]["words"][10] not in (0, 6)):
        raise ValueError("Existing pedal source/mode is outside the captured profile")
    if not matches and not any(e["source"] == e["effect_id"] == 0 for e in slots):
        raise ValueError("No unassigned modifier slot")
    return slots, context(dev, effect_id, slots), matches[0]["slot"] if matches else None


def bind(dev, effect_id, source, auto_engage=None):
    slots, before_context, slot = preflight(dev, effect_id, source, auto_engage)
    def write(frame):
        if dev.reg.firmware == '32.06':
            dev._write(frame)
        else:
            from .pedal_fw33 import Operation
            Operation(dev,effect_id).write(frame)
    wanted = [e["words"].copy() for e in slots]
    if slot is None:
        write(allocation_frame(effect_id))
        for _ in range(4):
            time.sleep(.15)
            after = modifiers.inspect(dev)
            changed = [i for i, e in enumerate(after) if e["words"] != wanted[i]]
            if not changed:
                continue
            if (len(changed) != 1 or wanted[changed[0]][0] != 0 or wanted[changed[0]][8] != 0
                    or after[changed[0]]["words"] != default_words(effect_id)):
                return SetResult(False, "Native allocation changed unexpected data; stopped", None, None)
            slot = changed[0] + 1
            wanted[slot - 1] = after[slot - 1]["words"].copy()
            break
        if slot is None:
            return SetResult(False, "Native allocation not verified; no retry or source write", None, None)
    updates = [(0, source)]
    if auto_engage is not None and effect_id != 102:
        updates.append((10, MODES[auto_engage]))
    for pid, value in updates:
        if context(dev, effect_id, slots) != before_context:
            return SetResult(False, "Pedal context changed; stopped", None, None)
        if [e["words"] for e in modifiers.inspect(dev)] != wanted:
            return SetResult(False, "Modifier state changed before write; stopped", None, None)
        if wanted[slot - 1][pid] == value:
            continue
        frame = modifiers.source_frame(slot, value) if pid == 0 else auto_frame(slot, value)
        previous = [w.copy() for w in wanted]
        write(frame)
        wanted[slot - 1][pid] = value
        matched = False
        for _ in range(4):
            time.sleep(.15)
            actual = [e["words"] for e in modifiers.inspect(dev)]
            if actual == wanted:
                matched = True
                break
            if actual != previous:
                return SetResult(False, "Modifier curve/another slot changed; stopped", None, None)
        if not matched:
            return SetResult(False, "Pedal write not independently verified; stopped", None, None)
    if context(dev, effect_id, slots) != before_context:
        return SetResult(False, "Final pedal context differs; stopped", None, None)
    if [e["words"] for e in modifiers.inspect(dev)] != wanted:
        return SetResult(False, "Final modifier state differs; stopped", None, None)
    return SetResult(True, "Complete modifier readback matched; physical sweep/bypass unverified", None, slot)


def execute(dev, requests, *, expected_preset, external_audio_muted):
    """Pedal-only review seam. Preserve arbitrary existing routing exactly.

    This does not enable parallel-grid reconstruction or general plan writes.
    Every request is checked before the first write. Not a server/GUI endpoint.
    """
    if external_audio_muted is not True or type(expected_preset) is not int:
        raise PermissionError("Explicit target and external mute acknowledgement required")
    if not isinstance(requests, list) or not 1 <= len(requests) <= 3:
        raise ValueError("Provide one to three explicit pedal requests")
    seen = set()
    with dev._lock:
        needed = 0
        for r in requests:
            if not isinstance(r, dict) or not {"effect_id", "source"} <= r.keys() or r.keys() - {"effect_id", "source", "auto_engage"}:
                raise ValueError("Unrecognized pedal request fields")
            slots, _, slot = preflight(dev, **r)
            needed += slot is None
            if r["effect_id"] in seen:
                raise ValueError("Duplicate pedal request")
            seen.add(r["effect_id"])
        if needed > sum(e["source"] == e["effect_id"] == 0 for e in slots):
            raise ValueError("Insufficient unassigned slots for the complete request")
        results = []
        with dev.edit_session(external_audio_muted=True, expected_preset=expected_preset):
            for r in requests:
                try:
                    result = dev.bind_pedal_control(**r)
                except (OSError, RuntimeError, ValueError, KeyError) as exc:
                    result = SetResult(False, f"Pedal execution stopped: {exc}", None, None)
                results.append(result)
                if not result.ok:
                    break
        return {"ok": len(results) == len(requests) and all(r.ok for r in results),
                "results": results, "skipped": len(requests) - len(results), "stored": False,
                "physical_pedal_verified": False,
                "recovery": "Partial edit-buffer changes may remain; keep audio muted. No automatic rollback."}

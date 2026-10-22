"""Modifier inspection and narrowly captured Wah source operations.

The old from-scratch fallback omitted unknown transfer-curve fields. That is
not evidence of a working expression pedal. Never synthesize such a curve.
"""
import time

from fm9.device import SetResult
from . import protocol, audio_safety

SOURCE_NAMES = {0: "NONE", 10: "Pedal 1", 11: "Pedal 2", 12: "External 1", 13: "External 2"}
FIELDS = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14)


def allocation_frame(effect_id):
    """FW 32.06 Axe-Edit native allocation, only Wah 1/2 Control.

    This asks the device to initialize its own modifier. It never sends
    synthesized curve fields or a guessed modifier-slot number.
    """
    if type(effect_id) is not int or effect_id not in (94, 95):
        raise ValueError("Native allocation captured only for Wah 1/2 Control")
    return protocol.envelope(1, [0x3A, 0, effect_id, 0, 5, 0] + [0] * 9)


def native_default(effect_id):
    """Comparison evidence only. These words must NEVER be transmitted."""
    return [0, 0, 65534, 0, 32767, 65534, 32767, 66, effect_id, 5,
            0, 0, 0, 32767, 32767, 66, 0, 0, 0, 0, 0, 65534, 65534, 0, 0]


def create_wah(dev, effect_id, source):
    """Experimental native creation, not an enabled planner capability.

    A failed allocation may remain in the edit buffer. Never allocate again
    after a failed read, and never overwrite an existing/inactive target.
    """
    frame = allocation_frame(effect_id)
    source_frame(1, source)  # Validate before any write; slot is chosen by the device.
    if dev.reg.firmware != "32.06":
        raise ValueError("Native modifier allocation requires captured firmware 32.06")
    before = preflight(dev)
    if any(len(e["words"]) != 25 for e in before):
        raise ValueError("Native allocation requires all 32 complete 25-word records")
    if any(e["effect_id"] == effect_id and e["param_id"] == 5 for e in before):
        raise ValueError("Wah Control already has a record; do not recreate its curve")
    if not any(e["source"] == e["effect_id"] == 0 for e in before):
        raise ValueError("No unassigned modifier slot; nothing written")
    blocks = dev.status_dump()
    scene, cells = dev.current_scene(), dev.read_grid()
    if (blocks is None or not any(b.effect_id == effect_id for b in blocks)
            or scene is None or cells is None):
        raise ValueError("Wah block/scene/grid unreadable or missing; nothing written")
    dev._write(frame)
    allocated = None
    for _ in range(4):
        time.sleep(.15)
        after = inspect(dev)
        changed = [(b, a) for b, a in zip(before, after) if b["words"] != a["words"]]
        if not changed:
            continue
        if len(changed) != 1:
            return SetResult(False, "Unexpected modifier-slot changes; stopped", None, None)
        old, new = changed[0]
        if (old["source"] != 0 or old["effect_id"] != 0
                or new["words"] != native_default(effect_id)):
            return SetResult(False, "Native modifier defaults differ from capture; source not written", None, new["words"])
        allocated = new
        break
    if allocated is None:
        return SetResult(False, "Native allocation not verified; source not written", None, None)
    if (dev.status_dump() != blocks or dev.current_scene() != scene or dev.read_grid() != cells):
        return SetResult(False, "Block/scene/grid changed during allocation; source not written", None, None)
    slot = allocated["slot"]
    dev._write(source_frame(slot, source))
    wanted = [e["words"].copy() for e in after]
    wanted[slot - 1][0] = source
    for _ in range(4):
        time.sleep(.15)
        actual = [e["words"] for e in inspect(dev)]
        if actual == wanted:
            if dev.status_dump() != blocks or dev.current_scene() != scene or dev.read_grid() != cells:
                return SetResult(False, "Block/scene/grid changed; stopped", None, None)
            return SetResult(True, "Device-built modifier and source verified; physical pedal unverified", None, slot)
        # An unchanged source can be a delayed write, but collateral changes cannot.
        waiting = [w.copy() for w in wanted]
        waiting[slot - 1][0] = 0
        if actual != waiting:
            return SetResult(False, "Modifier curve/other slots changed unexpectedly; stopped", None, None)
    return SetResult(False, "Source write not independently verified; stopped", None, None)


def slot_eid(slot):
    if type(slot) is not int or slot not in range(1, 33):
        raise ValueError("Modifier slot must be an integer 1..32")
    return slot + 2


def curve_usable(words):
    return (isinstance(words, list) and len(words) >= 15
            and all(type(w) is int and 0 <= w <= 65534 for w in words)
            and words[1] != words[2] and len({words[3], words[4], words[5]}) > 1)


def observed_target(reg, words):
    """Read-only labels paired with Axe-Edit on FW32.06 and exact FW33/MK2.

    In Volume/Pan 1, PID 0 is Volume, NOT a model selector. Naming that
    observed target never adds a writable spec or authorizes an allocation.
    Volume has a separate full-range, Type Volume,0dB acceptance boundary.
    Mode labels alone are not SET evidence. Off/Fast Pos have a separate
    bounded setter capture and replay; physical bypass remains unverified.
    """
    from . import fw33_profile,pedal_fw33
    modern = (reg.firmware == fw33_profile.KEY and pedal_fw33.RELEASED
              and getattr(reg,'hardware_variant',None) == 'mk2')
    if (reg.firmware != "32.06" and not modern) or len(words) != 25:
        return None
    target = (words[8], words[9])
    name = {(94, 5): "WAH_CONTROL", (95, 5): "WAH_CONTROL",
            (102, 0): "VOLUME_CONTROL"}.get(target)
    modern_targets={(94,5),(95,5)}
    if pedal_fw33.VOLUME_RELEASED:modern_targets.add((102,0))
    if modern and target not in modern_targets:
        return None
    if name is None:
        return None
    modes = {0: "Off", 6: "Fast Pos"} if name == "WAH_CONTROL" else {0: "Off"}
    return {"parameter": name, "auto_engage_word": words[10],
            "auto_engage_name": modes.get(words[10]),
            "auto_engage_write_verified": name == "WAH_CONTROL" and words[10] in (0, 6),
            "physical_bypass_verified": False}


def inspect(dev):
    """Read all slots without changing scenes/channels or asking a model GET."""
    entries = []
    for slot in range(1, 33):
        words = dev.read_modifier(slot)
        if not isinstance(words, list) or len(words) < 15 or any(type(w) is not int or not 0 <= w <= 65534 for w in words):
            raise ValueError(f"Modifier slot {slot} unreadable; do not execute a build")
        source, eid, pid = words[0], words[8], words[9]
        family = dev.reg.family_of_effect_id(eid)
        spec = None
        if family:
            try:
                spec = dev.reg.spec(family[0], pid, family[1])
            except (ValueError, KeyError):
                pass
        active = source != 0
        assessed = bool(spec is not None and not audio_safety.modifier_error(spec))
        observed = observed_target(dev.reg, words)
        # The separately measured FW33 modifier target does not imply a
        # scalar Control setter or an arbitrary controller parameter.
        assessed = assessed or bool(observed and observed['parameter']=='WAH_CONTROL')
        entries.append({"slot": slot, "source": source,
                        "source_name": SOURCE_NAMES.get(source, f"Source {source}"),
                        "effect_id": eid, "param_id": pid, "active": active,
                        "empty": source == eid == pid == 0,
                        "parameter": spec.name if spec else (observed or {}).get("parameter"),
                        "observed_target": observed,
                        "target_in_write_registry": spec is not None,
                        "curve_structurally_usable": curve_usable(words),
                        "assessed_target": assessed,
                        "physical_pedal_verified": False, "words": words})
    return entries


def preflight(dev):
    entries = inspect(dev)
    for item in entries:
        if item["active"] and (not item["assessed_target"] or not item["curve_structurally_usable"]):
            raise ValueError(f"Modifier {item['slot']} has an unassessed target/curve; build refused")
    return entries


def source_frame(slot, source):
    if type(source) is not int or source not in (12, 13):
        raise ValueError("Only captured External 1/2 source reassignment is enabled")
    return protocol.param_frame(slot_eid(slot), 0, source, opcode=9)


def assign_existing(dev, slot, target_effect_id, target_param_id, source_ordinal):
    frame = source_frame(slot, source_ordinal)
    entries = preflight(dev)
    entry = entries[slot - 1]
    if (type(target_effect_id) is not int or target_effect_id not in range(94, 98)
            or type(target_param_id) is not int or target_param_id != 5):
        raise ValueError("Only an existing Wah Control binding can be reassigned")
    before = entry["words"]
    if (not entry["active"] or (before[8], before[9]) != (target_effect_id, target_param_id)
            or not entry["curve_structurally_usable"]):
        return SetResult(False, "No existing usable Wah binding. A device-built curve must be captured and tested; "
                         "no partial default curve was written.", before[0], None)
    if any(e["active"] and e["slot"] != slot and (e["effect_id"], e["param_id"]) == (target_effect_id, target_param_id)
           for e in entries):
        return SetResult(False, "Duplicate controllers own Wah Control; nothing written", before[0], None)
    if before[0] == source_ordinal:
        return SetResult(True, "Source already matches; physical mapping/sweep unverified", before[0], before[0])
    dev._write(frame)
    for _ in range(4):
        time.sleep(.15)
        after = dev.read_modifier(slot)
        if not after or len(after) != len(before):
            continue
        if after[1:] != before[1:]:
            return SetResult(False, "Modifier curve/target changed unexpectedly; stopped", before[0], after[0])
        if after[0] == source_ordinal:
            return SetResult(True, "Source independently verified; curve unchanged. Physical mapping/sweep unverified.",
                             before[0], after[0])
    return SetResult(False, "Source write not verified; stop the build", before[0], None)

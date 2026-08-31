"""Writing to a preset SLOT: erasing one, and renaming one.

Both go through a store, which is the only way anything here reaches flash,
and both are therefore gated by the store whitelist and verified after a
reload rather than on the way past.

ERASING

This is the second irreversible operation in the product, and unlike the first
it destroys rather than overwrites: a store replaces a preset with the one you
are holding, and this replaces it with nothing. There is no undo, no snapshot,
and no copy kept anywhere. Treat every line here as load-bearing.

WHAT AN EMPTY SLOT ACTUALLY IS

Not "a preset with no blocks". The FM9 marks a cleared slot in its NAME field:
`"<EMPTY>\\0"` written over the FIRST 8 BYTES of the 32-byte field, with the
tail of the previous name left behind in flash as a ghost (PROTOCOL.md finding
14, verified over all 512 slots on fw 12.00). A slot whose grid is empty but
whose name still reads `Vibroverb` is not empty to the device, to FM9-Edit, or
to `first_empty_slot`. So all three parts are written: the grid is emptied, the
scene names are blanked, and the marker goes into the name.

WHY THE VERIFICATION RELOADS

Finding 16: modifier slots are validated at preset load, and an incomplete
write reads healthy immediately, survives a store, and is found undone after
the preset reloads. The same discipline applies to anything this project
stores. An immediate read-back races the device's own validation pass, so a
clear is only believed after selecting away and selecting back.

GATES

- the slot must be in the store whitelist, enforced by `store_preset` itself
  rather than re-implemented here, because a second copy of a safety boundary
  is a second thing to get wrong
- the caller is handed the slot's current name BEFORE anything happens
  (`describe`), so a confirmation can say what is about to be lost by name
- refuses a slot the device already reports as empty, which is not an error
  worth a destructive write

RENAMING

A rename is not a text edit: the FM9 keeps the name in the preset, so changing
it means selecting the preset, setting the name on the buffer, and storing the
whole thing back. That makes it a flash write with all the same gates, and it
is why the slot is selected fresh first rather than storing whatever happened
to be loaded.
"""
from __future__ import annotations

import time

from fm9 import protocol as p

SETTLE = 0.25
#: Somewhere to park while the target reloads. Any slot other than the target
#: works; slot 0 is used because it always exists.
PARK = 0


def describe(dev, slot: int) -> dict:
    """What is in the slot, read without loading it (finding 15).

    Called before the confirmation so the owner is told what they are about to
    destroy, by name. `slot_name` answers from flash and leaves the loaded
    preset and the edit buffer alone.
    """
    got = dev.slot_name(slot)
    if got is None:
        return {"ok": False, "slot": slot, "label": p.slot_label(slot),
                "detail": f"slot {p.slot_label(slot)} did not answer"}
    return {"ok": True, "slot": slot, "label": got.label, "name": got.name,
            "ghost": got.ghost, "empty": got.empty}


def clear(dev, slot: int) -> dict:
    """Empty a preset slot permanently. Returns a report; raises PermissionError
    only from the store whitelist, which is the caller's to surface.
    """
    before = describe(dev, slot)
    if not before["ok"]:
        return {"ok": False, "detail": before["detail"]}
    if before["empty"]:
        return {"ok": False, "slot": slot, "label": before["label"],
                "detail": f"slot {before['label']} already reads <EMPTY>; "
                          f"nothing to clear"}

    steps = [f"clearing {before['label']}: {before['name']!r}"]
    landed = dev.select_preset(slot)
    time.sleep(SETTLE * 2)
    # The select decides which preset every write below edits. A dropped bank
    # or program change would leave someone else's preset in the buffer and
    # this would then clear THAT one, permanently. Confirm the unit agrees.
    if landed is None or landed[0] != slot:
        return {"ok": False, "slot": slot, "label": before["label"],
                "steps": steps,
                "detail": (f"refusing to clear: asked for {before['label']} "
                           f"but the unit reports {landed!r} loaded. Not "
                           f"erasing a preset that was never confirmed.")}

    cells = dev.read_grid() or []
    for c in sorted(cells, key=lambda c: (c.col, c.row)):
        dev.place_block(c.row + 1, c.col + 1, 0)
        time.sleep(0.18)
    steps.append(f"emptied {len(cells)} grid cells")

    for scene in range(1, 9):
        dev.rename_scene(scene, "")
        time.sleep(0.12)
    steps.append("blanked all eight scene names")

    dev.rename_preset(p.EMPTY_SLOT_NAME)
    time.sleep(SETTLE)
    steps.append(f"wrote the {p.EMPTY_SLOT_NAME} marker into the name field")

    dev.store_preset(slot)          # whitelist enforced in there, not here
    steps.append(f"stored to {before['label']} - this is the irreversible part")

    # Finding 16: an immediate read-back races the device's validation pass.
    # Select away and back before believing any of it.
    dev.select_preset(PARK if slot != PARK else 1)
    time.sleep(SETTLE * 2)
    dev.select_preset(slot)
    time.sleep(SETTLE * 2)
    after = describe(dev, slot)
    grid_after = dev.read_grid() or []
    ok = bool(after.get("empty")) and not grid_after
    steps.append(f"reloaded: name {after.get('name')!r}, "
                 f"{len(grid_after)} grid cells")

    return {
        "ok": ok, "slot": slot, "label": before["label"],
        "was": before["name"], "steps": steps,
        "name": after.get("name"), "ghost": after.get("ghost"),
        "cells": len(grid_after),
        "detail": (f"{before['label']} is now empty. It read "
                   f"{before['name']!r}; that preset is gone and there is no "
                   f"copy of it here."
                   if ok else
                   f"clear did not take: after a reload the slot reads "
                   f"{after.get('name')!r} with {len(grid_after)} grid cells. "
                   f"The preset may be damaged rather than cleared; check it "
                   f"on the unit."),
    }


MAX_NAME = 32          # the FM9's preset name field


def rename(dev, slot: int, new_name: str) -> dict:
    """Give a stored preset a different name.

    Reaches flash, because the name lives in the preset rather than beside it.
    The slot is selected fresh before anything is written, so the store puts
    that preset back with a new name rather than baking in whatever edit
    buffer happened to be loaded.
    """
    name = (new_name or "").strip()
    if not name:
        return {"ok": False, "detail": "a preset needs a name; nothing was sent"}
    if len(name) > MAX_NAME:
        return {"ok": False,
                "detail": f"{name!r} is {len(name)} characters; the FM9's name "
                          f"field holds {MAX_NAME}"}
    before = describe(dev, slot)
    if not before["ok"]:
        return {"ok": False, "detail": before["detail"]}
    if before["name"] == name:
        return {"ok": False, "slot": slot, "label": before["label"],
                "detail": f"{before['label']} is already called {name!r}"}

    steps = [f"renaming {before['label']}: {before['name']!r} -> {name!r}"]
    landed = dev.select_preset(slot)
    time.sleep(SETTLE * 2)
    # Same reason as the erase: a dropped program change would leave someone
    # else's preset in the buffer, and the store below would then write it
    # over this slot under the new name.
    if landed is None or landed[0] != slot:
        return {"ok": False, "slot": slot, "label": before["label"],
                "steps": steps,
                "detail": (f"refusing to rename: asked for {before['label']} "
                           f"but the unit reports {landed!r} loaded.")}

    dev.rename_preset(name)
    time.sleep(SETTLE)
    dev.store_preset(slot)          # whitelist enforced in there, not here
    steps.append(f"stored to {before['label']}")

    # Finding 16 again: read it back only after a reload.
    dev.select_preset(PARK if slot != PARK else 1)
    time.sleep(SETTLE * 2)
    dev.select_preset(slot)
    time.sleep(SETTLE * 2)
    after = describe(dev, slot)
    ok = after.get("name") == name
    steps.append(f"reloaded: name {after.get('name')!r}")
    return {"ok": ok, "slot": slot, "label": before["label"],
            "was": before["name"], "name": after.get("name"), "steps": steps,
            "detail": (f"{before['label']} is now {name!r}"
                       if ok else
                       f"rename did not take: after a reload the slot reads "
                       f"{after.get('name')!r}. Check it on the unit.")}

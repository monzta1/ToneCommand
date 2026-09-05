"""Build a working chain into an empty preset slot, from nothing.

An empty FM9 slot is emptier than it looks: no grid cells at all, and no Input
or Output blocks either (PROTOCOL.md finding 18). There is nothing to splice
into and nothing to replace, which is why `add_block` cannot serve one and why
splicing cannot either: both displace or overwrite a cell that has to already
exist. So this places the whole chain and draws every cable itself.

This lived in `tools/build_from_scratch.py` and could therefore only ever be
run from a terminal (issue #36): `pyproject` ships `fm9` and `server`, not
`tools`, so nothing shipped could import it. Someone who selected an empty slot
in the app was told, correctly, that there was nothing to place a block onto,
and then had nowhere to go. The logic is unchanged and hardware proven; it is
just reachable now.

SAFETY, unchanged from the CLI:

- it ALWAYS lands on a slot the device itself reports as <EMPTY>, and refuses
  outright when there is no free slot. It will not pick a preset someone owns
  and it takes no force flag.
- EDIT BUFFER ONLY. Nothing is stored, so the slot's stored name stays <EMPTY>
  and re-selecting any preset discards the build. Storing is a separate,
  whitelisted operation on purpose.
- the blocks arrive at factory defaults and will sound plain until voiced.
  Audible is the claim being made, not good.
"""
from __future__ import annotations

import time

from fm9 import protocol as p
from fm9.signal_path import scene_alive

# Consecutive columns on display row 3: cables only ever run to the next
# column, and shunts cannot be inserted (PROTOCOL.md finding 8), so a gap
# would need a unity Volume block as a hop rather than a shunt.
ROW = 3
CHAIN = [(37, "INPUT"), (58, "amp"), (62, "cab"), (42, "OUTPUT")]
SETTLE = 0.4


def _refused(detail: str, steps: list[str]) -> dict:
    """A refusal carries the same keys as a success.

    A report whose shape depends on its outcome makes every caller write
    `.get` and guess, and the CLI raised KeyError on three refusal paths
    because of exactly that.
    """
    return {"ok": False, "detail": detail, "steps": steps, "slot": None,
            "slot_label": None, "cells": [], "bypassed": [], "alive": False,
            "why": detail, "undecoded": []}


def build(dev, reg, slot: int | None = None,
          search: tuple[int, int] = (0, 511),
          chain: list[tuple[int, str]] | None = None,
          bypass: set[int] = frozenset(),
          into_current: bool = False) -> dict:
    """Place a chain into an empty slot and cable it.

    Defaults to INPUT -> amp -> cab -> OUTPUT. A richer starter template passes
    its own `chain` and the `bypass` set of effect ids to leave bypassed (laid
    but silent until the tone calls for them); see fm9/starter_template.py.

    Placing left to right on an EMPTY grid never slides a neighbour, so no
    splices happen here however long the chain is - which is the whole point of
    the template: the splice-timing path (#46) is sidestepped entirely.

    Returns a report; raises nothing for a refusal. `steps` is a running
    account suitable for showing someone, because this switches the loaded
    preset out from under them and they are owed the detail.
    """
    chain = list(chain) if chain is not None else CHAIN
    steps: list[str] = []
    held = dev.current_preset()

    if into_current:
        # No free slot to land on (the unit is full): make a blank canvas out of
        # the CURRENTLY loaded preset's edit buffer instead. Edit buffer only,
        # so the stored preset is untouched and re-selecting it brings it back.
        if held is None:
            return _refused("refusing to build: no preset is loaded to clear",
                            steps)
        target_number, target_label = held[0], p.slot_label(held[0])
        steps.append(f"clearing the loaded preset {target_label} ({held[1]!r}) "
                     f"to a blank canvas in the edit buffer; nothing stored, so "
                     f"re-selecting it restores it")
        for c in sorted(dev.read_grid() or [], key=lambda c: (c.col, c.row),
                        reverse=True):
            dev.place_block(c.row + 1, c.col + 1, 0)   # clear frees cell + cables
            time.sleep(SETTLE)
    else:
        try:
            target = (dev.require_empty_slot(slot) if slot is not None
                      else dev.first_empty_slot(*search))
        # RuntimeError, not its subclasses: NoEmptySlot and FM9NotFound are both
        # RuntimeError, but _request raises the bare parent on a device NACK, and
        # naming only the children let that escape as a traceback where a refusal
        # belongs.
        except (RuntimeError, ValueError) as exc:
            return _refused(f"refusing to build: {exc}", steps)

        target_number, target_label = target.number, target.label
        steps.append(f"target: slot {target.label}, reported {target.name!r} by "
                     f"the device"
                     + (f" (ghost {target.ghost!r})" if target.ghost else ""))
        if held:
            steps.append(f"leaving preset {p.slot_label(held[0])} ({held[1]!r}); "
                         f"its edit buffer is discarded by the switch")

        # The select decides which preset every insert below edits. A dropped
        # bank or program change would leave the owner's loaded preset in the
        # buffer, and the verification afterwards would still pass because it
        # reads back what it just wrote. Confirm the unit agrees first.
        landed = dev.select_preset(target.number)
        time.sleep(SETTLE)
        if landed is None or landed[0] != target.number:
            return _refused(
                f"refusing to build: asked for slot {target.label} but the unit "
                f"reports {landed!r} loaded. Not editing a preset that was never "
                f"checked as empty.", steps)

    for col, (eid, label) in enumerate(chain, start=1):
        dev.place_block(ROW, col, eid)
        time.sleep(SETTLE)
        steps.append(f"placed {label} (eid {eid}) at row {ROW} col {col}")
    for col in range(1, len(chain)):
        dev.connect_cells(ROW, col, ROW)
        time.sleep(SETTLE)
        steps.append(f"cabled ({ROW},{col}) -> ({ROW},{col + 1})")
    # Optional starter blocks are laid but bypassed, so an unused template
    # block is silent until the tone un-bypasses it.
    for eid, label in chain:
        if eid in bypass:
            dev.set_bypass(eid, True)
            time.sleep(SETTLE)
            steps.append(f"bypassed {label} (eid {eid}); optional starter block")

    time.sleep(SETTLE)
    cells = sorted(dev.read_grid() or [], key=lambda c: (c.col, c.row))
    placed = {c.effect_id for c in cells}
    missing = [label for eid, label in chain if eid not in placed]
    blocks = {b.effect_id: b for b in dev.status_dump() or []}
    bypassed = [label for eid, label in chain
                if eid in blocks and blocks[eid].bypassed]
    # Membership is not a path. A block sitting on the cursor cell at row 1
    # col 1 is "present" and un-starved while being nowhere near the signal,
    # the silent-scene class this project has been bitten by repeatedly.
    alive, why = scene_alive(cells, blocks, reg)

    problems = []
    if missing:
        problems.append(f"never landed: {', '.join(missing)}")
    if not alive:
        problems.append(f"no live signal path: {why}")

    ok = not problems
    flash_note = ("the loaded preset's edit buffer (nothing stored; re-select "
                  "it to restore)" if into_current
                  else f"slot {target_label}, edit buffer only, nothing stored, "
                       f"so the slot still reads <EMPTY> in flash")
    return {
        "ok": ok,
        "slot": target_number,
        "slot_label": target_label,
        "steps": steps,
        "cells": [{"row": c.row + 1, "col": c.col + 1,
                   "effect_id": c.effect_id, "shunt": c.is_shunt,
                   "in_mask": c.cable_in_mask} for c in cells],
        "bypassed": bypassed,
        "alive": alive,
        "why": why,
        # Say what the simulator did NOT vouch for. Silence would read as "all
        # verified" when some of it was modelled rather than proven.
        "undecoded": sorted(getattr(getattr(dev, "sim_core", None),
                                    "undecoded", []) or []),
        "detail": (f"live signal path confirmed: {why}. Built into {flash_note}. "
                   f"The blocks are at factory defaults: play it, your ears "
                   f"outrank every read path here."
                   if ok else "; ".join(problems)),
    }

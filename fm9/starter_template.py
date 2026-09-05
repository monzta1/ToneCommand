"""The prebuilt starter template (issue #47, lever 1).

A from-empty build used to lay a bare INPUT -> amp -> cab -> OUTPUT chain and
then let the planner splice in whatever else the tone needed. Each of those
add_block splices is the slow, timing-fragile path (#46): clear a cell, slide
its neighbours, redraw cables, poll the grid.

The template lays the blocks a build almost always wants ALL AT ONCE, left to
right on the empty grid, so no cell ever slides and no splice ever happens. The
blocks a given tone does not use are laid bypassed (silent pass-through) rather
than removed. The planner is then told these blocks are already present, so it
voices them with set_type / set_param / set_bypass instead of adding them.

Nothing here is a stored .syx: the chain is laid and verified on the real unit
every build (read_grid + scene_alive), exactly the way scratch_build already
lays its four blocks, so it cannot drift out of step with the firmware.
"""
from __future__ import annotations

from fm9 import scratch_build

# effect id, label. One row, left to right, in signal order. Instance-1 effect
# ids from the registry (EFFECT_ID_BASE): INPUT 37, FUZZ/drive 118,
# DISTORT/amp 58, CABINET/cab 62, DELAY 70, REVERB 66, OUTPUT 42.
#
# No separate GATE block: the INPUT block carries its own noise gate (what
# "tighten the gate for drop C" adjusts), so a standalone GATE would duplicate
# it and spend a block for nothing.
TEMPLATE_CHAIN: list[tuple[int, str]] = [
    (37, "INPUT"),
    (118, "DRIVE"),
    (58, "amp"),
    (62, "cab"),
    (70, "DELAY"),
    (66, "REVERB"),
    (42, "OUTPUT"),
]

# Laid but bypassed until a tone calls for them. The core INPUT -> amp -> cab
# -> OUTPUT stays on; a plain tone through the template is exactly the old
# four-block chain, with the extras waiting one un-bypass away.
OPTIONAL_EIDS: frozenset[int] = frozenset({118, 70, 66})

# What the template guarantees is already on the grid, so a build voices these
# instead of adding them.
TEMPLATE_EIDS: frozenset[int] = frozenset(eid for eid, _ in TEMPLATE_CHAIN)


def lay(dev, reg, slot: int | None = None,
        search: tuple[int, int] = (0, 511)) -> dict:
    """Lay the starter template into an empty slot. Same report shape and same
    safety as scratch_build.build (empty-slot only, edit buffer only)."""
    return scratch_build.build(dev, reg, slot=slot, search=search,
                               chain=TEMPLATE_CHAIN, bypass=OPTIONAL_EIDS)


def has_block(eid: int) -> bool:
    """Whether the template already provides this block, so the planner should
    voice it rather than add_block it."""
    return eid in TEMPLATE_EIDS


def roster_text() -> str:
    """A one-line-per-block description of the laid template for the planner's
    device-state on an empty build, so it voices these blocks (un-bypass +
    set_type + set_param) instead of emitting add_block for them."""
    lines = ["Starter template already on the grid (voice these, do not "
             "add_block them):"]
    for eid, label in TEMPLATE_CHAIN:
        state = "bypassed, un-bypass to use" if eid in OPTIONAL_EIDS else "on"
        lines.append(f"  {label} ({state})")
    lines.append("add_block ONLY for a block not in this list (e.g. pitch, "
                 "chorus, wah).")
    return "\n".join(lines)

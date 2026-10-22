"""Fail-closed preconditions for AFX3 automated builds. No device writes.

Routing is a topology check, NOT proof of transparent bypass or audible sound.
External muting must cover the entire transaction, including scene transitions.
There is no verified device-wide mute/limiter in this implementation.
"""
from __future__ import annotations

import re

from fm9 import protocol as p
from . import audio_safety
from .evidence import AXE_FX_III_CAB_MIX_PARAMS


class GuardError(ValueError):
    pass


def needs_staging(actions: list[dict]) -> bool:
    kinds = {a.get("kind") for a in actions}
    return bool(any(a.get('kind') == 'set_param'
                    and a.get('param') in AXE_FX_III_CAB_MIX_PARAMS for a in actions)
                or kinds & {"set_type", "add_block", "set_channel"}
                or ("set_scene" in kinds and kinds & {
                    "set_param", "set_cab", "set_bypass", "bind_pedal", "unbind_pedal"}))


def route_ids(labels: list[str], reg) -> list[int]:
    ids = []
    for label in labels:
        match = re.fullmatch(r"(.+?)\s+(\d+)", label.strip())
        if not match:
            raise GuardError(f"Invalid route block: {label!r}; use e.g. 'Amp 1'.")
        try:
            _, eid = reg.resolve_block(match[1], int(match[2]))
        except (ValueError, KeyError) as exc:
            raise GuardError(f"Unknown route block: {label!r}.") from exc
        ids.append(eid)
    if len(ids) < 2 or len(set(ids)) != len(ids):
        raise GuardError("Required route must contain unique input, effect and output blocks.")
    if reg.family_of_effect_id(ids[0])[0] != "INPUT" or reg.family_of_effect_id(ids[-1])[0] != "OUTPUT":
        raise GuardError("Required route must start at Input and end at Output.")
    if any(reg.family_of_effect_id(e)[0] in {"INPUT", "OUTPUT"} for e in ids[1:-1]):
        raise GuardError("Extra Input/Output blocks require a graph contract, not a serial route.")
    return ids


def serial_route(cells, status, reg) -> list[int]:
    """Verify the COMPLETE single serial grid, including bypassed blocks.

    Reject ambiguous aliases, branches, dangling cables/cells and feedback bus
    blocks. Never sort blocks by column and mistake that for connected routing.
    Parallel routing needs a future explicit graph contract, not a guess.
    """
    if cells is None or status is None:
        raise GuardError("Routing/status could not be read.")
    # Non-grid records 200/201 occur even in EMPTY presets (PROTOCOL.md #18),
    # independently observed again on AFX3 FW32.06. Do not ignore arbitrary
    # unknown IDs or alias these system records to delay/reverb cells.
    present = {b.effect_id for b in status if b.effect_id not in (200, 201)}
    if not cells:
        if present:
            raise GuardError("Empty grid disagrees with block status.")
        return []
    graph = {}
    ids = []
    for c in cells:
        if c.row not in range(6) or c.col not in range(14):
            raise GuardError("Grid cell outside the verified layout.")
        if c.effect_id is None and not c.is_shunt:
            if c.cable_in_mask:
                raise GuardError("Cable ends at an empty cell.")
            continue
        eid = None
        if not c.is_shunt:
            # The FX3 parser keeps the complete effect ID, including NAM206.
            candidates = [e for e in present if e == c.effect_id]
            if len(candidates) != 1:
                raise GuardError("Ambiguous or unreadable grid block.")
            eid = candidates[0]
            family = reg.family_of_effect_id(eid)
            if not family or family[0] in audio_safety.BLOCKED_LOOP_FAMILIES:
                raise GuardError("Unassessed/feedback routing cannot be automated.")
            ids.append(eid)
        pos = (c.row, c.col)
        if pos in graph:
            raise GuardError("Duplicate grid cell.")
        graph[pos] = (eid, c.cable_in_mask)
    if set(ids) != present or len(ids) != len(set(ids)):
        raise GuardError(f"Grid and status disagree or contain duplicate blocks "
                         f"(grid={ids}, status={sorted(present)}).")
    inputs = [pos for pos, (e, _) in graph.items() if e and reg.family_of_effect_id(e)[0] == "INPUT"]
    outputs = [pos for pos, (e, _) in graph.items() if e and reg.family_of_effect_id(e)[0] == "OUTPUT"]
    if len(inputs) != 1 or len(outputs) != 1:
        raise GuardError("This build requires one verified serial Input-to-Output route.")
    children = {pos: [] for pos in graph}
    for pos, (_, mask) in graph.items():
        if pos == inputs[0]:
            if mask:
                raise GuardError("Input unexpectedly has an incoming cable.")
            continue
        if mask <= 0 or mask & (mask - 1):
            raise GuardError("Disconnected or parallel routing; nothing may be rewritten automatically.")
        parent = (mask.bit_length() - 2, pos[1] - 1)
        if parent not in graph:
            raise GuardError("A route cable has no source.")
        children[parent].append(pos)
    visited, result = set(), []
    pos = inputs[0]
    while True:
        visited.add(pos)
        if graph[pos][0] is not None:
            result.append(graph[pos][0])
        next_cells = children[pos]
        if pos == outputs[0]:
            if next_cells:
                raise GuardError("Unexpected routing after Output.")
            break
        if len(next_cells) != 1:
            raise GuardError("Broken or parallel signal path.")
        pos = next_cells[0]
    if len(visited) != len(graph):
        raise GuardError("Disconnected cells outside the required route.")
    return result


def labels(ids, reg) -> list[str]:
    friendly = {"DISTORT": "Amp", "CABINET": "Cab", "FUZZ": "Drive",
                "COMP": "Compressor", "GEQ": "GEQ", "PEQ": "PEQ", "NAM": "NAM"}
    return [f"{friendly.get(f, f.title())} {i}" for f, i in
            (reg.family_of_effect_id(e) for e in ids)]


def check_route(dev, reg, required, actions=(), *, complete=False):
    expected = route_ids(required, reg)
    actual = serial_route(dev.read_grid(), dev.status_dump(), reg)
    additions = {reg.resolve_block(a.get("block") or "", a.get("instance", 1))[1]
                 for a in actions if a.get("kind") == "add_block"}
    # Before a new build the grid can be truly empty. Never replace a nonempty
    # grid. Subsequent partial checks allow only explicitly planned insertions.
    if not complete and not actual and additions:
        return actual
    wanted = expected if complete else [e for e in expected if e in actual or e not in additions]
    if actual != wanted:
        raise GuardError("Routing mismatch. Required: " + " -> ".join(labels(wanted, reg))
                         + ". Actual: " + " -> ".join(labels(actual, reg))
                         + ". Regenerate against the actual route; TC will not overwrite it.")
    return actual


def planned_route(dev, reg, required, actions):
    """Prove the final membership/order is buildable before the first write.

    Empty builds lay the entire reviewed route at once. Existing blocks retain
    their relative order; only explicit additions may appear between them.
    """
    expected = route_ids(required, reg)
    actual = check_route(dev, reg, required, actions)
    additions = {reg.resolve_block(a.get('block') or '', a.get('instance', 1))[1]
                 for a in actions if a.get('kind') == 'add_block'}
    if not actual:
        if expected[0] != 37 or expected[-1] != 42:
            raise GuardError('Empty builds support Input 1 and Output 1 only.')
        allowed = additions | {37, 42}
    else:
        allowed = additions | set(actual)
    if set(expected) != allowed:
        raise GuardError('Required route and ADD actions disagree. Every new effect must be '
                         'explicitly added and every ADD must occur on the reviewed route.')
    if len(expected) > p.GRID_COLS:
        raise GuardError('Required serial route exceeds the available grid columns.')
    amps = [e for e in expected if reg.family_of_effect_id(e)[0] == 'DISTORT']
    for a in actions:
        if a.get('kind') != 'add_block' or not amps:
            continue
        _, eid = reg.resolve_block(a.get('block') or '', a.get('instance', 1))
        if eid in amps:
            continue
        pos, amp = expected.index(eid), expected.index(amps[0])
        if ((a.get('position') == 'pre' and pos >= amp)
                or (a.get('position') == 'post' and pos <= amp)):
            raise GuardError('ADD position contradicts the required route.')
    return expected, actual

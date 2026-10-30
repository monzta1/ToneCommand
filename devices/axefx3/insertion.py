"""Reviewed single-block insertion, using FM9 planning and captured AFX3 moves.

FW32.06: same-row serial routes on display row 3 only. No block clear,
disconnect, shunt consumption, preset reload, model reset or flash store.
Captured shunt moves preserve pass-through cells rather than spending them.
Moving temporarily breaks cables, so external audio mute remains required.
Partial failure stops; it never claims automatic rollback or topology Undo.
"""
import time

from fm9.device import FM9, SetResult
from fm9 import protocol as shared
from . import grid, protocol, route_guard


def move_right_frame():
    # Exact Axe-Edit drag captures for Output1, Reverb1 and Delay1, 2026-10-06.
    return protocol.envelope(1, [0x36, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0])


def plan(dev, required_route, actions):
    expected, actual = route_guard.planned_route(dev, dev.reg, required_route, actions)
    if not actual or actual == expected:
        return None
    missing = [e for e in expected if e not in actual]
    if (58 not in actual or 62 not in actual or not missing
            or set(missing)-{78,118,46}
            or [e for e in expected if e not in missing] != actual):
        raise ValueError('Only reviewed Chorus1, Drive1 and Compressor1 insertions are verified')
    if (78 in missing and expected.index(78)!=expected.index(62)+1
            or any(expected.index(e)>=expected.index(58) for e in missing if e in (118,46))):
        raise ValueError('Drive/Compressor must precede Amp1; Chorus1 must immediately follow Cab1')
    cells = grid.snapshot(dev.read_grid())
    columns = sorted(c for r, c in cells)
    if (dev.reg.firmware != '32.06' or {r for r,c in cells} != {3}
            or columns != list(range(columns[0], columns[-1]+1))):
        raise ValueError('Insertion requires one contiguous serial row 3 on FW32.06')
    if len(columns)+len(missing)>14 or columns[-1]+len(missing)>14:
        raise ValueError('No empty column to the right; existing shunts are not consumed')
    eid=missing[0]
    previous=expected[expected.index(eid)-1]
    col=next(c for (r,c),v in cells.items() if v[:2]==(previous,False))+1
    # Reuse the upstream read-only displacement calculation, not its clear
    # and reinsert execution. Full topology was already checked independently.
    if any(v[1] for (r,c),v in cells.items() if c>=col):
        # FM9's planner uses the first shunt as slack and would spend it.
        # Preserve every original cell instead, to the real empty right edge.
        intent=dict(ok=True,spends_shunt=False,at_col=col,slack_col=columns[-1]+1,
                    moves=[dict(effect_id=cells[3,c][0],is_shunt=cells[3,c][1],
                                from_col=c,to_col=c+1)
                           for c in range(columns[-1],col-1,-1)])
    else:
        intent = FM9.plan_splice(dev, 3, col)
    if (not intent['ok'] or intent['spends_shunt']
            or intent['slack_col'] != columns[-1]+1
            or grid.snapshot(dev.read_grid()) != cells):
        raise ValueError('Insertion geometry changed or has no verified empty slack')
    if any(m['effect_id'] is not None and m['effect_id'] >= 128 for m in intent['moves']):
        raise ValueError('Ambiguous grid IDs cannot be moved')
    return dict(expected=expected, actual=actual, cells=cells, intent=intent,
                missing=missing,effect_id=eid)


def _held(before, after):
    old_ids = set(before['bulk'])
    return (old_ids <= set(after['bulk'])
            and all(before['bulk'][e] == after['bulk'][e] for e in old_ids)
            and before['modifiers'] == after['modifiers']
            and before['preset'] == after['preset']
            and before['scene'] == after['scene']
            and before['scene_names'] == after['scene_names']
            and [(b.effect_id,b.bypassed,b.channel,b.channels_supported) for b in before['blocks']]
                == [(b.effect_id,b.bypassed,b.channel,b.channels_supported) for b in after['blocks']
                    if b.effect_id in {o.effect_id for o in before['blocks']}])


def build(dev, required_route, actions):
    from .tone_review import snapshot as full_snapshot
    prepared = plan(dev, required_route, actions)
    if prepared is None:
        raise ValueError('No single insertion to execute')
    if len(prepared['missing'])>1:
        initial=full_snapshot(dev)
        for eid in prepared['missing']:
            present=route_guard.serial_route(dev.read_grid(),dev.status_dump(),dev.reg)
            partial=[e for e in prepared['expected'] if e in present or e==eid]
            result=build(dev,route_guard.labels(partial,dev.reg),
                         [a for a in actions if a.get('kind')=='add_block'
                          and dev.reg.resolve_block(a['block'],a.get('instance',1))[1]==eid])
            if not result.ok:return result
            if not _held(initial,full_snapshot(dev)):
                return SetResult(False,'Existing state changed between insertions; keep external audio muted',None,None)
        route_guard.check_route(dev,dev.reg,required_route,complete=True)
        return SetResult(True,'All reviewed insertions and original state verified',prepared['actual'],prepared['expected'])
    initial = full_snapshot(dev)
    if grid.snapshot(initial['grid']) != prepared['cells']:
        raise ValueError('Routing changed before insertion; nothing written')
    fail = lambda detail: SetResult(False, detail+'; keep external audio muted, partial routing may remain', None, None)
    for move in prepared['intent']['moves']:
        col, eid = move['from_col'], move['effect_id']
        before = grid.snapshot(dev.read_grid())
        shunt=move.get('is_shunt',False)
        if before.get((3,col), ())[:2] != (eid,shunt) or (3,col+1) in before:
            return fail('Move source/destination changed')
        wanted = dict(before)
        del wanted[3,col]
        wanted[3,col+1] = (eid,shunt,0)
        dev._write(grid.reframe(shared.build_select_grid_cell(3,col)))
        # Permit is scoped to this checked move, never a generic transport flag.
        frame = move_right_frame()
        dev._grid_move_permit = tuple(frame)
        try:
            dev._write(frame)
        finally:
            dev._grid_move_permit = None
        for _ in range(4):
            time.sleep(.15)
            after = grid.snapshot(dev.read_grid())
            if after == wanted:
                break
        else:
            return fail('Move grid readback did not match exactly')
        interim = full_snapshot(dev)
        if not _held(initial,interim):
            return fail('Existing parameters, modifiers, names or block states changed')
    placed = dev.place_block((3,prepared['intent']['at_col']),prepared['effect_id'])
    if not placed.ok:
        return fail(placed.detail)
    # Reconnect only the disturbed contiguous span, using the shared FM9
    # cable builder and the existing independent AFX3 connect readback.
    for col in range(prepared['intent']['at_col']-1,prepared['intent']['slack_col']):
        cable = dev.connect_cells(3,col,3)
        if not cable.ok:
            return fail(cable.detail)
    final = full_snapshot(dev)
    if not _held(initial,final):
        return fail('Existing state changed during placement/routing')
    actual = route_guard.serial_route(final['grid'],final['blocks'],dev.reg)
    if actual != prepared['expected']:
        return fail('Final complete signal route did not verify')
    return SetResult(True,'Reviewed block inserted; complete route and original state independently verified',
                     prepared['actual'],actual)

"""Read-only complete graph validation, not permission for grid writes.

Parallel paths are kept as edges, never flattened into a serial block list.
The encoded grid permits only forward edges between adjacent columns. This
module does not enable a firmware profile, synthesize MIDI or prove loudness.
"""
from . import audio_safety
from .route_guard import GuardError


def inspect(cells, status, reg):
    if cells is None or status is None:
        raise GuardError('Complete grid and block status required.')
    blocks=[b.effect_id for b in status if b.effect_id not in (200,201)]
    if len(blocks)!=len(set(blocks)):
        raise GuardError('Duplicate block status.')
    nodes={};positions=set()
    ids=[]
    for cell in cells:
        if (type(cell.row) is not int or type(cell.col) is not int
                or cell.row not in range(6) or cell.col not in range(14)
                or type(cell.cable_in_mask) is not int or cell.cable_in_mask<0
                or cell.cable_in_mask & ~126):
            raise GuardError('Grid coordinates or incoming cable mask invalid.')
        pos=(cell.row,cell.col)
        if pos in positions:
            raise GuardError('Duplicate grid cell.')
        positions.add(pos)
        if type(cell.is_shunt) is not bool:
            raise GuardError('Shunt state unreadable.')
        if cell.effect_id is None and not cell.is_shunt:
            if cell.cable_in_mask:
                raise GuardError('Cable ends at an empty cell.')
            continue
        if cell.is_shunt:
            if cell.effect_id is not None:
                raise GuardError('Shunt has an ambiguous block identity.')
        else:
            family=reg.family_of_effect_id(cell.effect_id) if type(cell.effect_id) is int else None
            if not family or family[0] in audio_safety.BLOCKED_LOOP_FAMILIES:
                raise GuardError('Unknown or feedback-capable block is not assessed.')
            ids.append(cell.effect_id)
        nodes[pos]=(cell.effect_id,cell.cable_in_mask)
    if len(ids)!=len(set(ids)) or set(ids)!=set(blocks):
        raise GuardError('Grid and block status disagree.')
    if not nodes:
        return dict(nodes={},edges=(),input=None,output=None,parallel=False,
                    hardware_writes_supported=False,physical_volume_verified=False)
    inputs=[pos for pos,(eid,_) in nodes.items() if eid is not None and reg.family_of_effect_id(eid)[0]=='INPUT']
    outputs=[pos for pos,(eid,_) in nodes.items() if eid is not None and reg.family_of_effect_id(eid)[0]=='OUTPUT']
    if len(inputs)!=1 or len(outputs)!=1 or nodes[inputs[0]][0]!=37 or nodes[outputs[0]][0]!=42:
        raise GuardError('One Input1 and Output1 required; multi-IO is not assessed.')
    edges=[]
    children={pos:[] for pos in nodes}
    parents={pos:[] for pos in nodes}
    for dest,(_,mask) in nodes.items():
        if dest==inputs[0]:
            if mask:raise GuardError('Input has an incoming cable.')
            continue
        if mask==0:raise GuardError('Disconnected grid cell.')
        for row in range(6):
            if mask & (1<<(row+1)):
                src=(row,dest[1]-1)
                if src not in nodes:raise GuardError('Cable source is empty or outside the grid.')
                if src==outputs[0]:raise GuardError('Output has an outgoing cable.')
                edges.append((src,dest));children[src].append(dest);parents[dest].append(src)
    def reachable(start,links):
        seen=set();todo=[start]
        while todo:
            pos=todo.pop()
            if pos not in seen:
                seen.add(pos);todo.extend(links[pos])
        return seen
    if reachable(inputs[0],children)!=set(nodes) or reachable(outputs[0],parents)!=set(nodes):
        raise GuardError('Every cell must lie on an Input1-to-Output1 path.')
    return dict(nodes=nodes,edges=tuple(sorted(edges)),input=inputs[0],output=outputs[0],
                parallel=any(len(v)>1 for v in children.values()),
                hardware_writes_supported=False,physical_volume_verified=False)

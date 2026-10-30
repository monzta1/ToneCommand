"""Literal owner-operated FW33 two-by-two developer reference on320.

Detached cells measure fan-out/fan-in only, not a playable rig or headroom.
No arbitrary positions, replacements, models, levels or public AI capability.
"""
from fm9 import protocol as shared
from . import grid,protocol


POSITIONS=((5,1),(5,2),(6,1),(6,2))
INSERTS=((46,7),(118,25),(1024,6),(1025,6))
# Actual drawing order: both horizontal cables, then the two crossings.
EDGES=((5,5),(6,6),(5,6),(6,5))
TAILS=((2,2,64),(2,66,96),(2,2,96),(2,66,64))
REMOVAL=(0,2,3,1)


def _position(row,col):
    if type(row) is not int or type(col) is not int or (row,col) not in POSITIONS:
        raise ValueError('Only four measured developer cells')


def select(row,col):
    _position(row,col)
    return grid.reframe(shared.build_select_grid_cell(row,col))


def insert(row,col):
    _position(row,col);eid,payload=INSERTS[POSITIONS.index((row,col))]
    return protocol.envelope(1,[0x32,0,*shared.encode14(eid),0,0,payload,0,0,0,0,0,0,0,0])


def delete(row,col):
    _position(row,col);payload=select(row,col)[6:-2];payload[0]=0x33
    return protocol.envelope(1,payload)


def cable(source,target,op=1):
    if any(type(v) is not int for v in (source,target,op)) or (source,target) not in EDGES or op not in (1,2):
        raise ValueError('Only captured connect/disconnect geometry')
    return protocol.envelope(1,[0x35,0,0,0,0,0,op,0,0,0,0,0,0,2,0,*TAILS[EDGES.index((source,target))]])


def frames():
    result=[]
    for row,col in POSITIONS:result.extend((select(row,col),insert(row,col)))
    return tuple(result+[cable(*edge) for edge in EDGES])


def removal_frames():
    result=[cable(*EDGES[i],op=2) for i in REMOVAL]
    for row,col in POSITIONS:result.extend((select(row,col),delete(row,col)))
    return tuple(result)


def expected_grid():
    return {(5,1):(46,False,0),(5,2):(118,False,96),
            (6,1):(None,True,0),(6,2):(None,True,96)}


def steps():
    result=[];state={}
    for (row,col),(eid,_) in zip(POSITIONS,INSERTS):
        result.append((select(row,col),dict(state),dict(state)))
        before=dict(state);state[row,col]=(eid if row==5 else None,row==6,0)
        result.append((insert(row,col),before,dict(state)))
    for source,target in EDGES:
        before=dict(state);eid,shunt,mask=state[target,2]
        state[target,2]=(eid,shunt,mask | (1<<source))
        result.append((cable(source,target),before,dict(state)))
    for index in REMOVAL:
        source,target=EDGES[index];before=dict(state);eid,shunt,mask=state[target,2]
        state[target,2]=(eid,shunt,mask & ~(1<<source))
        result.append((cable(source,target,op=2),before,dict(state)))
    for row,col in POSITIONS:
        result.append((select(row,col),dict(state),dict(state)))
        before=dict(state);del state[row,col]
        result.append((delete(row,col),before,dict(state)))
    return tuple(result)

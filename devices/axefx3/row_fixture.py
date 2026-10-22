"""Exact outgoing FW33 two-row reference, not an executable AI capability.

User-operated Axe-Edit320 measurement2026-10-10, screenshot/UIA plus independent
native grid/mask readback. Row2 is intentionally detached for measurement.
Insert payload is retained literally, not replaced with a cursor position.
No general coordinate formula, move, model or level authority.
"""
from fm9 import protocol as shared
from . import fw33_profile,grid,protocol


# effect ID, independently captured INSERT payload
BLOCKS=((37,41),(94,20),(118,25),(58,10),(62,11),(78,16),(46,7),
        (70,13),(122,26),(114,24),(82,17),(50,8),(55,9),(42,46))
ROUTING={
    1:((0,1,64),(3,3,0),(6,4,64),(9,6,0),(12,7,64),(15,9,0),
       (18,10,64),(21,12,0),(24,13,64),(27,15,0),(30,16,64),(33,18,0),(36,19,64)),
    2:((0,65,96),(3,67,32),(6,68,96),(9,70,32),(12,71,96),(15,73,32),
       (18,74,96),(21,76,32),(24,77,96),(27,79,32),(30,80,96),(33,82,32),(36,83,96)),
}


def _position(row,col,max_col=14):
    if type(row) is not int or type(col) is not int or row not in (1,2) or not 1<=col<=max_col:
        raise ValueError('Only captured rows1/2 and bounded columns')


def select(row,col):
    _position(row,col)
    return grid.reframe(shared.build_select_grid_cell(row,col))


def insert(row,col):
    _position(row,col)
    effect,payload=BLOCKS[col-1] if row==1 else (1024+col-1,6)
    return protocol.envelope(1,[0x32,0,*shared.encode14(effect),0,0,payload,0,0,0,0,0,0,0,0])


def connect(row,col):
    _position(row,col,13)
    return protocol.envelope(1,[0x35,0,0,0,0,0,1,0,0,0,0,0,0,2,0,*ROUTING[row][col-1]])


def disconnect(row,col):
    _position(row,col,13)
    return protocol.envelope(1,[0x35,0,0,0,0,0,2,0,0,0,0,0,0,2,0,*ROUTING[row][col-1]])


def delete(row,col):
    _position(row,col)
    payload=select(row,col)[6:-2]
    payload[0]=0x33
    return protocol.envelope(1,payload)


def frames():
    result=[]
    for row in (1,2):
        for col in range(1,15):result.extend((select(row,col),insert(row,col)))
        result.extend(connect(row,col) for col in range(1,14))
    return tuple(result)


def removal_frames():
    result=[disconnect(row,col) for row in (1,2) for col in range(1,14)]
    for row in (1,2):
        for col in range(1,15):result.extend((select(row,col),delete(row,col)))
    return tuple(result)


def steps():
    """Exact ordered reference with expected whole-grid pre/post states."""
    result=[];state={}
    for row in (1,2):
        for col in range(1,15):
            result.append((select(row,col),dict(state),dict(state)))
            before=dict(state)
            state[row,col]=(BLOCKS[col-1][0] if row==1 else None,row==2,0)
            result.append((insert(row,col),before,dict(state)))
        for col in range(1,14):
            before=dict(state);eid,shunt,_=state[row,col+1]
            state[row,col+1]=(eid,shunt,1<<row)
            result.append((connect(row,col),before,dict(state)))
    for row in (1,2):
        for col in range(1,14):
            before=dict(state);eid,shunt,_=state[row,col+1]
            state[row,col+1]=(eid,shunt,0)
            result.append((disconnect(row,col),before,dict(state)))
    for row in (1,2):
        for col in range(1,15):
            result.append((select(row,col),dict(state),dict(state)))
            before=dict(state);del state[row,col]
            result.append((delete(row,col),before,dict(state)))
    return tuple(result)


def expected_grid():
    return {(row,col):(BLOCKS[col-1][0] if row==1 else None,row==2,0 if col==1 else 1<<row)
            for row in (1,2) for col in range(1,15)}


def readback(cells,firmware):
    if firmware!=fw33_profile.KEY:
        raise ValueError('Only exact independently measured FW33 identity')
    if (not isinstance(cells,list) or any(type(c.row) is not int or type(c.col) is not int
            or type(c.is_shunt) is not bool or type(c.cable_in_mask) is not int for c in cells)):
        raise ValueError('Complete typed native grid required')
    if grid.snapshot(cells)!=expected_grid():
        raise ValueError('Native grid does not match the exact measured reference')
    return dict(cells=28,cables=26,hardware_writes_supported=False,
                physical_volume_verified=False,detached_shunt_test_row=True)

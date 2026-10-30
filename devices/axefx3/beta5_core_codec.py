"""Closed Beta5 minimal AMP/CAB grammar. Pure codecs are not write permission.

Only four captured first-row cells, three captured edges and channel A.
No delete, free graph, raw frame input, Store, resource or controller command.
"""
from dataclasses import dataclass
import math

from . import protocol
from .name_edits import NameEdit
from .beta5_core_plan import AMP_PIDS, amp_frame

STRIDES = {37: 10, 42: 26, 58: 142, 62: 106}
NODES = (37, 58, 62, 42)
_INSERT = {
    37: 'f0 00 01 74 10 01 32 00 25 00 00 00 29 00 00 00 00 00 00 00 00 2a f7',
    58: 'f0 00 01 74 10 01 32 00 3a 00 00 00 0a 00 00 00 00 00 00 00 00 16 f7',
    62: 'f0 00 01 74 10 01 32 00 3e 00 00 00 0b 00 00 00 00 00 00 00 00 13 f7',
    42: 'f0 00 01 74 10 01 32 00 2a 00 00 00 2e 00 00 00 00 00 00 00 00 22 f7',
}
_EDGES = (
    'f0 00 01 74 10 01 35 00 00 00 00 00 01 00 00 00 00 00 00 02 00 00 01 40 63 f7',
    'f0 00 01 74 10 01 35 00 00 00 00 00 01 00 00 00 00 00 00 02 00 03 03 00 22 f7',
    'f0 00 01 74 10 01 35 00 00 00 00 00 01 00 00 00 00 00 00 02 00 06 04 40 60 f7',
)


def grid(connected=True):
    return [dict(row=0, col=col, effect_id=eid, is_shunt=False,
                 cable_in_mask=2 if col and connected else 0)
            for col, eid in enumerate(NODES)]


def _number(value, allowed):
    if type(value) not in (int, float) or not math.isfinite(value) or value not in allowed:
        raise ValueError('Value outside the closed core operation')


@dataclass(frozen=True)
class Operation:
    kind: str
    eid: int = 0
    pid: int = 0
    value: float = 0
    text: str = ''

    def frame(self, preset):
        """Validate again at the final transport boundary."""
        if type(preset) is not int or preset not in range(1024):
            raise ValueError('Pin one III preset')
        if (type(self.kind) is not str or type(self.eid) is not int
                or type(self.pid) is not int or type(self.text) is not str):
            raise ValueError('Invalid core operation fields')
        if self.kind == 'select' and self.eid in NODES:
            if self.pid or self.value or self.text:raise ValueError('Unexpected cursor fields')
            return protocol.envelope(1, [48,0,0,0,0,0,NODES.index(self.eid)*6,0,0,0,0,0,0,0,0])
        if self.kind == 'insert' and self.eid in NODES:
            if self.pid or self.value or self.text:raise ValueError('Unexpected insert fields')
            return list(bytes.fromhex(_INSERT[self.eid]))
        if self.kind == 'edge' and self.eid in NODES[1:]:
            if self.pid or self.value or self.text:raise ValueError('Unexpected edge fields')
            return list(bytes.fromhex(_EDGES[NODES.index(self.eid)-1]))
        if self.kind == 'channel' and self.eid in NODES:
            if self.pid or self.value or self.text:raise ValueError('Only explicit channel A')
            return protocol.envelope(1, [22,0,self.eid,0,0,0,0,0,0,0,0,0,0,0,0])
        if self.kind == 'name':
            if self.eid or self.value or self.pid not in (0,1):raise ValueError('Only preset and scene1 names')
            return NameEdit(preset, self.text, self.pid or None).frame()
        if self.kind != 'param' or self.text:
            raise ValueError('Unknown core operation')
        if self.eid == 58 and self.pid in AMP_PIDS.values():
            return amp_frame(next(k for k,v in AMP_PIDS.items() if v==self.pid),self.value)
        if self.eid == 58 and self.pid == 0:_number(self.value,range(336))
        elif (self.eid,self.pid) in ((58,28),(62,32)):_number(self.value,(0,1))
        elif (self.eid,self.pid) == (42,12):_number(self.value,(-18,))
        elif self.eid == 62:
            if self.pid == 0:_number(self.value,range(4))
            elif self.pid == 4:_number(self.value,range(1024))
            elif self.pid in (8,12,28,31):_number(self.value,(0,))
            elif self.pid in range(24,28):_number(self.value,(0,) if self.pid==24 else (1,))
            else:raise ValueError('Unreleased Cab control')
        else:raise ValueError('Unreleased core parameter')
        return protocol.param_frame(self.eid,self.pid,self.value,opcode=9)


def operations(plan, empty):
    """Server-owned staging, not AI-provided actions or serialized MIDI."""
    from .beta5_core_plan import Design
    d=Design.model_validate(plan['design'])
    ops=[]
    if empty:ops += [Operation('select',42),Operation('insert',42)]
    ops += [Operation('channel',42),Operation('param',42,12,-18)]
    if empty:
        for eid in NODES[:-1]:
            ops += [Operation('select',eid),Operation('insert',eid),Operation('channel',eid)]
    else:
        ops += [Operation('channel',eid) for eid in NODES[:-1]]
    ops += [Operation('param',58,28,1),Operation('param',58,21,-18),
            Operation('param',62,32,1),Operation('param',62,31,0),
            Operation('param',58,0,plan['amp_ordinal']),
            Operation('param',62,0,d.cab.bank),Operation('param',62,4,d.cab.slot-1)]
    ops += [Operation('param',62,pid,0) for pid in (8,12,28)]
    ops += [Operation('param',62,pid,0 if pid==24 else 1) for pid in range(24,28)]
    ops += [Operation('param',58,pid,getattr(d.amp,name)) for name,pid in AMP_PIDS.items()]
    ops += [Operation('name',text=plan['name']),Operation('name',pid=1,text=d.scene_name)]
    if empty:ops += [Operation('edge',eid) for eid in NODES[1:]]
    ops += [Operation('param',62,32,0),Operation('param',58,28,0)]
    for op in ops:op.frame(0)
    return tuple(ops)

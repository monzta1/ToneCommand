"""Exact FW33 developer measurements on322, never a planner capability.

Source: owner-operated Quick Build321, 2026-10-11, independently compared
with visible labels and native eight-bit IDs. Selection/INSERT payloads are
retained literally; DELETE was separately observed. Feedback Send/Return and
Output2-4 are excluded. Isolated mode has no cables; chain mode reuses only
the independently captured14-block row1 sequence. No model/Store/memory writes.
"""
import time
from functools import lru_cache
from fm9 import protocol as shared
from . import fw33_profile, grid, protocol, row_fixture


# Human row, column, effect ID, captured INSERT payload (not a grid cursor).
BLOCKS = (
    (1,1,37,41), (1,2,118,25), (1,3,58,10), (1,4,62,11),
    (1,5,78,16), (1,6,46,7), (1,7,70,13), (1,8,202,59),
    (1,9,122,26), (1,10,114,24), (1,11,82,17), (1,12,146,35),
    (1,13,50,8), (2,2,138,33), (2,3,126,28), (2,4,154,37),
    (2,5,191,54), (2,6,74,14), (2,7,206,60), (2,8,54,9),
    (2,9,90,19), (2,10,110,23), (2,11,178,15), (2,12,162,39),
    (2,13,66,12), (3,2,150,36), (3,3,86,18), (3,4,130,31),
    (3,5,158,38), (3,6,106,22), (3,7,134,32), (3,8,102,40),
    (3,9,94,20), (3,10,42,46),
)


@lru_cache(maxsize=3)
def steps(mode='isolated'):
    if type(mode) is not str or mode not in ('isolated','chain','chain_connect'):
        raise ValueError('Only independently captured isolated or row1-chain references')
    if mode=='chain':
        return tuple((tuple(frame),tuple(before.items()),tuple(after.items()))
                     for frame,before,after in row_fixture.steps()[:41])
    if mode=='chain_connect':
        return steps('chain')[28:]
    result = []
    for row,col,eid,payload in BLOCKS:
        select = grid.reframe(shared.build_select_grid_cell(row,col))
        insert = protocol.envelope(1,[0x32,0,*shared.encode14(eid),0,0,
                                     payload,0,0,0,0,0,0,0,0])
        deletion = select[6:-2]
        deletion[0] = 0x33
        delete = protocol.envelope(1,deletion)
        state = {(row,col):(eid,False,0)}
        result.extend(((tuple(select),(),()),
                       (tuple(insert),(),tuple(state.items())),
                       (tuple(select),tuple(state.items()),tuple(state.items())),
                       (tuple(delete),tuple(state.items()),())))
    return tuple(result)


def allowed(dev,frame):
    probe = getattr(dev,'_block_probe',None)
    return (isinstance(probe,Probe) and probe.dev is dev and probe.failed
            and probe.index < len(steps(probe.mode))
            and dev.reg.firmware == fw33_profile.KEY
            and getattr(dev.reg,'hardware_variant',None) == 'mk2'
            and getattr(dev,'_edit_target',None) == 322
            and getattr(dev,'_block_probe_permit',None) == tuple(frame)
            and tuple(frame) == steps(probe.mode)[probe.index][0])


class Probe:
    def __init__(self,dev,*,mode='isolated'):
        if type(mode) is not str or mode not in ('isolated','chain','chain_connect'):
            raise PermissionError('Only independently captured developer sequences')
        dev._check_edit_target()
        if (dev.reg.firmware != fw33_profile.KEY or dev._edit_target != 322
                or getattr(dev.reg,'hardware_variant',None) != 'mk2'
                or grid.snapshot(dev.read_grid()) != dict(steps(mode)[0][1])
                or getattr(dev,'_block_probe',None) is not None):
            raise PermissionError('Only exact MK2/FW33, captured322 prestate and one confirmed probe')
        self.dev,self.index,self.failed = dev,0,False
        self.mode=mode
        dev._block_probe = self

    def write(self,frame):
        with self.dev._lock:
            if self.failed or self.index >= len(steps(self.mode)):
                raise PermissionError('Block probe consumed or complete; no retry')
            self.failed = True
            dev = self.dev
            dev._check_edit_target()
            expected,before,after = steps(self.mode)[self.index]
            if (tuple(frame) != expected or dev.reg.firmware != fw33_profile.KEY
                    or dev._edit_target != 322 or getattr(dev.reg,'hardware_variant',None) != 'mk2'
                    or getattr(dev,'_block_probe',None) is not self
                    or grid.snapshot(dev.read_grid()) != dict(before)):
                raise PermissionError('Exact ordered frame and fresh whole-grid prestate required')
            dev._block_probe_permit = tuple(frame)
            try:
                dev._write(list(frame))
            finally:
                dev._block_probe_permit = None
            for _ in range(5):
                time.sleep(.2)
                if grid.snapshot(dev.read_grid()) == dict(after):
                    self.index += 1
                    self.failed = False
                    return
            raise ValueError('Block readback mismatch; stop without retry or restore')

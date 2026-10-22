"""Developer-only exact320 row/parallel fixtures, not public free-chain execution.

Starts empty, binds every frame to its ordered whole-grid pre/post state and
consumes the probe on any failure. The harness checks full bulks/status and
modifiers between changes. No Store, model, level or unknown write retry.
"""
import time
from . import fw33_profile,grid,row_fixture,parallel_fixture


def allowed(dev,frame):
    return (dev.reg.firmware==fw33_profile.KEY
            and getattr(dev.reg,'hardware_variant',None)=='mk2'
            and getattr(dev,'_edit_target',None)==320
            and getattr(dev,'_row_probe_permit',None)==tuple(frame)
            and frame in row_fixture.frames()+row_fixture.removal_frames()
                +parallel_fixture.frames()+parallel_fixture.removal_frames())


class Probe:
    def __init__(self,dev,*,mode='rows'):
        if type(mode) is not str or mode not in ('rows','parallel'):
            raise PermissionError('Only two independently captured developer sequences')
        dev._check_edit_target()
        if (dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=320
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or grid.snapshot(dev.read_grid())):
            raise PermissionError('Only exact FW33 MK2, empty320 and a confirmed edit session')
        self.dev,self.index,self.failed=dev,0,False
        self.sequence=(row_fixture if mode=='rows' else parallel_fixture).steps()

    def write(self,frame):
        with self.dev._lock:
            if self.failed or self.index>=len(self.sequence):
                raise PermissionError('Probe consumed or complete; no retry')
            self.failed=True
            dev=self.dev
            dev._check_edit_target()
            expected,before,after=self.sequence[self.index]
            if (frame!=expected or dev.reg.firmware!=fw33_profile.KEY
                    or dev._edit_target!=320 or getattr(dev.reg,'hardware_variant',None)!='mk2'
                    or grid.snapshot(dev.read_grid())!=before):
                raise PermissionError('Exact ordered frame and fresh whole-grid prestate required')
            dev._row_probe_permit=tuple(frame)
            try:
                dev._write(frame)
            finally:
                dev._row_probe_permit=None
            for _ in range(5):
                time.sleep(.2)
                if grid.snapshot(dev.read_grid())==after:
                    self.index+=1
                    self.failed=False
                    return
            raise ValueError('Native row readback mismatch; stop without retry or restore')

"""Opt-in recorded inventory replay on test322, never a public AI operation.

Requires all336 literal editor frames and a quiet bypassed Amp1/A fixture.
Unknown outcome consumes the probe. No rollback, Store or memory operation.
"""
import time
from . import amp_inventory,fw33_profile,protocol,serial_build,grid,tone_review


def frames():
    return tuple(tuple(protocol.param_frame(58,0,n,opcode=9)) for n in range(336))


def allowed(dev,frame):
    probe=getattr(dev,'_amp_probe',None)
    return (isinstance(probe,Probe) and probe.dev is dev and probe.failed
        and probe.index<336 and dev.reg.firmware==fw33_profile.KEY
        and getattr(dev.reg,'hardware_variant',None)=='mk2' and dev._edit_target==322
        and getattr(dev,'_amp_probe_permit',None)==tuple(frame)
        and tuple(frame)==probe.sequence[probe.index])


class Probe:
    def __init__(self,dev,recorded):
        dev._check_edit_target()
        if (dev._edit_target!=322 or dev.reg.firmware!=fw33_profile.KEY
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or getattr(dev,'_amp_probe',None) is not None
                or tuple(map(tuple,recorded))!=frames()):
            raise PermissionError('One exact all-model recorded sequence on muted322 required')
        before=tone_review.snapshot(dev,include_nam=False)
        amp=next(b for b in before['blocks'] if b.effect_id==58)
        if (before['scene']!=1 or grid.snapshot(before['grid'])!=serial_build.expected_grid()
                or len(before['bulk'].get(58,[]))!=568 or amp.channel!=0 or not amp.bypassed
                or any(m['active'] for m in before['modifiers'])):
            raise PermissionError('Measured Amp1/A fixture with inactive modifiers required')
        self.dev,self.sequence,self.expected=dev,frames(),before
        self.index,self.failed=0,False
        self.names=amp_inventory.roster(dev.reg.firmware)
        self.quiet()
        dev._amp_probe=self

    def quiet(self):
        d=self.dev
        if d.get_param_display(d.reg.find_param('OUTPUT','OUTPUT_LEVEL'))!=-18 or d.get_bypass(58) is not True:
            raise PermissionError('Bypassed Amp1 and verified Output1 -18dB required')

    def stage(self):
        if self.failed or tone_review.snapshot(self.dev,include_nam=False)!=self.expected:
            self.failed=True;raise PermissionError('Stale/consumed inventory measurement')
        self.quiet()
        spec=self.dev.reg.find_param('DISTORT','DISTORT_LEVEL')
        level=self.dev.get_param_display(spec)
        if type(level) not in (int,float):self.failed=True;raise ValueError('Amp level unreadable')
        if level<=-18:return
        self.failed=True
        result=self.dev.set_param_display(spec,-20)
        if not result.ok:raise ValueError('Quiet staging failed, no retry')
        for _ in range(5):
            time.sleep(.15)
            now=tone_review.snapshot(self.dev,include_nam=False)
            words=list(self.expected['bulk'][58]);words[21]=now['bulk'][58][21]
            wanted={**self.expected,'bulk':{**self.expected['bulk'],58:words}}
            if now==wanted and self.dev.get_param_display(spec)==-20:
                self.expected,self.failed=now,False;return
        raise ValueError('Staging changed unexpected state; no retry')

    def write(self,frame):
        d=self.dev
        if self.failed or self.index>=336:
            raise PermissionError('Probe consumed or complete')
        self.stage();self.failed=True
        if tuple(frame)!=self.sequence[self.index] or tone_review.snapshot(d,include_nam=False)!=self.expected:
            raise PermissionError('Unexpected frame or changed target')
        dev_level=d.get_param_display(d.reg.find_param('DISTORT','DISTORT_LEVEL'))
        if type(dev_level) not in (int,float) or dev_level>-18:
            raise PermissionError('Quiet level must precede each model transition')
        d._amp_probe_permit=tuple(frame)
        try:d._write(list(frame))
        finally:d._amp_probe_permit=None
        for _ in range(5):
            time.sleep(.2)
            now=tone_review.snapshot(d,include_nam=False)
            words=list(self.expected['bulk'][58]);words[:142]=now['bulk'][58][:142]
            wanted={**self.expected,'bulk':{**self.expected['bulk'],58:words}}
            if now==wanted and words[0]==self.index:
                self.quiet();self.expected=now;self.index+=1;self.failed=False
                return now
        raise ValueError('Model/full-state mismatch; no retry or rollback')

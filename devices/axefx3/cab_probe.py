"""Fixed developer CAB1 Legacy IR1 calibration on muted328, not planner IO.

Source: independently observed editor banks0/1, slots0/515/799, B/C/D/A.
Only these captured literals can execute in this order. No IR memory install,
second IR, mixer, output, model, modifier or Store write is authorized.
"""
from dataclasses import dataclass,replace
import time
from . import fw33_profile,grid,protocol,serial_build,tone_review


@dataclass(frozen=True)
class Step:
    channel: int
    pid: int | None
    value: int
    frame: tuple


def steps():
    result=[]
    def param(c,p,v):result.append(Step(c,p,v,tuple(protocol.param_frame(62,p,v,opcode=9))))
    def channel(c):result.append(Step(c,None,c,tuple(protocol.envelope(1,[22,0,62,0,0,0,c,0,0,0,0,0,0,0,0]))))
    for p,v in ((0,0),(4,0),(0,1),(4,799),(4,515)):param(0,p,v)
    for c,ordinal in ((1,799),(2,515),(3,799)):
        channel(c)
        for p,v in ((0,1),(4,ordinal),(4,515 if ordinal==799 else 799),(4,ordinal)):param(c,p,v)
    channel(0)
    return tuple(result)


def allowed(dev,frame):
    from . import cab_inventory_probe
    if cab_inventory_probe.allowed(dev,frame):
        return True
    probe=getattr(dev,'_cab_probe',None)
    return (isinstance(probe,Probe) and probe.dev is dev and probe.failed
        and probe.index<len(probe.sequence) and dev.reg.firmware==fw33_profile.KEY
        and getattr(dev.reg,'hardware_variant',None)=='mk2'
        and getattr(dev,'_edit_target',None)==328
        and getattr(dev,'_cab_probe_permit',None)==tuple(frame)
        and tuple(frame)==probe.sequence[probe.index].frame)


class Probe:
    def __init__(self,dev):
        dev._check_edit_target()
        if (dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=328
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or getattr(dev,'_cab_probe',None) is not None):
            raise PermissionError('One exact328 MK2/FW33 Cab measurement required')
        now=tone_review.snapshot(dev,include_nam=False)
        status={b.effect_id:b for b in now['blocks']}
        words=now['bulk'].get(62,[])
        if (now['scene']!=1 or grid.snapshot(now['grid'])!=serial_build.expected_grid()
                or len(words)!=424 or not status[58].bypassed or status[58].channel!=0
                or status[62].channel!=0 or any(m['active'] for m in now['modifiers'])):
            raise PermissionError('Exact quiet Legacy calibration foundation required')
        for c in range(4):
            v=words[106*c:106*(c+1)]
            if (v[31]!=0 or v[24:28]!=[0,1,1,1] or v[8:12]!=[65534]*4
                    or v[12:16]!=[32767]*4 or v[:8]!=( [1,0,0,0,840,0,0,0] if c==0 else [0]*8)):
                raise PermissionError('Measured Legacy selections/mixer baseline changed')
        self.dev,self.expected,self.sequence,self.index,self.failed=dev,now,steps(),0,False
        self._quiet()
        dev._cab_probe=self

    def _quiet(self):
        if self.dev.get_param_display(self.dev.reg.find_param('OUTPUT','OUTPUT_LEVEL'))!=-18:
            raise PermissionError('Measured Output1 attenuation must remain -18dB')

    def write(self,frame):
        with self.dev._lock:
            if self.failed or self.index>=len(self.sequence):
                raise PermissionError('Cab probe consumed or complete; no retry')
            self.failed=True
            dev,step=self.dev,self.sequence[self.index]
            dev._check_edit_target()
            if (getattr(dev,'_cab_probe',None) is not self
                    or dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=328
                    or getattr(dev.reg,'hardware_variant',None)!='mk2'
                    or tuple(frame)!=step.frame
                    or tone_review.snapshot(dev,include_nam=False)!=self.expected):
                raise PermissionError('Exact literal, identity and fresh full state required')
            self._quiet()
            wanted=dict(self.expected)
            if step.pid is None:
                wanted['blocks']=[replace(b,channel=step.channel) if b.effect_id==62 else b for b in wanted['blocks']]
            else:
                wanted['bulk']={**wanted['bulk'],62:list(wanted['bulk'][62])}
                wanted['bulk'][62][106*step.channel+step.pid]=step.value
            dev._cab_probe_permit=step.frame
            try:dev._write(list(frame))
            finally:dev._cab_probe_permit=None
            for _ in range(5):
                time.sleep(.2)
                now=tone_review.snapshot(dev,include_nam=False)
                if now==wanted:
                    self._quiet()
                    self.expected,self.index,self.failed=now,self.index+1,False
                    return now
            raise ValueError('Full-state selector/channel readback failed; no write retry or rollback')

"""Recorded Drive calibration only, not arbitrary effect or planner writes."""
from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import time
from . import fw33_profile,grid,protocol,serial_build,tone_review

SHA256='a796a6224f57dafad90ea3fed1670251271c9a27f0dc62b628fd0aa73cf258c5'


def steps():
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_drive_probe.json').read_text(encoding='utf-8'))
    seq=data.get('steps')
    if (data.get('firmware')!=fw33_profile.KEY or not isinstance(seq,list) or len(seq)!=171
            or hashlib.sha256(json.dumps(seq,separators=(',',':')).encode('ascii')).hexdigest()!=SHA256):
        raise ValueError('Recorded Drive sequence changed')
    return tuple(tuple(s) for s in seq)


def frame_for(step):
    c,p,v=step
    return tuple(protocol.envelope(1,[22,0,118,0,0,0,c,0,0,0,0,0,0,0,0]) if p is None
                 else protocol.param_frame(118,p,v,opcode=9))


def allowed(dev,frame):
    probe=getattr(dev,'_effect_probe',None)
    return (isinstance(probe,Probe) and probe.dev is dev and probe.failed
        and probe.index<len(probe.sequence) and dev.reg.firmware==fw33_profile.KEY
        and getattr(dev.reg,'hardware_variant',None)=='mk2' and dev._edit_target==322
        and getattr(dev,'_effect_probe_permit',None)==tuple(frame)
        and tuple(frame)==frame_for(probe.sequence[probe.index]))


class Probe:
    def __init__(self,dev):
        dev._check_edit_target()
        if (dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=322
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or getattr(dev,'_effect_probe',None) is not None):
            raise PermissionError('One exact muted322 FW33/MK2 Drive calibration required')
        before=tone_review.snapshot(dev,include_nam=False)
        status={b.effect_id:b for b in before['blocks']}
        if (before['scene']!=1 or grid.snapshot(before['grid'])!=serial_build.expected_grid()
                or len(before['bulk'].get(118,[]))!=176 or not status[58].bypassed
                or status[58].channel!=0 or status[118].channel!=0 or not status[118].bypassed
                or any(m['active'] for m in before['modifiers'])):
            raise PermissionError('Exact bypassed Amp1A/Drive1A and inactive modifiers required')
        self.dev,self.expected,self.sequence=dev,before,steps()
        self.index,self.failed=0,False
        self.quiet();dev._effect_probe=self

    def quiet(self):
        d=self.dev
        level=d.get_param_display(d.reg.find_param('DISTORT','DISTORT_LEVEL'))
        if (d.get_param_display(d.reg.find_param('OUTPUT','OUTPUT_LEVEL'))!=-18
                or d.get_bypass(58) is not True or d.get_bypass(118) is not True
                or type(level) not in (int,float) or level>-18):
            raise PermissionError('Bypassed Amp/Drive and verified quiet levels required')

    def write(self,frame):
        with self.dev._lock:
            if self.failed or self.index>=len(self.sequence):
                raise PermissionError('Drive calibration consumed or complete; no retry')
            self.failed=True;d=self.dev;d._check_edit_target()
            c,p,v=self.sequence[self.index]
            if (getattr(d,'_effect_probe',None) is not self or d.reg.firmware!=fw33_profile.KEY
                    or d._edit_target!=322 or getattr(d.reg,'hardware_variant',None)!='mk2'
                    or tuple(frame)!=frame_for(self.sequence[self.index])
                    or tone_review.snapshot(d,include_nam=False)!=self.expected):
                raise PermissionError('Exact literal, fresh full state and identity required')
            self.quiet();before=self.expected
            if p is not None and next(b.channel for b in before['blocks'] if b.effect_id==118)!=c:
                raise PermissionError('Recorded Drive channel context changed')
            d._effect_probe_permit=tuple(frame)
            try:d._write(list(frame))
            finally:d._effect_probe_permit=None
            for _ in range(5):
                time.sleep(.15);now=tone_review.snapshot(d,include_nam=False);wanted=dict(before)
                if p is None:
                    wanted['blocks']=[replace(b,channel=c) if b.effect_id==118 else b for b in before['blocks']]
                else:
                    base=44*c;words=list(before['bulk'][118])
                    if p==0:
                        if now['bulk'][118][base]!=int(v):continue
                        words[base:base+44]=now['bulk'][118][base:base+44]
                    else:
                        word=now['bulk'][118][base+p]
                        if abs(word-round(v*65534))>1:continue
                        words[base+p]=word
                    wanted['bulk']={**before['bulk'],118:words}
                if now!=wanted:continue
                if p in (1,2,3,4):
                    shown=d.read_display_text(118,p).strip().removesuffix(' %')
                    if abs(float(shown)-v*(100 if p==4 else 10))>.011:continue
                self.quiet();self.expected,self.index,self.failed=now,self.index+1,False
                return now
            raise ValueError('Drive selector/display/full-state mismatch; no retry or rollback')

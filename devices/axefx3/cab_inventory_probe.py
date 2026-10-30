"""Fixed recorded four-IR calibration on muted322, not a planner permission.

Only the exact editor sequence may run, preserving every unrelated word.
No model, memory, Store, output, grid or modifier writes. Failures consume it.
"""
from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import time
from . import fw33_profile, grid, protocol, serial_build, tone_review

SHA256='834d590ac29d640ff302fa3ed4b3d572d547e7a17f30802006778e057c72293b'


def steps():
    doc=json.loads(files('devices.axefx3').joinpath('data','fw33_cab_probe.json').read_text(encoding='utf-8'))
    result=doc.get('steps')
    if (doc.get('firmware')!=fw33_profile.KEY or not isinstance(result,list) or len(result)!=270
            or hashlib.sha256(json.dumps(result,separators=(',',':')).encode('ascii')).hexdigest()!=SHA256):
        raise ValueError('Recorded Cab calibration sequence changed')
    return tuple(tuple(s) for s in result)


def frame_for(step):
    c,p,v=step
    return tuple(protocol.envelope(1,[22,0,62,0,0,0,c,0,0,0,0,0,0,0,0]) if p is None
                 else protocol.param_frame(62,p,v,opcode=9))


def allowed(dev,frame):
    probe=getattr(dev,'_cab_probe',None)
    return (isinstance(probe,Probe) and probe.dev is dev and probe.failed
        and probe.index<len(probe.sequence) and dev.reg.firmware==fw33_profile.KEY
        and getattr(dev.reg,'hardware_variant',None)=='mk2' and dev._edit_target==322
        and getattr(dev,'_cab_probe_permit',None)==tuple(frame)
        and tuple(frame)==frame_for(probe.sequence[probe.index]))


class Probe:
    def __init__(self,dev):
        dev._check_edit_target()
        if (dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=322
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or getattr(dev,'_cab_probe',None) is not None):
            raise PermissionError('One exact muted322 FW33/MK2 calibration required')
        before=tone_review.snapshot(dev,include_nam=False)
        status={b.effect_id:b for b in before['blocks']}
        words=before['bulk'].get(62,[])
        if (before['scene']!=1 or grid.snapshot(before['grid'])!=serial_build.expected_grid()
                or len(words)!=424 or not status[58].bypassed or status[58].channel!=0
                or status[62].channel!=0 or any(m['active'] for m in before['modifiers'])
                or any(words[106*c+31]!=0 for c in range(4))):
            raise PermissionError('Exact bypassed Amp1A and four Legacy Cab channels required')
        self.dev,self.expected,self.sequence=dev,before,steps()
        self.index,self.failed=0,False
        self.quiet()
        dev._cab_probe=self

    def quiet(self):
        d=self.dev
        if d.get_param_display(d.reg.find_param('OUTPUT','OUTPUT_LEVEL'))!=-18 or d.get_bypass(58) is not True:
            raise PermissionError('Bypassed Amp1 and independently verified Output1 -18dB required')

    def write(self,frame):
        with self.dev._lock:
            if self.failed or self.index>=len(self.sequence):
                raise PermissionError('Cab calibration consumed or complete; no retry')
            self.failed=True
            d=self.dev
            d._check_edit_target()
            c,p,v=self.sequence[self.index]
            if (getattr(d,'_cab_probe',None) is not self or d.reg.firmware!=fw33_profile.KEY
                    or d._edit_target!=322 or getattr(d.reg,'hardware_variant',None)!='mk2'
                    or tuple(frame)!=frame_for(self.sequence[self.index])
                    or tone_review.snapshot(d,include_nam=False)!=self.expected):
                raise PermissionError('Exact literal, fresh full state and identity required')
            self.quiet()
            before=self.expected
            target=None
            if p is not None:
                current=next(b.channel for b in before['blocks'] if b.effect_id==62)
                if current!=c:raise PermissionError('Recorded channel context changed')
                target=round((v+40)/40*65534) if p in range(8,12) else round((v+1)/2*65534) if p in range(12,16) else int(v)
            d._cab_probe_permit=tuple(frame)
            try:d._write(list(frame))
            finally:d._cab_probe_permit=None
            for _ in range(5):
                time.sleep(.15)
                now=tone_review.snapshot(d,include_nam=False)
                wanted=dict(before)
                if p is None:
                    wanted['blocks']=[replace(b,channel=c) if b.effect_id==62 else b for b in before['blocks']]
                else:
                    pos=106*c+p
                    word=now['bulk'][62][pos]
                    if abs(word-target)>(1 if p in range(8,16) else 0):continue
                    words=list(before['bulk'][62]);words[pos]=word
                    wanted['bulk']={**before['bulk'],62:words}
                if now!=wanted:continue
                if p in (*range(8,16),*range(24,28)):
                    shown=d.read_display_text(62,p).strip()
                    if p in range(24,28):
                        if shown!=('--','MUTE','SOLO')[int(v)]:continue
                    else:
                        actual=float(shown.removesuffix(' dB'))
                        if abs(actual-(v*100 if p in range(12,16) else v))>.051:continue
                self.quiet()
                self.expected,self.index,self.failed=now,self.index+1,False
                return now
            raise ValueError('Cab literal/display/full-state mismatch; no write retry or rollback')

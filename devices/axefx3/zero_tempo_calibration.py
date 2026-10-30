"""Closed developer calibration only, not normal zero/tempo write authority."""
from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import time
from fm9 import protocol as shared
from . import fw33_profile,grid,protocol,serial_build,tone_review

HASHES={'amp':'495ec59b8afeb88fcf3b481d2d4ac84fff1ded7b6f84100c7d08f6a8cd9bb89b',
        'tempo':'d942c7ae8a0317a4445308377206ac44f7b64cb49595d2d67032dc36accff86a',
        'fxzero':'f2eb8eea5328c434906c471afd58677751cd477f98f55f9a54674e726b4e139c'}


def steps(mode):
    if mode not in HASHES:raise ValueError('Only closed Amp/Tempo/FX-zero calibration modes')
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_zero_tempo_calibration.json').read_text(encoding='utf-8'))
    values=data.get(mode+'_steps')
    if (data.get('firmware')!=fw33_profile.KEY or not isinstance(values,list)
            or hashlib.sha256(json.dumps(values,separators=(',',':')).encode('ascii')).hexdigest()!=HASHES[mode]):
        raise ValueError('Immutable measured zero/tempo sequence required')
    if mode=='amp':return tuple((kind,58,c,p,opcode,raw,shown) for kind,c,p,opcode,raw,shown in values)
    return tuple(('tempo' if mode=='tempo' else 'numeric',eid,0,p,opcode,raw,shown)
                 for eid,p,opcode,raw,shown in values)


def frame_for(step):
    kind,eid,c,p,opcode,raw,_=step
    if kind=='channel':return tuple(protocol.envelope(1,[22,0,eid,0,0,0,c,0,0,0,0,0,0,0,0]))
    return tuple(protocol.param_frame(eid,p,raw,opcode=opcode))


def allowed(dev,frame):
    probe=getattr(dev,'_zero_tempo_calibration',None)
    return (isinstance(probe,Probe) and probe.dev is dev and probe.failed
        and probe.index<len(probe.sequence) and dev.reg.firmware==fw33_profile.KEY
        and getattr(dev.reg,'hardware_variant',None)=='mk2' and dev._edit_target==322
        and getattr(dev,'_zero_tempo_permit',None)==tuple(frame)
        and tuple(frame)==frame_for(probe.sequence[probe.index]))


class Probe:
    def __init__(self,dev,mode):
        dev._check_edit_target()
        if (dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=322
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or getattr(dev,'_zero_tempo_calibration',None) is not None):
            raise PermissionError('One exact muted322 FW33/MK2 calibration required')
        before=tone_review.snapshot(dev,include_nam=False)
        status={b.effect_id:b for b in before['blocks']}
        if (before['scene']!=1 or grid.snapshot(before['grid'])!=serial_build.expected_grid()
                or any(m['active'] for m in before['modifiers'])
                or len(before['bulk'].get(58,[]))!=568 or status[58].channel!=0):
            raise PermissionError('Exact quiet row1/A and complete inactive modifiers required')
        if mode=='amp' and [before['bulk'][58][142*c] for c in range(4)]!=[14]*4:
            raise PermissionError('Four measured Brit800 model anchors required')
        if mode in ('tempo','fxzero') and any(status[eid].channel!=0 or not status[eid].bypassed or
                len(before['bulk'].get(eid,[]))!=stride*4 or before['bulk'][eid][0]!=model
                for eid,stride,model in ((78,32,3),(70,89,0))):
            raise PermissionError('Bypassed AnalogStereo/DigitalMono A anchors required')
        self.dev,self.expected,self.sequence=dev,before,steps(mode)
        self.index,self.failed=0,False
        self.quiet();dev._zero_tempo_calibration=self

    def quiet(self):
        d=self.dev
        level=d.get_param_display(d.reg.find_param('DISTORT','DISTORT_LEVEL'))
        if (d.get_param_display(d.reg.find_param('OUTPUT','OUTPUT_LEVEL'))!=-18
                or d.get_bypass(58) is not True or type(level) not in (int,float) or level>-18):
            raise PermissionError('Bypassed Amp and verified quiet levels required')

    def write(self,frame):
        with self.dev._lock:
            if self.failed or self.index>=len(self.sequence):
                raise PermissionError('Calibration consumed or complete; no retry')
            self.failed=True;d=self.dev;d._check_edit_target()
            step=self.sequence[self.index];kind,eid,c,p,opcode,raw,shown=step
            if (getattr(d,'_zero_tempo_calibration',None) is not self
                    or tuple(frame)!=frame_for(step) or tone_review.snapshot(d,include_nam=False)!=self.expected):
                raise PermissionError('Exact literal and fresh complete state required')
            self.quiet();before=self.expected
            if kind!='channel' and next(b.channel for b in before['blocks'] if b.effect_id==eid)!=c:
                raise PermissionError('Recorded current channel changed')
            d._zero_tempo_permit=tuple(frame)
            try:d._write(list(frame))
            finally:d._zero_tempo_permit=None
            for _ in range(5):
                time.sleep(.15);now=tone_review.snapshot(d,include_nam=False);wanted=dict(before)
                if kind=='channel':
                    wanted['blocks']=[replace(b,channel=c) if b.effect_id==eid else b for b in before['blocks']]
                else:
                    family='DISTORT' if eid==58 else 'CHORUS' if eid==78 else 'DELAY'
                    stride=fw33_profile.STRIDES[family];pos=stride*c+p
                    if kind=='tempo':
                        target=int(raw)
                        if str(d.read_display_text(eid,p)).strip().upper()!=shown:continue
                    else:
                        spec=d.reg.spec(family,p)
                        target=round(shared.display_to_normalized(shown,spec.dmin,spec.dmax,spec.scale)*65534)
                        actual=d.get_param_display(spec)
                        if actual is None or abs(actual-shown)>.011:continue
                    if abs(now['bulk'][eid][pos]-target)>(0 if kind=='tempo' else 1):continue
                    words=list(before['bulk'][eid]);words[pos]=now['bulk'][eid][pos]
                    wanted['bulk']={**before['bulk'],eid:words}
                if now!=wanted:continue
                self.quiet();self.expected,self.index,self.failed=now,self.index+1,False
                return now
            raise ValueError('Zero/tempo independent display/full-state mismatch; no retry or rollback')

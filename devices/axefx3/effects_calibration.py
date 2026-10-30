"""Fixed captured effect calibration only; no generic or AI write authority."""
from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import math
import time
from fm9 import protocol as shared
from . import fw33_profile,grid,protocol,serial_build,tone_review

SHA256='77741af17adb44fb266a1c0cf1900d7ef86e9d4ba5223f0913717d3e0e444082'
LAYOUTS={46:(37,12),50:(20,15),118:(44,0)}


def steps():
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_effect_calibration.json').read_text(encoding='utf-8'))
    seq=data.get('steps')
    if (not SHA256 or data.get('firmware')!=fw33_profile.KEY or not isinstance(seq,list)
            or hashlib.sha256(json.dumps(seq,separators=(',',':')).encode('ascii')).hexdigest()!=SHA256):
        raise ValueError('Closed exact effect calibration required')
    return tuple(tuple(s) for s in seq)


def frame_for(step):
    kind,eid,c,p,opcode,value=step
    if kind=='channel':return tuple(protocol.envelope(1,[22,0,eid,0,0,0,c,0,0,0,0,0,0,0,0]))
    return tuple(protocol.param_frame(eid,p,value,opcode=opcode))


def allowed(dev,frame):
    probe=getattr(dev,'_effects_calibration',None)
    return (isinstance(probe,Probe) and probe.dev is dev and probe.failed
        and probe.index<len(probe.sequence) and dev.reg.firmware==fw33_profile.KEY
        and getattr(dev.reg,'hardware_variant',None)=='mk2' and dev._edit_target==322
        and getattr(dev,'_effects_calibration_permit',None)==tuple(frame)
        and tuple(frame)==frame_for(probe.sequence[probe.index]))


def parameter(eid,p,value):
    """Return expected bulk word and independent display value for captured fields."""
    if eid==46:
        if p in (6,16):return int(value),'OFF' if value==0 else 'ON',0
        lo,hi,scale,mult,tol={0:(-60,20,'linear',1,.051),1:(1,20,'log10',1,.0011),
            2:(.1,100,'log10',1000,.011),3:(2,2000,'log10',1000,.21),
            4:(-20,20,'linear',1,.051),11:(0,100,'linear',100,.051)}[p]
    elif eid==50:
        if p in range(10):lo,hi,scale,mult,tol=-12,12,'linear',1,.026
        elif p==11:lo,hi,scale,mult,tol=-80,20,'linear',1,.051
        # Independently read GEQ A/B at Q1 as32767: geometric midpoint,
        # not the linear .1..10 law. Native .5/2/1 calibration is separate.
        elif p==16:lo,hi,scale,mult,tol=.1,10,'log10',1,.011
        else:raise ValueError('Unmeasured EQ field')
    else:raise ValueError('Unmeasured numeric effect')
    shown=value*mult
    return round(shared.display_to_normalized(shown,lo,hi,scale)*65534),shown,tol


class Probe:
    def __init__(self,dev):
        dev._check_edit_target()
        if (dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=322
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or getattr(dev,'_effects_calibration',None) is not None):
            raise PermissionError('One exact muted322 FW33/MK2 effect calibration required')
        before=tone_review.snapshot(dev,include_nam=False)
        if (before['scene']!=1 or grid.snapshot(before['grid'])!=serial_build.expected_grid()
                or any(len(before['bulk'].get(eid,[]))!=4*s for eid,(s,_) in LAYOUTS.items())
                or any(m['active'] for m in before['modifiers'])):
            raise PermissionError('Exact first-effect fixture and inactive modifiers required')
        sequence=steps();seen=set();status={b.effect_id:b for b in before['blocks']}
        for kind,eid,c,*_ in sequence:
            if eid not in seen and kind!='channel' and status[eid].channel!=c:
                raise PermissionError('Every first recorded channel context must match before ANY write')
            seen.add(eid)
        self.dev,self.expected,self.sequence=dev,before,sequence
        self.index,self.failed=0,False
        self.quiet();dev._effects_calibration=self

    def quiet(self):
        d=self.dev
        level=d.get_param_display(d.reg.find_param('DISTORT','DISTORT_LEVEL'))
        if (d.get_param_display(d.reg.find_param('OUTPUT','OUTPUT_LEVEL'))!=-18
                or d.get_bypass(58) is not True or d.get_channel(58)!=0
                or type(level) not in (int,float) or level>-18):
            raise PermissionError('Bypassed Amp1A and verified quiet levels required')

    def write(self,frame):
        with self.dev._lock:
            if self.failed or self.index>=len(self.sequence):
                raise PermissionError('Effect calibration consumed or complete; no retry')
            self.failed=True;d=self.dev;d._check_edit_target()
            step=self.sequence[self.index];kind,eid,c,p,opcode,value=step
            if (getattr(d,'_effects_calibration',None) is not self or d.reg.firmware!=fw33_profile.KEY
                    or d._edit_target!=322 or getattr(d.reg,'hardware_variant',None)!='mk2'
                    or tuple(frame)!=frame_for(step)
                    or tone_review.snapshot(d,include_nam=False)!=self.expected):
                raise PermissionError('Exact literal, full state and identity required')
            self.quiet();before=self.expected
            if kind!='channel' and next(b.channel for b in before['blocks'] if b.effect_id==eid)!=c:
                raise PermissionError('Recorded effect channel context changed')
            status=next(b for b in before['blocks'] if b.effect_id==eid)
            if kind=='model' and status.bypassed is not True:
                raise PermissionError('Effect must be bypassed before captured model change')
            if kind=='bypass' and value==0:
                stride,model=LAYOUTS[eid];v=before['bulk'][eid][stride*c:stride*(c+1)]
                safe={118:lambda:v[0]==8 and 0<=v[3]<=round(.25*65534),
                      46:lambda:v[12]==0 and v[6]==v[16]==0 and v[4]<=round(.2*65534),
                      50:lambda:v[15]==4 and v[11]<=round(.68*65534) and all(x<=32767 for x in v[:10])}
                if not safe[eid]():raise PermissionError('Captured engage requires explicitly quiet voiced effect')
            d._effects_calibration_permit=tuple(frame)
            try:d._write(list(frame))
            finally:d._effects_calibration_permit=None
            for _ in range(5):
                time.sleep(.15);now=tone_review.snapshot(d,include_nam=False);wanted=dict(before)
                if kind in ('channel','bypass'):
                    field='channel' if kind=='channel' else 'bypassed';v=c if kind=='channel' else bool(value)
                    wanted['blocks']=[replace(b,**{field:v}) if b.effect_id==eid else b for b in before['blocks']]
                else:
                    stride,model=LAYOUTS[eid];base=stride*c;words=list(before['bulk'][eid])
                    if p==model:
                        if now['bulk'][eid][base+p]!=int(value):continue
                        words[base:base+stride]=now['bulk'][eid][base:base+stride]
                    else:
                        target,shown,tol=parameter(eid,p,value)
                        if abs(now['bulk'][eid][base+p]-target)>1:continue
                        text=d.read_display_text(eid,p)
                        if not isinstance(text,str):continue
                        text=text.strip().replace(' %','').replace(' dB','').replace(' ms','').replace(' Hz','')
                        if isinstance(shown,str):
                            if text.upper()!=shown:continue
                        else:
                            try:actual=float(text)
                            except ValueError:continue
                            if not math.isfinite(actual) or abs(actual-shown)>tol:continue
                        words[base+p]=now['bulk'][eid][base+p]
                    wanted['bulk']={**before['bulk'],eid:words}
                if now!=wanted:continue
                self.quiet();self.expected,self.index,self.failed=now,self.index+1,False
                return now
            raise ValueError('Effect display/full-state mismatch; no retry or rollback')

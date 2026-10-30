"""Closed FW33 replay of editor-captured approved FW32.06 controls.

Developer329 fixture only, disconnected cells, no globals, route or Store.
Each literal gets independent display and complete unrelated-state checks.
"""
from dataclasses import replace
import hashlib,json,time
from importlib.resources import files
from fm9 import protocol as shared
from . import fw33_profile,grid,tone_review,protocol
from .registry import Registry

SHA='b3d74bf1b1cd3455a3c85d83d7b5b5187fa14c7018eead912bf5e9bc4a68841d'
LAYOUTS={94:('WAH',25),54:('PEQ',33),110:('PITCH',116),102:('VOLPAN',15)}
FIXTURE={(1,1):(94,False,0),(1,2):(54,False,0),(1,3):(110,False,0),(1,4):(102,False,0)}


def frames():
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_inherited_controls.json').read_text(encoding='utf-8'))
    seq=data.get('frames')
    if (data.get('firmware')!=fw33_profile.KEY or not isinstance(seq,list) or len(seq)!=38
            or hashlib.sha256(json.dumps(seq,separators=(',',':')).encode()).hexdigest()!=SHA):
        raise ValueError('Inherited-control capture changed')
    return tuple(tuple(bytes.fromhex(x)) for x in seq)


def allowed(dev,frame):
    p=getattr(dev,'_inherited_controls_probe',None)
    return (isinstance(p,Probe) and p.dev is dev and p.consumed and p.index<len(frames())
        and p.pending==tuple(frame)==frames()[p.index]
        and dev.reg.firmware==fw33_profile.KEY and dev._edit_target==329
        and getattr(dev.reg,'hardware_variant',None)=='mk2')


class Probe:
    def __init__(self,dev):
        dev._check_edit_target()
        if (dev.reg.firmware!=fw33_profile.KEY or dev._edit_target!=329
                or getattr(dev.reg,'hardware_variant',None)!='mk2'
                or getattr(dev,'_inherited_controls_probe',None) is not None):
            raise PermissionError('Exact muted329/FW33/MK2 measurement required')
        before=tone_review.snapshot(dev,include_nam=False)
        if (before['scene']!=1 or grid.snapshot(before['grid'])!=FIXTURE
                or any(b.channel!=0 or b.channels_supported!=4 for b in before['blocks'] if b.effect_id in LAYOUTS)
                or set(before['bulk'])!=set(LAYOUTS)
                or any(len(before['bulk'][e])!=4*n for e,(_,n) in LAYOUTS.items())):
            raise PermissionError('Disconnected four-block fixture and complete A layouts required')
        # Volume control is the only permitted active modifier in this fixture.
        from .pedal_control import default_words
        active=[m for m in before['modifiers'] if m['active']]
        if len(active)!=1 or active[0]['words']!=[13]+default_words(102)[1:]:
            raise PermissionError('Captured Volume External2/Off curve required, no modifier cleared')
        self.dev,self.expected=dev,before
        self.index,self.consumed,self.pending=0,False,None
        dev._inherited_controls_probe=self

    def write_next(self):
        if self.consumed or self.index>=len(frames()):raise PermissionError('Consumed measurement; never retry')
        self.consumed=True;d=self.dev;d._check_edit_target()
        before=tone_review.snapshot(d,include_nam=False)
        if before!=self.expected:raise PermissionError('Fresh fixture changed before write')
        frame=list(frames()[self.index]);eid=shared.decode14(*frame[8:10]);pid=shared.decode14(*frame[10:12])
        wire=shared.decode_f32_septets(frame[12:17])
        if eid not in (94,54,110):raise PermissionError('Uncaptured target')
        family,stride=LAYOUTS[eid]
        special=eid==94 and pid in (0,12)
        if special:spec=None
        else:
            # Reuse the already accepted FW33 override, notably direct-dB
            # Wah Level. Only genuinely missing controls use parent metadata.
            try:spec=d.reg.spec(family,pid)
            except (ValueError,KeyError):spec=Registry('32.06').spec(family,pid)
        value=None if special else (shared.normalized_to_display(wire,spec.dmin,spec.dmax,spec.scale)
            if spec.set_divisor is None else wire*spec.set_divisor)
        self.pending=tuple(frame)
        try:d._write(frame)
        finally:self.pending=None
        for _ in range(5):
            time.sleep(.15);now=tone_review.snapshot(d,include_nam=False);wanted=dict(before)
            if eid==94 and pid==12:
                wanted['blocks']=[replace(b,bypassed=bool(wire)) if b.effect_id==94 else b for b in before['blocks']]
            else:
                words=list(before['bulk'][eid])
                if eid==94 and pid==0:
                    if now['bulk'][94][0]!=2:continue
                    words[:stride]=now['bulk'][94][:stride]
                else:
                    target=round(shared.display_to_normalized(value,spec.dmin,spec.dmax,spec.scale)*65534)
                    if abs(now['bulk'][eid][pid]-target)>1:continue
                    shown=d._parse_display_value(d.read_display_text(eid,pid),spec.unit)
                    if shown is None or abs(shown-value)>(spec.display_tolerance or .051):continue
                    words[pid]=now['bulk'][eid][pid]
                wanted['bulk']={**before['bulk'],eid:words}
            if now!=wanted:continue
            self.expected,self.index,self.consumed=now,self.index+1,False
            return dict(index=self.index,effect_id=eid,param_id=pid,display=value,frame=bytes(frame).hex(' '),state=now)
        raise ValueError('Inherited control display/full-state mismatch; no retry or rollback')

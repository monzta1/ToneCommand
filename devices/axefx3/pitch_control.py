"""Reviewed existing Pitch1/A octave pedal, exact MK2 Beta5 profile only.

No generic setter, placement, scene/channel selection, global CC change,
Store, write retry or automatic restoration. This component shares the host's
existing device lock/connection but owns its final exact-frame output boundary.
Ordinary adapter writing capabilities remain unchanged.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import struct
import sys
import threading
import time

import mido

from fm9 import protocol as shared
from fm9.safety import sysex_guard
from . import firmware_identity, protocol


RELEASED = True  # Exact MK2 Beta5 existing-block feature, not builder support.
EID, STRIDE, MODEL = 110, 116, 9
PIDS = dict(model=0, control=3, start=15, stop=16, mix=38, level=39, bypass=44)
VALUES = dict(model=(0,9), control=(0.,50.,100.), start=(0.,6.),
    stop=(6.,12.), mix=(50.,100.), level=(-12.,0.), bypass=(0,1),
    source=(0,12,13), channel=(0,1), allocate=(None,), remove=(None,))
# Independently captured native factory curve. Comparison data, NEVER sent.
DEFAULT_MODIFIER = (0,0,65534,0,32767,65534,32767,66,110,3,
    0,0,0,32767,32767,66,0,0,0,0,0,65534,65534,0,0)


class PitchReadbackError(RuntimeError):
    """A Pitch write may have happened. Keep monitoring muted; do not retry."""


def _platform(dev):
    if getattr(dev, '_injected_ports', True) is False:
        from fm9 import midi_transport
        return (sys.platform == 'win32' and sys.version_info[:2] == (3,12)
            and struct.calcsize('P') == 8 and midi_transport.backend() == 'mido')
    return True  # Explicit scripted ports remain available to offline tests.


def supported(dev):
    """Metadata lookup only. Fresh full identity is checked before reviewing."""
    return (RELEASED and dev.reg.firmware == firmware_identity.BETA5_KEY
        and getattr(dev.reg, 'hardware_variant', None) == 'mk2' and _platform(dev))


@dataclass(frozen=True)
class Setup:
    source: int
    engage: bool = True

    def __post_init__(self):
        if type(self.source) is not int or self.source not in (12,13) or type(self.engage) is not bool:
            raise ValueError('Choose External 1 or External 2; octave-pedal setup has no global CC mapping')


@dataclass(frozen=True)
class Step:
    key: str
    value: float | None

    def __post_init__(self):
        if (type(self.key) is not str or self.key not in VALUES
                or type(self.value) not in (int,float,type(None))
                or self.value not in VALUES[self.key]):
            raise ValueError('Only independently captured Pitch operation literals')

    def frame(self, slot=None):
        if self.key == 'allocate':
            return protocol.envelope(1,[58,0,110,0,3,0]+[0]*9)
        if self.key in ('source','channel','remove'):
            if type(slot) is not int or slot not in range(1,33):
                raise ValueError('A freshly verified modifier owner is required')
            if self.key == 'remove':
                return protocol.envelope(1,[59,0,slot+2,0]+[0]*11)
            return protocol.param_frame(slot+2,0 if self.key=='source' else 17,self.value,opcode=9)
        value=self.value/100 if self.key in ('control','mix') else self.value
        return protocol.param_frame(EID,PIDS[self.key],value,opcode=9)


def stamp(state):
    return hashlib.sha256(json.dumps(state,sort_keys=True,allow_nan=False).encode()).hexdigest()


def owner(state):
    found=[i for i,w in enumerate(state['modifiers']) if w[8:10]==[EID,3]]
    if len(found)>1:raise ValueError('Multiple modifiers own Pitch Control; nothing inferred')
    return found[0] if found else None


def curve(words):
    expected=list(DEFAULT_MODIFIER)
    return (len(words)==25 and words[0] in (0,12,13) and words[17] in (0,1)
        and all(words[i]==expected[i] for i in range(25) if i not in (0,17)))


def numeric_word(key, value):
    if key in ('control','mix'):
        return round(value/100*65534)
    if key=='level':
        return round((value+80)/100*65534)
    return int(value)


class Output:
    """One consumed, owning-thread permit; always send fresh checked bytes."""
    guard=sysex_guard('Reviewed Pitch octave pedal',{1})

    def __init__(self, writer):
        self.writer,self.permit=writer,None

    @contextmanager
    def once(self, step, slot):
        if (type(step) is not Step or self.writer._active_step is not step
                or self.permit is not None):
            raise PermissionError('Only the active reviewed Pitch step can arm a permit')
        if not self.writer.calibration and (step.key=='remove'
                or step.key=='model' and step.value!=9 or step.key=='source' and step.value==0):
            raise PermissionError('Restoration/deletion is not an ordinary Pitch setup operation')
        frame=step.frame(slot)
        self.permit=(threading.get_ident(),tuple(frame))
        try:yield
        finally:self.permit=None

    def send(self, message):
        frame=message.bytes() if message.type=='sysex' else []
        w=self.writer
        if (not w.active or getattr(w.dev,'_pitch_uncertain',False)
                or getattr(w.dev.outp,'closed',False)
                or w._executing is None or self.writer._active_step is None
                or w.clock()>=w._executing.expires
                or w.dev.reg.firmware!=firmware_identity.BETA5_KEY
                or getattr(w.dev.reg,'hardware_variant',None)!='mk2'
                or self.permit!=(threading.get_ident(),tuple(frame))
                or len(frame)!=23 or frame[:6]!=[240,0,1,116,16,1]
                or frame[-1]!=247 or not protocol.valid_reply(frame[1:-1])):
            raise PermissionError('No active exact Pitch write permit')
        self.guard.check(frame[5])
        self.permit=None
        w._attempted=True
        w.dev.outp.send(mido.Message('sysex',data=frame[1:-1]))


@dataclass(frozen=True)
class Review:
    request: Setup | Step
    baseline: str
    expires: float


class Writer:
    """Same host connection, independently pinned feature permission."""
    def __init__(self,dev,*,calibration=False,clock=time.monotonic):
        if type(calibration) is not bool or not (supported(dev) or calibration):
            raise PermissionError('Pitch requires the accepted MK2 Beta5 feature profile')
        self.dev,self.calibration,self.clock=dev,calibration,clock
        self.active,self.pending=False,None
        self._active_step,self._executing,self._attempted=None,None,False
        self.output=Output(self)

    def observe(self):
        d=self.dev
        if (getattr(d,'_pitch_uncertain',False) or d.reg.firmware!=firmware_identity.BETA5_KEY
                or getattr(d.reg,'hardware_variant',None)!='mk2' or not _platform(d)):
            raise PermissionError('Pitch connection/profile changed or is uncertain')
        ident=d._request(protocol.envelope(8,[]),firmware_identity.parse_response)
        if ident is None or hashlib.sha256(bytes(ident)).hexdigest()!=firmware_identity.BETA5_IDENTITY_SHA256:
            raise PermissionError('Exact measured MK2 Beta5 identity required')
        preset,scene=d.current_preset(),d.current_scene()
        if (not preset or type(preset[0]) is not int or preset[0] not in range(1024)
                or type(scene) is not int or scene not in range(1,9)):
            raise ValueError('Current preset and scene must be readable')
        blocks,cells=d.status_dump(),d.read_grid()
        if blocks is None or cells is None:raise ValueError('Complete grid and block status required')
        ids=[b.effect_id for b in blocks]
        pitch=[b for b in blocks if b.effect_id==EID]
        if (len(ids)!=len(set(ids)) or len(pitch)!=1 or pitch[0].channel!=0
                or pitch[0].channels_supported!=4 or sum(c.effect_id==EID for c in cells)!=1):
            raise ValueError('An existing Pitch 1 on channel A is required; no insertion or channel switch')
        if self.calibration and (preset[0]!=327 or scene!=1
                or sorted((c.row,c.col,c.effect_id,c.is_shunt,c.cable_in_mask) for c in cells)
                !=[(0,i,e,False,0) for i,e in enumerate((58,62,118,110,206))]):
            raise PermissionError('Calibration requires disconnected327 with the measured five blocks')
        bulk={str(e):d.bulk_read(e) for e in sorted(ids)}
        mods=[d.read_modifier(s) for s in range(1,33)]
        if (any(not isinstance(w,list) or not w or len(w)>16384
                or any(type(v) is not int or not 0<=v<=65535 for v in w) for w in bulk.values())
                or len(bulk[str(EID)])!=4*STRIDE
                or any(not isinstance(w,list) or len(w)!=25 or any(type(v) is not int or not 0<=v<=65534 for v in w) for w in mods)):
            raise ValueError('All block bulks and32 complete modifier records are required')
        shown={}
        for key in ('start','stop','control','mix','level'):
            text=d.read_display_text(EID,PIDS[key])
            if not isinstance(text,str) or re.fullmatch(r'-?\d+(?:\.\d+)?(?: %| dB)?',text) is None:
                raise ValueError('Independent Pitch display unreadable: '+key)
            shown[key]=float(text.removesuffix(' %').removesuffix(' dB'))
        bypass_text=d.read_display_text(EID,44)
        if not isinstance(bypass_text,str) or not bypass_text:
            raise ValueError('Independent Pitch bypass display unreadable')
        shown['bypass']=bypass_text
        if bypass_text!=('BYPASSED' if pitch[0].bypassed else 'ENGAGED'):
            raise ValueError('Pitch status and independent bypass display disagree')
        names=[d.scene_name(s) for s in range(1,9)]
        if any(n is None or n[0]!=i or not isinstance(n[1],str) for i,n in enumerate(names,1)):
            raise ValueError('All eight scene names must be read')
        if d.current_preset()!=preset or d.current_scene()!=scene or d.status_dump()!=blocks:
            raise ValueError('Target or block status changed during reading')
        state=dict(identity=list(ident),preset=list(preset),scene=scene,
            firmware=d.reg.firmware,chassis=d.reg.hardware_variant,
            blocks=sorted((asdict(b) for b in blocks),key=lambda b:b['effect_id']),
            grid=sorted((asdict(c) for c in cells),key=lambda c:(c['row'],c['col'])),
            bulk=bulk,modifiers=mods,names=[list(n) for n in names],shown=shown)
        index=owner(state)
        if bulk[str(EID)][0] not in (0,MODEL):
            raise ValueError('Existing Pitch model must be Dual Detune or Advanced Whammy; other model transitions are unverified')
        if index is not None and not curve(mods[index]):
            raise ValueError('Existing Pitch modifier curve/source/mode is not the measured full-range curve')
        if any(w[0] and w[8]==EID and w[9]!=3 for w in mods):
            raise ValueError('Other active Pitch modifiers can override model/level/range; preserve and resolve first')
        if (not -24<=shown['start']<=24 or not -24<=shown['stop']<=24
                or not 0<=shown['control']<=100 or not 0<=shown['mix']<=100
                or not -80<=shown['level']<=0):
            raise ValueError('Pitch values exceed the conservative observed surface')
        return state

    def prepare(self,request):
        self.pending=None
        if type(request) is not Setup and not (self.calibration and type(request) is Step):
            raise ValueError('A typed octave-pedal setup is required')
        with self.dev._lock:
            before=self.observe()
            if self.observe()!=before:raise ValueError('Pitch baseline changed during review')
            self.preflight(request,before)
            self.pending=Review(request,stamp(before),self.clock()+60)
            return self.pending,before

    def preflight(self,request,state):
        """Reject predictable whole-setup blockers before any quiet staging SET."""
        index=owner(state)
        steps=self.steps(request,state)
        if (any(step.key=='model' and step.value==MODEL for step in steps)
                and state['bulk'][str(EID)][35] not in (1,2)):
            raise ValueError('Starting Pitch model-default word35 has not been measured')
        allocating=any(step.key=='allocate' for step in steps)
        if allocating and (index is not None or not any(w[0]==w[8]==0 for w in state['modifiers'])):
            raise ValueError('Allocation has an existing owner or no native free modifier slot')
        if not allocating and index is None and any(step.key in ('source','channel','remove') for step in steps):
            raise ValueError('No verified Pitch modifier owner')
        return steps

    def steps(self,request,state):
        if type(request) is Step:return [request]
        result=[Step('bypass',1),Step('level',-12)]
        if state['bulk'][str(EID)][0]!=MODEL:result.append(Step('model',MODEL))
        result.extend([Step('start',0),Step('stop',12),Step('mix',100)])
        if owner(state) is None:
            result.extend([Step('control',0),Step('allocate',None)])
        result.extend([Step('channel',1),Step('source',request.source),Step('level',0)])
        result.append(Step('bypass',0 if request.engage else int(next(b['bypassed'] for b in state['blocks'] if b['effect_id']==EID))))
        return result

    def expected(self,before,after,step):
        want=deepcopy(before)
        pitch=want['bulk'][str(EID)]
        index=owner(before)
        if step.key=='model':
            pitch[0]=int(step.value)
            if step.value==MODEL:
                pitch[35]=2  # Captured Advanced Whammy model default, not a separate setter.
            pitch[38]=65534 if step.value==9 else 32767
            want['shown']['mix']=100. if step.value==9 else 50.
        elif step.key=='bypass':
            for block in want['blocks']:
                if block['effect_id']==EID:block['bypassed']=bool(step.value)
            want['shown']['bypass']='BYPASSED' if step.value else 'ENGAGED'
        elif step.key in ('source','channel','remove'):
            if index is None:raise ValueError('Pitch modifier owner disappeared')
            if step.key=='remove':
                want['modifiers'][index]=list(DEFAULT_MODIFIER)
                want['modifiers'][index][8]=0
            else:want['modifiers'][index][0 if step.key=='source' else 17]=int(step.value)
        elif step.key=='allocate':
            if index is not None:raise ValueError('Pitch already has a modifier; never reallocate')
            free=next((i for i,w in enumerate(before['modifiers']) if w[0]==w[8]==0),None)
            if free is None:raise ValueError('No native free modifier slot')
            want['modifiers'][free]=list(DEFAULT_MODIFIER)
        else:
            pid=PIDS[step.key]
            pitch[pid]=numeric_word(step.key,step.value)
            want['shown'][step.key]=float(step.value)
        index=owner(want)
        if index is not None and want['modifiers'][index][0] in (12,13):
            # A physical source may move this one live Control, not its curve,
            # the range, other channels, levels, another modifier or any block.
            pitch[3]=after['bulk'][str(EID)][3]
            want['shown']['control']=after['shown']['control']
        return want

    def apply(self,review,*,external_audio_muted=False,target_confirmed=False):
        with self.dev._lock:
            if type(review) is not Review or review is not self.pending:
                raise ValueError('Pitch review is foreign, replaced or consumed')
            self.pending=None
            if (external_audio_muted is not True or target_confirmed is not True
                    or self.clock()>=review.expires):
                raise PermissionError('Confirm target and external mute with an unexpired Pitch review')
            state=self.observe()
            if stamp(state)!=review.baseline:raise ValueError('Pitch state changed after review; nothing sent')
            steps=self.preflight(review.request,state)
            result=[];complete=False
            self._attempted=False
            self._executing=review
            self.active=True
            try:
                for step in steps:
                    if self.clock()>=review.expires:raise PermissionError('Pitch review expired before the next SET')
                    now=self.observe()
                    if now!=state:raise ValueError('State changed before next Pitch SET')
                    index=owner(state)
                    if step.key in ('source','channel','remove') and index is None:
                        raise ValueError('No verified Pitch modifier owner')
                    if step.key=='allocate' and (index is not None or not any(w[0]==w[8]==0 for w in state['modifiers'])):
                        raise ValueError('Allocation has an existing owner or no free slot')
                    if self.clock()>=review.expires:raise PermissionError('Pitch review expired during preflight')
                    noop=(step.key in ('start','stop','control','mix','level')
                        and state['bulk'][str(EID)][PIDS[step.key]]==numeric_word(step.key,step.value)
                        and abs(state['shown'][step.key]-step.value)<.011
                        or step.key=='model' and state['bulk'][str(EID)][0]==step.value
                        or step.key=='bypass' and next(b['bypassed'] for b in state['blocks'] if b['effect_id']==EID)==bool(step.value)
                        or step.key in ('source','channel') and state['modifiers'][index][0 if step.key=='source' else 17]==step.value)
                    if noop:
                        result.append(dict(operation=step.key,sent=False));continue
                    frame=step.frame(None if index is None else index+1)
                    self._active_step=step
                    with self.output.once(step,None if index is None else index+1):
                        self.output.send(mido.Message('sysex',data=frame[1:-1]))
                    self._active_step=None
                    for _ in range(5):
                        time.sleep(.15)
                        after=self.observe()
                        if after==self.expected(state,after,step):break
                    else:raise ValueError('Pitch display/full-state preservation failed')
                    state=after
                    result.append(dict(operation=step.key,sent=True))
                complete=True
                return dict(ok=True,stored=False,results=result,pitch_verified=True,
                    notice='Edit buffer only. Test the physical pedal at low monitoring level. No limiter or automatic Undo.')
            except (ValueError,RuntimeError,OSError,PermissionError) as exc:
                if self._attempted:
                    self.dev._pitch_uncertain=True
                    raise PitchReadbackError('A Pitch write may have happened; connection is uncertain. Keep audio muted; no retry or rollback. '+str(exc)) from exc
                raise
            finally:
                self.active=False
                self._active_step,self._executing=None,None
                # Interruptions after a send also consume the connection.
                if self._attempted and not complete:
                    self.dev._pitch_uncertain=True

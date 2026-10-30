"""Unregistered Pitch placement primitive for the captured isolated327 fixture.

Existing connection only. No cables, other positions, model/parameter writes,
controller allocation, deletion, Store or normal text/planner activation.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict,dataclass
import hashlib
import json
import math
import re
import threading
import time

import mido
from fm9.safety import sysex_guard
from . import firmware_identity,protocol,pitch_control


TARGET=327
POSITION=(0,1)
WORDS={58:568,110:464,200:1525,201:350}
LITERALS={
    'cursor':'f0 00 01 74 10 01 30 00 00 00 00 00 06 00 00 00 00 00 00 00 00 22 f7',
    'insert':'f0 00 01 74 10 01 32 00 6e 00 00 00 17 00 00 00 00 00 00 00 00 5f f7',
}


class PlacementReadbackError(RuntimeError):
    """A grid command may have happened. Keep audio muted; no retry/restore."""


@dataclass(frozen=True)
class Request:
    preset:int

    def __post_init__(self):
        if type(self.preset) is not int or self.preset!=TARGET:
            raise ValueError('This captured placement primitive requires disposable preset327')


@dataclass(frozen=True)
class Review:
    request:Request
    baseline:str
    expires:float


class Output:
    guard=sysex_guard('Closed Pitch placement',{1})

    def __init__(self,writer):self.writer,self.permit=writer,None

    @contextmanager
    def once(self,operation):
        w=self.writer
        if (type(operation) is not str or operation not in LITERALS or not w.active
                or w._step!=operation or self.permit is not None):
            raise PermissionError('Only the active reviewed captured placement step may arm output')
        frame=tuple(bytes.fromhex(LITERALS[operation]))
        self.permit=(threading.get_ident(),frame)
        try:yield
        finally:self.permit=None

    def send(self,message):
        w=self.writer;frame=message.bytes() if message.type=='sysex' else []
        w.context()
        if (not w.active or w._executing is None or w._step not in LITERALS
                or w.clock()>=w._executing.expires
                or self.permit!=(threading.get_ident(),tuple(frame))
                or frame!=list(bytes.fromhex(LITERALS[w._step]))
                or not protocol.valid_reply(frame[1:-1])):
            raise PermissionError('No exact one-use, thread-owned Pitch placement permit')
        self.guard.check(frame[5]);self.permit=None;w._attempted=True
        w.dev.outp.send(mido.Message('sysex',data=frame[1:-1]))


def fingerprint(state):
    return hashlib.sha256(json.dumps(state,sort_keys=True,allow_nan=False).encode()).hexdigest()


class Writer:
    """Developer composition only; call outside an already held host lock.

    host_lock/selected/gig_locked must be the host's actual switching boundary.
    Explicit scripted devices are an offline test interface, not a sandbox.
    """
    def __init__(self,dev,*,host_lock,selected,gig_locked,calibration=False,clock=time.monotonic):
        if calibration is not True:
            raise PermissionError('Pitch placement is an unregistered calibration primitive')
        self.dev,self.host_lock,self.selected,self.gig_locked=dev,host_lock,selected,gig_locked
        self.clock,self.pending=clock,None
        self.active,self._attempted=False,False
        self._executing,self._step=None,None
        self.output=Output(self)

    def context(self):
        d=self.dev
        if (self.selected() is not d or self.gig_locked() is not False
                or getattr(d,'_pitch_uncertain',False) or getattr(d.outp,'closed',False)
                or d.reg.firmware!=firmware_identity.BETA5_KEY
                or getattr(d.reg,'hardware_variant',None)!='mk2' or not pitch_control._platform(d)):
            raise PermissionError('Current certain MK2 Beta5 connection, measured runtime and Gig Lock off required')

    def observe(self):
        self.context();d=self.dev
        identity=d._request(protocol.envelope(8,[]),firmware_identity.parse_response)
        if identity is None or hashlib.sha256(bytes(identity)).hexdigest()!=firmware_identity.BETA5_IDENTITY_SHA256:
            raise PermissionError('Exact full Beta5 identity required for placement')
        preset,scene=d.current_preset(),d.current_scene()
        blocks,cells=d.status_dump(),d.read_grid()
        if not preset or preset[0]!=TARGET or scene!=1 or blocks is None or cells is None:
            raise ValueError('Select disconnected disposable327/scene1 before preparing placement')
        ids=[b.effect_id for b in blocks]
        if (len(ids)!=len(set(ids)) or set(ids) not in ({58,200,201},{58,110,200,201})
                or any(b.channel!=0 or b.channels_supported!=(1 if b.effect_id in (200,201) else 4) for b in blocks)):
            raise ValueError('Only the isolated Amp1/A and optional existing Pitch1/A fixture is supported')
        grid=sorted((asdict(c) for c in cells),key=lambda c:(c['row'],c['col']))
        want=[dict(row=0,col=0,effect_id=58,is_shunt=False,cable_in_mask=0)]
        if 110 in ids:want.append(dict(row=0,col=1,effect_id=110,is_shunt=False,cable_in_mask=0))
        if grid!=want:raise ValueError('No I/O, cables, shunts, replacement or other placement position')
        bulk={str(e):d.bulk_read(e) for e in sorted(ids)}
        mods=[d.read_modifier(n) for n in range(1,33)]
        if (any(not isinstance(bulk[str(e)],list) or len(bulk[str(e)])!=WORDS[e]
                or any(type(v) is not int or not 0<=v<=65535 for v in bulk[str(e)]) for e in ids)
                or any(not isinstance(w,list) or len(w)!=25 or any(type(v) is not int or not 0<=v<=65534 for v in w)
                       or w[0]!=0 or w[8]!=0 for w in mods)):
            raise ValueError('Complete block data and32 inactive unassigned modifiers must be preserved')
        level=d.read_display_text(58,21)
        if not isinstance(level,str) or re.fullmatch(r'-?\d+(?:\.\d+)?(?: dB)?',level) is None:
            raise ValueError('Independent Amp level must be readable')
        level=float(level.removesuffix(' dB'))
        if not math.isfinite(level) or not -80<=level<=-12 or bulk['58'][0]!=0:
            raise ValueError('The existing Bassguy/A fixture must remain at most -12dB')
        names=[d.scene_name(n) for n in range(1,9)]
        if any(not n or n[0]!=i or type(n[1]) is not str for i,n in enumerate(names,1)):
            raise ValueError('All eight scene names are required')
        self.context()
        if (d.current_preset()!=preset or d.current_scene()!=scene or d.status_dump()!=blocks
                or d.read_grid()!=cells or d._request(protocol.envelope(8,[]),firmware_identity.parse_response)!=identity):
            raise ValueError('Placement context changed during inspection')
        return dict(identity=list(identity),preset=list(preset),scene=scene,
            status=sorted((asdict(b) for b in blocks),key=lambda b:b['effect_id']),grid=grid,
            bulk=bulk,modifiers=mods,names=[list(n) for n in names],level=level)

    def prepare(self,request):
        with self.host_lock,self.dev._lock:
            self.pending=None
            if type(request) is not Request:raise ValueError('An explicit placement Request is required')
            before=self.observe()
            if self.observe()!=before:raise ValueError('Placement baseline is unstable')
            review=Review(request,fingerprint(before),self.clock()+60)
            self.pending=review
            return review,before

    @staticmethod
    def matches(before,after):
        if '110' not in after['bulk']:return False
        normalized=deepcopy(after);normalized['bulk'].pop('110')
        normalized['status']=[b for b in normalized['status'] if b['effect_id']!=110]
        normalized['grid']=[c for c in normalized['grid'] if c['effect_id']!=110]
        return normalized==before

    def apply(self,review,*,external_audio_muted=False,target_confirmed=False):
        with self.host_lock,self.dev._lock:
            if type(review) is not Review or review is not self.pending:
                raise ValueError('Placement review is foreign, replaced or consumed')
            self.pending=None
            if (external_audio_muted is not True or target_confirmed is not True
                    or self.clock()>=review.expires):
                raise PermissionError('Fresh exact target confirmation and external mute are required')
            before=self.observe()
            if fingerprint(before)!=review.baseline:raise ValueError('Placement state changed since review')
            if self.clock()>=review.expires:raise PermissionError('Placement review expired during inspection')
            if '110' in before['bulk']:
                return dict(verified=True,sent=False,stored=False,already_present=True)
            complete=False;self.active=True;self._executing=review;self._attempted=False
            try:
                for operation in ('cursor','insert'):
                    if self.clock()>=review.expires or self.observe()!=before:
                        raise ValueError('Placement context changed or expired before the next frame')
                    if self.clock()>=review.expires:raise PermissionError('Review expired during preflight')
                    self._step=operation
                    with self.output.once(operation):
                        self.output.send(mido.Message('sysex',data=bytes.fromhex(LITERALS[operation])[1:-1]))
                    self._step=None
                for _ in range(4):
                    time.sleep(.15);after=self.observe()
                    if self.matches(before,after):break
                else:raise ValueError('Inserted Pitch or complete-state preservation was not verified')
                complete=True
                return dict(verified=True,sent=True,stored=False,already_present=False)
            except (ValueError,RuntimeError,OSError,PermissionError) as exc:
                if self._attempted:
                    raise PlacementReadbackError('A grid command may have happened; keep audio muted. No retry or automatic restoration. '+str(exc)) from exc
                raise
            finally:
                if self._attempted and not complete:self.dev._pitch_uncertain=True
                self.active=False;self._executing,self._step=None,None

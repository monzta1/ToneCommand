"""Explicit closed Beta5 Amp calibration, not constructed by the normal app.

Four captured Gain/Mid values on disconnected test327 only. No model, routing,
level, channel, controller, NAM, Store or general firmware write promotion.
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
from . import protocol, firmware_identity
from .adapter import AxeFxIII


TARGET = 327
IDS = (58,62,118,110,206,200,201)
WORDS = {58:568,62:424,118:176,110:464,206:72,200:1525,201:350}
# Exact outgoing editor literals, 27 October 2026, Axe-Edit 1.15.02.
LITERALS = {
    ('gain',4.6): 'f0 00 01 74 10 01 09 00 3a 00 01 00 1e 0a 2e 77 03 00 00 00 00 68 f7',
    ('gain',5.): 'f0 00 01 74 10 01 09 00 3a 00 01 00 00 00 00 78 03 00 00 00 00 5d f7',
    ('mid',5.6): 'f0 00 01 74 10 01 09 00 3a 00 03 00 29 38 3d 78 03 00 00 00 00 73 f7',
    ('mid',5.): 'f0 00 01 74 10 01 09 00 3a 00 03 00 00 00 00 78 03 00 00 00 00 5f f7',
}
PIDS = {'gain':1,'mid':3}


@dataclass(frozen=True)
class Edit:
    control: str
    value: float

    def __post_init__(self):
        if (type(self.control) is not str or type(self.value) not in (int,float)
                or not math.isfinite(self.value) or (self.control,self.value) not in LITERALS):
            raise ValueError('Only the four captured Beta5 Gain/Mid calibration literals')

    def frame(self):
        return list(bytes.fromhex(LITERALS[self.control,self.value]))


def read_query(frame):
    if (len(frame)<8 or frame[0]!=240 or frame[-1]!=247
            or not protocol.valid_reply(frame[1:-1])):
        return False
    fn,payload=frame[5],frame[6:-2]
    if fn in (8,19):return payload==[]
    if fn==13:return payload==[127,127]
    if fn==12:return payload==[127]
    if fn==14:return len(payload)==1 and payload[0] in (*range(8),127)
    if fn==31:return len(payload)==2 and shared.decode14(*payload) in (*IDS,*range(3,35))
    if frame==shared.envelope(1,[shared.SUB_GRID_LAYOUT,0]+[0]*13,model=16):return True
    return frame in [protocol.display_query(58,pid) for pid in (1,3,21)]


class Output:
    guard=sysex_guard('Closed Beta5 Amp calibration', {1,8,12,13,14,19,31})

    def __init__(self,port):
        self.port,self.permit,self.owner=port,None,None

    @contextmanager
    def once(self,edit):
        if type(edit) is not Edit or self.permit is not None:
            raise PermissionError('One exact calibration edit required')
        self.permit=(threading.get_ident(),tuple(edit.frame()))
        try:yield
        finally:self.permit=None

    def send(self,message):
        frame=message.bytes() if message.type=='sysex' else []
        if not read_query(frame):
            owner=self.owner
            if (owner is None or owner.uncertain or owner.closed or not owner.active
                    or self.permit!=(threading.get_ident(),tuple(frame))):
                raise PermissionError('No active single-use Beta5 calibration permit')
            self.guard.check(frame[5])
            self.permit=None
        self.port.send(mido.Message('sysex',data=frame[1:-1]))

    def close(self):self.port.close()


@dataclass(frozen=True)
class Review:
    edit: Edit
    baseline: str
    expires: float


class Device(AxeFxIII):
    """Separate developer component; ordinary adapter gates are not changed."""
    def __init__(self,ports=None):
        if ports is None:
            from fm9 import midi_transport
            if (sys.platform!='win32' or sys.version_info[:2]!=(3,12)
                    or struct.calcsize('P')!=8 or midi_transport.backend()!='mido'):
                raise PermissionError('Native calibration requires Windows/Python3.12/mido')
            ports=midi_transport.open_ports('axe-fx')
        self.closed,self.uncertain,self.active=False,False,False
        self.pending=None
        inp,outp=ports
        super().__init__((inp,Output(outp)))
        self.outp.owner=self

    def _send(self,frame):
        # All reads and writes use the final, narrowly scoped output boundary.
        self.outp.send(mido.Message('sysex',data=frame[1:-1]))

    def close(self):
        self.closed=True
        super().close()

    def identity(self):
        if self.closed or self.uncertain:raise PermissionError('Closed or uncertain calibration connection')
        reply=self._request(protocol.envelope(8,[]),tuple)
        if (reply is None or hashlib.sha256(bytes(reply)).hexdigest()!=firmware_identity.BETA5_IDENTITY_SHA256):
            raise PermissionError('Exact observed MK2 Beta5 identity required')
        return reply

    def display(self,pid):
        text=self.read_display_text(58,pid)
        pattern=r'-?\d+(?:\.\d+)?(?: dB)?' if pid==21 else r'\d+(?:\.\d+)?'
        if not isinstance(text,str) or re.fullmatch(pattern,text) is None:
            raise ValueError('Independent Amp display is unreadable')
        value=float(text.removesuffix(' dB'))
        if not math.isfinite(value) or not (-80<=value<=20 if pid==21 else 0<=value<=10):
            raise ValueError('Amp display outside the calibration surface')
        return value

    def observe(self):
        ident=self.identity()
        preset,scene=self.current_preset(),self.current_scene()
        if not preset or preset[0]!=TARGET or scene!=1:
            raise PermissionError('Select disconnected test327/scene1 manually')
        blocks,cells=self.status_dump(),self.read_grid()
        if blocks is None or cells is None or {b.effect_id for b in blocks}!=set(IDS):
            raise PermissionError('Exact disconnected five-block fixture required')
        if (len(blocks)!=len(IDS) or any(b.channel!=0 for b in blocks)
                or any(b.channels_supported!=4 for b in blocks if b.effect_id not in (200,201))
                or [(c.row,c.col,c.effect_id,c.is_shunt,c.cable_in_mask) for c in cells]
                !=[(0,i,eid,False,0) for i,eid in enumerate(IDS[:5])]):
            raise PermissionError('No I/O, cables, shunts or other channels in calibration fixture')
        bulk={str(eid):self.bulk_read(eid) for eid in IDS}
        if any(not isinstance(bulk[str(eid)],list) or len(bulk[str(eid)])!=WORDS[eid] for eid in IDS):
            raise ValueError('Incomplete or changed block layouts')
        mods=[self.bulk_read(eid) for eid in range(3,35)]
        if any(not isinstance(w,list) or len(w)!=25 or w[0]!=0 or w[8]!=0 for w in mods):
            raise PermissionError('All32 complete inactive unassigned modifiers required')
        shown={name:self.display(pid) for name,pid in PIDS.items()}
        level=self.display(21)
        if bulk['58'][0]!=0 or level>-12:
            raise PermissionError('Bassguy/A and Amp Level at most -12dB required')
        if any(abs(bulk['58'][pid]/65534*10-shown[name])>.011 for name,pid in PIDS.items()):
            raise ValueError('Bulk and independent display disagree')
        names=[self.scene_name(s) for s in range(1,9)]
        if any(n is None or n[0]!=i or not isinstance(n[1],str) for i,n in enumerate(names,1)):
            raise ValueError('All eight scene names must be read')
        if self.identity()!=ident or self.current_preset()!=preset or self.current_scene()!=scene or self.status_dump()!=blocks:
            raise PermissionError('Device context changed during inspection')
        return dict(identity=list(ident),preset=list(preset),scene=scene,
                    blocks=[asdict(b) for b in blocks],grid=[asdict(c) for c in cells],
                    bulk=bulk,modifiers=mods,names=[list(n) for n in names],shown=shown,level=level)

    def review(self,edit,*,external_audio_muted=False):
        with self._lock:
            self.pending=None
            if type(edit) is not Edit or external_audio_muted is not True:
                raise PermissionError('Explicit captured edit and fully muted external audio required')
            baseline=self.observe()
            if abs(baseline['shown'][edit.control]-edit.value)>1.00001:
                raise PermissionError('At most one knob unit per calibration review')
            if self.observe()!=baseline:raise PermissionError('Fresh baseline changed')
            self.pending=Review(edit,json.dumps(baseline,sort_keys=True),time.monotonic()+60)
            return self.pending

    def apply(self,review,*,external_audio_muted=False):
        with self._lock:
            if type(review) is not Review or review is not self.pending:
                raise PermissionError('Foreign, replaced or consumed calibration review')
            self.pending=None
            if external_audio_muted is not True or time.monotonic()>=review.expires:
                raise PermissionError('Muted audio and unexpired review required')
            before=self.observe()
            if json.dumps(before,sort_keys=True)!=review.baseline:
                raise PermissionError('Calibration baseline changed')
            if abs(before['shown'][review.edit.control]-review.edit.value)<.011:
                return dict(verified=True,sent=False,stored=False)
            if time.monotonic()>=review.expires:raise PermissionError('Expired during preflight')
            verified=False
            self.active=True
            try:
                with self.outp.once(review.edit):self._send(review.edit.frame())
                pid=PIDS[review.edit.control]
                for _ in range(4):
                    time.sleep(.15)
                    after=self.observe()
                    untouched=deepcopy(after)
                    untouched['bulk']['58'][pid]=before['bulk']['58'][pid]
                    untouched['shown'][review.edit.control]=before['shown'][review.edit.control]
                    if (untouched==before and abs(after['shown'][review.edit.control]-review.edit.value)<.011
                            and abs(after['bulk']['58'][pid]-round(review.edit.value/10*65534))<=1):
                        verified=True
                        return dict(verified=True,sent=True,stored=False)
                raise ValueError('Calibration readback failed; no write retry or automatic restoration')
            finally:
                self.active=False
                if not verified:self.uncertain=True

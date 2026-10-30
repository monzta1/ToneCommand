"""Explicit MK1 experiment, not a production write-capability promotion.

One scene and a feed-forward Amp/Cab chain. Candidate encodings come from
the measured MK2 FW33 surface; MK1 acceptance is the purpose of this trial.
Only the firmware fingerprint previously supplied by the MK1 tester is admitted.
No application adapter, Store allowlist or shared safety guard is changed.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Literal
import hashlib
import struct
import sys
import threading
import time

import mido
from pydantic import BaseModel, ConfigDict, Field, field_validator

from fm9 import protocol as shared
from fm9.safety import sysex_guard
from . import grid, protocol, row_fixture, fw33_profile, amp_inventory
from .adapter import AxeFxIII
from .registry import Registry

FINGERPRINT = '441c510ab4f4e037abee80951784cdb5bfdcc081236efb57cb51e8cc084e5a90'
# Shared Gen-3 names/ordinals; MK1 execution remains an explicit experiment
# with its own exact identity, model-word and unrelated-state verification.
# Metadata reuse does not declare all MK1 models hardware-accepted.
AMPS = {name: ordinal for ordinal, name in amp_inventory.roster(fw33_profile.KEY).items()}
CABS = {'Greenback': 515, 'Recto': 799}  # Factory2, zero-based IR ordinal.
STRIDES = {58: 142, 62: 106, 42: 26, 78: 32, 70: 89, 66: 71}
CELLS = {37: (1, 41), 58: (2, 10), 62: (3, 11), 78: (4, 16),
         70: (5, 13), 66: (6, 12), 42: (7, 46)}
METADATA = Registry(fw33_profile.KEY)  # Encoding reference, not MK1 recognition.


class Design(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=31)
    summary: str = Field(min_length=1, max_length=2000)
    amp: Literal[tuple(AMPS)]
    cab: Literal[tuple(CABS)]
    gain: float = Field(ge=.5, le=6)
    bass: float = Field(ge=1, le=8)
    mid: float = Field(ge=1, le=8)
    treble: float = Field(ge=1, le=8)
    master: float = Field(ge=1, le=6)
    presence: float = Field(ge=1, le=7)
    depth: float = Field(ge=.5, le=5)
    chorus: bool = Field(strict=True)
    chorus_rate: float = Field(ge=.1, le=1)
    chorus_depth: float = Field(ge=10, le=60)
    chorus_mix: float = Field(ge=5, le=30)
    delay: bool = Field(strict=True)
    delay_ms: float = Field(ge=200, le=600)
    delay_feedback: float = Field(ge=5, le=30)
    delay_mix: float = Field(ge=5, le=30)
    reverb: bool = Field(strict=True)
    reverb_seconds: float = Field(ge=.5, le=3)
    reverb_mix: float = Field(ge=5, le=20)

    @field_validator('name')
    @classmethod
    def ascii_name(cls, value):
        if value != value.strip() or any(not 32 <= ord(c) <= 126 for c in value):
            raise ValueError('Use a printable ASCII name without outer spaces')
        return value

    @field_validator('amp', 'cab')
    @classmethod
    def model(cls, value, info):
        if value not in (AMPS if info.field_name == 'amp' else CABS):
            raise ValueError('Model is outside this experimental selection')
        return value

    @field_validator('gain', 'bass', 'mid', 'treble', 'master', 'presence', 'depth',
                     'chorus_rate', 'chorus_depth', 'chorus_mix', 'delay_ms',
                     'delay_feedback', 'delay_mix', 'reverb_seconds', 'reverb_mix', mode='before')
    @classmethod
    def real_number(cls, value):
        if type(value) not in (int, float):
            raise ValueError('A numeric control is required')
        return value


@dataclass(frozen=True)
class Step:
    label: str
    frame: tuple
    kind: str
    eid: int = 0
    pid: int = 0
    value: float = 0
    family: str = ''
    name: str = ''


def steps(design):
    """AI supplies only validated musical choices, never MIDI or topology."""
    if type(design) is not Design:
        raise ValueError('One validated design is required')
    result = []
    def add(label, frame, kind, **data):
        result.append(Step(label, tuple(frame), kind, **data))
    def place(eid):
        col, native_choice = CELLS[eid]
        add('Select empty cell', row_fixture.select(1, col), 'cursor')
        add('Place block '+str(eid), protocol.envelope(1,
            [0x32, 0, *shared.encode14(eid), 0, 0, native_choice, 0, 0, 0, 0, 0, 0, 0, 0]),
            'insert', eid=eid)
    def param(family, name, value):
        spec = METADATA.find_param(family, name)
        add(name+' = '+str(value), protocol.set_parameter(METADATA, spec, value),
            'numeric', eid=spec.effect_id, pid=spec.param_id,
            value=value, family=family, name=name)
    def bypass(eid, value):
        add(('Bypass ' if value else 'Engage ')+str(eid),
            protocol.envelope(0x0a, [eid, 0, int(value)]), 'bypass', eid=eid, value=value)
    # Output attenuation first, before any possible input-to-output route.
    place(42)
    param('OUTPUT', 'OUTPUT_LEVEL', -18.)
    place(37)
    place(58)
    bypass(58, True)
    param('DISTORT', 'DISTORT_LEVEL', -12.)
    add('Amp model: '+design.amp, protocol.param_frame(58, 0, AMPS[design.amp], opcode=9),
        'model', eid=58, value=AMPS[design.amp])
    param('DISTORT', 'DISTORT_LEVEL', -12.)  # Model loading can reset its level.
    for key, name in (('gain', 'DRIVE'), ('bass', 'BASS'), ('mid', 'MID'),
                      ('treble', 'TREBLE'), ('master', 'MASTER'),
                      ('presence', 'PRESENCE'), ('depth', 'DEPTH')):
        param('DISTORT', 'DISTORT_'+name, getattr(design, key))
    place(62)
    for pid, value in ((0, 1), (4, CABS[design.cab])):
        add('Factory cab selector', protocol.param_frame(62, pid, value, opcode=9),
            'selector', eid=62, pid=pid, value=value)
    param('CABINET', 'CABINET_LEVEL1', -3.)
    for slot in range(1, 5):
        param('CABINET', 'CABINET_MUTE'+str(slot), 0 if slot == 1 else 1)
    for eid, model, family, controls in (
        (78, 3, 'CHORUS', [('RATE', design.chorus_rate), ('DEPTH', design.chorus_depth), ('MIX', design.chorus_mix)]),
        (70, 0, 'DELAY', [('TIME', design.delay_ms), ('FEED', design.delay_feedback), ('MIX', design.delay_mix)]),
        (66, 0, 'REVERB', [('TIME', design.reverb_seconds), ('MIX', design.reverb_mix)]),
    ):
        place(eid)
        bypass(eid, True)
        param(family, family+'_LEVEL', -12.)
        add(family+' model', protocol.param_frame(eid, 0, model, opcode=9),
            'model', eid=eid, value=model)
        for control, value in controls:
            param(family, family+'_'+control, value)
        param(family, family+'_LEVEL', -1.)
        bypass(eid, not getattr(design, family.lower()))
    for eid in (58, 62, 42):
        bypass(eid, False)
    # Join the input LAST. No parallel path, Send/Return or feedback topology.
    for col in (6, 5, 4, 3, 2, 1):
        add('Connect columns '+str(col)+' -> '+str(col+1), row_fixture.connect(1, col),
            'cable', eid=col)
    add('Name preset', grid.reframe(shared.build_rename_preset(design.name)), 'preset_name')
    add('Name scene 1', grid.reframe(shared.build_set_scene_name(0, 'First Sound')), 'scene_name')
    return tuple(result)


def allowed_read(frame):
    from tools.mk1_tester import read_query
    if read_query(frame):
        return True
    if frame in [protocol.envelope(0x1f, list(shared.encode14(e)))
                 for e in (*range(3, 35), *CELLS)]:
        return True
    specs = [('OUTPUT', 'OUTPUT_LEVEL'), ('DISTORT', 'DISTORT_LEVEL')]
    specs += [('DISTORT', 'DISTORT_'+n) for n in
              ('DRIVE', 'BASS', 'MID', 'TREBLE', 'MASTER', 'PRESENCE', 'DEPTH')]
    specs += [('CABINET', 'CABINET_LEVEL1')]
    specs += [('CABINET', 'CABINET_MUTE'+str(i)) for i in range(1, 5)]
    specs += [(f, f+'_'+n) for f, names in (
        ('CHORUS', ('RATE', 'DEPTH', 'MIX', 'LEVEL')),
        ('DELAY', ('TIME', 'FEED', 'MIX', 'LEVEL')),
        ('REVERB', ('TIME', 'MIX', 'LEVEL'))) for n in names]
    return frame in [protocol.display_query(METADATA.find_param(f, n).effect_id,
                    METADATA.find_param(f, n).param_id) for f, n in specs]


class Output:
    guard = sysex_guard('MK1 explicit first-sound experiment', (1, 0x0a))

    def __init__(self, port):
        self.port, self.owner, self.permit, self.writes = port, None, None, 0

    def send(self, message):
        frame = [0xf0, *message.data, 0xf7] if message.type == 'sysex' else []
        if not allowed_read(frame):
            owner = self.owner
            if (not owner or owner.failed or not owner.active or
                    self.permit != (threading.get_ident(), tuple(frame)) or
                    tuple(frame) != owner.sequence[owner.index].frame):
                raise PermissionError('No exact reviewed experimental frame is armed')
            self.guard.check(frame[5])
            self.permit = None
            self.writes += 1  # Count attempts, including an uncertain transport error.
        self.port.send(mido.Message('sysex', data=frame[1:-1]))

    def close(self):
        self.port.close()


class Device(AxeFxIII):
    def __init__(self, ports=None):
        if ports is None:
            from fm9 import midi_transport
            if (sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or
                    struct.calcsize('P') != 8 or midi_transport.backend() != 'mido'):
                raise PermissionError('This experiment requires Windows, 64-bit Python3.12 and mido')
            ports = midi_transport.open_ports('axe-fx')
        inp, port = ports
        self.uncertain = False
        super().__init__((inp, Output(port)))

    def _send(self, frame):
        # All inherited read helpers still pass through this exact output boundary.
        self.outp.send(mido.Message('sysex', data=frame[1:-1]))

    def identity(self):
        reply = self._request(protocol.envelope(8, []), tuple)
        if (self.uncertain or reply is None or
                hashlib.sha256(bytes(reply)).hexdigest() != FINGERPRINT):
            raise PermissionError('Firmware differs from the recorded MK1 Beta2 fingerprint')
        return FINGERPRINT

    def observe(self, target):
        if type(target) is not int or not 0 <= target < 512:
            raise ValueError('Choose your own empty MK1 preset, 0..511')
        with self._lock:
            ident = self.identity()
            preset, scene = self.current_preset(), self.current_scene()
            if not preset or preset[0] != target or scene != 1:
                raise ValueError('Select the permitted empty preset and scene 1 manually')
            blocks, cells = self.status_dump(), self.read_grid()
            names = [self.scene_name(i) for i in range(1, 9)]
            if blocks is None or cells is None or any(n is None for n in names):
                raise ValueError('Incomplete status, grid or scene-name read')
            status = {b.effect_id: asdict(b) for b in blocks}
            if len(status) != len(blocks) or set(status) - {*CELLS, 200, 201}:
                raise ValueError('An unsupported existing block is present')
            bulk = {eid: self.bulk_read(eid) for eid in status if eid not in (200, 201)}
            if any(not isinstance(w, list) or not w for w in bulk.values()):
                raise ValueError('Incomplete parameter read')
            for eid, stride in STRIDES.items():
                if eid in bulk and (len(bulk[eid]) != 4*stride or
                        status[eid]['channel'] != 0 or status[eid]['channels_supported'] != 4):
                    raise ValueError('Unverified MK1 block layout or channel')
            mods = [self.bulk_read(i) for i in range(3, 35)]
            if any(not isinstance(w, list) or len(w) != 25 or w[0] != 0 for w in mods):
                raise ValueError('All 32 complete inactive modifiers are required')
            if (self.identity() != ident or self.current_preset() != preset or
                    self.current_scene() != scene or self.status_dump() != blocks):
                raise ValueError('Device state changed while reading')
            return dict(identity=ident, preset=preset, scene=scene, names=names,
                        grid=grid.snapshot(cells), blocks=status, bulk=bulk, modifiers=mods)


class UncertainWrite(RuntimeError):
    """Partial changes may remain. Never retry, reload or automatically restore."""


class Execution:
    def __init__(self, dev, target, design, baseline, expires):
        if dev.outp.owner is not None or baseline['grid'] or set(baseline['blocks']) - {200, 201}:
            raise PermissionError('A new connection and genuinely empty preset are required')
        self.dev, self.target, self.design = dev, target, design
        self.sequence, self.expected = steps(design), baseline
        self.expires, self.index, self.failed, self.active = expires, 0, False, False
        self.verified = []
        dev.outp.owner = self

    def matches(self, step, after):
        wanted = deepcopy(self.expected)
        if step.kind == 'insert':
            eid, col = step.eid, CELLS[step.eid][0]
            if eid in wanted['blocks'] or set(after['blocks']) != set(wanted['blocks']) | {eid}:
                return False
            wanted['grid'][(1, col)] = (eid, False, 0)
            wanted['blocks'][eid] = after['blocks'][eid]
            wanted['bulk'][eid] = after['bulk'][eid]
            if after['blocks'][eid]['channel'] != 0 or after['blocks'][eid]['bypassed']:
                return False
        elif step.kind == 'bypass':
            wanted['blocks'][step.eid]['bypassed'] = bool(step.value)
        elif step.kind == 'model':
            if after['bulk'][step.eid][0] != step.value:
                return False
            stride = STRIDES[step.eid]
            wanted['bulk'][step.eid][:stride] = after['bulk'][step.eid][:stride]
        elif step.kind == 'selector':
            wanted['bulk'][step.eid][step.pid] = int(step.value)
        elif step.kind == 'numeric':
            spec = METADATA.find_param(step.family, step.name)
            if ((step.name == 'DELAY_TIME' and self.expected['bulk'][70][9] != 0) or
                    (step.name == 'CHORUS_RATE' and self.expected['bulk'][78][3] != 0)):
                return False  # No timing claim while the effect is tempo-synchronised.
            value = self.dev._parse_display_value(self.dev.read_display_text(step.eid, step.pid), spec.unit)
            if value is None or abs(value-step.value) > spec.display_tolerance:
                return False
            actual = after['bulk'][step.eid][step.pid]
            expected = int(step.value) if spec.kind == 'enum' else round(
                shared.display_to_normalized(step.value, spec.dmin, spec.dmax, spec.scale)*65534)
            if abs(actual-expected) > (0 if spec.kind == 'enum' else 1):
                return False
            wanted['bulk'][step.eid][step.pid] = actual
        elif step.kind == 'cable':
            eid, shunt, _ = wanted['grid'][(1, step.eid+1)]
            wanted['grid'][(1, step.eid+1)] = (eid, shunt, 2)
        elif step.kind == 'preset_name':
            wanted['preset'] = (self.target, self.design.name)
        elif step.kind == 'scene_name':
            wanted['names'][0] = (1, 'First Sound')
        return wanted == after

    def run(self, *, muted=False, target_confirmed=False, check_source=None):
        if muted is not True or target_confirmed is not True:
            raise PermissionError('Confirm the target and fully muted external monitoring')
        with self.dev._lock:
            if self.failed or self.active or self.index or time.monotonic() >= self.expires:
                raise PermissionError('Expired or consumed review; nothing resent')
            if self.dev.observe(self.target) != self.expected:
                raise PermissionError('State changed since review')
            if time.monotonic() >= self.expires:
                raise PermissionError('Review expired during preflight')
            if check_source is not None:
                check_source()
            self.active = True
            try:
                for self.index, step in enumerate(self.sequence):
                    if self.dev.observe(self.target) != self.expected:
                        raise ValueError('Unexpected state change before the next frame')
                    if check_source is not None:
                        check_source()
                    if ((step.name == 'DELAY_TIME' and self.expected['bulk'][70][9] != 0) or
                            (step.name == 'CHORUS_RATE' and self.expected['bulk'][78][3] != 0)):
                        raise ValueError('Default effect tempo is not NONE; no guessed tempo write')
                    self.dev.outp.permit = (threading.get_ident(), step.frame)
                    try:
                        self.dev._send(list(step.frame))
                    finally:
                        self.dev.outp.permit = None
                    verified = False
                    for _ in range(4):
                        time.sleep(.15)
                        after = self.dev.observe(self.target)
                        if self.matches(step, after):
                            self.expected = after
                            self.verified.append(step.label)
                            verified = True
                            break
                    if not verified:
                        raise ValueError('Independent readback did not match: '+step.label)
                self.index = len(self.sequence)
                return dict(verified=True, stored=False, actions=len(self.verified))
            except Exception as error:
                self.failed = self.dev.uncertain = True
                raise UncertainWrite('Build stopped; partial edits may remain. Keep audio muted; no retry.') from error
            finally:
                self.active = False

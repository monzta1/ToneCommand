"""Connection-owned scalar deltas over observed original scenes.

Explicit acceptance component, not a generic FM9 executor. The first port is
limited to Gain/Mid on measured existing Amp 1 scopes; unknown state is opaque.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import threading
import time

import mido

from fm9.device import ReadOnly
from .amp_writer import AmpEdit, AmpReadbackError
from .existing_contract import compile_design
from .scene_observation import SceneSurvey, _SceneOutput


# An explicit candidate surface for this opt-in port, not firmware permission
# derived from the AI or a catalog. Native acceptance is recorded separately.
SCOPES = {(0, 0): '59 Bassguy Bright', (1, 121): 'Vibrato Lux'}
PARAMETERS = {'DISTORT_DRIVE': ('gain', 1), 'DISTORT_MID': ('mid', 3)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class ScalarWrite:
    channel: int
    model: int
    parameter: str
    value: float

    def __post_init__(self):
        if (type(self.channel) is not int or type(self.model) is not int
                or (self.channel, self.model) not in SCOPES
                or type(self.parameter) is not str or self.parameter not in PARAMETERS):
            raise ValueError('Only the explicit observed Amp 1 scopes and controls are admitted')
        AmpEdit(0, PARAMETERS[self.parameter][0], self.value)

    @property
    def pid(self):
        return PARAMETERS[self.parameter][1]

    def frame(self):
        return AmpEdit(0, PARAMETERS[self.parameter][0], self.value).frame()


class _DeltaOutput(_SceneOutput):
    def __init__(self, port, chassis):
        super().__init__(port, chassis)
        self._scalar_permit = None
        self._scalar_deadline = None

    @contextmanager
    def _scalar_once(self, edit, deadline):
        if (type(edit) is not ScalarWrite or self._scalar_permit is not None
                or self._scene_permit is not None or self._permit is not None
                or type(deadline) not in (int,float) or not math.isfinite(deadline)
                or time.monotonic() >= deadline):
            raise ReadOnly('One exact scalar requires an idle output boundary')
        self._scalar_permit = (threading.get_ident(), tuple(edit.frame()))
        self._scalar_deadline = deadline
        try:
            yield
        finally:
            self._scalar_permit = None
            self._scalar_deadline = None

    def send(self, message):
        frame = message.bytes() if message.type == 'sysex' else []
        if self._scalar_permit == (threading.get_ident(), tuple(frame)):
            deadline = self._scalar_deadline
            self._scalar_permit = None
            self._scalar_deadline = None
            self.guard.check(frame[5])
            if deadline is None or time.monotonic() >= deadline:
                raise ReadOnly('Scalar review expired before final transmission')
            return self._port.send(mido.Message('sysex', data=frame[1:-1]))
        return super().send(message)


def context(survey):
    """Host-owned complete state and actual maps, never an AI-supplied Context."""
    state, maps = survey['state'], survey['maps']
    rows, words = [], state['bulk'].get('58')
    block = next((b for b in state['status'] if b['effect_id'] == 58), None)
    if words is not None and len(words) == 568 and block and block['channels_supported'] == 4:
        for channel in range(4):
            model = words[channel * 142]
            if (channel, model) not in SCOPES:
                continue
            for name, (_, pid) in PARAMETERS.items():
                if any(w[8:10] == [58, pid] for w in state['modifiers']):
                    continue
                rows.append(dict(effect_id=58, channel='ABCD'[channel], parameter=name,
                    param_id=pid, model=SCOPES[channel, model],
                    current=words[channel * 142 + pid] / 65534 * 10,
                    minimum=.1, maximum=8., tolerance=.011, qualified=True))
    return dict(declared_chassis=state['variant'], preset=state['preset'][0],
        name=state['preset'][1], scene=state['scene'], observed_state=deepcopy(state),
        scene_maps=[dict(scene=m['scene'], name=m['name'], blocks=[
            dict(effect_id=b['effect_id'], channel='ABCD'[b['channel']], bypassed=b['bypassed'])
            for b in m['status']]) for m in maps], editable_parameters=rows)


@dataclass(frozen=True)
class DeltaReview:
    _json: str = field(repr=False)
    _expires: float

    def preview(self):
        return json.loads(self._json)['plan']


class ExistingEditor(SceneSurvey):
    def __init__(self, ports=None, *, chassis='mk2'):
        self._scan, self._delta = None, None
        super().__init__(ports, chassis=chassis)

    @staticmethod
    def _output(port, chassis):
        return _DeltaOutput(port, chassis)

    def scan(self, preset, *, external_audio_muted=False, target_confirmed=False):
        with self._lock:
            self._scan, self._delta = None, None
            if (external_audio_muted is not True or target_confirmed is not True
                    or type(preset) is not int or preset not in range(1024)):
                raise ReadOnly('Explicit current target and external mute required before scanning')
            success = False
            try:
                survey = self.survey(preset, external_audio_muted=external_audio_muted,
                                     target_confirmed=target_confirmed)
                self._scan = (survey, time.monotonic() + 900)
                reference = self.reference()
                success = True
                return reference
            finally:
                if not success:
                    self._uncertain = True
                    self._scan, self._delta = None, None

    def reference(self):
        if self._scan is None or time.monotonic() >= self._scan[1] or self._uncertain:
            raise ReadOnly('Scan the original scenes again before proposing a delta')
        value = context(self._scan[0])
        # Raw factory/system/modifier words are a private preservation baseline,
        # not input to a provider and never accepted back from a browser.
        del value['observed_state']
        return deepcopy(value)

    def prepare_delta(self, design):
        with self._lock:
            self._delta = None
            self.reference()
            self._identity()
            survey = self._scan[0]
            if self.capture().data() != survey['state']:
                raise ReadOnly('Preset changed after survey; scan again')
            plan = compile_design(design, context(survey))
            for row in plan['changes']:
                if abs(row['after'] - row['before']) > 1.00001:
                    raise ValueError('At most one display unit per fresh scalar review')
                ScalarWrite('ABCD'.index(row['channel']),
                    survey['state']['bulk']['58']['ABCD'.index(row['channel']) * 142],
                    row['parameter'], row['after'])
            self._delta = DeltaReview(canonical(dict(plan=plan, design=design, survey=survey)),
                                      time.monotonic() + 180)
            return self._delta

    def apply_delta(self, review, *, external_audio_muted=False, target_confirmed=False):
        with self._lock:
            owned, self._delta = self._delta, None
            if (type(review) is not DeltaReview or review is not owned
                    or time.monotonic() >= review._expires or self._uncertain
                    or external_audio_muted is not True or target_confirmed is not True):
                raise ReadOnly('Fresh connection-owned delta, target confirmation and external mute required')
            payload = json.loads(review._json)
            plan, survey = payload['plan'], payload['survey']
            if compile_design(payload['design'], context(survey)) != plan:
                raise ReadOnly('Scalar surface or plan changed since review')
            self._identity()
            if self.capture().data() != survey['state']:
                raise ReadOnly('Preset changed before SEND')
            success, sent = False, 0
            try:
                # Revalidate every original map, not only the displayed scene.
                fresh = self.survey(survey['state']['preset'][0], external_audio_muted=True,
                                    target_confirmed=True)
                if fresh != survey:
                    raise ReadOnly('An original scene assignment changed since review')
                current = fresh['state']
                for row in plan['changes']:
                    if time.monotonic() >= review._expires:
                        raise ReadOnly('Delta expired during execution; inspect without retry')
                    channel = 'ABCD'.index(row['channel'])
                    number = next(m['scene'] for m in survey['maps'] if any(
                        b['effect_id'] == 58 and b['channel'] == channel for b in m['status']))
                    current = self._recall(number, current)
                    block = next(b for b in current['status'] if b['effect_id'] == 58)
                    if block['channel'] != channel:
                        raise ReadOnly('Original scene did not select the intended channel')
                    edit = ScalarWrite(channel, current['bulk']['58'][channel * 142],
                                       row['parameter'], row['after'])
                    if any(w[8:10] == [58, edit.pid] for w in current['modifiers']):
                        raise ReadOnly('Scalar became modifier-owned')
                    if self.capture().data() != current:
                        raise ReadOnly('Concurrent preset change before scalar SET')
                    before = current
                    if time.monotonic() >= review._expires:
                        raise ReadOnly('Delta expired after preflights; no scalar permit armed')
                    with self.outp._scalar_once(edit, review._expires):
                        self._send(edit.frame())
                    sent += 1
                    for _ in range(4):
                        time.sleep(.15)
                        after = self.capture().data()
                        actual = after['bulk']['58'][channel * 142 + edit.pid]
                        wanted = deepcopy(before)
                        wanted['bulk']['58'][channel * 142 + edit.pid] = actual
                        shown = self._display(edit.pid)
                        if (wanted == after and abs(actual - round(edit.value / 10 * 65534)) <= 1
                                and type(shown) in (int, float) and abs(shown - edit.value) <= .011):
                            break
                    else:
                        raise AmpReadbackError('Scalar not independently preserved; no SET retry')
                    current = after
                final = self.survey(survey['state']['preset'][0], external_audio_muted=True,
                                    target_confirmed=True)
                if final['maps'] != survey['maps']:
                    raise AmpReadbackError('An original scene assignment changed')
                current = self._recall(survey['state']['scene'], final['state'])
                wanted = deepcopy(survey['state'])
                for row in plan['changes']:
                    offset = 'ABCD'.index(row['channel']) * 142 + row['param_id']
                    actual = current['bulk']['58'][offset]
                    if abs(actual - round(row['after'] / 10 * 65534)) > 1:
                        raise AmpReadbackError('Final scalar differs')
                    wanted['bulk']['58'][offset] = actual
                if current != wanted or self.capture().data() != wanted:
                    raise AmpReadbackError('An unrequested final word or scene changed')
                success = True
                self._scan = None
                return dict(verified=True, sent=sent, stored=False, undo_available=False,
                            scene_maps_verified=8, original_scene_returned=True)
            finally:
                if not success:
                    self._uncertain = True
                    self._scan = None

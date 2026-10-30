"""Unregistered preparation for an app REVIEW/CONFIRM/SEND bridge.

Explicitly injected NameWriter OR AmpWriter, one action, one existing
connection. Never opens ports, combines writers, enables capabilities,
registers routes, calls an AI or invokes the generic FM9 executor.
"""
from dataclasses import dataclass
import json
import secrets
import threading
import time

from fm9.device import ReadOnly
from .amp_writer import AmpEdit, AmpWriter
from .beta5_amp_writer import Beta5AmpWriter
from .name_edits import NameEdit
from .name_writer import NameWriter

FIELDS = dict(kind=None, block=None, instance=1, param=None, value=None,
              bypassed=None, type_name=None, position=None, ref=None,
              bank=None, pedal=None, reason='')


def proposal(actions, preset):
    """Strict raw action validation BEFORE shared Action may coerce booleans.

    Returns the existing app Action field shape and the exact writer edit.
    No unknown keys, irrelevant non-null fields, batch, Store or whole rig.
    """
    if type(actions) is not list or len(actions) != 1 or type(actions[0]) is not dict:
        raise ValueError('This preparation accepts exactly one plain action')
    raw = actions[0]
    if set(raw) - set(FIELDS):
        raise ValueError('Unknown action fields require a separate reviewed contract')
    action = dict(FIELDS, **raw)
    if type(action['instance']) is not int or action['instance'] != 1:
        raise ValueError('Only instance 1 is supported')
    if type(action['reason']) is not str or len(action['reason']) > 2048:
        raise ValueError('Reason must be a bounded string')
    kind = action['kind']
    if type(kind) is not str:
        raise ValueError('Action kind must be an explicit string')
    allowed = {'kind', 'block', 'instance', 'reason', 'type_name'}
    if kind == 'set_param':
        allowed = {'kind', 'block', 'instance', 'reason', 'param', 'value'}
        if type(action['block']) is not str or action['block'].lower() not in ('amp', 'distort'):
            raise ValueError('Only Amp 1/channel A is supported')
        if type(action['param']) is not str:
            raise ValueError('Parameter must be an explicit supported identifier')
        control = {'DISTORT_DRIVE':'gain', 'DISTORT_MID':'mid'}.get(action['param'])
        edit = AmpEdit(preset, control, action['value'])
        action['value'] = float(action['value'])  # Shared Action/JS round-trip shape.
    elif kind in ('rename_preset', 'rename_scene'):
        if action['block'] not in (None, 'PRESET' if kind == 'rename_preset' else 'SCENE'):
            raise ValueError('Rename target is ambiguous')
        scene = None
        if kind == 'rename_scene':
            allowed.add('value')
            value = action['value']
            if type(value) not in (int, float) or value not in range(1, 9):
                raise ValueError('Scene name target must be an integer 1..8')
            scene = int(value)
            action['value'] = float(value)
        edit = NameEdit(preset, action['type_name'], scene)
    else:
        raise ValueError('Only rename, Gain or Mid is supported; no Store or structural actions')
    if any(value is not None for key, value in action.items() if key not in allowed):
        raise ValueError('Irrelevant action fields must be absent or null')
    return action, edit


@dataclass
class _Pending:
    writer: object
    edit: object
    review: object
    token: str
    digest: str
    action_json: str
    preset: int
    scene: int
    stage: str = 'plan'
    armed_until: float = 0


class EditWorkflow:
    """Preparation only, no constructor or registration in server.py.

    selected returns the host's current writer. host_lock MUST be the same
    lock used by device switching, Gig Lock and disconnect, acquired here
    before the workflow and writer locks. Do not call while already holding
    a non-reentrant host lock. fingerprint can be server.plan_digest.
    """
    def __init__(self, *, selected, host_lock, gig_locked, fingerprint, clock=time.monotonic):
        self._selected, self._host_lock = selected, host_lock
        self._gig_locked, self._fingerprint, self._clock = gig_locked, fingerprint, clock
        self._lock, self._pending = threading.RLock(), None

    @staticmethod
    def _canonical(action):
        return json.dumps(action, sort_keys=True, separators=(',', ':'), allow_nan=False)

    def _context(self, writer, preset, scene):
        if (self._gig_locked() is not False or self._selected() is not writer
                or type(writer) not in (NameWriter, AmpWriter, Beta5AmpWriter)
                or writer._closed or writer._uncertain or writer.chassis != 'mk2'):
            raise ReadOnly('Selected measured writer, Gig Lock off and a certain open connection required')
        if type(scene) is not int or scene not in range(1, 9):
            raise ValueError('Pin the current scene explicitly')
        current = writer.current_preset()
        if (type(preset) is not int or not current or current[0] != preset
                or writer.current_scene() != scene):
            raise ReadOnly('Preset or scene changed; prepare and review again')

    def _view(self, pending):
        change = dict(pending.review.preview(), executable=False)
        return dict(token=pending.token, plan_digest=pending.digest,
                    actions=[json.loads(pending.action_json)], stage=pending.stage,
                    expected_preset=pending.preset, expected_scene=pending.scene,
                    change=change, can_send=(pending.stage == 'confirm'
                                            and self._clock() < pending.armed_until),
                    stored=False, undo_available=False,
                    warning='Edit buffer only. No automatic undo or physical limiter; other scenes may share the edited channel.')

    def prepare(self, actions, *, expected_preset, expected_scene, whole_rig=False):
        with self._host_lock, self._lock:
            self._pending = None  # A replacement, even refused, disarms the old plan.
            if whole_rig is not False:
                raise ValueError('Whole-rig builds are outside this prepared bridge')
            action, edit = proposal(actions, expected_preset)
            writer = self._selected()
            needed = AmpWriter if type(edit) is AmpEdit else NameWriter
            accepted = (AmpWriter, Beta5AmpWriter) if needed is AmpWriter else (NameWriter,)
            if type(writer) not in accepted:
                raise ReadOnly('Explicit matching writer injection required; no fallback or second connection')
            self._context(writer, expected_preset, expected_scene)
            method = writer.review_amp if needed is AmpWriter else writer.review_name
            review = method(edit)  # Reads only. The opaque native review stays server-side.
            self._context(writer, expected_preset, expected_scene)
            digest = self._fingerprint([action])
            if type(digest) is not str or not digest.isascii() or not 1 <= len(digest) <= 128:
                raise ValueError('A bounded app plan fingerprint is required')
            pending = _Pending(writer, edit, review, secrets.token_urlsafe(32), digest,
                               self._canonical(action), expected_preset, expected_scene)
            if self._clock() >= review._expires:
                raise ReadOnly('Native review expired during preparation')
            result = self._view(pending)
            self._pending = pending
            return result

    def _take(self, stage, token, actions, plan_digest, expected_preset, expected_scene, whole_rig):
        pending, self._pending = self._pending, None  # Consume before validation/IO.
        if (pending is None or pending.stage != stage or type(token) is not str
                or not token.isascii() or not secrets.compare_digest(token, pending.token)
                or type(plan_digest) is not str or not plan_digest.isascii()
                or not secrets.compare_digest(plan_digest, pending.digest)
                or whole_rig is not False or type(expected_preset) is not int
                or expected_preset != pending.preset or type(expected_scene) is not int
                or expected_scene != pending.scene or self._clock() >= pending.review._expires):
            raise ReadOnly('Missing, changed, out-of-order, expired or consumed review')
        action, _ = proposal(actions, expected_preset)
        if self._canonical(action) != pending.action_json:
            raise ReadOnly('Actions changed since review; prepare a new revision')
        self._context(pending.writer, pending.preset, pending.scene)
        if (self._clock() >= pending.review._expires
                or pending.writer._review is not pending.review):
            raise ReadOnly('Native review changed or expired during the transition')
        return pending

    def review(self, token, actions, plan_digest, *, expected_preset, expected_scene, whole_rig=False):
        with self._host_lock, self._lock:
            p = self._take('plan', token, actions, plan_digest, expected_preset, expected_scene, whole_rig)
            p.stage = 'review'
            result = self._view(p)
            self._pending = p
            return result

    def confirm(self, token, actions, plan_digest, *, expected_preset, expected_scene,
                whole_rig=False, target_confirmed=False, external_audio_muted=False):
        with self._host_lock, self._lock:
            p = self._take('review', token, actions, plan_digest, expected_preset, expected_scene, whole_rig)
            if target_confirmed is not True or external_audio_muted is not True:
                raise ReadOnly('Explicit target review and fully muted external monitoring required')
            p.stage = 'confirm'
            p.armed_until = min(self._clock() + 8, p.review._expires)
            result = self._view(p)
            self._pending = p
            return result

    def send(self, token, actions, plan_digest, *, expected_preset, expected_scene,
             whole_rig=False, target_confirmed=False, external_audio_muted=False):
        with self._host_lock, self._lock:
            p = self._take('confirm', token, actions, plan_digest, expected_preset, expected_scene, whole_rig)
            if (target_confirmed is not True or external_audio_muted is not True
                    or self._clock() >= p.armed_until):
                raise ReadOnly('Fresh confirmed target, mute and unexpired SEND arm required')
            method = p.writer.apply_amp if type(p.edit) is AmpEdit else p.writer.apply_name
            # The writer rereads its full baseline and rechecks expiry itself.
            # Unknown outcomes propagate unchanged; no catch, retry or restore.
            out = method(p.review, external_audio_muted=True)
            return dict(results=[dict(action=json.loads(p.action_json), ok=out['verified'],
                                     detail='Verified in edit buffer; not stored; no automatic undo.')],
                        health=[], verified=out['verified'], sent=out['sent'], stored=False,
                        undo_available=False, stage='sent')

    def discard(self):
        with self._host_lock, self._lock:
            self._pending = None
            return dict(stage='request', can_send=False, stored=False)

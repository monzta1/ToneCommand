"""Opt-in MK2 edit-buffer names only. Not registered in the application.

The normal adapter and its final read-only guard remain read-only. This
separate acceptance component never selects a preset or stores it to flash.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import threading
import time

import mido

from fm9.device import FM9NotFound, ReadOnly
from fm9.safety import sysex_guard
from . import readonly_protocol as protocol
from .readonly_adapter import AxeFxIII, ReadOnlyOutput, snapshot
from .name_edits import NameEdit


# Full measured response, not the ambiguous raw 97.00 version fields.
MK2_FW33_IDENTITY = (
    0, 1, 116, 16, 8, 97, 0, 16, 1, 17, 0, 0, 79, 99, 116, 32, 32, 54, 32,
    50, 48, 50, 54, 32, 49, 54, 58, 50, 50, 58, 53, 51, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 21,
)


class NameReadbackError(RuntimeError):
    """A write may have happened. Do not repeat, reload or auto-restore it."""


class _NameOutput(ReadOnlyOutput):
    write_guard = sysex_guard('Axe-Fx III reviewed edit-buffer names', {1})

    def __init__(self, port, chassis):
        super().__init__(port, chassis)
        self._permit = None

    @contextmanager
    def _once(self, edit):
        if type(edit) is not NameEdit or self._permit is not None:
            raise ReadOnly('One reviewed name frame is required')
        checked = NameEdit(edit.preset, edit.name, edit.scene)
        self._permit = (threading.get_ident(), tuple(checked.frame()))
        try:
            yield
        finally:
            self._permit = None

    def send(self, message):
        frame = [0xF0, *message.data, 0xF7] if message.type == 'sysex' else []
        if protocol.allowed(frame, self._chassis):
            return super().send(mido.Message('sysex', data=frame[1:-1]))
        if self._permit != (threading.get_ident(), tuple(frame)):
            raise ReadOnly('No exact single-use reviewed name frame is armed')
        self.write_guard.check(frame[5])
        self._permit = None  # Consume BEFORE IO, even when the port raises.
        self._port.send(mido.Message('sysex', data=frame[1:-1]))


@dataclass(frozen=True)
class NameReview:
    """Opaque, connection-owned review. Caller-created copies are refused."""
    edit: NameEdit
    _baseline: str
    _expires: float

    def preview(self):
        result = self.edit.preview(json.loads(self._baseline))
        result['executable'] = True
        return result


class NameWriter(AxeFxIII):
    """Explicit developer acceptance API, not normal GUI write support.

    Only the measured MK2 profile is admitted. No capability is advertised
    to the shared planner, and the application never constructs this class.
    """

    def __init__(self, ports=None, *, chassis='mk2'):
        if chassis != 'mk2':
            raise ReadOnly('Name writing requires the measured MK2 profile')
        self._review = None
        self._uncertain = False
        super().__init__(ports, chassis=chassis)

    @staticmethod
    def _output(port, chassis):
        return _NameOutput(port, chassis)

    def set_chassis(self, chassis):
        if chassis != 'mk2':
            raise ReadOnly('The name-writing connection is pinned to MK2')
        super().set_chassis(chassis)

    def _identity(self):
        if (self._closed or self.chassis != 'mk2' or self._uncertain
                or self._request(8, [], tuple) != MK2_FW33_IDENTITY):
            raise ReadOnly('Exact MK2 firmware identity required; reconnect after uncertainty')

    def review_name(self, edit):
        if type(edit) is not NameEdit:
            raise ValueError('An explicit NameEdit is required')
        with self._lock:
            self._review = None
            self._identity()
            before = snapshot(self)
            edit.preview(before)
            self._identity()
            review = NameReview(edit, json.dumps(before, sort_keys=True),
                                time.monotonic() + 60)
            self._review = review
            return review

    def apply_name(self, review, *, external_audio_muted=False):
        """One exact write, read retries only, no automatic recovery writes."""
        if external_audio_muted is not True:
            raise ReadOnly('External audio must be confirmed muted for this operation')
        with self._lock:
            if (review is not self._review or not isinstance(review, NameReview)
                    or time.monotonic() >= review._expires):
                raise ReadOnly('Review is stale, foreign, consumed or expired')
            self._review = None
            self._identity()
            before = snapshot(self)
            if json.dumps(before, sort_keys=True) != review._baseline:
                raise ReadOnly('Observed state changed since review; make a new review')
            edit = review.edit
            expected = edit.expected_after(before)
            self._identity()
            if expected == before:
                return dict(verified=True, sent=False, stored=False, state=before)
            if time.monotonic() >= review._expires:
                raise ReadOnly('Review expired during preflight; make a new review')
            success = False
            try:
                with self.outp._once(edit):
                    self.outp.send(mido.Message('sysex', data=edit.frame()[1:-1]))
                for _ in range(3):
                    time.sleep(0.15)
                    self._identity()
                    try:
                        after = snapshot(self)
                    except FM9NotFound:
                        continue  # Read failure only. Never retry the SET.
                    try:
                        if edit.verify(before, after):
                            success = True
                            return dict(verified=True, sent=True, stored=False, state=after)
                    except ValueError:
                        # A stale name can settle. Any OTHER change stops now.
                        if edit.expected_after(after) != expected:
                            raise NameReadbackError('Other observed context changed after the write')
                raise NameReadbackError('Name was not independently verified; no write retry')
            except NameReadbackError:
                raise
            except Exception as error:
                # Transport and verification can fail after the SET left the
                # host. Never report that as a pre-write refusal or retry it.
                raise NameReadbackError(
                    'Name write may have been sent; verification failed; no write retry'
                ) from error
            finally:
                if not success:
                    self._uncertain = True

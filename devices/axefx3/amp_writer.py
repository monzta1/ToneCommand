"""Explicit MK2 Amp 1/channel A experiment, never constructed by the app.

One Gain or Mid change. No model/channel/bypass/scene/routing/level writes,
Store, NAM or global settings. Readback covers the stated observed surfaces,
not every parameter on every other block or physical audio.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
import struct
import threading
import time

import mido

from fm9 import protocol as shared
from fm9.device import FM9NotFound, ReadOnly
from fm9.safety import sysex_guard
from . import protocol
from .adapter import AxeFxIII, ReadOnlyOutput, snapshot


CONTROLS = {'gain': 1, 'mid': 3}
AMP_WORDS = 4 * 142
BULK_IDS = frozenset({58, *range(3, 35)})
# Pin separately: a future name-writer firmware update must not promote this SET.
IDENTITY_SHA256 = '045dd3498d485ee32ebf5e87540830429fddac821fee5851e109f4db3c056217'


def _display_query(pid):
    return protocol.envelope(1, [16, 0, 58, 0, pid, 0])


def _extra_read(frame):
    return frame in ([protocol.envelope(31, [eid, 0]) for eid in BULK_IDS]
                     + [_display_query(pid) for pid in CONTROLS.values()])


@dataclass(frozen=True)
class AmpEdit:
    """Pure proposal. Construction is not permission to transmit."""
    preset: int
    control: str
    value: float

    def __post_init__(self):
        if type(self.preset) is not int or self.preset not in range(1024):
            raise ValueError('Pin one current MK2 wire preset, 0..1023')
        if type(self.control) is not str or self.control not in CONTROLS:
            raise ValueError('Only Amp 1 Gain or Mid on channel A is supported')
        if (type(self.value) not in (int, float) or not math.isfinite(self.value)
                or not .1 <= self.value <= 8
                or abs(self.value * 10 - round(self.value * 10)) > 1e-8):
            raise ValueError('Use a finite 0.1..8.0 value in steps of 0.1; no clamp or zero setter')

    @property
    def pid(self):
        return CONTROLS[self.control]

    def frame(self):
        # FW33 rounds the display value to float32 before division by ten.
        value = struct.unpack('<f', struct.pack('<f', self.value))[0] / 10
        return protocol.envelope(1, [9, 0, 58, 0, self.pid, 0,
                                    *shared.encode_f32_septets(value), 0, 0, 0, 0])

    def preview(self, before):
        if before['status']['preset']['number'] != self.preset:
            raise ValueError('Selected preset differs from the pinned target')
        if abs(before['shown'] - self.value) > 1.00001:
            raise ValueError('This experiment permits at most one display unit per review')
        return dict(preset=self.preset, effect_id=58, channel='A', control=self.control,
                    before=before['shown'], after=self.value, executable=False, stored=False)

    def matches(self, before, after):
        """Only the addressed A-word and its independent display may differ."""
        self.preview(before)
        unchanged = deepcopy(after)
        unchanged['amp'][self.pid] = before['amp'][self.pid]
        unchanged['shown'] = before['shown']
        if unchanged != before:
            raise ValueError('Other observed context, Amp words or modifiers changed')
        expected = round(self.value / 10 * 65534)
        return (abs(after['shown'] - self.value) <= .011
                and abs(after['amp'][self.pid] - expected) <= 1)


class AmpReadbackError(RuntimeError):
    """A write may have happened. Do not retry, reload or auto-restore."""


class _AmpOutput(ReadOnlyOutput):
    guard = sysex_guard('Axe-Fx III explicit Amp experiment', {1, 8, 10, 11, 12, 13, 14, 19, 31})

    def __init__(self, port, chassis):
        super().__init__(port, chassis)
        self._permit = None

    @contextmanager
    def _once(self, edit):
        if type(edit) is not AmpEdit or self._permit is not None:
            raise ReadOnly('One reviewed AmpEdit is required')
        checked = AmpEdit(edit.preset, edit.control, edit.value)
        self._permit = (threading.get_ident(), tuple(checked.frame()))
        try:
            yield
        finally:
            self._permit = None

    def send(self, message):
        frame = [240, *message.data, 247] if message.type == 'sysex' else []
        if protocol.allowed(frame, self._chassis):
            return super().send(mido.Message('sysex', data=frame[1:-1]))
        if _extra_read(frame):
            self.guard.check(frame[5])
        else:
            if self._permit != (threading.get_ident(), tuple(frame)):
                raise ReadOnly('No exact single-use reviewed Amp frame is armed')
            self.guard.check(frame[5])
            self._permit = None  # Consume before transport, even on uncertainty.
        self._port.send(mido.Message('sysex', data=frame[1:-1]))


@dataclass(frozen=True)
class AmpReview:
    edit: AmpEdit
    _baseline: str
    _expires: float

    def preview(self):
        result = self.edit.preview(json.loads(self._baseline))
        result['executable'] = True
        return result


class AmpWriter(AxeFxIII):
    """Opt-in acceptance component; ordinary adapter capabilities stay read-only."""

    def __init__(self, ports=None, *, chassis='mk2'):
        if chassis != 'mk2':
            raise ReadOnly('Amp writing requires the measured MK2 profile')
        self._review, self._uncertain = None, False
        super().__init__(ports, chassis=chassis)

    @staticmethod
    def _output(port, chassis):
        return _AmpOutput(port, chassis)

    def _send(self, frame):
        self.outp.send(mido.Message('sysex', data=frame[1:-1]))

    def set_chassis(self, chassis):
        if chassis != 'mk2':
            raise ReadOnly('The Amp-writing connection is pinned to MK2')
        super().set_chassis(chassis)

    def _identity(self):
        if self._closed or self._uncertain or self.chassis != 'mk2':
            raise ReadOnly('Exact measured MK2 firmware identity required; reconnect after uncertainty')
        reply = self._request(8, [], tuple)
        if (self._closed or self._uncertain or self.chassis != 'mk2'
                or reply is None or hashlib.sha256(bytes(reply)).hexdigest() != IDENTITY_SHA256):
            raise ReadOnly('Exact measured MK2 firmware identity required; reconnect after uncertainty')

    def _bulk(self, eid, timeout=1.5):
        if type(eid) is not int or eid not in BULK_IDS:
            raise ValueError('Only the Amp and modifier inspection surfaces are admitted')
        with self._lock:
            for _ in self.inp.iter_pending():
                pass
            self._send(protocol.envelope(31, [eid, 0]))
            deadline, count, words = time.monotonic() + timeout, None, []
            while time.monotonic() < deadline:
                for message in self.inp.iter_pending():
                    data = list(message.data) if message.type == 'sysex' else []
                    if not protocol.valid_reply(data):
                        continue
                    if data[4] == shared.FN_BCAST_HEAD:
                        head = shared.parse_bcast_head(data)
                        if (count is not None or len(data) != 10 or not head
                                or head != (eid, AMP_WORDS if eid == 58 else 25)):
                            return None
                        count = head[1]
                    elif data[4] == shared.FN_BCAST_BODY:
                        body = data[7:-1]
                        if count is None or not body or len(body) % 3 or any(b > 3 for b in body[2::3]):
                            return None
                        words.extend(shared.parse_bcast_body(data) or [])
                        if len(words) > count or any(w > 65534 for w in words):
                            return None
                    elif data[4] == shared.FN_BCAST_END:
                        return words if len(data) == 6 and count == len(words) else None
                time.sleep(.005)
        return None

    def _display(self, pid):
        def parse(data):
            if len(data) < 22 or data[5:11] != [16, 0, 58, 0, pid, 0]:
                return None
            length = shared.decode14(data[18], data[19])
            if not length or len(data[20:-1]) < length:
                return None
            bits = ''.join(f'{b:07b}' for b in data[20:20+length])
            raw = bytes(int(bits[i:i+8], 2) for i in range(0, len(bits)-7, 8))
            text = raw.split(b'\0', 1)[0].decode('ascii', errors='replace').strip()
            return float(text) if re.fullmatch(r'(?:\d|10)(?:\.\d{1,3})?', text) else None
        return self._request(1, _display_query(pid)[6:-2], parse)

    def _observe(self, edit):
        self._identity()
        status = snapshot(self)
        amp_status = [b for b in status['blocks'] if b['effect_id'] == 58]
        if len(amp_status) != 1 or amp_status[0]['channel'] != 'A' or amp_status[0]['channels'] != 4:
            raise ReadOnly('An existing Amp 1 on channel A with four channels is required')
        amp = self._bulk(58)
        modifiers = [self._bulk(eid) for eid in range(3, 35)]
        shown = self._display(edit.pid)
        if (amp is None or any(w is None or w[0] != 0 or w[8:10] != [0, 0] for w in modifiers)
                or shown is None or not 0 <= shown <= 10
                or abs(amp[edit.pid] / 65534 * 10 - shown) > .011):
            raise ReadOnly('Complete Amp words, 32 inactive unassigned modifiers and coherent display read required')
        if self._bulk(58) != amp or snapshot(self) != status:
            raise ReadOnly('Observed context changed during parameter inspection')
        self._identity()
        return dict(status=status, amp=amp, modifiers=modifiers, shown=shown)

    def review_amp(self, edit):
        if type(edit) is not AmpEdit:
            raise ValueError('An explicit AmpEdit is required')
        with self._lock:
            self._review = None
            before = self._observe(edit)
            edit.preview(before)
            self._review = AmpReview(edit, json.dumps(before, sort_keys=True), time.monotonic()+60)
            return self._review

    def apply_amp(self, review, *, external_audio_muted=False):
        if external_audio_muted is not True:
            raise ReadOnly('Confirm fully muted external monitoring')
        with self._lock:
            if (type(review) is not AmpReview or review is not self._review
                    or time.monotonic() >= review._expires):
                raise ReadOnly('Review is stale, foreign, consumed or expired')
            self._review = None
            before = self._observe(review.edit)
            if json.dumps(before, sort_keys=True) != review._baseline:
                raise ReadOnly('Observed parameter context changed since review')
            if review.edit.matches(before, before):
                return dict(verified=True, sent=False, stored=False)
            if time.monotonic() >= review._expires:
                raise ReadOnly('Review expired during preflight')
            success = False
            try:
                with self.outp._once(review.edit):
                    self._send(review.edit.frame())
                for _ in range(3):
                    time.sleep(.15)
                    after = self._observe(review.edit)
                    if review.edit.matches(before, after):
                        success = True
                        return dict(verified=True, sent=True, stored=False)
                raise AmpReadbackError('Amp value was not independently verified; no write retry')
            except AmpReadbackError:
                raise
            except Exception as error:
                # Includes failures during attempted transport and all readback.
                raise AmpReadbackError('Amp write may have been sent; verification failed; no write retry') from error
            finally:
                if not success:
                    self._uncertain = True

"""FW33 wah-source migration, captured in Axe-Edit on muted323.

Reuse the FW32.06 modifier implementation, not its firmware authorization.
No global CC mapping, transfer-curve SET, scene/channel change or Store.
"""
from dataclasses import replace
import time

from . import fw33_profile

# Eight existing-binding and five native-allocation/source/mode checks, full
# readback plus fresh Axe-Edit comparison on323/324, 2026-10-18.
RELEASED = True
TARGETS = frozenset({94, 95})
# Three native frames, two normal controller review/SENDs and fresh editor
# full-range/External2/Off comparison passed on muted325.
VOLUME_RELEASED=True
# Exact editor allocation on disconnected329, full default record captured.
VOLUME_CAPTURED=(
    'f0 00 01 74 10 01 3a 00 66 00 00 00 00 00 00 00 00 00 00 00 00 48 f7',
    'f0 00 01 74 10 01 09 00 03 00 00 00 00 00 00 0a 04 00 00 00 00 10 f7',
    'f0 00 01 74 10 01 09 00 03 00 00 00 00 00 40 0a 04 00 00 00 00 50 f7',
)
# Literal editor capture: allocation and both sources/modes in slots1 and2.
CAPTURED = (
    'f0 00 01 74 10 01 3a 00 5f 00 05 00 00 00 00 00 00 00 00 00 00 74 f7',
    'f0 00 01 74 10 01 3a 00 5e 00 05 00 00 00 00 00 00 00 00 00 00 75 f7',
    'f0 00 01 74 10 01 09 00 03 00 00 00 00 00 00 0a 04 00 00 00 00 10 f7',
    'f0 00 01 74 10 01 09 00 03 00 00 00 00 00 40 0a 04 00 00 00 00 50 f7',
    'f0 00 01 74 10 01 09 00 03 00 0a 00 00 00 00 06 04 00 00 00 00 16 f7',
    'f0 00 01 74 10 01 09 00 03 00 0a 00 00 00 00 00 00 00 00 00 00 14 f7',
    'f0 00 01 74 10 01 09 00 04 00 00 00 00 00 00 0a 04 00 00 00 00 17 f7',
    'f0 00 01 74 10 01 09 00 04 00 00 00 00 00 40 0a 04 00 00 00 00 57 f7',
    'f0 00 01 74 10 01 09 00 04 00 0a 00 00 00 00 06 04 00 00 00 00 11 f7',
    'f0 00 01 74 10 01 09 00 04 00 0a 00 00 00 00 00 00 00 00 00 00 13 f7',
)


def supported(dev, target):
    from . import fw33
    return (RELEASED and type(target) is int and (target in TARGETS or target==102 and VOLUME_RELEASED)
            and dev.reg.firmware == fw33_profile.KEY
            and dev.firmware_label() == fw33_profile.KEY
            and getattr(dev.reg, 'hardware_variant', None) == 'mk2'
            and fw33.runtime_write_error(dev) is None)


def expected_modifiers(before, frame, target):
    """Predict only captured fields. Never transmit the comparison records."""
    from . import modifiers, pedal_control
    from fm9 import protocol as shared
    if not isinstance(frame,list) or len(frame)!=23:
        raise ValueError('One exact captured23-byte editor frame required')
    result = [x['words'].copy() for x in before['modifiers']]
    param=pedal_control.TARGETS[target]
    if len(result) != 32 or any(len(w) != 25 for w in result):
        raise ValueError('All32 complete modifier records required')
    if frame == pedal_control.allocation_frame(target):
        if any(w[8:10] == [target, param] for w in result):
            raise ValueError('Existing inactive/active target cannot be allocated again')
        # Deleted/default models can leave a parameter ordinal in an unused
        # record. NONE source plus absent target is the native free-slot rule;
        # retain all other records, including their stale parameter metadata.
        index = next((i for i,w in enumerate(result) if w[0] == w[8] == 0), None)
        if index is None:
            raise ValueError('No unassigned modifier slot')
        result[index] = pedal_control.default_words(target)
        return result
    if frame[5] != 1 or frame[6:8] != [9,0]:
        raise ValueError('Only captured modifier source/mode frames')
    slot = shared.decode14(*frame[8:10]) - 3
    pid = shared.decode14(*frame[10:12])
    if slot not in range(32) or result[slot][8:10] != [target, param]:
        raise ValueError('Modifier slot no longer owns the requested Wah Control')
    value = shared.decode_f32_septets(frame[12:17])
    if pid == 0 and value in (12,13):
        expected = modifiers.source_frame(slot + 1, int(value))
    elif target in TARGETS and pid == 10 and value in (0,6):
        expected = pedal_control.auto_frame(slot + 1, int(value))
    else:
        raise ValueError('Uncaptured modifier field/value')
    if frame != expected:
        raise ValueError('Modifier encoding differs from capture')
    result[slot][pid] = int(value)
    return result


def allowed(dev, frame):
    operation = getattr(dev, '_pedal_fw33_operation', None)
    return (isinstance(operation, Operation) and operation.dev is dev
            and operation.pending == tuple(frame) and operation.consumed
            and dev.reg.firmware == fw33_profile.KEY
            and getattr(dev.reg, 'hardware_variant', None) == 'mk2'
            and getattr(dev, '_edit_target', None) == operation.preset
            and (RELEASED or operation.calibration))


class Operation:
    """One exact write, complete preservation readback, no retry/rollback."""
    def __init__(self, dev, target, *, calibration=False):
        dev._check_edit_target()
        if (type(target) is not int or not (target in TARGETS or target==102 and (VOLUME_RELEASED or calibration))
                or dev.reg.firmware != fw33_profile.KEY
                or dev.firmware_label() != fw33_profile.KEY
                or getattr(dev.reg, 'hardware_variant', None) != 'mk2'
                or getattr(dev, '_pedal_fw33_operation', None) is not None
                or (calibration and dev._edit_target not in ((325,) if target==102 else (323,324)))
                or (not RELEASED and not calibration)):
            raise PermissionError('Exact independently measured FW33/MK2 wah context required')
        self.dev, self.target, self.preset = dev, target, dev._edit_target
        self.calibration, self.consumed, self.pending = calibration, False, None

    def write(self, frame):
        from . import tone_review
        if self.consumed:
            raise PermissionError('Consumed modifier operation; never retry')
        self.consumed = True
        d = self.dev
        d._check_edit_target()
        if d._edit_target != self.preset:
            raise PermissionError('Reviewed preset changed')
        before = tone_review.snapshot(d, include_nam=False)
        if not any(b.effect_id == self.target for b in before['blocks']):
            raise ValueError('Wah target is absent')
        if self.target==102:
            from . import pedal_control
            words=before['bulk'].get(102)
            if (not isinstance(words,list) or len(words)!=60
                    or any(words[15*c+2]!=2 or words[15*c+6]!=52427 for c in range(4))
                    or any(m['words'][8:10]==[102,0] and
                        m['words'][1:]!=pedal_control.default_words(102)[1:] for m in before['modifiers'])):
                raise PermissionError('Volume requires full-range native curve, Type Volume and0dB on all channels')
        capture=VOLUME_CAPTURED if self.target==102 else CAPTURED
        if self.calibration and tuple(frame) not in tuple(tuple(bytes.fromhex(x)) for x in capture):
            raise PermissionError('Calibration permits only literal captured frames')
        wanted = expected_modifiers(before, frame, self.target)
        self.pending = tuple(frame)
        d._pedal_fw33_operation = self
        try:
            d._write(frame)
        finally:
            self.pending = None
            d._pedal_fw33_operation = None
        for _ in range(5):
            time.sleep(.15)
            now = tone_review.snapshot(d, include_nam=False)
            if [x['words'] for x in now['modifiers']] != wanted:
                # Native allocation can briefly expose an intermediate record.
                # Retry only independent reads, never the allocation/source SET.
                continue
            # Auto Engage/source may change only this wah's bypass state.
            normalized = dict(now)
            normalized['modifiers'] = before['modifiers']
            previous = {b.effect_id:b for b in before['blocks']}
            normalized['blocks'] = [replace(b, bypassed=previous[b.effect_id].bypassed)
                if self.target in TARGETS and b.effect_id == self.target and b.effect_id in previous else b for b in now['blocks']]
            if normalized != before:
                continue
            return now
        raise ValueError('Modifier full-state verification failed; no retry or rollback')

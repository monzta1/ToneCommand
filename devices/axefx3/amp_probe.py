"""Fixed developer-only AMP1 channel replay on328, not a planner capability.

Source: owner Axe-Edit recording2026-10-11 on exact FW33. Four channel SETs
use internal subcommand16 with raw channels1/2/3/0. Model, numeric, CAB,
controller, grid and Store writes are deliberately not part of this probe.
"""
from dataclasses import replace
import time

from . import fw33_profile, grid, protocol, serial_build, tone_review


def frames():
    return tuple(tuple(protocol.envelope(1, [0x16,0,58,0,0,0,c,0,0,0,0,0,0,0,0]))
                 for c in (1,2,3,0))


def allowed(dev, frame):
    from . import amp_calibration,amp_inventory_probe
    if amp_inventory_probe.allowed(dev, frame):
        return True
    if amp_calibration.allowed(dev, frame):
        return True
    probe = getattr(dev, '_amp_probe', None)
    return (isinstance(probe, Probe) and probe.dev is dev and probe.failed
            and probe.index < 4 and dev.reg.firmware == fw33_profile.KEY
            and getattr(dev.reg, 'hardware_variant', None) == 'mk2'
            and getattr(dev, '_edit_target', None) == 328
            and getattr(dev, '_amp_probe_permit', None) == tuple(frame)
            and tuple(frame) == frames()[probe.index])


class Probe:
    def __init__(self, dev):
        dev._check_edit_target()
        if (dev.reg.firmware != fw33_profile.KEY or dev._edit_target != 328
                or getattr(dev.reg, 'hardware_variant', None) != 'mk2'
                or getattr(dev, '_amp_probe', None) is not None):
            raise PermissionError('Only one confirmed328 MK2/FW33 AMP measurement')
        before = tone_review.snapshot(dev, include_nam=False)
        if (before['scene'] != 1 or grid.snapshot(before['grid']) != serial_build.expected_grid()
                or len(before['bulk'].get(58, [])) != 568
                or any(m['active'] for m in before['modifiers'])
                or next(b.channel for b in before['blocks'] if b.effect_id == 58) != 0):
            raise PermissionError('Exact measured chain, inactive modifiers and AMP1A required')
        level = dev.reg.find_param('OUTPUT', 'OUTPUT_LEVEL')
        if dev.get_param_display(level) != -18:
            raise PermissionError('Measured Output1 attenuation must already be -18dB')
        self.dev, self.index, self.failed = dev, 0, False
        self.expected = before
        dev._amp_probe = self

    def write(self, frame):
        with self.dev._lock:
            if self.failed or self.index >= 4:
                raise PermissionError('AMP probe consumed or complete; no retry')
            self.failed = True
            dev = self.dev
            dev._check_edit_target()
            if (not allowed_prewrite(self, frame)
                    or tone_review.snapshot(dev, include_nam=False) != self.expected):
                raise PermissionError('Exact ordered frame and fresh full state required')
            channel = (1,2,3,0)[self.index]
            wanted = dict(self.expected)
            wanted['blocks'] = [replace(b, channel=channel) if b.effect_id == 58 else b
                                for b in self.expected['blocks']]
            dev._amp_probe_permit = tuple(frame)
            try:
                dev._write(list(frame))
            finally:
                dev._amp_probe_permit = None
            for _ in range(5):
                time.sleep(.2)
                now = tone_review.snapshot(dev, include_nam=False)
                if now == wanted:
                    self.expected = now
                    self.index += 1
                    self.failed = False
                    return now
            raise ValueError('Channel/full-state readback mismatch; no retry or rollback')


def allowed_prewrite(probe, frame):
    dev = probe.dev
    return (getattr(dev, '_amp_probe', None) is probe
            and dev.reg.firmware == fw33_profile.KEY and dev._edit_target == 328
            and getattr(dev.reg, 'hardware_variant', None) == 'mk2'
            and tuple(frame) == frames()[probe.index])

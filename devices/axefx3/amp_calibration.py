"""Developer-only captured AMP1 calibration, not a planner capability.

Exact MK2/FW33 test328, bypassed AMP, Output1 -18dB, no active modifiers.
Two measured models and 24 measured nonzero numeric literals are replayed
across B/C/D, then restored to the editor's original B/C/D values. Each
transition requires a fresh full snapshot, followed by independent reads.
No other model, block, channel, CAB, modifier, memory or Store is authorized.
"""
from dataclasses import dataclass, replace
import struct
import time

from . import fw33_profile, grid, protocol, serial_build, tone_review


# Editor batch10, 2026-10-11; same literals independently anchored in bulk.
PIDS = (21,1,2,3,4,5,16,20)
VALUES = ((-19,4.6,3.8,6.2,5.4,4.8,2.2,4.2),
          (-20,5.3,4.1,5.8,5.6,5.2,2.6,4.4),
          (-21,6.1,3.6,6.6,5.2,4.6,2.4,4.0))
WORDS = ((39976,30146,24903,40631,35388,31456,14417,27524),
         (39320,34733,26869,38010,36699,34078,17039,28835),
         (38665,39976,23592,43252,34078,30146,15728,26214))


@dataclass(frozen=True)
class Step:
    kind: str
    channel: int
    frame: tuple
    pid: int = 0
    value: float = 0
    word: int = 0


def channel_frame(channel):
    return tuple(protocol.envelope(1,[22,0,58,0,0,0,channel,0,0,0,0,0,0,0,0]))


def steps():
    result = [Step('model',0,tuple(protocol.param_frame(58,0,m,opcode=9)),value=m)
              for m in (267,14)]
    for order in ((1,2,0),(0,1,2)):
        for channel, source in enumerate(order,1):
            result.append(Step('channel',channel,channel_frame(channel)))
            for pid,value,word in zip(PIDS,VALUES[source],WORDS[source]):
                # Axe-Edit first converts the display value to float32,
                # then divides the seven 0-10 knobs by10 before packing.
                single = struct.unpack('<f',struct.pack('<f',value))[0]
                raw = single if pid == 21 else single/10
                result.append(Step('numeric',channel,
                    tuple(protocol.param_frame(58,pid,raw,opcode=9)),pid,value,word))
        result.append(Step('channel',0,channel_frame(0)))
    return tuple(result)


def model_channel_steps():
    result=[]
    numeric=steps()[3:11]+steps()[12:20]+steps()[21:29]
    for channel,models in ((1,(14,267)),(2,(267,14)),(3,(14,267))):
        result.append(Step('channel',channel,channel_frame(channel)))
        for model in models:
            result.append(Step('model',channel,tuple(protocol.param_frame(58,0,model,opcode=9)),value=model))
        source=channel-1
        # Restore exactly the eight editor-calibrated controls, not a raw bulk.
        for pid,value,word in zip(PIDS,VALUES[source],WORDS[source]):
            original=next(s for s in numeric if s.pid==pid and s.value==value)
            result.append(replace(original,channel=channel,word=word))
    result.append(Step('channel',0,channel_frame(0)))
    return tuple(result)


def allowed(dev, frame):
    probe = getattr(dev,'_amp_probe',None)
    return (isinstance(probe,Calibration) and probe.dev is dev and probe.failed
        and probe.index < len(probe.sequence) and dev.reg.firmware == fw33_profile.KEY
        and getattr(dev.reg,'hardware_variant',None) == 'mk2'
        and getattr(dev,'_edit_target',None) == 328
        and getattr(dev,'_amp_probe_permit',None) == tuple(frame)
        and tuple(frame) == probe.sequence[probe.index].frame)


class Calibration:
    def __init__(self, dev):
        dev._check_edit_target()
        if (dev.reg.firmware != fw33_profile.KEY or dev._edit_target != 328
                or getattr(dev.reg,'hardware_variant',None) != 'mk2'
                or getattr(dev,'_amp_probe',None) is not None):
            raise PermissionError('Only one confirmed328 MK2/FW33 calibration')
        before = tone_review.snapshot(dev,include_nam=False)
        amp = next(b for b in before['blocks'] if b.effect_id == 58)
        if (before['scene'] != 1 or grid.snapshot(before['grid']) != serial_build.expected_grid()
                or len(before['bulk'].get(58,[])) != 568 or amp.channel != 0 or not amp.bypassed
                or any(m['active'] for m in before['modifiers'])
                or [before['bulk'][58][142*c] for c in range(4)] != [14,267,14,267]):
            raise PermissionError('Exact measured bypassed four-channel AMP foundation required')
        for channel in range(1,4):
            if tuple(before['bulk'][58][142*channel+p] for p in PIDS) != WORDS[channel-1]:
                raise PermissionError('Editor calibration anchors changed; nothing sent')
        self.dev,self.index,self.failed = dev,0,False
        self.sequence,self.expected = steps(),before
        self._quiet()
        dev._amp_probe = self

    def _quiet(self):
        output = self.dev.reg.find_param('OUTPUT','OUTPUT_LEVEL')
        level = self.dev.reg.find_param('DISTORT','DISTORT_LEVEL')
        value = self.dev.get_param_display(level)
        if self.dev.get_param_display(output) != -18 or value is None or value > -18:
            raise PermissionError('Measured Output1 -18dB and AMP level <= -18dB required')

    def _matches(self, now, step):
        wanted = dict(self.expected)
        if step.kind == 'channel':
            wanted['blocks'] = [replace(b,channel=step.channel) if b.effect_id == 58 else b
                                for b in wanted['blocks']]
        elif step.kind == 'numeric':
            wanted['bulk'] = {**wanted['bulk'],58:list(wanted['bulk'][58])}
            wanted['bulk'][58][142*step.channel+step.pid] = step.word
        else:
            # A model resets its active142-word voicing. Nothing else may change.
            wanted['bulk'] = {**wanted['bulk'],58:list(wanted['bulk'][58])}
            base=142*step.channel
            if now['bulk'][58][base] != step.value:
                return False
            wanted['bulk'][58][base:base+142] = now['bulk'][58][base:base+142]
        return now == wanted

    def write(self, frame):
        with self.dev._lock:
            if self.failed or self.index >= len(self.sequence):
                raise PermissionError('Calibration consumed or complete; no write retry')
            self.failed = True
            dev,step = self.dev,self.sequence[self.index]
            dev._check_edit_target()
            if (getattr(dev,'_amp_probe',None) is not self
                    or dev.reg.firmware != fw33_profile.KEY or dev._edit_target != 328
                    or getattr(dev.reg,'hardware_variant',None) != 'mk2'
                    or tuple(frame) != step.frame
                    or tone_review.snapshot(dev,include_nam=False) != self.expected):
                raise PermissionError('Exact literal, identity and fresh full state required')
            self._quiet()
            dev._amp_probe_permit = step.frame
            try:
                dev._write(list(frame))
            finally:
                dev._amp_probe_permit = None
            for _ in range(5):
                time.sleep(.2)
                now = tone_review.snapshot(dev,include_nam=False)
                if self._matches(now,step):
                    self._quiet()
                    if step.kind == 'numeric':
                        spec = dev.reg.spec('DISTORT',step.pid,1)
                        value = dev.get_param_display(spec)
                        if value is None or abs(value-step.value) > (spec.display_tolerance or .011):
                            raise ValueError('Independent display mismatch; no write retry')
                    self.expected,self.index,self.failed = now,self.index+1,False
                    return now
            raise ValueError('Independent full-state mismatch; no retry or automatic rollback')


class ModelChannels(Calibration):
    """Second exact measurement: two models on B/C/D and numeric restoration."""
    def __init__(self,dev):
        super().__init__(dev)
        self.sequence=model_channel_steps()

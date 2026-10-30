"""Legacy IR selection only; no installs, implicit blending or stereo pan."""
import time

from fm9.device import SetResult
from . import protocol, cab_mix


def frame(effect_id, pid, value):
    if (type(effect_id) is not int or effect_id not in range(62, 66)
            or type(pid) is not int or pid not in (0, 1, 4, 5)
            or type(value) is not int or value not in range(3 if pid < 4 else 1024)):
        raise ValueError("Cab selector outside the verified address/range")
    # Historical independently-read-back selector path, not a numeric taper.
    return protocol.param_frame(effect_id, pid, value, opcode=0x52 if value == 0 else 9)


def select(dev, effect_id, bank, ordinal, side):
    if side not in ("left", "right", "both"):
        raise ValueError("Choose left, right or explicitly both IR slots")
    slots = (0, 1) if side == "both" else (0,) if side == "left" else (1,)
    for slot in slots:
        frame(effect_id, slot, bank)
        frame(effect_id, slot + 4, ordinal)
    dev._check_edit_target()
    channel = dev.get_channel(effect_id)
    before = dev.bulk_read(effect_id)
    mixer = cab_mix.inspect(dev, effect_id, words=before, channel=channel)
    if not mixer.get("supported"):
        return SetResult(False, "Cab Legacy state unknown; nothing written", None, None)
    original = [(before[channel * 106 + s], before[channel * 106 + s + 4]) for s in slots]
    base = channel * 106
    current = before
    allowed = set()
    for slot in slots:
        allowed.update((base + slot, base + slot + 4))
        for pid, target in ((slot, bank), (slot + 4, ordinal)):
            if current[base + pid] == target:
                continue
            if dev.get_channel(effect_id) != channel:
                return SetResult(False, "Cab channel changed; selection stopped", original, None)
            dev._write(frame(effect_id, pid, target))
            verified = False
            for _ in range(4):
                time.sleep(.15)
                after = dev.bulk_read(effect_id)
                if dev.get_channel(effect_id) != channel:
                    break
                if after is None or len(after) != len(before):
                    continue
                if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(before, after))):
                    return SetResult(False, "Cab changed outside the requested IR; partial edit, stopped", original, None)
                if after[base + pid] == target:
                    current, verified = after, True
                    break
            if not verified:
                return SetResult(False, "Cab selector did not verify; partial edit may remain", original, None)
    final = dev.bulk_read(effect_id)
    final_mix = cab_mix.inspect(dev, effect_id, words=final, channel=channel)
    ok = (final is not None and len(final) == len(before) and final_mix.get("supported")
          and all(final[base + s] == bank and final[base + s + 4] == ordinal for s in slots)
          and all(a == b or i in allowed for i, (a, b) in enumerate(zip(before, final))))
    return SetResult(bool(ok), cab_mix.selection_note(final_mix, side) if ok else
                     "Final Cab selection/mixer verification failed", original,
                     [(bank, ordinal)] * len(slots) if ok else None)

"""Measured FW33 NAM Player 1 selector, independent of memory installation.

Editor trace on preset328: slot250 ->256 ->250 is parameter0, effect206,
opcode09, float32 ordinals249/255/249. Full independent bulk is four18-word
channels with the ordinal at offset0. A later user-operated256 ->001 ->256
->001 capture on329 records opcode09 zero twice, with visible001 and an
independent complete bulk ordinal0 after the editor closes.
"""
import time

from fm9.device import SetResult
from . import fw33_profile, nam_slots, protocol


def frame(slot):
    nam_slots.number(slot)
    return protocol.param_frame(206, 0, slot - 1, opcode=9)


def slots(words):
    if not isinstance(words, list) or len(words) != 72:
        raise ValueError('Complete four-channel NAM bulk is required')
    if any(type(word) is not int or not 0 <= word <= 65535 for word in words):
        raise ValueError('Malformed NAM bulk words')
    result = []
    for channel in range(4):
        ordinal = words[channel * 18]
        if type(ordinal) is not int or not 0 <= ordinal <= 255:
            raise ValueError('Unreadable NAM capture ordinal')
        result.append(ordinal + 1)
    return result


def capture(dev, slot):
    nam_slots.number(slot)
    got = dev.read_nam_slot1() if slot == 1 else dev.read_nam_slot(slot)
    if (got.slot != slot or got.byte_count != 65536 or got.empty
            or not got.name or got.name.upper() in {'EMPTY', '<EMPTY>'}
            or not isinstance(got.payload_sha256, str) or len(got.payload_sha256) != 64):
        raise ValueError('Selected NAM must be installed and independently read completely')
    return got


def state(dev):
    if (dev.reg.firmware != fw33_profile.KEY or dev.firmware_label() != fw33_profile.KEY
            or getattr(dev.reg, 'hardware_variant', None) != 'mk2'):
        raise ValueError('NAM selection requires the measured MK2/FW33 profile')
    before = dev.current_preset(), dev.current_scene()
    status = dev.status_dump()
    channel = dev.get_channel(206)
    words = dev.bulk_read(206)
    selected = slots(words)
    if (status is None or dev._channels.get(206) != 4
            or type(channel) is not int or channel not in fw33_profile.NAM_CHANNELS
            or not any(b.effect_id == 206 and b.channel == channel for b in status)
            or dev.get_channel(206) != channel
            or (dev.current_preset(), dev.current_scene()) != before):
        raise ValueError('NAM channel/target changed or is outside measured A/B')
    return dict(channel=channel, words=words, slots=selected, slot=selected[channel])


def select(dev, slot):
    """One selector write, quiet/bypassed staging and independent bulk readback.

    Success leaves the block bypassed; the reviewed design explicitly voices
    and engages it afterwards. No implicit memory install or rollback.
    """
    nam_slots.number(slot)
    dev._check_edit_target()
    before = state(dev)
    wanted = capture(dev, slot)
    if before['slot'] == slot:
        return SetResult(True, 'NAM already selected; all voicing preserved', slot, slot)
    encoded = frame(slot)
    from . import modifiers
    records = modifiers.inspect(dev)
    if len(records) != 32 or any(len(r['words']) != 25 or r['active'] for r in records):
        raise ValueError('Complete inactive modifiers required; no modifier is cleared')
    channel = before['channel']
    level = dev.reg.find_param('NAM', 'NAM_LEVEL')
    if dev.set_bypass(206, True) is not True or dev.get_bypass(206) is not True:
        return SetResult(False, 'NAM bypass failed; selector not written', before['slot'], None)
    staged = dev.set_param_display(level, -18)
    if not staged.ok:
        return SetResult(False, 'Quiet NAM staging failed; selector not written', before['slot'], None)
    baseline = state(dev)
    if baseline['channel'] != channel or baseline['slot'] != before['slot']:
        return SetResult(False, 'NAM changed while staging; selector not written', before['slot'], None)
    dev._nam_select_permit = tuple(encoded)
    try:
        dev._write(encoded)
    finally:
        dev._nam_select_permit = None
    for _ in range(4):
        time.sleep(.15)
        after = state(dev)
        if after['channel'] != channel:
            break
        if any(after['words'][c*18:(c+1)*18] != baseline['words'][c*18:(c+1)*18]
               for c in range(4) if c != channel):
            return SetResult(False, 'Another NAM channel changed; stop, no rollback', before['slot'], None)
        if after['slot'] == slot:
            if capture(dev, slot) != wanted or dev.get_bypass(206) is not True:
                return SetResult(False, 'NAM memory/bypass changed; stop with external mute', before['slot'], slot)
            staged = dev.set_param_display(level, -18)
            if not staged.ok or dev.get_channel(206) != channel:
                return SetResult(False, 'Final quiet staging failed; block left bypassed', before['slot'], slot)
            return SetResult(True, 'NAM slot and full memory verified; left quiet and bypassed', before['slot'], slot)
    return SetResult(False, 'NAM selector readback failed; no retry or rollback', before['slot'], None)

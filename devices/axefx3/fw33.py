"""Exact FW33 boundary ported from owner checkpoint 939e3ef.

No FM9 inheritance, guard widening, global state change or firmware guessing.
The port still requires a new hardware regression before user deployment.
"""
import time
import sys
import math

import mido

from fm9 import protocol as shared, midi_transport
from fm9.device import get_store_slots, FM9NotFound
from fm9.safety import sysex_guard
from . import protocol, fw33_profile as profile, nam_file, nam_slots, nam_selector


def platform_supported():
    return sys.platform == 'win32'


def runtime_write_error(dev):
    """FM9 transport/platform acceptance is not FX3 hardware evidence."""
    if dev.reg.firmware!=profile.KEY or getattr(dev,'_injected_ports',True) is not False:
        return None  # Explicit scripted ports remain available to isolated tests.
    if not platform_supported() or sys.version_info[:2]!=(3,12):
        return 'Native FW33 writes are measured on Windows/Python3.12 only; read-only connection remains available.'
    try:backend=midi_transport.backend()
    except midi_transport.TransportError:
        return 'FW33 MIDI backend could not be verified; no write is allowed.'
    if backend!='mido':
        return 'Native FX3 FW33 writes require the measured mido backend; FM9 supriya acceptance does not release FX3 writes.'
    return None


def check_frame(dev, frame):
    fn, payload = frame[5], frame[6:-2]
    from . import amp_probe,cab_probe,album_build,effect_probe,effects_calibration,zero_tempo_calibration,tempo_control,pedal_fw33,inherited_controls_probe
    if (amp_probe.allowed(dev, frame) or cab_probe.allowed(dev,frame)
            or album_build.frame_allowed(dev,frame) or effect_probe.allowed(dev,frame)
            or effects_calibration.allowed(dev,frame) or zero_tempo_calibration.allowed(dev,frame)
            or tempo_control.allowed(dev,frame) or pedal_fw33.allowed(dev,frame)
            or inherited_controls_probe.allowed(dev,frame)):
        return
    if fn != 1:
        if fn == 0x0c and payload != [127] and payload not in ([0],[1]):
            if (len(payload)!=1 or payload[0] not in range(8)
                    or getattr(dev,'_navigation_frame_permit',None)!=tuple(frame)):
                raise PermissionError('FW33 scene transition outside the measured NAM scope')
        if fn in (0x0a,0x0b) and len(payload) == 3 and payload[2] != 127:
            eid=shared.decode14(*payload[:2])
            from . import serial_build
            if serial_build.bypass_allowed(dev,frame):
                return
            if eid not in profile.NAM_ROUTE or (fn == 0x0b and payload[2] not in ({0,1} if eid == 206 else {0})):
                raise PermissionError('FW33 block transition outside the measured NAM scope')
        return  # The ordinary guard and command checks remain authoritative.
    sub = payload[:2]
    if nam_slots.is_name_request(frame):
        return
    if sub in ([0x10, 0], [0x2e, 0]):
        return
    if sub in ([9,0],[0x52,0]) and len(payload) == 15:
        eid, pid = shared.decode14(*payload[2:4]), shared.decode14(*payload[4:6])
        if eid == 206 and pid == 0:
            value = shared.decode_f32_septets(payload[6:11])
            if (not math.isfinite(value) or value != int(value) or not 0 <= value <= 255
                    or frame != nam_selector.frame(int(value) + 1)
                    or getattr(dev, '_nam_select_permit', None) != tuple(frame)):
                raise PermissionError('NAM selector differs from the measured reviewed frame')
            return
        family = dev.reg.family_of_effect_id(eid)
        if family:
            spec=dev.reg.spec(family[0], pid, family[1])
            value=shared.decode_f32_septets(payload[6:11]) * spec.set_divisor
            if family[0] in ('CABINET','FUZZ','COMP','GEQ'):
                session=getattr(dev,'_album_session',None)
                if (not isinstance(session,album_build.Session) or session.item is None
                        or session.item.spec!=spec
                        or frame!=protocol.set_parameter(dev.reg,spec,session.item.value)
                        or not album_build.amp_domain(dev,spec,dev.get_channel(eid))):
                    raise PermissionError('Cab/Drive SET requires the exact active reviewed parameter')
            expected=protocol.set_parameter(dev.reg,spec,value)
            if frame != expected:
                raise PermissionError('FW33 numeric SET differs from the measured encoding')
            return
    if sub in ([0x28, 0], [0x2b, 0], [0x26, 0]):
        return
    from . import grid_probe,row_probe,block_probe
    if grid_probe.allowed(dev,frame) or row_probe.allowed(dev,frame) or block_probe.allowed(dev,frame):
        return
    from . import serial_build
    if serial_build.allowed(dev,frame):
        return
    if sub in ([0x30, 0], [0x32, 0], [0x35, 0]) and getattr(dev, '_fw33_route_permit', None) == tuple(frame):
        return
    raise PermissionError('Editor command is not in the exact measured FW33 scope')


def zero_control_error(dev,spec,value):
    """The new scalar-zero evidence covers two exact first-instance models."""
    if (dev.reg.firmware!=profile.KEY or value!=0
            or spec.name not in profile.FX_ZERO_NAMES):return None
    from .tempo_control import DOMAINS
    eid,stride,model,_,_=DOMAINS[spec.family]
    words=dev.bulk_read(eid)
    if (not profile.FX_ZERO_RELEASED or spec.instance!=1 or spec.effect_id!=eid
            or dev.get_channel(eid)!=0 or not isinstance(words,list)
            or len(words)!=4*stride or type(words[0]) is not int or words[0]!=model):
        return 'Exact-zero FX control requires its measured first-instance model on A'
    return None


def domain_error(dev, spec, channel):
    channels = {0, 1} if spec.family == 'NAM' else {0}
    from . import album_build
    if album_build.amp_domain(dev,spec,channel): channels=set(range(4))
    if spec.family in ('CABINET','FUZZ','COMP','GEQ') and not album_build.amp_domain(dev,spec,channel):
        return 'FW33 Cab/Drive requires the exact active reviewed build operation'
    if channel not in channels:
        return 'FW33 numeric channel is outside the measured profile'
    words = dev.bulk_read(spec.effect_id)
    dev.status_dump()
    if (dev._channels.get(spec.effect_id) != 4 or not isinstance(words, list)
            or len(words) != 4 * profile.STRIDES[spec.family]):
        return 'FW33 full four-channel layout could not be verified'
    if spec.family=='FUZZ' and words[channel*44]!=8:
        return 'FW33 Drive numeric voicing requires measured T808 Mod'
    if spec.family in ('COMP','GEQ'):
        _,stride,selector,ordinal,_=profile.effect_controls.MODELS[spec.family]
        base=channel*stride
        if words[base+selector]!=ordinal:return 'Auxiliary numeric voicing requires its exact measured model'
        if (spec.family=='COMP' and spec.name not in profile.effect_controls.AUTO_OFF
                and (words[base+6]!=0 or words[base+16]!=0)):
            return 'Compressor manual modes must be independently OFF before manual voicing'
    if spec.family=='PEQ' and words[15:20]!=[0]*5:
        return 'Inherited PEQ controls require the independently measured filter layout'
    if spec.family=='PITCH' and words[0]!=0:
        return 'Inherited Pitch Level requires the independently measured Dual Detune model'
    if spec.family == 'NAM':
        try:
            nam_selector.capture(dev, nam_selector.slots(words)[channel])
        except ValueError as exc:
            return str(exc)
    return None


def prepare(dev, resolved, expected, actual):
    """Read-only NAM-build preflight, never promote an arbitrary FW33 route."""
    from . import modifiers,serial_build,album_build
    if tuple(expected) == serial_build.ROUTE:
        if any(i.action['kind'] in ('set_type','set_cab','set_scene') for i in resolved):
            return album_build.prepare(dev,resolved,expected,actual)
        return serial_build.prepare(dev,resolved,expected,actual)
    if getattr(dev.reg,'hardware_variant',None) != 'mk2':
        raise ValueError('FW33 NAM build requires the declared measured MK2 profile')
    if tuple(expected) != profile.NAM_ROUTE or (actual and actual != expected):
        raise ValueError('FW33 build requires the exact measured NAM route; no splicing')
    additions = [i for i in resolved if i.action['kind'] == 'add_block']
    if actual and additions:
        raise ValueError('FW33 additions require an entirely empty preset')
    scene = dev.current_scene()
    if scene not in (profile.NAM_SCENES if actual else {1}):
        raise ValueError('FW33 foundation requires scene 1; existing NAM route scenes 1/2')
    channels = {b.effect_id: b.channel for b in dev.status_dump() or []}
    if actual and any(channels.get(e) not in ({0,1} if e == 206 else {0}) for e in expected):
        raise ValueError('Existing NAM route uses an unmeasured channel')
    choices = {item.value for item in resolved if item.action['kind'] == 'select_nam'}
    if len(choices) > 1:
        raise ValueError('This NAM design requires one explicitly selected installed capture')
    selected_slot = next(iter(choices), 1)
    capture = nam_selector.capture(dev, selected_slot)
    if not actual and not any(i.family == 'NAM' and i.action.get('type_name') == capture.name for i in additions):
        raise ValueError('NAM ADD must name the independently read installed capture')
    entries = modifiers.inspect(dev)
    if len(entries) != 32 or any(len(e['words']) != 25 for e in entries):
        raise ValueError('All complete modifier records are required')
    if any(e['active'] for e in entries):
        raise ValueError('FW33 automated NAM builds require no active modifiers; no modifier is cleared')
    final = {}
    for index,item in enumerate(resolved):
        kind = item.action['kind']
        if kind not in profile.BUILD_KINDS - {'store'}:
            raise ValueError('FW33 models, CAB selectors and modifiers are not measured')
        if item.effect_id is not None and item.effect_id not in expected:
            raise ValueError('Action outside the measured NAM route')
        if kind in {'set_scene','rename_scene'} and item.value not in (profile.NAM_SCENES if actual else {1}):
            raise ValueError('Unmeasured FW33 scene transition')
        if kind == 'set_scene':
            channels.clear()
        if kind == 'set_channel':
            if item.value not in ({0,1} if actual and item.family == 'NAM' else {0}):
                raise ValueError('Unmeasured FW33 channel transition')
            channels[item.effect_id] = item.value
        if kind == 'select_nam':
            if item.effect_id != 206 or 206 not in channels:
                raise ValueError('NAM choice requires an explicit preceding NAM channel')
            final_level = False
            for later in resolved[index+1:]:
                if later.action['kind'] == 'set_scene' or (later.effect_id == 206 and later.action['kind'] in {'set_channel','select_nam','set_bypass'}):
                    break
                if later.effect_id == 206 and later.action['kind'] == 'set_param' and later.spec.name == 'NAM_LEVEL':
                    final_level = True
            if not final_level:
                raise ValueError('NAM selection requires explicit final level before engage or channel transition')
        if kind == 'set_param':
            if item.effect_id not in channels:
                raise ValueError('FW33 parameter requires an explicit preceding channel')
            final[item.spec.name] = item.value
            if actual:
                error = domain_error(dev, item.spec, channels[item.effect_id])
                if error:
                    raise ValueError(error)
                if item.spec.tempo_param_id is not None:
                    words = dev.bulk_read(item.effect_id)
                    pos = channels[item.effect_id] * profile.STRIDES[item.family] + item.spec.tempo_param_id
                    if words[pos] != 0 or str(dev.read_display_text(item.effect_id, item.spec.tempo_param_id)).strip().upper() != 'NONE':
                        raise ValueError('Literal delay/chorus timing requires verified Tempo NONE; no automatic FW33 setter')
    if not actual:
        if any(final.get(n, 1) > -12 for n in ('NAM_LEVEL','OUTPUT_LEVEL')):
            raise ValueError('Foundation requires explicit NAM and Output levels <= -12 dB')
        if any(n not in final for n in ('DELAY_LEVEL','CHORUS_LEVEL','REVERB_LEVEL')):
            raise ValueError('Foundation requires explicit final effect levels')
    return resolved, expected, actual


def memory_read(dev, read):
    if (not platform_supported() or dev.firmware_label() != profile.KEY
            or getattr(dev, '_injected_ports', True)
            or getattr(dev.reg,'hardware_variant',None) != 'mk2'):
        raise PermissionError('NAM read requires the measured live FW33 hardware')
    if midi_transport.backend() != 'mido':
        raise FM9NotFound('Native NAM read currently requires the measured mido backend')
    name = dev.inp.name
    dev.inp.close()
    try:
        return read(dev.outp)
    finally:
        try:
            dev.inp = mido.open_input(name)
            dev._drain()
        except (OSError, RuntimeError, ValueError) as exc:
            dev.close()
            raise FM9NotFound('MIDI input could not reopen after NAM read') from exc


def install(dev, compiled, expected_sha256, *, slot=1):
    nam_slots.number(slot)
    dev._check_edit_target()
    if (dev.reg.firmware != profile.KEY or getattr(dev, '_injected_ports', True)
            or not platform_supported()
            or getattr(dev.reg, 'hardware_variant', None) != 'mk2'
            or not isinstance(compiled, nam_file.CompiledNAM)):
        raise PermissionError('Only measured live MK2/FW33 NAM installation is allowed')
    if getattr(dev,'_nam_install_permit',None) != (slot,compiled.source_sha256,expected_sha256):
        raise PermissionError('Native NAM write requires the exact reviewed slot/source/memory permit')
    rebuilt = nam_file.compile_nam(compiled.source, compiled.name)
    if rebuilt.payload != compiled.payload or rebuilt.source_sha256 != compiled.source_sha256:
        raise PermissionError('Compiled NAM and source differ; nothing sent')
    if dev.read_nam_slot(slot).payload_sha256 != expected_sha256:
        raise PermissionError('NAM slot changed after preview; nothing sent')
    guard = sysex_guard('Reviewed FX3 NAM slot', {0x54, 0x55, 0x56})
    dev._drain()
    for frame in rebuilt.frames(slot):
        guard.check(frame[5])
        dev._check_edit_target()
        dev.outp.send(mido.Message('sysex', data=frame[1:-1]))
        time.sleep(.03)
    time.sleep(1)
    after = dev.read_nam_slot(slot)
    if (after.slot != slot or after.empty or after.payload_sha256 != rebuilt.payload_sha256 or after.name != rebuilt.name
            or after.byte_count != 65536):
        raise RuntimeError('NAM complete-memory readback mismatch; retain external mute')
    return after


def store(dev, slot):
    dev._check_edit_target()
    preset = dev.current_preset()
    if (type(slot) is not int or slot not in get_store_slots()
            or not preset or preset[0] != slot or dev.reg.firmware != profile.KEY):
        raise PermissionError('Store requires the allowed current slot and exact FW33 profile')
    before = dev.slot_name(slot)
    if before is None or before.number != slot:
        raise PermissionError('Stored target cannot be read; nothing sent')
    frame = protocol.envelope(1, [0x26, 0, 0, 0, 0, 0, *shared.encode14(slot),
                                  0, 0, 0, 0, 0, 0, 0])
    dev._store_permit = tuple(frame)
    try:
        dev._write(frame)
    finally:
        dev._store_permit = None
    for _ in range(4):
        time.sleep(.15)
        after = dev.slot_name(slot)
        if (after and after.number == slot and after.name == preset[1]
                and dev.current_preset() == preset):
            return slot, after.name
    raise RuntimeError('Store was sent but flash-name/target readback failed')

"""Deterministic FW33 NAM designs, no account/installation/Store permissions.

The empty foundation is the historically measured scene1/A route. After its
successful build a second reviewed design may use scenes1/2 and NAM A/B.
Shared effect settings stay on A; bypass state can differ between scenes.
"""
import json
from typing import Annotated

from pydantic import Field, StrictBool
from . import planning, executor, fw33_profile, route_guard, nam_slots, scene_intent,effect_capabilities


class NAM(planning.Shape):
    input_gain: Annotated[float,Field(ge=-20,le=0,strict=True,allow_inf_nan=False)]
    bass: planning.Knob
    mid: planning.Knob
    treble: planning.Knob
    level: Annotated[float,Field(ge=-60,le=-12,strict=True,allow_inf_nan=False)]


class Scene(planning.Shape):
    name: planning.Text
    nam: NAM
    delay: StrictBool
    chorus: StrictBool
    reverb: StrictBool


class Design(planning.Shape, scene_intent.IntentDesign):
    name: planning.Text
    summary: Annotated[str,Field(min_length=1,max_length=4000)]
    cab_active: StrictBool
    delay: planning.Delay
    chorus: planning.Chorus
    reverb: planning.Reverb
    scenes: Annotated[list[Scene],Field(min_length=1,max_length=2)]


SYSTEM = """Design the supplied installed NAM capture for Axe-Fx III exact FW33.
Return only the design schema, not MIDI/actions. Never claim direct listening,
original gear, a sound match or installation success from creator metadata.
An empty preset requires a one-scene foundation first; an existing exact NAM
route permits two scenes using NAM A/B. Other blocks use shared channel A.
Choose tone EQ and effect settings yourself within the schema. Preserve solo
backing versus solo lead roles. Do not select amp/cab/effect models or modifiers.
Delay, chorus and reverb settings are shared; only bypass differs per scene.
Keep NAM input gain <=0, NAM level <=-12; deterministic output is -18 dB.
Gain above the measured NAM input domain requires a different capture, not an
invented boost. Cab selection/mixer writes and extra pedals are not measured.
Keep Cab bypassed for a creator-declared amp+cab capture; that claim is not
proof. An amp-only capture needs a previously configured verified cab, which
this build preserves, not selects. Delay/chorus timing needs existing Tempo
NONE. Do not ask routine musical questions or give prose instead of a design.
Permanent installation and Store need separate explicit UI confirmation.
Explain limitations briefly in the user's language, no guessed controls.
"""


def reference(reg, state):
    return json.dumps(dict(device='Axe-Fx III',firmware=reg.firmware,
        effect_catalog=effect_capabilities.reference(reg,'nam'),
        installed_nam=state.get('nam'),route=route_guard.labels(fw33_profile.NAM_ROUTE,reg),
        controls=fw33_profile.NAMES, models_selectable=False,
        empty_foundation_scenes=1, existing_scenes=2,
        note='Complete NAM memory is read independently. No audio or physical pedal verification.'))


def compile_design(reg, raw, current_route, scene_count, capture):
    design = Design.model_validate(raw)
    if reg.firmware != fw33_profile.KEY or len(design.scenes) != scene_count:
        raise ValueError('Exact FW33 and requested scene count required')
    if current_route and tuple(current_route) != fw33_profile.NAM_ROUTE:
        raise ValueError('NAM build cannot replace or splice an existing route')
    if not current_route and scene_count != 1:
        raise ValueError('Build the measured one-scene foundation first; then request scenes 1/2')
    if not capture or capture['bytes'] != 65536 or capture['name'].upper() in {'EMPTY','<EMPTY>'}:
        raise ValueError('Install and independently read the selected NAM slot before designing')
    slot = nam_slots.number(capture.get('slot'))
    actions=[]
    def emit(kind,block=None,**kw):
        if block: kw.update(block=block,instance=1)
        actions.append(dict(kind=kind,**kw))
    def param(family,name,value):emit('set_param',family,param=name,value=value)
    if not current_route:
        for family in ('NAM','CABINET','DELAY','CHORUS','REVERB'):
            emit('add_block',family,**({'type_name':capture['name']} if family == 'NAM' else {}))
    emit('rename_preset',type_name=design.name)
    for number,scene in enumerate(design.scenes,1):
        emit('set_scene',value=number)
        for family in ('OUTPUT','NAM','CABINET','DELAY','CHORUS','REVERB'):
            emit('set_channel',family,value=number-1 if family == 'NAM' else 0)
        param('OUTPUT','OUTPUT_LEVEL',-18)
        emit('set_bypass','NAM',bypassed=True)
        emit('select_nam','NAM',value=slot)
        for name,value in scene.nam.model_dump().items():
            param('NAM','NAM_'+name.upper(),value)
        emit('set_bypass','NAM',bypassed=False)
        emit('set_bypass','CABINET',bypassed=not design.cab_active)
        for family,config,pairs in (
            ('DELAY',design.delay,('TIME','FEED','MIX')),
            ('CHORUS',design.chorus,('RATE','DEPTH','MIX')),
            ('REVERB',design.reverb,('TIME','MIX'))):
            emit('set_bypass',family,bypassed=True)
            if number == 1:
                values=({ 'TIME':config.time_ms,'FEED':config.feedback,'MIX':config.mix } if family=='DELAY'
                        else {'RATE':config.rate_hz,'DEPTH':config.depth,'MIX':config.mix} if family=='CHORUS'
                        else {'TIME':config.time_s,'MIX':config.mix})
                for name in pairs:param(family,family+'_'+name,values[name])
                param(family,family+'_LEVEL',0)
            emit('set_bypass',family,bypassed=not (getattr(scene,family.lower()) and config.active))
        emit('rename_scene',value=number,type_name=scene.name)
    for action in actions:executor.resolve(reg,action)
    return scene_intent.attach(dict(name=executor.preset_name(design.name),summary=design.summary,
        design=design.model_dump(),scenes=[s.name for s in design.scenes],actions=actions,
        required_route=route_guard.labels(fw33_profile.NAM_ROUTE,reg),cab_choices=[],
        capture=capture,controller=None,mode='nam',
        warnings=['FW33 exact measured build; selected installed NAM only, no amp/cab/modifier writes.',
                  'Installed NAM001-256 selection is separate from memory installation; changed selection stays quiet/bypassed until voiced.',
                  'NAM A/B; effects share A. Scenes 3-8 can also share these settings.',
                  'Separate confirmation for permanent NAM install and preset Store.',
                  'Readback is not proof of audible volume, guitar isolation or sound matching.']))

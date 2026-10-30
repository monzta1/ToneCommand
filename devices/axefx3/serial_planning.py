"""One-scene voicing of the measured serial template, without model guesses."""
import json
from typing import Annotated
from pydantic import Field
from . import planning, serial_build, route_guard, executor, scene_intent,effect_capabilities


class Design(planning.Shape, scene_intent.IntentDesign):
    name: planning.Text
    summary: Annotated[str,Field(min_length=1,max_length=2500)]
    scene_name: planning.Text
    amp: planning.Amp
    delay: planning.Delay
    chorus: planning.Chorus


SYSTEM = '''Design one scene of the measured Axe-Fx III FW33 serial template.
Return only the design schema. Choose gain/EQ, delay and chorus yourself.
Keep existing/default amp and cabinet models; no model or IR selector is
available in this mode. Do not invent names, original gear, exact reproduction,
listening or a measured delay tempo from metadata. Use audio measurements only
as cautious tonal evidence. Amp level must be <=-12dB. Output is fixed-18dB.
All reserve Wah/Drive/Compressor/Enhancer/Filter/Flanger/GEQ/PEQ blocks remain
bypassed. No wah controller, reverb, scene/channel change or new model.
Use one scene on channel A. Effects are explicitly voiced before engaging.
Models/cabs are retained, not chosen to match the artist. Say so briefly.
User review and mute acknowledgement are separate; never authorize SEND/Store.
'''


def reference(reg):
    return json.dumps(dict(device='Axe-Fx III',firmware=reg.firmware,
        effect_catalog=effect_capabilities.reference(reg,'serial'),
        route=route_guard.labels(serial_build.ROUTE,reg),scenes=1,channel='A',
        controls={f:reg.definitions[f] for f in ('DISTORT','DELAY','CHORUS','OUTPUT')},
        models_selectable=False,cab_selectable=False,controllers=False,
        note='Fixed captured chain; bypassed reserve blocks remain in the grid. No NAM required.'))


def compile_design(reg,raw,current_route,scene_count):
    design = Design.model_validate(raw)
    if not serial_build.supported(reg) or scene_count != 1:
        raise ValueError('Measured serial template requires exact FW33/MK2 and one scene')
    if current_route and tuple(current_route) != serial_build.ROUTE:
        raise ValueError('Serial template cannot overwrite or splice an existing different route')
    if design.amp.level > -12:
        raise ValueError('Serial Amp level must stay at or below-12dB')
    actions = [dict(kind='set_param',block='OUTPUT',instance=1,param='OUTPUT_LEVEL',value=-18)]
    def emit(kind,eid,**kw):
        family,instance = reg.family_of_effect_id(eid)
        actions.append(dict(kind=kind,block=family,instance=instance,**kw))
    if not current_route:
        for eid in serial_build.ROUTE[1:-1]: emit('add_block',eid)
    for eid in sorted(serial_build.RESERVE): emit('set_bypass',eid,bypassed=True)
    emit('set_bypass',58,bypassed=True)
    for key,value in design.amp.model_dump().items():
        emit('set_param',58,param='DISTORT_'+('DRIVE' if key=='gain' else key.upper()),value=value)
    emit('set_bypass',58,bypassed=False)
    emit('set_bypass',62,bypassed=False)
    for eid,family,config,values in (
        (70,'DELAY',design.delay,dict(TIME=design.delay.time_ms,FEED=design.delay.feedback,MIX=design.delay.mix)),
        (78,'CHORUS',design.chorus,dict(RATE=design.chorus.rate_hz,DEPTH=design.chorus.depth,MIX=design.chorus.mix))):
        emit('set_bypass',eid,bypassed=True)
        for name,value in {**values,'LEVEL':0}.items(): emit('set_param',eid,param=family+'_'+name,value=value)
        emit('set_bypass',eid,bypassed=not config.active)
    actions.extend([dict(kind='rename_preset',type_name=design.name),
        dict(kind='rename_scene',value=1,type_name=design.scene_name)])
    for action in actions: executor.resolve(reg,action)
    return scene_intent.attach(dict(mode='serial',name=executor.preset_name(design.name),summary=design.summary,
        design=design.model_dump(),scenes=[design.scene_name],actions=actions,
        required_route=route_guard.labels(serial_build.ROUTE,reg),cab_choices=[],controller=None,
        warnings=['Vaste gemeten14-blokkenketen, uitsluitend scene1/kanaal A; geen vrije ketenindeling.',
            'Amp- en cabmodellen blijven bestaand/standaard. Geen modelkeuze of IR/mixerwijziging.',
            'Reserve-effecten blijven bypassed. Geen NAM, reverb of nieuwe controllerkoppeling.',
            'Delay/Chorus vereisen onafhankelijk uitgelezen Tempo NONE; anders stopt uitvoering.',
            'Gedeelde A-kanalen kunnen andere scenes beinvloeden. Geen limiter, klankmatch of permanente opslag.']))

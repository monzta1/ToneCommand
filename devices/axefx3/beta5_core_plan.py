"""Pure one-scene AMP/CAB proposals, not a transport or write permission.

MK1/MK2 share this grammar. Declared storage policy filters local names;
native firmware/layout/route acceptance belongs to the separate executor.
"""
from typing import Annotated
import json
import struct

from pydantic import BaseModel,ConfigDict,Field,StrictInt
from . import amp_catalog,cab_inventory,fw33_profile,protocol,profile
from .catalog import modern_cab_metadata

TEXT=Annotated[str,Field(min_length=1,max_length=31,pattern=r'^[ -~]+$')]
KNOB=Annotated[float,Field(ge=0,le=10,multiple_of=.1,allow_inf_nan=False,strict=True)]
AMP_PIDS={'gain':1,'bass':2,'mid':3,'treble':4,'master':5,'depth':16,'presence':20,'level':21}
ROUTE=('Input 1','Amp 1','Cab 1','Output 1')


class Shape(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)


class Voice(Shape):
    gain:KNOB
    bass:KNOB
    mid:KNOB
    treble:KNOB
    master:KNOB
    depth:KNOB
    presence:KNOB
    level:Annotated[float,Field(ge=-60,le=-12,multiple_of=.1,allow_inf_nan=False,strict=True)]


class Cab(Shape):
    bank:Annotated[StrictInt,Field(ge=0,le=3)]
    slot:Annotated[StrictInt,Field(ge=1,le=1024)]


class Design(Shape):
    name:TEXT
    scene_name:TEXT
    summary:Annotated[str,Field(min_length=1,max_length=1500)]
    amp_model:Annotated[str,Field(min_length=1,max_length=120)]
    amp:Voice
    cab:Cab


def amp_frame(name,value):
    """Display float32 first, then divide. Never reuse a normalized FW32 SET."""
    voice={k:5. for k in AMP_PIDS};voice['level']=-18.
    if name not in voice:raise ValueError('Unsupported core Amp control')
    voice[name]=value;checked=Voice.model_validate(voice)
    value=getattr(checked,name)
    wire=value if name=='level' else struct.unpack('<f',struct.pack('<f',value))[0]/10
    return protocol.param_frame(58,AMP_PIDS[name],wire,opcode=9)


def cabinet_choices(reg):
    # Facts-only older catalog. Exact Beta5 selector acceptance is separate.
    names=dict(cab_inventory.factory_roster(fw33_profile.KEY))
    policy=profile.memory_policy(reg.firmware,getattr(reg,'hardware_variant',None))
    if modern_cab_metadata(reg.firmware):
        names.update({(b,o):n for (b,o),n in reg.cab_catalog.names.items()
                      if b in (2,3) and (b!=3 or policy['user2_cabs'])})
    return {(b,o):n for (b,o),n in names.items() if cab_inventory.occupied(n)}


def compile_design(reg,raw):
    design=Design.model_validate(raw)
    if any(value!=value.strip() for value in (design.name,design.scene_name)):
        raise ValueError('Names cannot contain outer spaces')
    names=amp_catalog.roster(amp_catalog.FIRMWARE)
    matches=[int(i) for i,n in names.items() if n==design.amp_model]
    if len(matches)!=1:raise ValueError('Choose one exact III Amp name from the supplied catalog')
    selected=cabinet_choices(reg).get((design.cab.bank,design.cab.slot-1))
    if selected is None:raise ValueError('Cab bank/slot is unavailable, empty or reserved for NAM')
    name=design.name if design.name.startswith('AI-') else 'AI-'+design.name
    if len(name)>31:raise ValueError('Preset name including AI-prefix must fit31 ASCII characters')
    return dict(mode='beta5-core',name=name,summary=design.summary,
                design=design.model_dump(),scenes=[design.scene_name],required_route=list(ROUTE),
                amp_ordinal=matches[0],cab_choices=[dict(side='IR1',name=selected,
                position=f'bank {design.cab.bank}, slot {design.cab.slot}',
                wire_bank=design.cab.bank,wire_ordinal=design.cab.slot-1)],
                warnings=['One scene on channel A. Only the exact minimal AMP/CAB route is supported.',
                          'Other default scenes may share these A-channel settings.',
                          'External audio must remain muted during construction; no physical limiter.',
                          'No additional effects, NAM, controllers, permanent Store or automatic Undo.'])


def reference(reg):
    return json.dumps(dict(device='Axe-Fx III',mode='one-scene core AMP/CAB',
        amp_models=amp_catalog.roster(amp_catalog.FIRMWARE),
        cabs=[dict(bank=b,slot=o+1,name=n) for (b,o),n in sorted(cabinet_choices(reg).items())],
        output_level_db=-18,amp_level_db_max=-12,route=ROUTE,scenes=1,
        unsupported=['effects','controllers','NAM','Store','multiple scenes']))


SYSTEM='''Design one playable Axe-Fx III AMP/CAB scene using the supplied catalog.
Choose the amplifier, cabinet and eight amp settings for the requested character.
Return the design or clarification envelope supplied by the host. If the
request requires effects, multiple scenes, NAM, controllers or permanent
saving, explain that limitation and ask which explicitly reduced supported
scope the user wants. Never silently omit a requested feature. No raw MIDI, effect, NAM, controller or
Store actions. Do not invent catalog names, listening, measured volume or exact
audio matching. The host stages quiet levels and requires independent review
and external muting before SEND. The preset is not permanently saved.
'''

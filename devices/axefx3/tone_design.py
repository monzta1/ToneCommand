"""Optional existing-block voicing and explicit captured model choices."""
from typing import Annotated
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,StrictBool
from . import tone_controls


def number(lo,hi):
    return Annotated[float,Field(ge=lo,le=hi,strict=True,allow_inf_nan=False)]


class Shape(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Drive(Shape):
    model:Literal['Rat Distortion','T808 OD','T808 Mod'] | None = None
    active:StrictBool
    drive:number(0,10)
    tone:number(0,10)
    mix:number(0,100)
    level:number(0,5)


class Compressor(Shape):
    model:Literal['Modern VCA Compressor','Classic VCA Compressor'] | None = None
    active:StrictBool
    threshold:number(-60,0)
    ratio:number(1,20)
    attack_ms:number(.1,100)
    release_ms:number(2,2000)
    mix:number(0,100)
    level:number(-20,0)


class GraphicEQ(Shape):
    active:StrictBool
    gains:Annotated[list[number(-12,0)],Field(min_length=10,max_length=10)]
    level:number(-80,0)


class Band(Shape):
    frequency_hz:number(20,20000)
    gain:number(-20,0)


class ParametricEQ(Shape):
    active:StrictBool
    bands:Annotated[list[Band],Field(min_length=5,max_length=5)]
    level:number(-80,0)


FIELDS={'drive':'FUZZ','compressor':'COMP','geq':'GEQ','peq':'PEQ'}
NEW_MODELS={'FUZZ':'T808 OD','COMP':'Modern VCA Compressor'}


def reference(reg):
    return dict(existing_blocks_only=['geq','peq'],automatic_insertion=['drive','compressor'],
        modes={'FUZZ':['Rat Distortion','T808 OD','T808 Mod'],
               'COMP':['Modern VCA Compressor','Classic VCA Compressor'],
               'GEQ':'10 Band Variable Q','PEQ':'Shelving/Peaking/Peaking/Peaking/Shelving'},
        geq_band_hz=[31,63,125,250,500,1000,2000,4000,8000,16000],
        controls={f:[dict(name=n,pid=d['pid'],unit=d['unit'],min=d['min'],max=d['max'])
                      for n,d in defs.items()] for f,defs in tone_controls.DEFINITIONS.items()
                  if reg.find_param(f,next(iter(defs))) is not None},
        limits='No positive EQ gain or dB effect level; Drive level knob 0..5. '
               'Optional Drive/Compressor model uses only the listed captured choices; '
               'omitted model preserves voicing. PEQ Q/filter types and modifiers are preserved.')


def validate_route(design,blocks,ids,reg):
    added=[]
    for attr,family in FIELDS.items():
        if any(getattr(s,attr) is not None for s in design.scenes):
            if family not in blocks:
                if family not in NEW_MODELS:
                    raise ValueError(f'{attr}: an existing first EQ block is required; automatic EQ insertion is not verified.')
                eid=reg.resolve_block(family,1)[1]
                amp=reg.resolve_block('DISTORT',blocks['DISTORT'])[1]
                anchor=amp
                if family=='FUZZ' and 'COMP' in blocks:
                    comp=reg.resolve_block('COMP',blocks['COMP'])[1]
                    if ids.index(comp)<ids.index(amp):anchor=comp
                ids.insert(ids.index(anchor),eid);blocks[family]=1;added.append(family)
                for scene in design.scenes:
                    config=getattr(scene,attr)
                    if config is not None and config.model is None:config.model=NEW_MODELS[family]
            if blocks[family]!=1:
                raise ValueError(f'{attr}: only the captured first instance is supported.')
            eid=reg.resolve_block(family,1)[1]
            cab=reg.resolve_block('CABINET',blocks['CABINET'])[1]
            amp=reg.resolve_block('DISTORT',blocks['DISTORT'])[1]
            if ((family in ('FUZZ','COMP') and ids.index(eid)>ids.index(amp))
                    or (family in ('GEQ','PEQ') and ids.index(eid)<ids.index(cab))):
                raise ValueError('Requested Drive/Compressor must precede Amp; EQ must follow Cab. No automatic moves.')
    return added


def compile_scene(scene,number,emit,added=(),*,channels=None):
    for attr,family in FIELDS.items():
        channel = channels[family][number-1] if channels is not None else number-1
        config=getattr(scene,attr)
        if config is None:
            if family in added:
                emit('set_channel',family,value=channel)
                emit('set_bypass',family,bypassed=True)
            continue
        values=[]
        if family=='FUZZ':
            values=[('DRIVE',config.drive),('TONE',config.tone),('MIX',config.mix)]
        elif family=='COMP':
            values=[('THRESH',config.threshold),('RATIO',config.ratio),('ATTACK',config.attack_ms),
                    ('RELEASE',config.release_ms),('MIX',config.mix)]
        elif family=='GEQ':values=[(f'GAIN{i+1}',v) for i,v in enumerate(config.gains)]
        elif family=='PEQ':
            values=[(key+str(i+1),v) for i,b in enumerate(config.bands)
                    for key,v in [('FREQ',b.frequency_hz),('GAIN',b.gain)]]
        values.append(('LEVEL',config.level))
        emit('set_channel',family,value=channel)
        emit('set_bypass',family,bypassed=True)
        if family in ('FUZZ','COMP') and config.model is not None:
            emit('set_type',family,type_name=config.model)
        for name,value in values:emit('set_param',family,param=family+'_'+name,value=value)
        emit('set_bypass',family,bypassed=not config.active)

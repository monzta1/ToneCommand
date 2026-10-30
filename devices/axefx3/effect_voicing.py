"""Measured FW33 voicing descriptions, not a generic effect write permit.

Source: closed379-step Compressor/GEQ/Drive calibration and independent
editor comparison. Normal builder integration and acceptance stay separate.
No I/O, user override, global mapping, arbitrary model or routing authority.
"""
from typing import Annotated,Literal
from pydantic import Field
from . import planning,protocol
from .effect_controls_fw33 import MODELS,AUTO_OFF,DEFINITIONS,ZERO_TYPED

# Native379-step calibration, actual selected-AI536-action normal SEND and
# independent16-effect/eight-scene editor comparison, exact FW33/MK2 only.
COMPRESSOR_RELEASED=True
GEQ_RELEASED=True


def number(lo,hi):return Annotated[float,Field(ge=lo,le=hi,strict=True,allow_inf_nan=False)]


class Compressor(planning.Shape):
    model:Literal['Modern VCA Compressor']='Modern VCA Compressor'
    threshold:number(-60,0)
    ratio:number(1,20)
    attack_ms:number(.1,100)
    release_ms:number(2,2000)
    mix:number(0,100)
    level:number(-20,0)
    auto_makeup:Literal[False]=False
    auto_attack_release:Literal[False]=False


class GraphicEQ(planning.Shape):
    model:Literal['10 Band Variable Q']='10 Band Variable Q'
    gains:Annotated[list[number(-12,0)],Field(min_length=10,max_length=10)]
    q:number(.1,10)=1.
    level:number(-80,0)


def default(family):
    if family=='COMP':return Compressor(threshold=-36.,ratio=3.,attack_ms=5.,release_ms=120.,mix=75.,level=-12.)
    if family=='GEQ':return GraphicEQ(gains=[0.]*10,q=1.,level=-12.)
    raise ValueError('Only measured Compressor/GEQ voices')


def parameters(family,voice):
    """Ordered values only. Consumers must independently verify every write.

    A model operation must remain bypassed under quiet Amp/external mute.
    Compressor automatic gain/timing is disabled before manual controls;
    final levels must be read back before any engage/scene transition.
    """
    if family=='COMP':
        if not isinstance(voice,Compressor):raise ValueError('Measured Compressor voicing required')
        return [*( (name,0) for name in AUTO_OFF),('COMP_LEVEL',-12.),
            ('COMP_THRESH',voice.threshold),('COMP_RATIO',voice.ratio),
            ('COMP_ATTACK',voice.attack_ms),('COMP_RELEASE',voice.release_ms),
            ('COMP_MIX',voice.mix),('COMP_LEVEL',voice.level)]
    if family=='GEQ':
        if not isinstance(voice,GraphicEQ):raise ValueError('Measured Graphic EQ voicing required')
        return [('GEQ_LEVEL',-12.),*((f'GEQ_GAIN{i+1}',v) for i,v in enumerate(voice.gains)),
            ('GEQ_Q',voice.q),('GEQ_LEVEL',voice.level)]
    raise ValueError('No additional effect or model authority')


def captured_frame(family,name,value):
    """Encode factual captured domains only, never send or authorize them."""
    if family not in DEFINITIONS or name not in DEFINITIONS[family]:raise ValueError('Unmeasured effect control')
    d=DEFINITIONS[family][name]
    if type(value) not in (int,float) or not d['min']<=value<=d['max']:
        raise ValueError('Finite in-range numeric value required')
    if name in AUTO_OFF and value!=0:raise ValueError('Only measured automatic-mode OFF is supported')
    return protocol.param_frame(MODELS[family][0],d['pid'],value/d['set_divisor'],opcode=int(d['set_opcode'],16))

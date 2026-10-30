"""Inherited Cry Babe voice; pitch transposition and global CCs are separate."""
from typing import Annotated,Literal
from pydantic import Field,model_validator
from . import planning

#201-action normal four-scene SEND and fresh editor/controller comparison,
# exact FW33/MK2 on muted329. Source and Auto Engage remain explicit.
RELEASED=True
Knob=Annotated[float,Field(ge=0,le=10,strict=True,allow_inf_nan=False)]


def reference(reg):
    """Describe server-owned binding separately from the AI's tone schema."""
    from . import serial_build,pedal_fw33
    ready=RELEASED and pedal_fw33.RELEASED and serial_build.supported(reg)
    return dict(executable=ready,block='Wah 1',channel='A',model='Cry Babe',
        sources=['External 1','External 2'] if ready else [],
        auto_engage_modes=['Off','Fast Pos'] if ready else [],
        binding_owner='server',binding_in_design_schema=False,
        allocation_executable=ready,global_cc_mapping_executable=False,
        pitch_transposition_executable=False,
        rule='When executable, the server compiles the selected External source and Auto Engage after validating the AI wah voice. Their absence from the musical design schema is NOT missing support. Do not ask to omit this supported controller or ask for a CC number.')


def request_state(reg,initial,source,auto):
    """Only read snapshot evidence; preserve never means invent Fast Pos."""
    if not reference(reg)['executable']:
        raise ValueError('Wah request context requires the released AMP/CAB profile')
    current=existing_controller(initial['modifiers'])
    effective_source=source or (current['source'] if current else None)
    effective_auto=(auto if source and auto is not None else
        current['auto_engage'] if current else 'Off' if source else None)
    return dict(existing_binding=current,requested_source=source,
        requested_auto_engage=auto if source else None,
        effective_source=effective_source,effective_auto_engage=effective_auto,
        new_binding=bool(source and not current),
        preserve_without_binding=bool(source and auto is None and not current),
        preservation_rule='Null means preserve the independently read mode. With no existing binding, native allocation defaults to Off, NOT Fast Pos. If the user explicitly chose preserve, explain this consequence once; never override that choice or falsely claim External is unsupported.')


class Voice(planning.Shape):
    model:Literal['Cry Babe']='Cry Babe'
    frequency_min:Annotated[float,Field(ge=100,le=1000,strict=True,allow_inf_nan=False)]
    frequency_max:Annotated[float,Field(ge=500,le=5000,strict=True,allow_inf_nan=False)]
    resonance:Knob
    q_tracking:Knob
    fat:Knob
    drive:Knob
    inductor_bias:Knob
    low_cut:Annotated[float,Field(ge=20,le=2000,strict=True,allow_inf_nan=False)]
    level:Annotated[float,Field(ge=-40,le=0,strict=True,allow_inf_nan=False)]=0.

    @model_validator(mode='after')
    def ascending(self):
        if self.frequency_min>=self.frequency_max:raise ValueError('Wah filter must sweep upwards')
        return self


FIELDS=dict(frequency_min='WAH_FREQMIN',frequency_max='WAH_FREQMAX',resonance='WAH_RESONANCE',
    q_tracking='WAH_QTRACKING',fat='WAH_FAT',drive='WAH_DRIVE',inductor_bias='WAH_INDUCTOR_BIAS',
    low_cut='WAH_LOWCUT',level='WAH_LEVEL')


def parameters(voice):return [(name,getattr(voice,key)) for key,name in FIELDS.items()]


def controller(source,auto):
    if source is None:return None
    from . import pedal_control
    ordinal={'External 1':12,'External 2':13}.get(source)
    pedal_control.validate(94,ordinal,auto)
    return dict(source=source,auto_engage=auto)


def modifiers_allowed(entries):
    """Preserve only the independently assessed Wah1 Control binding."""
    return (len(entries)==32 and all(len(m['words'])==25 for m in entries)
        and sum(bool(m['active']) for m in entries)<=1
        and all(not m['active'] or (m.get('effect_id')==94 and m.get('param_id')==5
            and m.get('source') in (12,13) and m['words'][10] in (0,6)
            and m.get('assessed_target') and m.get('curve_structurally_usable')) for m in entries))


def existing_controller(entries):
    if not modifiers_allowed(entries):raise ValueError('Unassessed existing controller; nothing inferred')
    active=[m for m in entries if m['active']]
    if not active:return None
    if len(active)!=1:raise ValueError('Duplicate Wah controller ownership')
    return dict(source={12:'External 1',13:'External 2'}[active[0]['source']],
        auto_engage={0:'Off',6:'Fast Pos'}[active[0]['words'][10]])

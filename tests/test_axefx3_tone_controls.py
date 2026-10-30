"""Captured core controls, not a claim of arbitrary effect/model support."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from devices.axefx3 import protocol, tone_controls, audio_safety
from devices.axefx3.registry import Registry
from fm9 import protocol as shared


@pytest.mark.parametrize('family,name,value,wire', [
    ('FUZZ','FUZZ_DRIVE',6.2,.62),('FUZZ','FUZZ_TONE',4.3,.43),
    ('FUZZ','FUZZ_LEVEL',2,.2),('FUZZ','FUZZ_MIX',80,.8),
    ('COMP','COMP_THRESH',-30,-30),('COMP','COMP_RATIO',4,4),
    ('COMP','COMP_ATTACK',5,.005),('COMP','COMP_RELEASE',250,.25),
    ('COMP','COMP_LEVEL',-12,-12),('COMP','COMP_MIX',75,.75),
    *[('GEQ',f'GEQ_GAIN{i}',-3,-3) for i in range(1,11)],
    ('GEQ','GEQ_LEVEL',-12,-12),
    *[('PEQ',f'PEQ_FREQ{i}',v,v) for i,v in enumerate((300,500,1000,2000,4000),1)],
    *[('PEQ',f'PEQ_GAIN{i}',-3,-3) for i in range(1,6)],
    ('PEQ','PEQ_LEVEL',-12,-12),
])
def test_addressed_captured_numeric_units(family,name,value,wire):
    reg=Registry('32.06'); spec=reg.find_param(family,name)
    frame=protocol.set_parameter(reg,spec,value)
    assert frame[:8]==[0xF0,0,1,0x74,0x10,1,9,0]
    assert frame[8:12]==[spec.effect_id,0,spec.param_id,0]
    assert shared.decode_f32_septets(frame[12:17])==pytest.approx(wire)
    assert frame[-2]==shared.checksum(frame[1:-2])


@pytest.mark.parametrize('family,name',[(f,n) for f,defs in tone_controls.DEFINITIONS.items()
                                     for n,d in defs.items() if d['zero_typed']])
def test_only_captured_typed_zeros(family,name):
    reg=Registry('32.06')
    frame=protocol.set_parameter(reg,reg.find_param(family,name),0)
    assert frame[6:8]==[9,0]
    assert shared.decode_f32_septets(frame[12:17])==0


@pytest.mark.parametrize('eid',[46,50,54])
def test_numeric_parameter_zero_is_not_a_model_query(eid):
    frame=protocol.display_query(eid,0)
    assert frame[6:-2]==[16,0,eid,0,0,0]


@pytest.mark.parametrize('eid',[58,62,66,70,78,94,118])
def test_model_zero_still_never_queried(eid):
    with pytest.raises(ValueError):protocol.display_query(eid,0)


def words(family):
    eid,stride=tone_controls.LAYOUTS[family]
    data=[0]*(4*stride)
    if family=='GEQ':
        for c in range(4):data[c*stride+15]=4
    return data


@pytest.mark.parametrize('family',list(tone_controls.LAYOUTS))
def test_existing_modes_full_layout_and_explicit_channels_only(family):
    reg=Registry('32.06');spec=reg.find_param(family,next(iter(tone_controls.DEFINITIONS[family])))
    data=words(family)
    assert tone_controls.profile_error(spec,data,0) is None
    assert tone_controls.profile_error(spec,data,3) is None
    assert tone_controls.profile_error(spec,data[:-1],0)
    assert tone_controls.profile_error(spec,data,True)
    pid={'FUZZ':0,'COMP':12,'GEQ':15,'PEQ':15}[family]
    data[3*tone_controls.LAYOUTS[family][1]+pid]=2
    assert tone_controls.profile_error(spec,data,0) is None
    assert tone_controls.profile_error(spec,data,3)
    with pytest.raises(ValueError):reg.spec(family,spec.param_id,2)


def test_no_guessed_q_model_filter_or_bulk_restore():
    reg=Registry('32.06')
    assert reg.find_param('PEQ','PEQ_Q1') is None
    for defs in tone_controls.DEFINITIONS.values():
        assert all(d['bulk_restore_supported'] is False for d in defs.values())
    assert not Registry('32.07').params


@pytest.mark.parametrize('family,ordinal',[('FUZZ',6),('FUZZ',8),('COMP',13)])
def test_captured_additional_models_have_the_measured_control_profile(family,ordinal):
    reg=Registry('32.06');data=words(family)
    selector=12 if family=='COMP' else 0
    data[selector]=ordinal
    for name in tone_controls.DEFINITIONS[family]:
        assert tone_controls.profile_error(reg.find_param(family,name),data,0) is None
    data[selector]=99
    assert tone_controls.profile_error(reg.find_param(family,name),data,0)


def test_drive_level_is_a_pinned_knob_not_fm9_db_or_unity():
    reg=Registry('32.06');spec=reg.find_param('FUZZ','FUZZ_LEVEL')
    assert protocol.set_parameter(reg,spec,5)
    with pytest.raises(ValueError):protocol.set_parameter(reg,spec,5.01)
    with pytest.raises(ValueError):protocol.set_parameter(reg,replace(spec,set_divisor=1),2)
    unknown=dict(family='FUZZ',name='FUZZ_LEVEL',label='Level',unit='numeric')
    assert audio_safety.parameter_error(unknown,2)
    assert audio_safety.modifier_error(spec)


@pytest.mark.parametrize('family,name',[('COMP','COMP_LEVEL'),('GEQ','GEQ_GAIN1'),
                                       ('GEQ','GEQ_LEVEL'),('PEQ','PEQ_GAIN5'),('PEQ','PEQ_LEVEL')])
def test_positive_db_boosts_refused(family,name):
    reg=Registry('32.06')
    with pytest.raises(ValueError):protocol.set_parameter(reg,reg.find_param(family,name),.1)


def test_live_profile_rechecks_channel_and_firmware_before_write():
    dev=Mock();dev.reg=Registry('32.06');spec=dev.reg.find_param('COMP','COMP_THRESH')
    dev.bulk_read.return_value=words('COMP');dev.get_channel.return_value=0
    assert tone_controls.domain_error(dev,spec,0) is None
    dev.get_channel.return_value=1
    assert tone_controls.domain_error(dev,spec,0)
    dev.reg.firmware='32.07'
    assert tone_controls.domain_error(dev,spec,0)

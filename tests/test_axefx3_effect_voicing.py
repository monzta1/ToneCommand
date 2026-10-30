"""Factual metadata/order does not bypass normal builder or release gates."""
import math
import pytest
from devices.axefx3 import effect_voicing as voices,effects_calibration as captured


def test_default_voices_use_only_literal_measured_set_domains():
    seq=captured.steps()
    for family in ('COMP','GEQ'):
        eid=voices.MODELS[family][0]
        for name,value in voices.parameters(family,voices.default(family)):
            expected=tuple(voices.captured_frame(family,name,value))
            assert any(s[1]==eid and s[0]=='param' and captured.frame_for(s)==expected for s in seq),(name,value)


def test_manual_compressor_order_disables_both_automatic_modes_first():
    values=voices.parameters('COMP',voices.default('COMP'))
    assert values[:3]==[('COMP_AUTO_MAKEUP',0),('COMP_AUTO_ATT_REL',0),('COMP_LEVEL',-12.)]
    assert values[-1]==('COMP_LEVEL',-12.)
    assert voices.captured_frame('COMP','COMP_AUTO_MAKEUP',0)[6]==0x52
    assert voices.captured_frame('COMP','COMP_LEVEL',0)[6]==9


def test_geq_uses_log_q_and_cut_only_schema():
    voice=voices.default('GEQ')
    assert voice.gains==[0.]*10 and voices.DEFINITIONS['GEQ']['GEQ_Q']['scale']=='log10'
    assert voices.parameters('GEQ',voice)[-2:]==[('GEQ_Q',1.),('GEQ_LEVEL',-12.)]
    with pytest.raises(ValueError):voices.GraphicEQ(gains=[1.]*10,level=0.)


@pytest.mark.parametrize('field,value',[
    ('model','Optical Compressor'),('auto_makeup',True),('auto_attack_release',True),
    ('level',1.),('threshold',math.nan),('ratio',0.),('mix',101.),('attack_ms',-1.),('release_ms',math.inf)])
def test_unmeasured_or_unsafe_compressor_fields_are_not_accepted(field,value):
    data=voices.default('COMP').model_dump();data[field]=value
    with pytest.raises(ValueError):voices.Compressor.model_validate(data)


@pytest.mark.parametrize('field,value',[
    ('model','5 Band Passive'),('gains',[0.]*9),('gains',[0.]*11),('gains',[True]*10),
    ('level',1.),('q',0.),('q',math.nan),('q',math.inf)])
def test_unmeasured_or_unsafe_eq_fields_are_not_accepted(field,value):
    data=voices.default('GEQ').model_dump();data[field]=value
    with pytest.raises(ValueError):voices.GraphicEQ.model_validate(data)


@pytest.mark.parametrize('family,name,value',[
    ('COMP','COMP_AUTO_MAKEUP',1),('COMP','COMP_AUTO_ATT_REL',True),
    ('COMP','COMP_LEVEL',math.nan),('COMP','COMP_LEVEL',math.inf),
    ('COMP','COMP_RATIO','2'),('GEQ','GEQ_Q',0),('PEQ','GEQ_Q',1)])
def test_encoder_does_not_invent_additional_modes_or_values(family,name,value):
    with pytest.raises(ValueError):voices.captured_frame(family,name,value)


def test_metadata_and_release_flags_do_not_expose_io():
    assert voices.COMPRESSOR_RELEASED is True and voices.GEQ_RELEASED is True
    assert not any(hasattr(voices,name) for name in ('send','write','execute','connect'))

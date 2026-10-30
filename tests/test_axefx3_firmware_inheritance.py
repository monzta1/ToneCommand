"""A new firmware inherits approved controls; metadata does not authorize IO."""
from copy import deepcopy
import pytest
from devices.axefx3 import firmware_inheritance as inheritance
from devices.axefx3.evidence import AXE_FX_III_PARAM_DEFINITIONS as legacy
from devices.axefx3.registry import Registry
from devices.axefx3 import fw33_profile


def test_parent_approval_is_reused_without_erasing_old_controls():
    before=deepcopy(legacy)
    child=inheritance.compose(legacy,overrides={'DISTORT':{'DISTORT_DRIVE':{'set_divisor':10.}}},
        additions={'NAM':{'NAM_LEVEL':dict(pid=1,label='Level',min=-80.,max=20.)}})
    assert all(child[f].keys()>=controls.keys() for f,controls in legacy.items())
    assert child['DISTORT']['DISTORT_DRIVE']['set_divisor']==10.
    assert 'NAM_LEVEL' in child['NAM'] and legacy==before
    child['WAH']['WAH_CONTROL']['pid']=900
    assert legacy['WAH']['WAH_CONTROL']['pid']==5


def test_next_firmware_inherits_the_child_not_an_outdated_baseline():
    first=inheritance.compose(legacy,overrides={'DISTORT':{'DISTORT_DRIVE':{'set_divisor':10.}}},
        additions={'NAM':{'NAM_LEVEL':dict(pid=1)}})
    second=inheritance.compose(first,additions={'NAM':{'NAM_MID':dict(pid=11)}})
    assert second['DISTORT']['DISTORT_DRIVE']['set_divisor']==10.
    assert set(second['NAM'])=={'NAM_LEVEL','NAM_MID'}
    assert len(Registry('future-unverified-firmware').params)==0


def test_actual_fw33_catalog_contains_every_approved_parent_parameter():
    child=fw33_profile.definitions(legacy)
    for family,controls in legacy.items():
        assert set(controls)<=set(child[family])
    assert sum(map(len,legacy.values()))==75
    assert sum(map(len,child.values()))==83
    assert child['WAH']['WAH_CONTROL']['set_opcode']=='09'
    assert legacy['WAH']['WAH_CONTROL']['set_opcode']=='52'


def test_family_overrides_preserve_additional_approved_parent_controls():
    parent=deepcopy(legacy)
    for family in ('CHORUS','COMP','GEQ','FUZZ','NAM'):
        parent.setdefault(family,{})['APPROVED_PARENT_EXTRA']=dict(pid=120,label='Additional approved control',unit='',min=0.,max=1.)
    child=fw33_profile.definitions(parent)
    assert all('APPROVED_PARENT_EXTRA' in child[f] for f in ('CHORUS','COMP','GEQ','FUZZ','NAM'))


@pytest.mark.parametrize('options,expected',[
    ([],0),(['--require-complete'],1),(['--firmware','future-unverified-firmware'],2)])
def test_migration_report_is_readonly_and_cannot_claim_complete(options,expected,monkeypatch,capsys):
    import json,sys
    from tools.afx3_firmware_parity import main
    monkeypatch.setattr(sys,'argv',['afx3_firmware_parity.py',*options])
    assert main()==expected
    result=json.loads(capsys.readouterr().out)
    assert not result['automatically_enables_writes']
    if expected!=2:
        assert result['retained_parameters']==75 and not result['pending_parameters']
        assert not result['functionality_complete']


@pytest.mark.parametrize('kwargs',[
    dict(overrides={'WAH':{'WAH_CONTROL':None}}),
    dict(overrides={'WAH':{'WAH_CONTROL':{'pid':None}}}),
    dict(overrides={'WAH':{'NEW_CONTROL':{'pid':99}}}),
    dict(additions={'WAH':{'WAH_CONTROL':dict(pid=999)}}),
    dict(additions={'WAH':{'DUPLICATE':dict(pid=5)}}),
])
def test_silent_deletion_replacement_and_wire_aliases_are_refused(kwargs):
    with pytest.raises(ValueError):inheritance.compose(legacy,**kwargs)


def test_all_approved_parent_zero_controls_have_a_child_setter():
    from devices.axefx3.evidence import AXE_FX_III_32_06_ZERO_NORMALIZED,AXE_FX_III_32_06_ZERO_TYPED
    from devices.axefx3 import protocol
    reg=Registry(fw33_profile.KEY)
    for name in set(AXE_FX_III_32_06_ZERO_NORMALIZED)|set(AXE_FX_III_32_06_ZERO_TYPED):
        spec=reg.find_param(name.split('_')[0],name)
        assert spec is not None
        assert protocol.set_parameter(reg,spec,0)[4]==16


def test_legacy_zero_encodings_equal_all16_editor_literals(monkeypatch):
    import hashlib,json
    from importlib.resources import files
    from fm9 import protocol as shared
    from devices.axefx3 import protocol
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_legacy_zeros.json').read_text(encoding='utf-8'))
    assert len(data['frames'])==16 and data['firmware']==fw33_profile.KEY
    assert hashlib.sha256(json.dumps(data['frames'],separators=(',',':')).encode()).hexdigest()==data['sha256']=='a686a8d7fcd1a1047daf7016320ed5a8de455d44e8daaef42961ac8d894c62ae'
    reg=Registry(fw33_profile.KEY)
    for literal in data['frames']:
        frame=list(bytes.fromhex(literal));eid=shared.decode14(*frame[8:10]);pid=shared.decode14(*frame[10:12])
        spec=reg.spec(reg.family_of_effect_id(eid)[0],pid)
        value=shared.decode_f32_septets(frame[12:17])*spec.set_divisor
        assert protocol.set_parameter(reg,spec,value)==frame
    monkeypatch.setattr(fw33_profile,'LEGACY_ZERO_RELEASED',False)
    for name in fw33_profile.LEGACY_ZERO_TYPED|fw33_profile.LEGACY_ZERO_NORMALIZED:
        with pytest.raises(ValueError):protocol.set_parameter(reg,reg.find_param(name.split('_')[0],name),0)

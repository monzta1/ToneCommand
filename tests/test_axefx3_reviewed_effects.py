"""Measured auxiliary prototype remains blocked before native acceptance."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from fm9 import protocol as shared
from devices.axefx3 import album_planning as planning,album_build as build,effect_voicing as voices,executor,fw33,protocol,scene_intent
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_album_build import device,design


@pytest.fixture(autouse=True)
def candidate(monkeypatch):
    monkeypatch.setattr(voices,'COMPRESSOR_RELEASED',True)
    monkeypatch.setattr(voices,'GEQ_RELEASED',True)


def raw():
    source=design()
    for c,a in enumerate(source['albums']):
        a['compressor']=voices.default('COMP').model_dump()
        a['geq']=dict(voices.default('GEQ').model_dump(),gains=[float(-c)]*10)
        a['lead'].update(compressor=False,geq=False)
        a['solo'].update(compressor=True,geq=True)
    return source


def fixture(monkeypatch):
    d=device(monkeypatch);old=d.get_param_display
    def display(spec):
        if spec.family not in voices.MODELS:return old(spec)
        c=d.get_channel(spec.effect_id);stride=voices.MODELS[spec.family][1]
        word=d._test_bulk[spec.effect_id][stride*c+spec.param_id]
        return word if spec.kind=='enum' else shared.normalized_to_display(word/65534,spec.dmin,spec.dmax,spec.scale)
    d.get_param_display=display
    return d


def test_normal_auxiliary_send_four_channels_and_complete_proofs(monkeypatch):
    d=fixture(monkeypatch);source=raw()
    plan=planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    build.validate_actions(d.reg,plan['actions'],True)
    result=executor.execute(d,plan['actions'],plan['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result
    assert len(result['album_verification']['scene_fingerprints'])==8
    for n,states in d._test_scenes.items():
        for eid in (46,50):
            assert states[eid].channel==(n-1)//2 and states[eid].bypassed is bool(n%2)
    assert [d._test_bulk[50][20*c+15] for c in range(4)]==[4]*4
    assert all(d._test_bulk[46][37*c+6]==d._test_bulk[46][37*c+16]==0 for c in range(4))
    d.store_preset.assert_not_called()


@pytest.mark.parametrize('count',range(1,9))
def test_auxiliary_voices_follow_explicit_short_layout_and_complete_prefix(monkeypatch,count):
    from devices.axefx3 import fw33_profile
    monkeypatch.setattr(fw33_profile,'ALBUM_SCENE_COUNTS',frozenset(range(1,9)))
    d=fixture(monkeypatch);source=raw();source['scene_count']=count
    source['scene_layout']=planning.layout(source)[:count]
    plan=planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),count)
    result=executor.execute(d,plan['actions'],plan['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result
    assert set(result['album_verification']['scene_fingerprints'])==set(map(str,range(1,count+1)))
    assert d.current_scene()==count


@pytest.mark.parametrize('key,family,flag',[('compressor','COMP','COMPRESSOR_RELEASED'),('geq','GEQ','GEQ_RELEASED')])
def test_release_gate_is_authoritative_at_compile_and_executor(monkeypatch,key,family,flag):
    d=fixture(monkeypatch);source=raw()
    plan=planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    monkeypatch.setattr(voices,flag,False)
    with pytest.raises(ValueError,match='awaits'):planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    with pytest.raises(ValueError,match='not released'):executor.prepare(d,plan['actions'],plan['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


@pytest.mark.parametrize('fault',['auto_on','boost','wrong_model','wrong_channel','staging','extra'])
def test_changed_auxiliary_grammar_refused_before_any_write(monkeypatch,fault):
    d=fixture(monkeypatch);p=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    actions=deepcopy(p['actions'])
    if fault=='auto_on':next(a for a in actions if a.get('param')=='COMP_AUTO_MAKEUP')['value']=1
    if fault=='boost':next(a for a in actions if a.get('param')=='GEQ_GAIN1')['value']=1.
    if fault=='wrong_model':next(a for a in actions if a['kind']=='set_type' and a['block']=='GEQ')['type_name']='5 Band'
    if fault=='staging':next(a for a in actions if a.get('param')=='COMP_LEVEL')['value']=0.
    if fault=='wrong_channel':
        first=next(i for i,a in enumerate(actions) if a['kind']=='set_scene')
        next(a for a in actions[first:] if a['kind']=='set_channel' and a.get('block')=='COMP')['value']=3
    if fault=='extra':actions.append(dict(kind='set_param',block='COMP',instance=1,param='COMP_LEVEL',value=-12.))
    with pytest.raises((ValueError,KeyError)):executor.prepare(d,actions,p['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


def test_active_missing_voice_is_not_a_successful_effect_request(monkeypatch):
    d=fixture(monkeypatch);source=raw();source['albums'][1]['compressor']=None
    with pytest.raises(ValueError,match='explicit voicing'):planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)


def test_auxiliary_set_requires_exact_active_reviewed_spec_and_manual_model(monkeypatch):
    d=fixture(monkeypatch);p=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    resolved=[executor.resolve(d.reg,a) for a in p['actions']]
    item=next(i for i in resolved if i.spec and i.spec.name=='COMP_RATIO')
    frame=protocol.set_parameter(d.reg,item.spec,item.value)
    d._approved_frame=tuple(frame)
    with pytest.raises(PermissionError):AxeFxIII._send(d,frame)
    with build.execution(d,resolved,True) as s:
        s.item=item
        d._test_bulk[46][6]=1
        assert 'manual' in fw33.domain_error(d,item.spec,0)
        d._test_bulk[46][6]=0
        assert fw33.domain_error(d,item.spec,0) is None
        AxeFxIII._send(d,frame)
    d._approved_frame=None


def test_full_cab_drive_auxiliary_plan_has_a_bounded_explicit_size(monkeypatch):
    from test_axefx3_cab_design import design as cab_design
    from test_axefx3_drive_build import raw as drive_design
    d=fixture(monkeypatch);source=raw();cabs=cab_design();drives=drive_design()
    for i,a in enumerate(source['albums']):
        a.update(cab=cabs['albums'][i]['cab'],drive=drives['albums'][i]['drive'])
        for ir in a['cab']['irs']:ir.update(bank=1,slot=516)
    p=planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    assert 512<len(p['actions'])<=640
    executor.prepare(d,p['actions'],p['required_route'],322)
    d._write.assert_not_called()

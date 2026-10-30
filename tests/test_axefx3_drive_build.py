"""Reviewed T808 Mod extension, not generic FW33 effect permissions."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from devices.axefx3 import album_build as build,album_planning as planning,executor,fw33,protocol,scene_intent
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_album_build import device,design
from devices.axefx3 import fw33_profile


@pytest.fixture(autouse=True)
def synthetic_prototype(monkeypatch):
    monkeypatch.setattr(fw33_profile,'DRIVE_RELEASED',True)


def fixture(monkeypatch):
    d=device(monkeypatch);previous=d.get_param_display
    d.get_param_display=lambda s:(d._test_bulk[118][44*d.get_channel(118)+s.param_id]/65534*(100 if s.param_id==4 else 10)
        if s.family=='FUZZ' else previous(s))
    return d


def raw():
    d=design()
    for c,a in enumerate(d['albums']):
        a['drive']=dict(model='T808 Mod',gain=float(c),tone=5.,level=1.5,mix=100.)
        a['lead']['drive']=c%2==0;a['solo']['drive']=True
    return d


def test_four_drive_voices_normal_send_and_full_scene_proof(monkeypatch):
    d=fixture(monkeypatch);source=raw()
    plan=planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    build.validate_actions(d.reg,plan['actions'],True)
    result=executor.execute(d,plan['actions'],plan['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result
    assert len(result['album_verification']['scene_fingerprints'])==8
    assert [d._test_bulk[118][44*c] for c in range(4)]==[8]*4
    for n,states in d._test_scenes.items():
        assert states[118].channel==(n-1)//2
        assert states[118].bypassed is (not source['albums'][(n-1)//2]['lead' if n%2 else 'solo']['drive'])
        assert all(states[e].bypassed for e in planning.serial_build.RESERVE-{118})
    d.store_preset.assert_not_called()


def test_explicit_scene_layout_drive_follows_amp_not_fixed_album_pair(monkeypatch):
    d=fixture(monkeypatch);source=raw()
    source['scene_layout']=[dict(name='Scene'+str(n+1),amp_channel=c,cab_channel=c,delay=False,chorus=False,drive=bool(n%2)) for n,c in enumerate((0,3,2,1,2,0,3,1))]
    plan=planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    build.validate_actions(d.reg,plan['actions'],True)
    assert [m['drive'] for m in plan['channel_mapping']]==[m['amp'] for m in plan['channel_mapping']]
    sounds=scene_intent.scenes(plan)
    assert [s['effects']['drive']['gain'] for s in sounds]==[0.,3.,2.,1.,2.,0.,3.,1.]
    result=executor.execute(d,plan['actions'],plan['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result


@pytest.mark.parametrize('fault',['model','too_loud','pre_model_engage','staging','wrong_scene_channel','extra'])
def test_changed_drive_grammar_refused_before_any_write(monkeypatch,fault):
    d=device(monkeypatch);plan=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    actions=deepcopy(plan['actions'])
    if fault=='model':next(a for a in actions if a.get('kind')=='set_type' and a.get('block')=='FUZZ')['type_name']='Rat Distortion'
    if fault=='too_loud':next(a for a in actions if a.get('param')=='FUZZ_LEVEL')['value']=5.
    if fault=='pre_model_engage':next(a for a in actions if a.get('kind')=='set_bypass' and a.get('block')=='FUZZ')['bypassed']=False
    if fault=='staging':next(a for a in actions if a.get('param')=='FUZZ_LEVEL')['value']=1.
    if fault=='wrong_scene_channel':
        first=next(i for i,a in enumerate(actions) if a['kind']=='set_scene')
        next(a for a in actions[first:] if a['kind']=='set_channel' and a.get('block')=='FUZZ')['value']=3
    if fault=='extra':actions.append(dict(kind='set_param',block='FUZZ',instance=1,param='FUZZ_LEVEL',value=0.))
    with pytest.raises((ValueError,KeyError)):executor.prepare(d,actions,plan['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called();d.set_bypass.assert_not_called()


def test_drive_requires_exact_active_spec_and_reviewed_value(monkeypatch):
    d=device(monkeypatch);plan=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    resolved=[executor.resolve(d.reg,a) for a in plan['actions']]
    item=next(i for i in resolved if i.spec and i.spec.name=='FUZZ_LEVEL')
    frame=protocol.set_parameter(d.reg,item.spec,item.value)
    for active in (False,True):
        d._approved_frame=tuple(frame)
        if not active:
            with pytest.raises(PermissionError):AxeFxIII._send(d,frame)
        else:
            with build.execution(d,resolved,True) as session:
                session.item=item
                assert fw33.domain_error(d,item.spec,0) is not None # model0 not calibrated8
                d._test_bulk[118][0]=8
                assert fw33.domain_error(d,item.spec,0) is None
                AxeFxIII._send(d,frame)
                wrong=protocol.set_parameter(d.reg,item.spec,1.)
                d._approved_frame=tuple(wrong)
                with pytest.raises(PermissionError):AxeFxIII._send(d,wrong)
    d._approved_frame=None


def test_active_drive_without_voicing_is_not_a_prose_only_success(monkeypatch):
    d=device(monkeypatch);source=design();source['albums'][0]['lead']['drive']=True
    with pytest.raises(ValueError,match='voicing'):planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)


def test_other_voiced_channel_does_not_make_missing_active_voice_valid(monkeypatch):
    d=device(monkeypatch);source=raw();source['albums'][1]['drive']=None
    with pytest.raises(ValueError,match='selected amp voice'):
        planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


def test_prototype_is_not_available_in_normal_release(monkeypatch):
    d=fixture(monkeypatch);source=raw()
    plan=planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    monkeypatch.setattr(fw33_profile,'DRIVE_RELEASED',False)
    with pytest.raises(ValueError,match='awaits'):planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    with pytest.raises(ValueError,match='not released'):executor.prepare(d,plan['actions'],plan['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


def test_drive_bypass_requires_captured_typed_frame_not_assumed_legacy_command(monkeypatch):
    d=fixture(monkeypatch)
    plan=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    resolved=[executor.resolve(d.reg,a) for a in plan['actions']]
    item=next(i for i in resolved if i.action['kind']=='set_bypass' and i.effect_id==118)
    typed=protocol.param_frame(118,7,1,opcode=9)
    assumed=protocol.envelope(0x0a,[118,0,1])
    with build.execution(d,resolved,True) as session:
        session.item=item
        session.frame=tuple(typed)
        assert build.frame_allowed(d,typed)
        assert not build.frame_allowed(d,assumed)
        d._approved_frame=tuple(typed)
        AxeFxIII._send(d,typed)
        d._approved_frame=tuple(assumed)
        with pytest.raises(PermissionError):AxeFxIII._send(d,assumed)
    d._approved_frame=None

"""Synthetic checks of exact reviewed serial route; not hardware evidence."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from threading import RLock
from unittest.mock import Mock
from contextlib import nullcontext

import pytest
from fm9 import protocol as shared
from fm9.device import SetResult
from devices.axefx3 import serial_build as serial,serial_planning,fw33,fw33_profile,grid,executor,tone_review,route_guard
from devices.axefx3.registry import Registry
from devices.axefx3.adapter import AxeFxIII
from fastapi.testclient import TestClient
import server
from tests.scene_intent_fixtures import with_goals


def design():
    return dict(name='AI-Serial Test',summary='Retained models, not an exact recording match',
        scene_name='Crunch',amp=dict(gain=5.5,bass=3.5,mid=6.5,treble=5.0,master=5.0,
            depth=2.0,presence=3.5,level=-18.),
        delay=dict(active=True,time_ms=320.,feedback=20.,mix=18.),
        chorus=dict(active=True,rate_hz=.7,depth=25.,mix=12.))


def fake(existing=False):
    reg=Registry(fw33_profile.KEY);reg.hardware_variant='mk2'
    cells=dict(serial.expected_grid()) if existing else {}
    blocks={e:shared.BlockStatus(e,False,0,4) for e in serial.ROUTE} if existing else {}
    bulk={e:[0]*(4*fw33_profile.STRIDES.get(reg.family_of_effect_id(e)[0],12)) for e in blocks}
    levels={}
    d=SimpleNamespace(reg=reg,_lock=RLock(),_serial_session=None,_edit_target=322,
        _serial_bypass_permit=None,_approved_frame=None,_check_edit_target=Mock(),
        current_preset=Mock(return_value=(322,'Test')),current_scene=Mock(return_value=1),
        firmware_label=Mock(return_value=fw33_profile.KEY),_channels={e:4 for e in blocks},
        read_grid=lambda:[shared.GridCell(r-1,c-1,e,s,m) for (r,c),(e,s,m) in cells.items()],
        status_dump=lambda:list(blocks.values()),bulk_read=lambda e:list(bulk[e]),
        read_modifier=lambda slot:[0]*25,scene_name=lambda n:(n,'Scene'+str(n)),
        read_display_text=Mock(return_value='NONE'),
        read_nam_slot=Mock(side_effect=AssertionError('NAM must not be required')),
        edit_session=lambda **kw:nullcontext(),
        rename_preset=Mock(side_effect=lambda n:(322,n)),rename_scene=Mock(side_effect=lambda n,name:(n,name)),
        store_preset=Mock(),set_scene=Mock(),set_channel=Mock())
    def set_param(spec,value):
        levels[spec.name]=value
        bulk[spec.effect_id][spec.param_id]=123
        return SetResult(True,'independent display',None,value)
    d.set_param_display=Mock(side_effect=set_param)
    d.get_param_display=lambda spec:levels.get(spec.name,-18.)
    def bypass(eid,value):
        blocks[eid]=replace(blocks[eid],bypassed=value)
        frame=serial.protocol.envelope(0x0a,[*shared.encode14(eid),int(value)])
        fw33.check_frame(d,frame)
        return value
    d.set_bypass=Mock(side_effect=bypass)
    def write(frame):
        assert serial.allowed(d,frame)
        fw33.check_frame(d,frame)
        seq=serial.row_fixture.steps()[d._serial_session.index]
        cells.clear();cells.update(seq[2])
        for _,(e,_,_) in cells.items():
            if e not in blocks:
                blocks[e]=shared.BlockStatus(e,False,0,4)
                bulk[e]=[0]*(4*fw33_profile.STRIDES.get(reg.family_of_effect_id(e)[0],12))
                d._channels[e]=4
    d._write=Mock(side_effect=write)
    d.build_route=lambda required,actions:serial.build(d,required,actions)
    d._test_cells=cells;d._test_blocks=blocks;d._test_bulk=bulk
    return d


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):monkeypatch.setattr(serial.time,'sleep',lambda _:None)


def plan(d,existing=False):
    return serial_planning.compile_design(d.reg,design(),list(serial.ROUTE) if existing else [],1)


@pytest.mark.parametrize('existing',[False,True])
def test_complete_normal_executor_path_and_no_nam_dependency(existing):
    d=fake(existing);p=plan(d,existing)
    executor.prepare(d,p['actions'],p['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called()
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result
    assert grid.snapshot(d.read_grid())==serial.expected_grid()
    assert d._write.call_count==(0 if existing else 41)
    assert not result['stored'] and d._serial_session is None and d._serial_bypass_permit is None
    assert all(d._test_blocks[e].bypassed for e in serial.RESERVE)
    d.read_nam_slot.assert_not_called();d.store_preset.assert_not_called()
    d.set_scene.assert_not_called();d.set_channel.assert_not_called()
    assert d.set_param_display.call_args_list[0].args[0].name=='OUTPUT_LEVEL'


def test_schema_and_route_never_enable_models_unmeasured_peq_numeric_or_extra_actions():
    d=fake();p=plan(d)
    assert len([a for a in p['actions'] if a['kind']=='add_block'])==12
    assert route_guard.route_ids(p['required_route'],d.reg)==list(serial.ROUTE)
    assert not {a['kind'] for a in p['actions']} & {'store','set_type','set_cab','select_nam','bind_controller','set_channel','set_scene'}
    assert d.reg.effect_id('PEQ',2)==55
    with pytest.raises((ValueError,KeyError)):d.reg.spec('PEQ',0,2)
    assert 'no model' in serial_planning.SYSTEM.lower()
    for key in ('actions','amp_model','cab_left'):
        raw=design();raw[key]=[]
        with pytest.raises(ValueError):serial_planning.compile_design(d.reg,raw,[],1)


@pytest.mark.parametrize('fault',['scene','channel','grid','modifier','missing_add','duplicate_add',
    'output','amp','reserve','model','tempo','layout','variant','firmware'])
def test_all_preflight_faults_refuse_before_writes(fault,monkeypatch):
    existing=fault not in ('missing_add','duplicate_add');d=fake(existing);p=plan(d,existing)
    if fault=='scene':d.current_scene.return_value=2
    if fault=='channel':d._test_blocks[58]=replace(d._test_blocks[58],channel=1)
    if fault=='grid':d._test_cells[2,1]=d._test_cells.pop((1,1))
    if fault=='modifier':monkeypatch.setattr(serial.modifiers,'inspect',lambda d:[dict(words=[0]*25,active=True)]*32)
    if fault=='missing_add':p['actions']=[a for a in p['actions'] if not(a['kind']=='add_block' and a['block']=='PEQ')]
    if fault=='duplicate_add':p['actions'].append(next(a for a in p['actions'] if a['kind']=='add_block'))
    if fault=='output':p['actions'][0]['value']=-12
    if fault=='amp':next(a for a in p['actions'] if a.get('param')=='DISTORT_LEVEL')['value']=-1
    if fault=='reserve':next(a for a in p['actions'] if a['kind']=='set_bypass' and a['block']=='WAH')['bypassed']=False
    if fault=='model':p['actions'].append(dict(kind='set_type',block='DISTORT',type_name='fake'))
    if fault=='tempo':d.read_display_text.return_value='1/4'
    if fault=='layout':d._test_bulk[58]=[0]*12
    if fault=='variant':d.reg.hardware_variant='mk1'
    if fault=='firmware':d.firmware_label.return_value='33.01'
    with pytest.raises((ValueError,KeyError)):executor.prepare(d,p['actions'],p['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called();d.set_bypass.assert_not_called()


def test_builder_fails_without_retry_and_session_released_on_dropped_write():
    d=fake();p=plan(d);original=d._write.side_effect
    def dropped(frame):
        if d._serial_session.index==3:return
        return original(frame)
    d._write.side_effect=dropped
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert not result['ok'] and result['phase']=='build_route' and result['skipped']==len(p['actions'])
    assert d._write.call_count==4 and len(d._test_cells)==1
    assert d._serial_session is None and d._serial_bypass_permit is None
    d.store_preset.assert_not_called()


def test_cable_phase_waits_for_verified_staging_and_tempo():
    d=fake();p=plan(d);d.read_display_text.return_value='1/4'
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert not result['ok'] and d._write.call_count==28 and len(d._test_cells)==14
    assert all(v[2]==0 for v in d._test_cells.values())
    assert [c.args[0].name for c in d.set_param_display.call_args_list]==['OUTPUT_LEVEL','DISTORT_LEVEL']


def test_raw_transport_still_needs_both_session_and_exact_action_permits():
    d=fake();d.guard=AxeFxIII.guard;d.outp=Mock()
    frame=serial.row_fixture.select(1,1)
    with serial.execution(d,serial.ROUTE) as session:
        with pytest.raises(PermissionError):AxeFxIII._send(d,frame)
        session.failed=True;session.frame=tuple(frame)
        with pytest.raises(PermissionError):AxeFxIII._send(d,frame)
        d._approved_frame=tuple(frame);AxeFxIII._send(d,frame)
        d._edit_target=323
        with pytest.raises(PermissionError):AxeFxIII._send(d,frame)
    assert d.outp.send.call_count==1 and d._serial_session is None


def test_completed_sequence_cannot_continue_into_detached_row2():
    d=fake(True)
    with serial.execution(d,serial.ROUTE) as session:
        session.index=41
        frame,before,after=serial.row_fixture.steps()[41]
        with pytest.raises(PermissionError):session.write(frame,before,after)
    d._write.assert_not_called()


def test_failed_parameter_consumes_review_and_preserves_no_automatic_store():
    d=fake(True);p=plan(d,True);reviews=tone_review.Reviews()
    initial=tone_review.snapshot(d,include_nam=False)
    prepared=reviews.prepare(d,p,initial)
    d.set_param_display.side_effect=lambda *args:SetResult(False,'mismatch',None,None)
    result=reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    assert not result['ok'] and result['skipped']>0 and d._serial_session is None
    with pytest.raises(ValueError):reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    d.read_nam_slot.assert_not_called();d.store_preset.assert_not_called()


def test_stale_review_is_readonly_and_missing_mute_does_not_consume_valid_review():
    d=fake(True);p=plan(d,True);reviews=tone_review.Reviews()
    prepared=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    with pytest.raises(PermissionError):reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=False)
    assert reviews.pending is not None
    d._test_bulk[58][1]=1
    with pytest.raises(ValueError):reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


@pytest.fixture
def http(monkeypatch):
    d=fake(True)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False})
    monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None)
    monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock(side_effect=lambda *args,**kw:dict(**kw['validate'](with_goals(design())),backend='cli',model='synthetic'))
    monkeypatch.setattr(server.planner,'plan',ask)
    server._afx3_tone_reviews.clear()
    with TestClient(server.app) as client:yield client,d,ask
    server._afx3_tone_reviews.clear()


def test_http_serial_plan_review_and_send_do_not_read_nam(http):
    client,d,ask=http
    body=dict(prompt='Maak een warme crunch met delay en chorus',expected_preset=322,scenes=1,mode='serial')
    result=client.post('/api/axefx3/plan',json=body)
    assert result.status_code==200,result.text
    prepared=result.json()
    assert prepared['mode']=='serial' and prepared['target']['nam'] is None
    assert ask.call_count==1 and 'FW33 serial template' in ask.call_args.kwargs['system']
    assert len(prepared['required_route'])==14
    d.set_param_display.assert_not_called();d._write.assert_not_called()
    assert client.post('/api/axefx3/send',json=dict(token=prepared['token'],target_confirmed=True,external_audio_muted=False)).status_code==409
    sent=client.post('/api/axefx3/send',json=dict(token=prepared['token'],target_confirmed=True,external_audio_muted=True))
    assert sent.status_code==200 and sent.json()['ok'],sent.text
    d.read_nam_slot.assert_not_called();d.store_preset.assert_not_called()


def test_http_serial_state_is_not_dependent_on_nam_memory(http):
    client,d,ask=http
    response=client.get('/api/axefx3/state')
    assert response.status_code==200,response.text
    result=response.json()
    assert result['serial_build_supported'] and result['nam'] is None and len(result['route'])==14
    assert len(result['route_blocks'])==14
    assert result['route_blocks'][0]==dict(label='Input 1',channel='A',bypassed=False)
    d.read_nam_slot.assert_not_called();d._write.assert_not_called();ask.assert_not_called()


@pytest.mark.parametrize('field,value',[('scenes',2),('nam_slot',1),('wah_source','External 1'),('source_kind','rig')])
def test_http_incompatible_serial_options_are_rejected_before_ai(http,field,value):
    client,d,ask=http
    body=dict(prompt='test serial',expected_preset=322,scenes=1,mode='serial')
    body[field]=value
    response=client.post('/api/axefx3/plan',json=body)
    if field in ('scenes','wah_source'):
        assert response.status_code==200 and response.json()['needs_clarification']
        assert 'token' not in response.json() and 'actions' not in response.json()
    else:
        assert response.status_code==409
    ask.assert_not_called();d._write.assert_not_called();d.read_nam_slot.assert_not_called()


@pytest.mark.parametrize('fault',['scene','moved','different_route'])
def test_http_incompatible_current_state_is_rejected_without_wasting_ai_call(http,fault):
    client,d,ask=http
    if fault=='scene':d.current_scene.return_value=2
    if fault=='moved':d._test_cells[2,1]=d._test_cells.pop((1,1))
    if fault=='different_route':
        d._test_cells.clear();d._test_blocks.clear();d._test_bulk.clear()
        for i,eid in enumerate(fw33_profile.NAM_ROUTE,1):
            d._test_cells[3,i]=(eid,False,8 if i>1 else 0)
            d._test_blocks[eid]=shared.BlockStatus(eid,False,0,4)
            d._test_bulk[eid]=[0]*72
    assert client.post('/api/axefx3/plan',json=dict(prompt='test',expected_preset=322,scenes=1,mode='serial')).status_code==409
    ask.assert_not_called();d._write.assert_not_called();d.read_nam_slot.assert_not_called()

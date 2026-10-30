import copy
import json
import threading
from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3 import planning, tone_review, executor
from devices.axefx3.registry import Registry
from fm9.device import SetResult
from fm9.protocol import GridCell, BlockStatus
from tests.scene_intent_fixtures import with_goals

REAL_PLAN = server.planner.plan


def extra_config():
    return dict(drive=dict(active=True,drive=6,tone=4,mix=100,level=2),
        compressor=dict(active=True,threshold=-30,ratio=4,attack_ms=5,release_ms=250,mix=75,level=-12),
        geq=dict(active=True,gains=[-3]*10,level=-6),
        peq=dict(active=True,bands=[dict(frequency_hz=v,gain=-3) for v in (200,400,800,1600,3200)],level=-6))


def test_optional_existing_effects_compile_without_model_reset_or_insertion(dev,design):
    route=[37,118,46,58,62,50,54,70,66,42]
    for scene in design['scenes']:
        scene['wah']=False;scene.update(extra_config())
    plan=planning.compile_design(dev.reg,design,route,4)
    extras=[a for a in plan['actions'] if a.get('block') in ('FUZZ','COMP','GEQ','PEQ')]
    assert not any(a['kind'] in ('set_type','add_block') for a in extras)
    for f in ('FUZZ','COMP','GEQ','PEQ'):
        assert [a['value'] for a in extras if a['kind']=='set_channel' and a['block']==f]==[0,1,2,3]
        assert [a['bypassed'] for a in extras if a['kind']=='set_bypass' and a['block']==f]==[True,False]*4
    assert len([a for a in extras if a['kind']=='set_param'])==32*4
    for scene in design['scenes']:
        for key in extra_config():scene.pop(key)
    preserved=planning.compile_design(dev.reg,design,route,4)
    assert preserved['required_route']==plan['required_route']
    assert not any(a.get('block') in ('FUZZ','COMP','GEQ','PEQ') for a in preserved['actions'])


def test_optional_captured_model_choices_precede_voicing_and_explicit_final_level(dev,design):
    route=[37,118,46,58,62,50,54,70,66,42]
    for scene in design['scenes']:
        scene['wah']=False;scene.update(extra_config())
        scene['drive']['model']='T808 Mod'
        scene['compressor']['model']='Classic VCA Compressor'
    plan=planning.compile_design(dev.reg,design,route,4)
    for family,name in [('FUZZ','T808 Mod'),('COMP','Classic VCA Compressor')]:
        actions=[a for a in plan['actions'] if a.get('block')==family]
        types=[i for i,a in enumerate(actions) if a['kind']=='set_type']
        assert len(types)==4
        for i in types:
            assert actions[i]['type_name']==name
            assert actions[i-1]['kind']=='set_bypass' and actions[i-1]['bypassed'] is True
            assert actions[i-2]['kind']=='set_channel'
            tail=actions[i+1:]
            end=next(j for j,a in enumerate(tail) if a['kind']=='set_bypass')
            assert any(a.get('param')==family+'_LEVEL' for a in tail[:end])
    design['scenes'][0]['drive']['model']='FAS Boost'
    with pytest.raises(ValueError):planning.compile_design(dev.reg,design,route,4)
    dev._write.assert_not_called()


@pytest.mark.parametrize('existing',[True,False])
def test_new_drive_comp_compile_adds_models_and_bypasses_unrequested_scenes(dev,design,existing):
    route=[37,58,62,70,66,42] if existing else []
    for s in design['scenes']:s['wah']=False
    configs=extra_config()
    design['scenes'][0].update({k:configs[k] for k in ('drive','compressor')})
    plan=planning.compile_design(dev.reg,design,route,4)
    assert plan['required_route'][:4]==['Input 1','Drive 1','Compressor 1','Amp 1']
    for family,name in [('FUZZ','T808 OD'),('COMP','Modern VCA Compressor')]:
        actions=[a for a in plan['actions'] if a.get('block')==family]
        assert len([a for a in actions if a['kind']=='add_block'])==1
        assert [a['type_name'] for a in actions if a['kind']=='set_type']==[name]
        assert [a['value'] for a in actions if a['kind']=='set_channel']==[0,1,2,3]
        assert [a['bypassed'] for a in actions if a['kind']=='set_bypass']==[True,False,True,True,True]
    assert plan['design']['scenes'][0]['drive']['model']=='T808 OD'
    assert plan['design']['scenes'][0]['compressor']['model']=='Modern VCA Compressor'
    assert not any(a['kind']=='add_block' and a.get('block') in ('GEQ','PEQ') for a in plan['actions'])
    if not existing:executor.prepare(dev,plan['actions'],plan['required_route'],324)


@pytest.mark.parametrize('bad',['missing','post_drive','pre_eq','boost','drive_level','bands','q','nan','bool'])
def test_optional_effects_fail_closed_without_write(dev,design,bad):
    route=[37,118,46,58,62,50,54,70,66,42]
    for s in design['scenes']:s['wah']=False
    design['scenes'][0].update(extra_config())
    if bad=='missing':route.remove(50)
    if bad=='post_drive':route.remove(118);route.insert(4,118)
    if bad=='pre_eq':route.remove(50);route.insert(1,50)
    if bad=='boost':design['scenes'][0]['geq']['gains'][0]=1
    if bad=='drive_level':design['scenes'][0]['drive']['level']=6
    if bad=='bands':design['scenes'][0]['peq']['bands'].pop()
    if bad=='q':design['scenes'][0]['peq']['bands'][0]['q']=1
    if bad=='nan':design['scenes'][0]['compressor']['ratio']=float('nan')
    if bad=='bool':design['scenes'][0]['drive']['drive']=True
    with pytest.raises(ValueError):planning.compile_design(dev.reg,design,route,4)
    dev._write.assert_not_called()


@pytest.fixture
def design():
    return dict(name='AI-Test',summary='Four distinct scenes',amp_model='Brit 800 2204 High',
        cab_left=dict(bank=2,slot=28),cab_right=None,
        scenes=[dict(name=name,amp=dict(gain=gain,bass=4,mid=6,treble=5,master=5,
            depth=2,presence=4,level=-15),wah=i in (0,3),
            delay=dict(active=i in (0,3),time_ms=280+i*30,feedback=20,mix=15),
            reverb=dict(active=True,time_s=1.2,mix=8))
            for i,(name,gain) in enumerate(zip(['Intro','Verse','Heavy','Lead'],[2,4,5.5,6.2]))])


@pytest.fixture
def dev():
    d=Mock()
    d.reg=Registry('32.06');d.reg.import_cab_names('U1.0028 Test Greenback','user')
    d._lock=threading.RLock()
    d.current_preset.return_value=(324,'Empty');d.current_scene.return_value=1
    d.firmware_label.return_value='32.06'
    d.read_grid.return_value=[];d.status_dump.return_value=[]
    d.read_modifier.side_effect=lambda slot:[0]*25
    d.scene_name.side_effect=lambda n:(n,f'Scene {n}')
    d.bulk_read.side_effect=lambda eid:[1]*100
    d.edit_session.side_effect=lambda **kw:nullcontext()
    d.build_route.side_effect=lambda route,actions: build_route(d,route)
    d.set_param_display.return_value=SetResult(True,'verified',5,6)
    d.set_model.return_value=SetResult(True,'verified','old','new')
    d.set_cab.return_value=SetResult(True,'verified',None,28)
    d.bind_pedal_control.return_value=SetResult(True,'verified',None,12)
    d.set_scene.side_effect=lambda value:value
    d.set_channel.side_effect=lambda eid,value:value
    d.set_bypass.side_effect=lambda eid,value:value
    d.rename_preset.side_effect=lambda name:(324,name)
    d.rename_scene.side_effect=lambda number,name:(number,name)
    return d


def build_route(dev,route):
    ids=executor.route_guard.route_ids(route,dev.reg)
    dev.read_grid.return_value=[GridCell(2,i,e,False,8 if i else 0) for i,e in enumerate(ids)]
    dev.status_dump.return_value=[BlockStatus(e,False,0,4) for e in ids]
    return SetResult(True,'built',None,ids)


def test_compilation_names_channels_final_levels_cab_mixer_and_user_controller(dev,design):
    plan=planning.compile_design(dev.reg,design,[],4,'External 2')
    assert plan['name']=='AI-Test'
    assert plan['cab_choices']==[dict(side='IR1',name='Test Greenback',
        position='USER 1 slot 28',wire_bank=2,wire_ordinal=27)]
    actions=plan['actions']
    assert [a['value'] for a in actions if a['kind']=='set_channel' and a['block']=='DISTORT']==[0,1,2,3]
    assert [a['value'] for a in actions if a.get('param')=='DISTORT_DRIVE']==[2,4,5.5,6.2]
    assert all(a['value']==0 for a in actions if a.get('param') in ('WAH_LEVEL','DELAY_LEVEL','REVERB_LEVEL'))
    assert [a['value'] for a in actions if a.get('param','').startswith('CABINET_MUTE')]==[0,1,1,1]
    assert actions[-1]==dict(kind='bind_controller',block='WAH',instance=1,source='External 2',auto_engage='Fast Pos')
    assert not any(a['kind'] in ('store','select_preset') for a in actions)
    executor.prepare(dev,actions,plan['required_route'],324)


@pytest.mark.parametrize('bad',['cab','model','level','feedback','scenes','extra','nan','bool','controller'])
def test_invalid_design_refused_without_device_write(dev,design,bad):
    source=None
    if bad=='cab':design['cab_left']['slot']=29
    if bad=='model':design['amp_model']='Imaginary amp'
    if bad=='level':design['scenes'][0]['amp']['level']=1
    if bad=='feedback':design['scenes'][0]['delay']['feedback']=101
    if bad=='scenes':design['scenes'].pop()
    if bad=='extra':design['actions']=[{'kind':'store'}]
    if bad=='nan':design['scenes'][0]['amp']['gain']=float('nan')
    if bad=='bool':design['scenes'][0]['amp']['gain']=True
    if bad=='controller':source='CC6'
    with pytest.raises((ValueError,KeyError)):
        planning.compile_design(dev.reg,design,[],4,source)
    dev._write.assert_not_called()


def test_dual_ir_is_explicit_with_moderate_mix_levels(dev,design):
    dev.reg.import_cab_names('F1.0001 Factory Test','factory')
    design['cab_right']=dict(bank=0,slot=1)
    actions=planning.compile_design(dev.reg,design,[],4)['actions']
    assert [a['cab_side'] for a in actions if a['kind']=='set_cab']==['left','right']
    assert [a['value'] for a in actions if a.get('param','').startswith('CABINET_MUTE')]==[0,0,1,1]
    assert all(a['value']==-6 for a in actions if a.get('param','').startswith('CABINET_LEVEL'))


@pytest.mark.parametrize('mode', ['Off', 'Fast Pos', None])
def test_user_controls_auto_engage_not_ai(dev,design,mode):
    plan=planning.compile_design(dev.reg,design,[],4,'External 1',mode)
    assert plan['actions'][-1]['auto_engage']==mode
    assert plan['controller']==dict(source='External 1',auto_engage=mode)
    if mode=='Fast Pos':
        assert any('scene met Wah uit' in warning for warning in plan['warnings'])
    elif mode is None:
        assert any('niet door dit ontwerp vastgesteld' in warning for warning in plan['warnings'])
    else:
        assert plan['warnings']==['Geen vastgelegde klankdoelen in dit oudere ontwerp.']
    assert [a['bypassed'] for a in plan['actions'] if a['kind']=='set_bypass'
            and a['block']=='WAH']==[True,False,True,True,False]
    executor.prepare(dev,plan['actions'],plan['required_route'],324)
    dev._write.assert_not_called()


def test_no_source_preserves_binding_and_warns_instead_of_inventing_one(dev,design):
    plan=planning.compile_design(dev.reg,design,[],4,None,'Off')
    assert not any(a['kind']=='bind_controller' for a in plan['actions'])
    assert plan['controller']==dict(source=None,auto_engage=None)
    assert any('geen nieuwe Wah-controller' in warning for warning in plan['warnings'])


def test_unknown_auto_engage_refused(dev,design):
    with pytest.raises(ValueError,match='Auto Engage'):
        planning.compile_design(dev.reg,design,[],4,'External 1','Slow Pos')
    dev._write.assert_not_called()


def test_existing_route_does_not_add_or_remove_blocks(dev,design):
    route=[37,95,58,62,70,66,42]
    plan=planning.compile_design(dev.reg,design,route,4,'External 1')
    assert not any(a['kind']=='add_block' for a in plan['actions'])
    assert plan['actions'][-1]['instance']==2
    with pytest.raises(ValueError,match='compatible serial'):
        planning.compile_design(dev.reg,design,[37,58,62,102,42],4)


def test_dry_empty_build_reserves_voiced_bypassed_delay_for_later_adjustments(dev,design):
    design['scenes']=design['scenes'][:1]
    design['scenes'][0]['wah']=False
    design['scenes'][0]['delay']['active']=False
    plan=planning.compile_design(dev.reg,design,[],1)
    assert plan['required_route']==['Input 1','Amp 1','Cab 1','Delay 1','Reverb 1','Output 1']
    delay=[a for a in plan['actions'] if a.get('block')=='DELAY']
    assert delay[0]==dict(kind='add_block',block='DELAY',instance=1)
    assert [a['bypassed'] for a in delay if a['kind']=='set_bypass']==[True,True]
    assert [a['value'] for a in delay if a.get('param')=='DELAY_LEVEL']==[0]
    assert {a['param'] for a in delay if a['kind']=='set_param'}=={
        'DELAY_TIME','DELAY_FEED','DELAY_MIX','DELAY_LEVEL'}
    result=executor.execute(dev,plan['actions'],plan['required_route'],
        expected_preset=324,external_audio_muted=True)
    assert result['ok'] and not result['stored']
    dev.store_preset.assert_not_called()
    # A later request can activate the existing reserve, without another ADD.
    design['scenes'][0]['delay']['active']=True
    later=planning.compile_design(dev.reg,design,[37,58,62,70,66,42],1)
    assert not any(a['kind']=='add_block' for a in later['actions'])
    assert [a['bypassed'] for a in later['actions'] if a['kind']=='set_bypass'
            and a['block']=='DELAY']==[True,False]
    executor.prepare(dev,later['actions'],later['required_route'],324)


def test_reserving_delay_does_not_rebuild_existing_dry_routes(dev,design):
    design['scenes']=design['scenes'][:1]
    design['scenes'][0]['delay']['active']=False
    plan=planning.compile_design(dev.reg,design,[37,94,58,62,66,42],1,'External 1')
    assert not any(a.get('block')=='DELAY' or a['kind']=='add_block' for a in plan['actions'])
    design['scenes'][0]['delay']['active']=True
    with pytest.raises(ValueError,match='Automatic insertion is not verified'):
        planning.compile_design(dev.reg,design,[37,94,58,62,66,42],1,'External 1')
    dev._write.assert_not_called()


def test_active_ambience_delay_before_cab_is_refused_without_moving_blocks(dev,design):
    for route in ([37,94,70,58,62,66,42], [37,94,58,70,62,66,42]):
        with pytest.raises(ValueError,match='ambience delay must follow Cab'):
            planning.compile_design(dev.reg,design,route,4,'External 1')
    for scene in design['scenes']:
        scene['delay']['active']=False
    plan=planning.compile_design(dev.reg,design,[37,94,70,58,62,66,42],4,'External 1')
    assert plan['required_route']==['Input 1','Wah 1','Delay 1','Amp 1','Cab 1','Reverb 1','Output 1']
    assert not any(a['kind']=='add_block' for a in plan['actions'])
    assert all(a['bypassed'] for a in plan['actions'] if a['kind']=='set_bypass' and a['block']=='DELAY')
    dev._write.assert_not_called()


@pytest.fixture
def chorus_support(monkeypatch):
    # Only the delegated, verified model/control facts are mocked. The real
    # executor still resolves every non-Chorus action. No device I/O occurs.
    original_target = planning.models.target
    original_roster = planning.models.roster
    original_resolve = executor.resolve
    def target(reg, family, eid, name):
        if family == 'CHORUS':
            if reg.firmware != '32.06' or eid not in range(78,82) or name != 'Analog Stereo':
                raise ValueError('Unverified Chorus model')
            return 3
        return original_target(reg,family,eid,name)
    def roster(reg, family, *, selectable=False):
        if family == 'CHORUS':
            return {'3':'Analog Stereo'} if reg.firmware == '32.06' else {}
        return original_roster(reg,family,selectable=selectable)
    def resolve(reg, action):
        if action.get('block') != 'CHORUS':
            return original_resolve(reg,action)
        family,eid = reg.resolve_block('CHORUS',action['instance'])
        if action['kind'] == 'set_type':
            target(reg,family,eid,action['type_name'])
        if action['kind'] == 'set_param':
            bounds = {'CHORUS_RATE':(.1,10), 'CHORUS_DEPTH':(0,100),
                      'CHORUS_MIX':(0,100), 'CHORUS_LEVEL':(0,0)}
            lo,hi = bounds[action['param']]
            assert lo <= action['value'] <= hi
        return executor.Resolved(action,family,eid)
    monkeypatch.setattr(planning.models,'target',target)
    monkeypatch.setattr(planning.models,'roster',roster)
    monkeypatch.setattr(executor,'resolve',resolve)


def test_chorus_full_design_channels_voicing_and_serial_insertion(dev,design,chorus_support):
    for i,scene in enumerate(design['scenes']):
        scene['chorus']=dict(active=i != 1,rate_hz=.8+i,depth=40+i,mix=20+i)
    for current in ([],[37,94,58,62,70,66,42]):
        plan=planning.compile_design(dev.reg,design,current,4)
        assert plan['required_route']==[
            'Input 1','Wah 1','Amp 1','Cab 1','Chorus 1','Delay 1','Reverb 1','Output 1']
        chorus=[a for a in plan['actions'] if a.get('block')=='CHORUS']
        assert chorus[0]==dict(kind='add_block',block='CHORUS',instance=1)
        assert sum(a['kind']=='add_block' for a in chorus)==1
        for i,scene in enumerate(design['scenes']):
            config=scene['chorus']
            assert chorus[1+i*8:1+(i+1)*8]==[
                dict(kind='set_channel',block='CHORUS',instance=1,value=i),
                dict(kind='set_bypass',block='CHORUS',instance=1,bypassed=True),
                dict(kind='set_type',block='CHORUS',instance=1,type_name='Analog Stereo'),
                *[dict(kind='set_param',block='CHORUS',instance=1,param='CHORUS_'+key,value=value)
                  for key,value in [('RATE',config['rate_hz']),('DEPTH',config['depth']),
                                    ('MIX',config['mix']),('LEVEL',0)]],
                dict(kind='set_bypass',block='CHORUS',instance=1,bypassed=not config['active'])]
        assert not any(a['kind']=='clear' for a in plan['actions'])
    dev._write.assert_not_called()


def test_omitted_chorus_preserves_existing_instance_without_actions(dev,design):
    design['scenes'][0]['chorus']=None
    plan=planning.compile_design(dev.reg,design,[37,94,58,62,79,70,66,42],4)
    assert 'Chorus 2' in plan['required_route']
    assert not any(a.get('block')=='CHORUS' for a in plan['actions'])


def test_existing_chorus_is_reused_only_for_configured_scenes(dev,design,chorus_support):
    design['scenes'][2]['chorus']=dict(active=False,rate_hz=1,depth=30,mix=10)
    plan=planning.compile_design(dev.reg,design,[37,94,58,62,78,70,66,42],4)
    chorus=[a for a in plan['actions'] if a.get('block')=='CHORUS']
    assert len(chorus)==8 and all(a['instance']==1 for a in chorus)
    assert chorus[0]['value']==2 and chorus[-1]['bypassed'] is True
    assert not any(a['kind']=='add_block' for a in plan['actions'])


def test_new_chorus_is_bypassed_in_unrequested_scenes(dev,design,chorus_support):
    design['scenes'][2]['chorus']=dict(active=True,rate_hz=.3,depth=25,mix=20)
    for route in ([],[37,94,58,62,70,66,42]):
        plan=planning.compile_design(dev.reg,design,route,4)
        chorus=[a for a in plan['actions'] if a.get('block')=='CHORUS']
        assert len(chorus)==15
        assert chorus[1:3]==[
            dict(kind='set_channel',block='CHORUS',instance=1,value=0),
            dict(kind='set_bypass',block='CHORUS',instance=1,bypassed=True)]
        assert chorus[-2:]==[
            dict(kind='set_channel',block='CHORUS',instance=1,value=3),
            dict(kind='set_bypass',block='CHORUS',instance=1,bypassed=True)]
        assert sum(a['kind']=='set_type' for a in chorus)==1


@pytest.mark.parametrize('field,value',[
    ('rate_hz',0),('rate_hz',10.1),('depth',-1),('depth',101),
    ('mix',-1),('mix',101),('rate_hz',float('nan')),('depth',float('inf')),
    ('mix',True),('rate_hz','1'),('active',1)])
def test_unsafe_chorus_config_refused(dev,design,field,value):
    config=dict(active=True,rate_hz=1,depth=40,mix=20)
    config[field]=value
    design['scenes'][0]['chorus']=config
    with pytest.raises(ValueError):
        planning.compile_design(dev.reg,design,[],4)
    dev._write.assert_not_called()


def test_chorus_model_and_pre_delay_order_fail_closed(dev,design,chorus_support):
    design['scenes'][0]['chorus']=dict(active=True,rate_hz=1,depth=40,mix=20)
    for route in ([37,94,70,58,62,66,42],[37,94,58,70,62,66,42],
                  [37,94,58,62,70,78,66,42]):
        with pytest.raises(ValueError,match='no block is moved'):
            planning.compile_design(dev.reg,design,route,4)
    design['chorus_model']='Invented Chorus'
    with pytest.raises(ValueError):
        planning.compile_design(dev.reg,design,[],4)


def test_reference_exposes_only_available_chorus_facts(dev,chorus_support):
    ref=json.loads(planning.reference(dev.reg))
    assert ref['chorus']['models']==['Analog Stereo']
    assert 'rate_hz' in planning.SYSTEM and 'percent' in planning.SYSTEM
    unsupported=Registry('unknown')
    assert json.loads(planning.reference(unsupported))['chorus']==dict(models=[],controls=[])


def test_chorus_design_resolves_against_native_dependencies(dev,design):
    if not planning.models.roster(dev.reg,'CHORUS',selectable=True):
        pytest.skip('Main-agent verified Chorus model dependency is not available yet')
    design['scenes'][0]['chorus']=dict(active=True,rate_hz=.8,depth=40,mix=20)
    plan=planning.compile_design(dev.reg,design,[],4)
    executor.prepare(dev,plan['actions'],plan['required_route'],324)
    controls=json.loads(planning.reference(dev.reg))['chorus']['controls']
    assert [(c['name'],c['pid']) for c in controls]==[
        ('CHORUS_RATE',2),('CHORUS_DEPTH',4),('CHORUS_MIX',10),('CHORUS_LEVEL',11)]
    dev._write.assert_not_called()


@pytest.fixture
def api(dev,design,monkeypatch):
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',dev.reg,dev,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False})
    monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server,'_settings_lock',threading.Lock())
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None)
    monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock(side_effect=lambda *args,**kw:dict(**kw['validate'](with_goals(design)),backend='cli',model='test'))
    monkeypatch.setattr(server.planner,'plan',ask)
    server._afx3_tone_reviews.clear()
    with TestClient(server.app) as client:yield client,ask
    server._afx3_tone_reviews.clear()


BODY=dict(prompt='Four bluesrock scenes',expected_preset=324,scenes=4,wah_source='External 1')


def test_existing_core_effects_reach_http_review_and_executor(api,dev,design):
    from devices.axefx3 import tone_controls
    client,ask=api
    route=['Input 1','Drive 1','Compressor 1','Amp 1','Cab 1','GEQ 1','PEQ 1','Delay 1','Reverb 1','Output 1']
    build_route(dev,route)
    for s in design['scenes']:
        s['wah']=False;s.update(extra_config())
    by_eid={eid:[0]*(4*stride) for eid,stride in tone_controls.LAYOUTS.values()}
    for c in range(4):by_eid[50][c*20+15]=4
    dev.bulk_read.side_effect=lambda eid:by_eid.get(eid,[1]*100)
    proposal=client.post('/api/axefx3/plan',json={**BODY,'wah_source':None})
    assert proposal.status_code==200,proposal.text
    data=proposal.json()
    assert data['required_route']==route
    assert data['design']['scenes'][0]['drive']['level']==2
    reference=json.loads(ask.call_args.args[2])
    assert reference['existing_effects']['existing_blocks_only']
    assert len(reference['existing_effects']['controls']['GEQ'])==11
    dev.set_param_display.assert_not_called()
    result=client.post('/api/axefx3/send',json=dict(token=data['token'],target_confirmed=True,external_audio_muted=True))
    assert result.status_code==200,result.text
    assert result.json()['ok'] and not result.json()['stored']
    assert sum(c.args[0].family in tone_controls.LAYOUTS for c in dev.set_param_display.call_args_list)==128
    dev.store_preset.assert_not_called()


@pytest.mark.parametrize('mode', ['Off', 'Fast Pos', None])
def test_auto_engage_api_choice_survives_review_and_execution(api,dev,mode):
    client,ask=api
    response=client.post('/api/axefx3/plan',json={**BODY,'wah_auto_engage':mode})
    assert response.status_code==200,response.text
    plan=response.json()
    assert plan['controller']['auto_engage']==mode
    assert plan['actions'][-1]['auto_engage']==mode
    assert f'Wah Auto Engage: {mode or "preserve"}' in ask.call_args.args[0]
    dev.bind_pedal_control.assert_not_called()
    sent=client.post('/api/axefx3/send',json=dict(token=plan['token'],
        target_confirmed=True,external_audio_muted=True))
    assert sent.json()['ok']
    assert dev.bind_pedal_control.call_args.args==(94,12,mode)
    dev.store_preset.assert_not_called()


def test_invalid_auto_engage_api_choice_never_calls_ai(api,dev):
    client,ask=api
    assert client.post('/api/axefx3/plan',json={**BODY,'wah_auto_engage':'invented'}).status_code==422
    ask.assert_not_called();dev.edit_session.assert_not_called()


def test_whole_text_review_send_route_uses_afx3_and_no_fm9_executor(api,dev,monkeypatch):
    client,ask=api
    generic=Mock(side_effect=AssertionError('FM9 executor reached'))
    monkeypatch.setattr(server,'run_action',generic)
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    proposal=response.json();assert proposal['target']['preset']==324
    dev.edit_session.assert_not_called();dev.build_route.assert_not_called()
    send=dict(token=proposal['token'],target_confirmed=True,external_audio_muted=True)
    result=client.post('/api/axefx3/send',json=send)
    assert result.status_code==200,result.text
    assert result.json()['ok'] and not result.json()['stored']
    assert dev.bind_pedal_control.call_args.args==(94,12,'Fast Pos')
    assert client.post('/api/axefx3/send',json=send).status_code==409
    generic.assert_not_called();dev.store_preset.assert_not_called()
    assert ask.call_args.kwargs['system'].startswith(planning.SYSTEM)


@pytest.mark.parametrize('change',['preset','scene','bulk','catalogue','connection'])
def test_stale_tone_review_is_refused_before_build(api,dev,change,monkeypatch):
    client,_=api
    if change=='bulk':build_route(dev,['Input 1','Wah 1','Amp 1','Cab 1','Delay 1','Reverb 1','Output 1'])
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    if change=='preset':dev.current_preset.return_value=(325,'Other')
    if change=='scene':dev.current_scene.return_value=2
    if change=='bulk':dev.bulk_read.side_effect=lambda eid:[2]*100
    if change=='catalogue':dev.reg.import_cab_names('U1.0028 Changed','user')
    if change=='connection':monkeypatch.setattr(server,'_context',server._default_context)
    result=client.post('/api/axefx3/send',json=dict(token=response.json()['token'],target_confirmed=True,external_audio_muted=True))
    assert result.status_code==409
    dev.edit_session.assert_not_called()


def test_changed_state_during_ai_invalidates_plan(api,dev):
    client,ask=api
    original=ask.side_effect
    def changed(*args,**kw):
        result=original(*args,**kw);dev.current_scene.return_value=2;return result
    ask.side_effect=changed
    assert client.post('/api/axefx3/plan',json=BODY).status_code==409
    assert server._afx3_tone_reviews.pending is None
    dev.edit_session.assert_not_called()


def test_cross_origin_and_missing_consent_refused(api,dev):
    client,ask=api
    assert client.post('/api/axefx3/plan',json=BODY,headers={'Origin':'https://elsewhere.invalid'}).status_code==403
    ask.assert_not_called()
    response=client.post('/api/axefx3/plan',json=BODY)
    send=dict(token=response.json()['token'],target_confirmed=True,external_audio_muted=False)
    assert client.post('/api/axefx3/send',json=send).status_code==409
    dev.edit_session.assert_not_called()


def test_unsupported_audio_and_missing_cabs_never_call_ai(api,dev):
    client,ask=api
    assert client.post('/api/axefx3/plan',json={**BODY,'prompt':'https://example.com/song'}).status_code==409
    dev.reg.cab_catalog.names={}
    assert client.post('/api/axefx3/plan',json=BODY).status_code==409
    ask.assert_not_called()


def test_first_verification_failure_skips_remaining_plan(api,dev):
    client,_=api
    proposal=client.post('/api/axefx3/plan',json=BODY).json()
    dev.set_param_display.return_value=SetResult(False,'Mismatch',0,None)
    result=client.post('/api/axefx3/send',json=dict(token=proposal['token'],target_confirmed=True,external_audio_muted=True)).json()
    assert not result['ok'] and result['skipped']>0
    dev.bind_pedal_control.assert_not_called()


def test_auto_backend_refused_instead_of_falling_back(api,monkeypatch):
    client,ask=api
    monkeypatch.delenv('PLANNER_BACKEND')
    monkeypatch.setattr(server.planner,'_env',lambda name,*args:'')
    result=client.post('/api/axefx3/plan',json=BODY)
    assert result.status_code==409 and 'explicit AI' in result.text
    ask.assert_not_called()


def test_expiry_and_regeneration_invalidate_old_tokens(api,dev,monkeypatch):
    client,_=api
    first=client.post('/api/axefx3/plan',json=BODY).json()
    second=client.post('/api/axefx3/plan',json=BODY).json()
    body=dict(token=first['token'],target_confirmed=True,external_audio_muted=True)
    assert client.post('/api/axefx3/send',json=body).status_code==409
    reviews=server._afx3_tone_reviews
    # send clears pending before checking its deadline; capture that deadline.
    expired=reviews.pending['expires']+1
    monkeypatch.setattr(reviews,'clock',lambda:expired)
    assert client.post('/api/axefx3/send',json={**body,'token':second['token']}).status_code==409
    dev.edit_session.assert_not_called()


def test_gig_lock_and_overlapping_ai_never_send(api,dev,monkeypatch):
    client,ask=api
    monkeypatch.setitem(server._gig_mode,'on',True)
    assert client.post('/api/axefx3/plan',json=BODY).status_code==423
    ask.assert_not_called()
    monkeypatch.setitem(server._gig_mode,'on',False)
    original=ask.side_effect
    def nested(*args,**kw):
        assert client.post('/api/axefx3/plan',json=BODY).status_code==409
        return original(*args,**kw)
    ask.side_effect=nested
    assert client.post('/api/axefx3/plan',json=BODY).status_code==200
    assert ask.call_count==1
    dev.edit_session.assert_not_called()


def test_native_binding_failure_stops_without_store(api,dev):
    client,_=api
    proposal=client.post('/api/axefx3/plan',json=BODY).json()
    dev.bind_pedal_control.return_value=SetResult(False,'Allocation not verified',None,None)
    result=client.post('/api/axefx3/send',json=dict(token=proposal['token'],target_confirmed=True,external_audio_muted=True)).json()
    assert not result['ok'] and 'Allocation' in result['results'][-1]['detail']
    dev.store_preset.assert_not_called()


def test_actual_planner_entrypoint_compiles_selected_backend_design(api,dev,design,monkeypatch):
    client,_=api
    runner=Mock(return_value=(with_goals(design),'selected-model'))
    monkeypatch.setattr(server.planner,'plan',REAL_PLAN)
    monkeypatch.setattr(server.planner,'_RUNNERS',{'cli':runner})
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['backend']=='cli' and result['model']=='selected-model'
    assert len(result['actions'])>100 and result['plan_quality']=='actions'
    assert runner.call_args.args[3].startswith(planning.SYSTEM)
    assert 'scene_goals' in runner.call_args.args[3]
    assert result['actions'][-1]['kind']=='bind_controller'
    dev.edit_session.assert_not_called()


def test_full_modifier_capacity_checked_before_any_route_write(dev,design,monkeypatch):
    from devices.axefx3 import pedal_control
    plan=planning.compile_design(dev.reg,design,[],4,'External 1')
    monkeypatch.setattr(pedal_control,'entries',lambda device:[
        dict(effect_id=58,param_id=n+1,source=12) for n in range(32)])
    with pytest.raises(ValueError,match='Insufficient'):
        executor.execute(dev,plan['actions'],plan['required_route'],
                         expected_preset=324,external_audio_muted=True)
    dev.edit_session.assert_not_called();dev.build_route.assert_not_called()


def test_empty_preset_system_records_are_not_bulk_parameter_blocks(api,dev):
    client,_=api
    dev.status_dump.return_value=[BlockStatus(200,False,0,1),BlockStatus(201,False,0,1)]
    dev.bulk_read.side_effect=AssertionError('System records must not get a bulk query')
    assert client.get('/api/axefx3/state').status_code==200
    result=client.post('/api/axefx3/plan',json=BODY)
    assert result.status_code==200,result.text
    dev.bulk_read.assert_not_called();dev.edit_session.assert_not_called()

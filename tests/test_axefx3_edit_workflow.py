"""Offline app contract with real extracted writers and independent fake ports.

No provider call or physical MIDI. The production application is unchanged.
"""
from copy import deepcopy
import json
import threading

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

import server
from devices.axefx3.readonly_adapter import AxeFxIII, ReadOnlyRegistry
from devices.axefx3.amp_writer import AmpWriter, AmpReadbackError
from devices.axefx3.name_writer import NameWriter, NameReadbackError
from devices.axefx3.edit_workflow import EditWorkflow, proposal
from fm9.device import ReadOnly
from tests.test_axefx3_amp_writer import AmpPorts, GAIN3_3
from tests.test_axefx3_name_writer import NamedPorts


GAIN = dict(kind='set_param', block='amp', instance=1, param='DISTORT_DRIVE', value=3.3)
MID = dict(kind='set_param', block='DISTORT', param='DISTORT_MID', value=5.6)
NAME = dict(kind='rename_preset', type_name='Exact Name')
SCENE = dict(kind='rename_scene', block='SCENE', value=8, type_name='Final Scene')


@pytest.fixture(autouse=True)
def forbid_physical_ports(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *a,**k:pytest.fail('Physical MIDI is forbidden in workflow tests'))


@pytest.fixture(params=['amp', 'name'])
def setup(request, monkeypatch):
    # Forbid real ports even if this test fixture accidentally loses injection.
    monkeypatch.setattr('fm9.midi_transport.open_ports', lambda *a, **k: pytest.fail('Native MIDI opened'))
    ports = AmpPorts() if request.param == 'amp' else NamedPorts()
    dev = (AmpWriter if request.param == 'amp' else NameWriter)((ports.inp, ports.outp))
    monkeypatch.setattr('devices.axefx3.amp_writer.time.sleep', lambda _: None)
    state = dict(selected=dev, gig=False, now=0)
    flow = EditWorkflow(selected=lambda: state['selected'], host_lock=threading.Lock(),
                        gig_locked=lambda: state['gig'], fingerprint=server.plan_digest,
                        clock=lambda: state['now'])
    action = GAIN if request.param == 'amp' else NAME
    yield flow, dev, ports, state, action
    dev.close()


def prepared(setup, action=None):
    flow, dev, ports, state, default = setup
    return flow.prepare([deepcopy(action or default)], expected_preset=320, expected_scene=1)


def payload(view):
    return {k:deepcopy(view[k]) for k in ('token','actions','plan_digest','expected_preset','expected_scene')}


def arm(setup, action=None):
    flow = setup[0]
    view = prepared(setup, action)
    view = flow.review(**payload(view))
    view = flow.confirm(**payload(view), target_confirmed=True, external_audio_muted=True)
    return view


def test_real_writers_follow_review_confirm_send_once(setup):
    flow, dev, ports, state, action = setup
    view = prepared(setup)
    assert view['stage']=='plan' and not view['can_send'] and not ports.writes
    assert view['change']['executable'] is False and not view['undo_available']
    assert view['plan_digest']==server.plan_digest([server.Action(**view['actions'][0])])
    view = flow.review(**payload(view))
    assert view['stage']=='review' and not view['can_send'] and not ports.writes
    view = flow.confirm(**payload(view), target_confirmed=True, external_audio_muted=True)
    assert view['can_send'] and not ports.writes
    # Caller-mutated display objects are not the opaque writer review.
    view['change']['after']='not the native edit'
    result=flow.send(**payload(view), target_confirmed=True, external_audio_muted=True)
    assert result['verified'] and result['sent'] and not result['stored']
    assert result['results'][0]['ok'] and not result['undo_available']
    assert len(ports.writes)==1
    if action['kind']=='set_param':assert ports.writes==[GAIN3_3]
    else:assert ports.preset_name=='Exact Name'
    with pytest.raises(ReadOnly):flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert len(ports.writes)==1
    assert not dev.capabilities().verifies_writes and not dev.capabilities().can_rename


@pytest.mark.parametrize('action',[MID, SCENE])
def test_mid_and_explicit_other_scene_name(setup,action):
    if (action['kind']=='set_param') != (type(setup[1]) is AmpWriter):
        with pytest.raises(ReadOnly):prepared(setup,action)
        assert not setup[2].writes
        return
    view=arm(setup,action)
    out=setup[0].send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert out['verified'] and len(setup[2].writes)==1
    if action['kind']=='rename_scene':assert setup[2].names[7]=='Final Scene'


@pytest.mark.parametrize('method',['confirm','send'])
def test_cannot_skip_review_or_confirm(setup,method):
    view=prepared(setup)
    with pytest.raises(ReadOnly):
        getattr(setup[0],method)(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert not setup[2].writes


@pytest.mark.parametrize('stage',['review','confirm','send'])
@pytest.mark.parametrize('fault',['token','digest','action','reason','preset','scene','whole_rig'])
def test_every_stage_rejects_changed_or_missing_authority(setup,stage,fault):
    flow=setup[0];view=prepared(setup)
    if stage in ('confirm','send'):view=flow.review(**payload(view))
    if stage=='send':view=flow.confirm(**payload(view),target_confirmed=True,external_audio_muted=True)
    request=payload(view)
    if fault=='token':request['token']='other'
    elif fault=='digest':request['plan_digest']='other'
    elif fault=='action':request['actions'][0]['type_name']='Changed'
    elif fault=='reason':request['actions'][0]['reason']='changed after review'
    elif fault=='preset':request['expected_preset']=321
    elif fault=='scene':request['expected_scene']=2
    elif fault=='whole_rig':request['whole_rig']=True
    if stage!='review':request.update(target_confirmed=True,external_audio_muted=True)
    with pytest.raises((ReadOnly,ValueError)):getattr(flow,stage)(**request)
    assert not setup[2].writes
    # A failed send/transition is not a reusable authorization.
    with pytest.raises(ReadOnly):flow.review(**payload(view))


@pytest.mark.parametrize('stage',['confirm','send'])
@pytest.mark.parametrize('field',['target_confirmed','external_audio_muted'])
@pytest.mark.parametrize('value',[False,1,'yes',None])
def test_target_and_mute_are_exact_explicit_booleans(setup,stage,field,value):
    flow=setup[0];view=prepared(setup);view=flow.review(**payload(view))
    if stage=='send':view=flow.confirm(**payload(view),target_confirmed=True,external_audio_muted=True)
    flags=dict(target_confirmed=True,external_audio_muted=True);flags[field]=value
    with pytest.raises(ReadOnly):getattr(flow,stage)(**payload(view),**flags)
    assert not setup[2].writes


@pytest.mark.parametrize('stage',['review','confirm','send'])
@pytest.mark.parametrize('change',['selected','closed','uncertain','gig','preset','scene'])
def test_reconnection_navigation_and_gig_disarm_the_plan(setup,stage,change):
    flow,dev,ports,state,_=setup;view=prepared(setup)
    if stage in ('confirm','send'):view=flow.review(**payload(view))
    if stage=='send':view=flow.confirm(**payload(view),target_confirmed=True,external_audio_muted=True)
    if change=='selected':state['selected']=object()
    elif change=='closed':dev._closed=True
    elif change=='uncertain':dev._uncertain=True
    elif change=='gig':state['gig']=True
    elif change=='preset':ports.preset=321
    elif change=='scene':ports.scene=1
    flags={} if stage=='review' else dict(target_confirmed=True,external_audio_muted=True)
    with pytest.raises(ReadOnly):getattr(flow,stage)(**payload(view),**flags)
    assert not ports.writes


def test_expiry_discard_replacement_and_native_baseline_recheck(setup):
    flow,dev,ports,state,action=setup
    view=arm(setup);state['now']=8
    with pytest.raises(ReadOnly):flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert not ports.writes
    state['now']=0;view=arm(setup);flow.discard()
    with pytest.raises(ReadOnly):flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    view=arm(setup)
    with pytest.raises(ValueError):flow.prepare([dict(kind='store',value=320)],expected_preset=320,expected_scene=1)
    with pytest.raises(ReadOnly):flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    view=arm(setup)
    if type(dev) is AmpWriter:ports.amp[3]+=1
    else:ports.names[1]='Changed on unit'
    with pytest.raises(ReadOnly):flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert not ports.writes


def test_native_review_deadline_is_not_extended_by_confirm(setup):
    flow,dev,ports,state,_=setup;view=prepared(setup)
    state['now']=flow._pending.review._expires
    with pytest.raises(ReadOnly):flow.review(**payload(view))
    assert not ports.writes


def test_deadline_crossed_during_context_read_cannot_arm(setup,monkeypatch):
    flow,dev,ports,state,_=setup;view=prepared(setup)
    real=dev.current_scene
    def slow():
        result=real();state['now']=flow._pending.review._expires if flow._pending else expiry
        return result
    expiry=flow._pending.review._expires
    monkeypatch.setattr(dev,'current_scene',slow)
    with pytest.raises(ReadOnly,match='expired'):flow.review(**payload(view))
    assert not ports.writes and flow._pending is None


def test_connection_owned_native_review_cannot_be_replaced_by_another_flow(setup):
    flow,dev,ports,state,_=setup;view=arm(setup)
    edit=flow._pending.edit
    (dev.review_amp if type(dev) is AmpWriter else dev.review_name)(edit)
    with pytest.raises(ReadOnly):flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert not ports.writes


def test_native_noop_is_verified_without_claiming_a_write(setup):
    flow,dev,ports,state,_=setup
    action=dict(GAIN,value=3.0) if type(dev) is AmpWriter else dict(NAME,type_name='Read Test')
    view=arm(setup,action)
    out=flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert out['verified'] and out['sent'] is False and not out['stored']
    assert not ports.writes


def test_simultaneous_send_cannot_duplicate_the_write(setup):
    flow,dev,ports,state,_=setup;view=arm(setup)
    barrier=threading.Barrier(2);results=[]
    def run():
        barrier.wait()
        try:
            results.append(flow.send(**payload(view),target_confirmed=True,external_audio_muted=True))
        except ReadOnly:
            results.append('consumed')
    workers=[threading.Thread(target=run) for _ in range(2)]
    for t in workers:t.start()
    for t in workers:t.join(3)
    assert all(not t.is_alive() for t in workers)
    assert len(ports.writes)==1 and len(results)==2 and results.count('consumed')==1


def test_edit_plan_for_another_connection_cannot_supply_consent(setup):
    flow,dev,ports,state,_=setup;view=arm(setup)
    other=EditWorkflow(selected=lambda:dev,host_lock=threading.Lock(),gig_locked=lambda:False,
                       fingerprint=server.plan_digest)
    with pytest.raises(ReadOnly):other.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert not ports.writes


@pytest.mark.parametrize('behavior',['raise','ignore','identity'])
def test_uncertain_outcome_is_preserved_without_resend_or_undo(setup,behavior):
    flow,dev,ports,state,_=setup;view=arm(setup);ports.behavior=behavior
    error=AmpReadbackError if type(dev) is AmpWriter else NameReadbackError
    with pytest.raises(error):flow.send(**payload(view),target_confirmed=True,external_audio_muted=True)
    assert len(ports.writes)==1 and dev._uncertain
    with pytest.raises(ReadOnly):prepared(setup)
    assert len(ports.writes)==1


def test_ordinary_readonly_adapter_cannot_be_armed(setup):
    flow,dev,ports,state,action=setup
    basic=AxeFxIII((ports.inp,ports.outp),chassis='mk2');state['selected']=basic
    try:
        with pytest.raises(ReadOnly):prepared(setup)
        assert not ports.writes
    finally:basic.close()


@pytest.mark.parametrize('action',[
    dict(kind='store',value=320),dict(kind='set_type',block='amp',type_name='Brit 800'),
    dict(kind='add_block',block='amp'),dict(kind='set_channel',block='amp',value=1),
    dict(kind='set_scene',value=2),dict(kind='bind_pedal',block='wah',pedal=1),
    dict(GAIN,value=True),dict(GAIN,value=0),dict(GAIN,value=9),dict(GAIN,value=3.31),
    dict(GAIN,instance=True),dict(GAIN,instance=2),dict(GAIN,param='DISTORT_LEVEL'),
    dict(GAIN,param=[]),dict(GAIN,bank=2),dict(GAIN,channel='B'),
    dict(SCENE,value=1.2),dict(SCENE,value=True),dict(NAME,type_name=' x '),
])
def test_unsupported_or_ambiguous_actions_fail_before_io(action):
    with pytest.raises((ValueError,TypeError)):proposal([action],320)


def test_mixed_or_empty_batches_are_not_partially_accepted():
    for actions in ([],[GAIN,MID],[NAME,GAIN],None):
        with pytest.raises(ValueError):proposal(actions,320)


def test_fake_http_steps_use_real_writers_but_production_routes_remain_readonly(setup):
    flow,dev,ports,state,action=setup
    app=FastAPI()
    # Harness routes only, not registration in the real application.
    @app.post('/prepare')
    def prepare(body:dict):
        return flow.prepare(**body)
    @app.post('/step/{stage}')
    def step(stage:str,body:dict):
        if stage not in ('review','confirm','send'):raise HTTPException(404)
        return getattr(flow,stage)(**body)
    with TestClient(app) as client:
        view=client.post('/prepare',json=dict(actions=[action],expected_preset=320,expected_scene=1)).json()
        for stage in ('review','confirm','send'):
            body=payload(view)
            if stage!='review':body.update(target_confirmed=True,external_audio_muted=True)
            response=client.post('/step/'+stage,json=body)
            assert response.status_code==200
            view=response.json()
        assert view['verified'] and len(ports.writes)==1
    # Preparation must not register a new production endpoint or enable its executor.
    assert not any('edit_workflow' in getattr(route.endpoint,'__module__','')
                   for route in server.app.routes if hasattr(route,'endpoint'))


def test_production_plan_and_apply_do_not_gain_writer_access(setup,monkeypatch):
    flow,dev,ports,state,action=setup
    prepared(setup)
    monkeypatch.setattr(server,'detected_devices',lambda:[dict(kind='axefx3')])
    monkeypatch.setattr(server,'_selected_kind',dict(kind='axefx3'))
    monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_gig_mode',dict(on=False))
    monkeypatch.setattr(server.planner,'plan',lambda *a,**k:pytest.fail('Provider reached'))
    # No TestClient lifespan: no real bus watcher or native startup.
    with server.use_device('axefx3',dev,ReadOnlyRegistry(),'Axe-Fx III'):
        client=TestClient(server.app)
        try:
            response=client.post('/api/plan',json=dict(prompt='More gain'))
            assert response.status_code==409 and response.json()['read_only']
            response=client.post('/api/apply',json=dict(actions=[action],expected_preset=320))
            assert response.status_code in (200,409)
            if response.status_code==200:
                assert not any(r.get('ok') for r in response.json()['results'])
        finally:client.close()
    assert not ports.writes

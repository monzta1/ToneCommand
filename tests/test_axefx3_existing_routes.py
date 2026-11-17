"""Registered preserving-edit stages, independent fake ports and selected AI."""
from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

import server
from devices.axefx3 import edit_routes, existing_routes
from devices.axefx3.adapter import ReadOnlyRegistry
from devices.axefx3.existing_scalar import ExistingEditor
from fm9.device import ReadOnly
from tests.test_axefx3_existing_scalar import ExistingPorts, design


@pytest.fixture
def api(monkeypatch):
    for flag in ('TONECOMMAND_AXEFX3_REVIEWED_AMP','TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5'):
        monkeypatch.delenv(flag,raising=False)
    monkeypatch.setenv(existing_routes.FLAG,'1')
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *a,**k:pytest.fail('No real MIDI'))
    monkeypatch.setattr('devices.axefx3.scene_observation.time.sleep',lambda _:None)
    monkeypatch.setattr(existing_routes.ai_settings,'apply_to_env',lambda:None)
    monkeypatch.setattr(existing_routes.planner,'_env',lambda name:'openai' if name=='PLANNER_BACKEND' else '')
    monkeypatch.setattr(existing_routes.planner,'candidates',lambda:['openai'])
    monkeypatch.setattr(server,'_gig_mode',{'on':False})
    monkeypatch.setattr(server,'_plan_revisions',{})
    ports=ExistingPorts();dev=ExistingEditor((ports.inp,ports.outp))
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',ReadOnlyRegistry(),dev,'Axe-Fx III'))
    state=server._afx3_existing_workflow
    state.update(scan=None,plan=None,generation=state['generation']+1)
    calls=[]
    def selected_ai(prompt,device,reference,**kwargs):
        calls.append(dict(prompt=prompt,reference=reference,schema=kwargs['schema']))
        return dict(kwargs['validate'](dict(design=design(),question=None)),backend='openai',model='fake')
    monkeypatch.setattr(existing_routes.planner,'plan',selected_ai)
    monkeypatch.setattr(server,'run_action',lambda *a,**k:pytest.fail('No generic executor'))
    client=TestClient(server.app)
    yield client,dev,ports,calls
    client.close();dev.close();state.update(scan=None,plan=None,generation=state['generation']+1)


def scan(client):
    response=client.post('/api/axefx3/existing/scan',json=dict(expected_preset=323,expected_scene=1,target_confirmed=True,external_audio_muted=True))
    assert response.status_code==200,response.text
    return response.json()


def propose(client):
    result=scan(client)
    response=client.post('/api/axefx3/existing/plan',json=dict(scan_token=result['scan_token'],prompt='Add body and controlled Gain/Mid without replacing the existing rig.'))
    assert response.status_code==200,response.text
    return response.json()


def payload(view,consent=False):
    body={key:view[key] for key in ('token','plan_digest','expected_preset','expected_scene')}
    if consent:body.update(target_confirmed=True,external_audio_muted=True)
    return body


def arm(client):
    view=propose(client)
    response=client.post('/api/axefx3/existing/review',json=payload(view));assert response.status_code==200,response.text
    response=client.post('/api/axefx3/existing/confirm',json=payload(response.json(),True));assert response.status_code==200,response.text
    return response.json()


def test_selected_ai_and_normal_stages_send_only_after_final_confirmation(api):
    client,dev,ports,calls=api
    assert client.get('/api/axefx3/existing/state').json()['available']
    view=arm(client);assert not ports.writes
    assert calls and 'observed_state' not in calls[0]['reference'] and 'bulk' not in calls[0]['reference']
    assert '$defs' in calls[0]['schema'] and '$defs' not in calls[0]['schema']['properties']['design']['anyOf'][0]
    out=client.post('/api/axefx3/existing/send',json=payload(view,True))
    assert out.status_code==200,out.text
    assert out.json()['verified'] and out.json()['sent']==4 and out.json()['scene_maps_verified']==8
    assert not out.json()['stored'] and len(ports.writes)==4
    assert client.post('/api/axefx3/existing/send',json=payload(view,True)).status_code==409
    assert len(ports.writes)==4


@pytest.mark.parametrize('step',['confirm','send'])
def test_cannot_skip_stages(api,step):
    client,dev,ports,_=api;view=propose(client)
    assert client.post('/api/axefx3/existing/'+step,json=payload(view,True)).status_code==409
    assert not ports.writes


@pytest.mark.parametrize('field,value',[('target_confirmed',False),('external_audio_muted',False),
    ('target_confirmed',1),('external_audio_muted','yes')])
def test_strict_confirmation_before_scalar_writes(api,field,value):
    client,dev,ports,_=api;view=arm(client);body=payload(view,True);body[field]=value
    assert client.post('/api/axefx3/existing/send',json=body).status_code in (409,422)
    assert not ports.writes


@pytest.mark.parametrize('step',['scan','plan','review','confirm','send','discard'])
def test_cross_origin_refuses_before_io(api,step):
    client,dev,ports,_=api
    bodies=dict(scan=dict(expected_preset=323,expected_scene=1,target_confirmed=True,external_audio_muted=True),
        plan=dict(scan_token='a'*43,prompt='More body'),discard={})
    body=bodies.get(step,dict(token='a'*43,plan_digest='b'*64,expected_preset=323,expected_scene=1))
    before=len(ports.sent)
    assert client.post('/api/axefx3/existing/'+step,json=body,headers={'Origin':'https://foreign.example'}).status_code==403
    assert len(ports.sent)==before and not ports.recalls


@pytest.mark.parametrize('flag',['TONECOMMAND_AXEFX3_REVIEWED_AMP','TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5'])
def test_conflicting_modes_do_not_promote_existing_connection(api,monkeypatch,flag):
    client,dev,ports,_=api;monkeypatch.setenv(flag,'1')
    assert not client.get('/api/axefx3/existing/state').json()['configured']
    with pytest.raises(ReadOnly):edit_routes.connect('mk2')
    assert not ports.writes


def test_scope_question_is_answered_with_original_request_and_empty_execution(api,monkeypatch):
    client,dev,ports,calls=api
    captured=[]
    def provider(prompt,device,reference,**kwargs):
        captured.append(prompt)
        raw=dict(design=None,question='Keep this adjustment to Gain and Mid only?') if len(captured)==1 else dict(design=design(),question=None)
        return dict(kwargs['validate'](raw),backend='openai',model='fake')
    monkeypatch.setattr(existing_routes.planner,'plan',provider)
    scanned=scan(client);base=dict(scan_token=scanned['scan_token'],prompt='Make this existing preset broader.')
    out=client.post('/api/axefx3/existing/plan',json=base)
    assert out.status_code==200 and out.json()['question'] and not ports.writes
    assert server._afx3_existing_workflow['plan'] is None
    out=client.post('/api/axefx3/existing/plan',json=dict(base,answer='Yes, preserve the effects and adjust Gain and Mid.'))
    assert out.status_code==200,out.text
    assert out.json()['stage']=='plan' and 'Make this existing preset broader.' in captured[-1]
    assert 'Keep this adjustment to Gain and Mid only?' in captured[-1] and 'Yes, preserve' in captured[-1]
    assert not ports.writes


def test_one_bounded_same_provider_repair_for_invalid_design(api,monkeypatch):
    client,dev,ports,_=api;calls=[]
    def provider(prompt,device,reference,**kwargs):
        calls.append(prompt);raw=design()
        if len(calls)==1:raw['changes'][0]['value']=9.
        return dict(kwargs['validate'](dict(design=raw,question=None)),backend='openai',model='fake')
    monkeypatch.setattr(existing_routes.planner,'plan',provider)
    propose(client);assert len(calls)==2 and 'Correct the rejected proposal' in calls[-1] and not ports.writes


def test_transport_failure_does_not_retry_or_fall_back(api,monkeypatch):
    client,dev,ports,_=api;calls=[]
    def fail(*a,**k):calls.append(True);raise RuntimeError('Provider unavailable')
    monkeypatch.setattr(existing_routes.planner,'plan',fail)
    scanned=scan(client)
    out=client.post('/api/axefx3/existing/plan',json=dict(scan_token=scanned['scan_token'],prompt='More body.'))
    assert out.status_code==409 and len(calls)==1 and not ports.writes


def test_discard_during_provider_call_cannot_restore_a_stale_review(api,monkeypatch):
    client,dev,ports,_=api
    def provider(*a,**kwargs):
        assert client.post('/api/axefx3/existing/discard',json={}).status_code==200
        return dict(kwargs['validate'](dict(design=design(),question=None)),backend='openai',model='fake')
    monkeypatch.setattr(existing_routes.planner,'plan',provider)
    scanned=scan(client)
    out=client.post('/api/axefx3/existing/plan',json=dict(scan_token=scanned['scan_token'],prompt='More body.'))
    assert out.status_code==409 and server._afx3_existing_workflow['plan'] is None and not ports.writes


def test_back_to_review_revokes_confirmation_and_allows_fresh_arm(api):
    client,dev,ports,_=api;view=arm(client)
    out=client.post('/api/axefx3/existing/review',json=payload(view));assert out.status_code==200,out.text
    assert out.json()['stage']=='review' and not out.json()['can_send']
    assert client.post('/api/axefx3/existing/send',json=payload(out.json(),True)).status_code==409
    assert not ports.writes


def test_gig_lock_and_other_pending_plan_refuse_before_scene_recalls(api,monkeypatch):
    client,dev,ports,_=api
    monkeypatch.setattr(server,'_gig_mode',{'on':True})
    before=len(ports.sent)
    out=client.post('/api/axefx3/existing/scan',json=dict(expected_preset=323,expected_scene=1,target_confirmed=True,external_audio_muted=True))
    assert out.status_code==409 and len(ports.sent)==before
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{'other':object()})
    assert not client.get('/api/axefx3/existing/state').json()['available']
    assert not ports.recalls and not ports.writes


@pytest.mark.parametrize('extra',[dict(frames=[[1,2]]),dict(actions=[]),dict(observed_state={}),dict(expected_preset=True)])
def test_scan_rejects_extra_or_coerced_authority_before_io(api,extra):
    client,dev,ports,_=api;before=len(ports.sent)
    body=dict(expected_preset=323,expected_scene=1,target_confirmed=True,external_audio_muted=True,**extra) if 'expected_preset' not in extra else dict(expected_scene=1,target_confirmed=True,external_audio_muted=True,**extra)
    assert client.post('/api/axefx3/existing/scan',json=body).status_code==422
    assert len(ports.sent)==before

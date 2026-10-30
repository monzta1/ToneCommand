"""Opt-in API lifecycle, isolation and AI clarification with no real ports."""
from copy import deepcopy
import threading
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from devices.axefx3 import tone_ui,beta5_core as core,design_dialogue
from tests.test_axefx3_beta5_core import design,reg,state


@pytest.fixture
def workspace(monkeypatch):
    monkeypatch.setenv('TONECOMMAND_BETA5_CORE','1')
    class Device:pass
    dev=Device();dev.reg=reg();dev._lock=threading.RLock();dev.outp=Mock()
    now=state();now.update(scene=1,variant='mk2',firmware=dev.reg.firmware,catalogs=[])
    read=Mock(side_effect=lambda _:deepcopy(now));monkeypatch.setattr(core,'snapshot',read)
    host=SimpleNamespace(_lock=threading.RLock(),_settings_lock=threading.Lock(),
        _gig_mode={'on':False},_plan_revisions={},_audition={'open':False},
        device_context=lambda:SimpleNamespace(kind='axefx3',adapter=dev))
    monkeypatch.setattr(tone_ui.ai_settings,'apply_to_env',lambda:None)
    monkeypatch.setenv('PLANNER_BACKEND','cli')
    monkeypatch.setattr(tone_ui.planner,'candidates',lambda:['cli'])
    ai=Mock(side_effect=lambda *a,**kw:kw['validate']({'proposal':design(),'clarification':None}))
    monkeypatch.setattr(tone_ui.planner,'plan',ai)
    app=FastAPI();tone_ui.register(app,host)
    with TestClient(app) as client:yield client,dev,now,host,ai


BODY=dict(prompt='One British crunch scene, AMP/CAB only.',expected_preset=327,scenes=1)


def test_current_opt_in_core_not_a_legacy_write_profile(workspace):
    client,dev,now,host,ai=workspace
    response=client.get('/api/axefx3/state');assert response.status_code==200,response.text
    data=response.json();assert data['beta5_core_supported'] and not data['profile']['write_supported']
    assert data['route']==list(tone_ui.beta5_core_plan.ROUTE)
    assert not data.get('navigation_supported') and not data.get('nam_selection_supported')
    assert dev.reg.params=={}


def test_plan_is_proposal_only_and_discard_invalidates_send(workspace):
    client,dev,now,host,ai=workspace
    response=client.post('/api/axefx3/plan',json=BODY);assert response.status_code==200,response.text
    proposal=response.json();assert proposal['mode']=='beta5-core' and proposal['token']
    dev.outp.send.assert_not_called()
    assert client.post('/api/axefx3/discard',json={}).status_code==200
    refused=client.post('/api/axefx3/send',json=dict(token=proposal['token'],external_audio_muted=True,target_confirmed=True))
    assert refused.status_code==409;dev.outp.send.assert_not_called()


@pytest.mark.parametrize('change',[{'scenes':2},{'mode':'nam'},{'wah_source':'External 2'},
    {'nam_query':'Search please'},{'nam_slot':250},{'source_kind':'rig'}])
def test_unsupported_structured_scope_is_not_silently_omitted(workspace,change):
    client,dev,now,host,ai=workspace
    response=client.post('/api/axefx3/plan',json={**BODY,**change})
    assert response.status_code==409;ai.assert_not_called();dev.outp.send.assert_not_called()


def test_real_ai_question_and_recorded_answer_do_not_authorize_writes(workspace):
    client,dev,now,host,ai=workspace
    q=dict(message='This experiment has no pedal-pitch setter.',questions=[dict(id='scope',text='Build AMP/CAB only instead?',suggestions=['Yes, AMP/CAB only'])])
    ai.side_effect=lambda *a,**kw:kw['validate'](dict(proposal=None,clarification=q))
    first=client.post('/api/axefx3/plan',json=BODY).json()
    assert first['needs_clarification'] and 'token' not in first
    ai.side_effect=lambda *a,**kw:kw['validate'](dict(proposal=design(),clarification=None))
    answer=client.post('/api/axefx3/plan',json=dict(**BODY,dialogue_token=first['dialogue_token'],answers=[dict(id='scope',text='Yes, AMP/CAB only')]))
    assert answer.status_code==200,answer.text
    assert answer.json()['token'] and 'Yes, AMP/CAB only' in ai.call_args.args[0]
    dev.outp.send.assert_not_called()


@pytest.mark.parametrize('mutation',['preset','catalogs','variant','modifiers'])
def test_stale_baseline_is_refused_without_transmission(workspace,mutation):
    client,dev,now,host,ai=workspace
    plan=client.post('/api/axefx3/plan',json=BODY).json()
    if mutation=='preset':now['preset'][0]=325
    elif mutation=='catalogs':now['catalogs']=[(2,0,'Changed name')]
    elif mutation=='variant':now['variant']='mk1'
    else:now['modifiers']=[[1]*25]
    refused=client.post('/api/axefx3/send',json=dict(token=plan['token'],external_audio_muted=True,target_confirmed=True))
    assert refused.status_code==409;dev.outp.send.assert_not_called()


def test_failed_native_write_is_one_attempt_consumed_and_connection_latched(workspace):
    client,dev,now,host,ai=workspace
    dev.outp.send.side_effect=OSError('Synthetic transport uncertainty')
    proposal=client.post('/api/axefx3/plan',json=BODY).json()
    sent=client.post('/api/axefx3/send',json=dict(token=proposal['token'],external_audio_muted=True,target_confirmed=True))
    assert sent.status_code==200 and sent.json()['ok'] is False
    assert dev.outp.send.call_count==1
    again=client.post('/api/axefx3/send',json=dict(token=proposal['token'],external_audio_muted=True,target_confirmed=True))
    assert again.status_code==409 and dev.outp.send.call_count==1
    count=ai.call_count
    assert client.post('/api/axefx3/plan',json=BODY).status_code==409
    assert ai.call_count==count


def test_gig_lock_prevents_even_proposal(workspace):
    client,dev,now,host,ai=workspace;host._gig_mode['on']=True
    assert client.post('/api/axefx3/plan',json=BODY).status_code==423
    ai.assert_not_called();dev.outp.send.assert_not_called()

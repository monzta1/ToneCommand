"""Capability-aware AI questions stay read-only and preserve user choices."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
import server
from devices.axefx3 import album_planning,design_dialogue,fw33_profile,pedal_control
from devices.axefx3 import pedal_fw33,request_intake,wah_voicing
from tests.scene_intent_fixtures import with_goals
from tests.test_axefx3_inherited_wah_planner import rig


def question(message):
    return dict(proposal=None,clarification=dict(message=message,
        questions=[dict(id='wah_choice',text=message,suggestions=[])]))


@pytest.fixture
def workspace(monkeypatch):
    dev,raw,records=rig(monkeypatch)
    raw['scene_count']=4
    raw['scene_layout']=album_planning.layout(raw)[:4]
    raw=with_goals(raw)
    for goal in raw['scene_goals']:
        if raw['scene_layout'][goal['scene']-1]['wah']:
            goal['required_features']=['wah_controller']
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',dev.reg,dev,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False})
    monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None)
    monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock()
    monkeypatch.setattr(server.planner,'plan',ask)
    server._afx3_tone_reviews.clear()
    try:
        with TestClient(server.app) as client:yield client,dev,ask,raw,records
    finally:
        server._afx3_tone_reviews.clear();server._afx3_tone_reviews.last_sent=None


def sequence(ask,*raw):
    replies=iter(raw)
    ask.side_effect=lambda *a,**kw:dict(**kw['validate'](deepcopy(next(replies))),backend='cli',model='test')


BODY=dict(prompt='Vier scenes met wah op external 2. Wah moet auto engaged worden.',
    mode='amp',scenes=4,expected_preset=322,wah_source=None,wah_auto_engage=None)


def test_contract_explicitly_releases_server_owned_binding_not_global_cc(workspace):
    _,dev,_,_,_=workspace
    facts=json.loads(album_planning.reference(dev.reg))['wah_controller']
    assert facts['executable'] and facts['allocation_executable']
    assert facts['sources']==['External 1','External 2']
    assert facts['auto_engage_modes']==['Off','Fast Pos']
    assert facts['binding_owner']=='server' and not facts['binding_in_design_schema']
    assert not facts['global_cc_mapping_executable'] and not facts['pitch_transposition_executable']
    for firmware,variant in [('32.06','mk2'),('33.01','mk2'),(fw33_profile.KEY,'mk1')]:
        blocked=wah_voicing.reference(SimpleNamespace(firmware=firmware,hardware_variant=variant))
        assert not blocked['executable'] and not blocked['sources']


def test_release_flags_still_gate_ai_reference(workspace,monkeypatch):
    _,dev,_,_,_=workspace
    monkeypatch.setattr(pedal_fw33,'RELEASED',False)
    assert not wah_voicing.reference(dev.reg)['executable']


@pytest.mark.parametrize('prompt,mode',[
    ('wah moet auto engaged worden op external 2','Fast Pos'),
    ('wah auto-engage on','Fast Pos'),
    ('wah op External 2, automatisch inschakelen','Fast Pos'),
    ('wah automatically engages on pedal movement','Fast Pos'),
    ('wah Auto Engage behouden',None),('wah zonder auto engage',None),
    ('wah auto engage off',None),('wah auto engage. auto engage behouden',None),
    ('wah auto engage Slow Pos',None),
    ('wah geen auto engage',None),('wah auto engage disabled',None),
    ('wah auto engage uitgeschakeld',None),('wah auto engage Med Pos',None),
    ('wah external 2',None)])
def test_text_inference_is_positive_and_unambiguous(prompt,mode):
    assert request_intake.explicit_wah_auto_engage(prompt)==mode


def test_inferred_external_auto_request_reaches_real_plan_validator(workspace):
    client,dev,ask,raw,_=workspace
    sequence(ask,dict(proposal=raw,clarification=None))
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    assert response.json()['controller']==dict(source='External 2',auto_engage='Fast Pos')
    facts=json.loads(ask.call_args.args[2])
    assert facts['wah_request']['new_binding']
    assert facts['wah_request']['effective_auto_engage']=='Fast Pos'
    assert ask.call_count==1
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called();dev.store_preset.assert_not_called()


def test_false_unsupported_question_is_self_checked_then_normal_review(workspace):
    client,dev,ask,raw,_=workspace
    sequence(ask,question('External 2 wordt niet ondersteund. Zonder wah verder?'),
        dict(proposal=raw,clarification=None))
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['token'] and not data.get('needs_clarification')
    assert data['controller']['source']=='External 2'
    assert ask.call_count==2 and 'CAPABILITY SELF-CHECK' in ask.call_args.args[0]
    assert any(a['kind']=='bind_controller' for a in data['actions'])
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called();dev.store_preset.assert_not_called()


def test_preserve_empty_does_not_silently_enable_auto_engage(workspace):
    client,dev,ask,raw,_=workspace
    sequence(ask,dict(proposal=raw,clarification=None))
    response=client.post('/api/axefx3/plan',json=dict(BODY,wah_source='External 2'))
    assert response.status_code==200,response.text
    assert response.json()['controller']==dict(source='External 2',auto_engage=None)
    facts=json.loads(ask.call_args.args[2])['wah_request']
    assert facts['preserve_without_binding'] and facts['effective_auto_engage']=='Off'
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called()


def test_explicit_form_off_and_source_win_over_text(workspace):
    client,dev,ask,raw,_=workspace
    sequence(ask,dict(proposal=raw,clarification=None))
    response=client.post('/api/axefx3/plan',json=dict(BODY,wah_source='External 1',wah_auto_engage='Off'))
    assert response.status_code==200,response.text
    assert response.json()['controller']==dict(source='External 1',auto_engage='Off')
    assert json.loads(ask.call_args.args[2])['wah_request']['effective_auto_engage']=='Off'
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called()


def test_existing_source_and_mode_are_evidence_not_ai_guesses(workspace):
    client,dev,ask,raw,records=workspace
    records[0]=pedal_control.default_words(94);records[0][0]=12;records[0][10]=6
    sequence(ask,dict(proposal=raw,clarification=None))
    response=client.post('/api/axefx3/plan',json=dict(BODY,wah_source='External 2'))
    assert response.status_code==200,response.text
    facts=json.loads(ask.call_args.args[2])['wah_request']
    assert facts['existing_binding']==dict(source='External 1',auto_engage='Fast Pos')
    assert facts['effective_source']=='External 2' and facts['effective_auto_engage']=='Fast Pos'
    assert not facts['new_binding']
    dev._write.assert_not_called()


def test_genuine_question_stays_a_question_and_records_answer_once(workspace):
    client,dev,ask,raw,_=workspace
    clarification=question('Er is geen bestaande koppeling. Behouden wordt Off. Toch behouden?')
    sequence(ask,clarification,clarification,dict(proposal=raw,clarification=None))
    body=dict(BODY,wah_source='External 2')
    response=client.post('/api/axefx3/plan',json=body)
    assert response.status_code==200,response.text
    data=response.json();assert data['needs_clarification'] and 'token' not in data
    assert ask.call_count==2
    assert len(data['dialogue_history'])==1
    answer=client.post('/api/axefx3/plan',json=dict(body,dialogue_token=data['dialogue_token'],
        answers=[dict(id='wah_choice',text='Ja behouden, geen automatische inschakeling.')]))
    assert answer.status_code==200,answer.text
    assert answer.json()['controller']['auto_engage'] is None
    assert ask.call_count==3 and 'geen automatische inschakeling' in ask.call_args.args[0]
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called();dev.store_preset.assert_not_called()


def test_self_check_is_bounded_even_if_ai_repeats_question():
    initial=dict(ai_question=question('Welke rol?')['clarification'])
    ask=Mock(return_value=deepcopy(initial))
    result=design_dialogue.review_question(ask,initial,'prompt','state','reference',validate=lambda raw:raw)
    assert result['ai_question']==initial['ai_question'] and result['question_self_checked']
    assert ask.call_count==1


def test_bad_proposal_is_repaired_without_asking_user_or_writing(workspace):
    client,dev,ask,raw,_=workspace
    bad=deepcopy(raw);bad['wah']['model']='Unverified Wah'
    sequence(ask,dict(proposal=bad,clarification=None),dict(proposal=raw,clarification=None))
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    assert response.json()['token'] and response.json()['controller']['source']=='External 2'
    assert ask.call_count==2 and 'DESIGN SELF-CORRECTION' in ask.call_args.args[0]
    assert 'Unverified Wah' in ask.call_args.args[0]
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called();dev.store_preset.assert_not_called()


def test_failed_correction_retains_resolved_scope_in_last_question(workspace):
    client,dev,ask,raw,_=workspace
    bad=deepcopy(raw);bad['wah']['model']='Unverified Wah'
    last=dict(message='De gevraagde extra functie is onbeschikbaar.',questions=[dict(id='other',text='Wil je deze extra functie uitstellen?')])
    replies=iter([dict(proposal=bad,clarification=None),dict(proposal=bad,clarification=None),last])
    ask.side_effect=lambda *a,**kw:dict(**kw['validate'](deepcopy(next(replies))),backend='cli',model='test')
    body=dict(BODY,prompt=BODY['prompt']+' high pitch toe down',resolution=dict(pitch_meaning='filter'))
    response=client.post('/api/axefx3/plan',json=body)
    assert response.status_code==200,response.text
    assert response.json()['needs_clarification'] and 'token' not in response.json()
    assert 'Unverified Wah' in response.json()['design_validation_issue']
    assert ask.call_count==3 and 'pitch meaning=filter' in ask.call_args.args[0]
    assert 'User-selected wah source: External 2' in ask.call_args.args[0]
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called();dev.store_preset.assert_not_called()


def test_transport_failure_does_not_trigger_design_repair_or_backend_fallback(workspace):
    client,dev,ask,_,_=workspace
    ask.side_effect=RuntimeError('Selected backend timed out')
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==409 and 'timed out' in response.text
    assert ask.call_count==1
    dev._write.assert_not_called();dev.bind_pedal_control.assert_not_called();dev.store_preset.assert_not_called()

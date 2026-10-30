"""Independent musical brief, actual parameter contrast and honest IR labels."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
import server
from devices.axefx3 import album_planning,scene_contract as quality,serial_build,tone_review,design_history
from tests.test_axefx3_album_build import device
from tests.test_axefx3_scene_counts import short_design


def brief():
    return dict(scenes=[dict(scene=n,role=f'Role {n}',target='A musical function for this scene',
        reference_scene=None if n==1 else 1 if n in (2,3) else 3,
        difference='either' if n==1 else 'effects' if n in (2,4) else 'base_tone',
        reason='A deliberate passage-appropriate difference, not another name',
        reuse_quote=None,required_features=[]) for n in range(1,5)])


def plan(monkeypatch):
    d=device(monkeypatch);raw=short_design(4)
    p=album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),4)
    return d,raw,p


def test_request_brief_is_complete_ordered_and_reference_safe():
    assert quality.validate(brief(),4,'four scenes')==brief()
    for mutate in ('count','self','future','first','quote','scope'):
        raw=brief()
        if mutate=='count':raw['scenes'].pop()
        if mutate=='self':raw['scenes'][1]['reference_scene']=2
        if mutate=='future':raw['scenes'][1]['reference_scene']=4
        if mutate=='first':raw['scenes'][0]['reference_scene']=1
        if mutate=='quote':raw['scenes'][3].update(difference='shared',reuse_quote='AI suggested a repeat')
        if mutate=='scope':raw['scenes'][3]['reuse_quote']='User mentioned a repeat'
        with pytest.raises(ValueError):quality.validate(raw,4,'four scenes')


def test_actual_parameter_changes_not_ai_goals_decide(monkeypatch):
    _,_,p=plan(monkeypatch)
    audit=quality.assess(p,brief())
    assert audit['rows'][1]['effects_changed'] and not audit['rows'][1]['base_changed']
    assert audit['rows'][2]['base_changed'] and audit['rows'][3]['effects_changed']
    assert not audit['exact_duplicates'] and not audit['audible_match_verified']
    assert audit['rows'][0]['cab_names']


@pytest.mark.parametrize('fake',['name','channel','level'])
def test_unapproved_copy_rejected_even_if_design_calls_it_reprise(monkeypatch,fake):
    d,raw,_=plan(monkeypatch)
    raw['scene_layout'][3]=dict(raw['scene_layout'][0],name='Reprise after design')
    if fake in ('channel','level'):
        raw['albums'][3]=deepcopy(raw['albums'][0]);raw['scene_layout'][3]['amp_channel']=3
        if fake=='level':raw['albums'][3]['amp']['level']=-24.
    p=album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),4)
    assert raw['scene_goals'][3]['distinction']=='shared'
    with pytest.raises(ValueError,match='identiek'):quality.assess(p,brief())
    assert quality.assess(p)['exact_duplicates']==[dict(scene=4,same_as=1)]
    d._write.assert_not_called()


def test_user_requested_reuse_allowed_and_explained(monkeypatch):
    d,raw,_=plan(monkeypatch)
    raw['scene_layout'][3]=dict(raw['scene_layout'][0],name='Return')
    p=album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),4)
    contract=brief();quote='Scene 4 must have the same sound as scene 1'
    contract['scenes'][3].update(reference_scene=1,difference='shared',reuse_quote=quote)
    contract=quality.validate(contract,4,quote)
    report=quality.assess(p,contract)
    assert report['rows'][3]['same_as']==[1] and report['rows'][3]['reuse_reason']
    d._write.assert_not_called()


def test_dry_chorus_cannot_fake_effect_contrast(monkeypatch):
    d,raw,_=plan(monkeypatch)
    raw['scene_layout'][1].update(delay=False,chorus=True)
    raw['chorus']['mix']=0.
    p=album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),4)
    with pytest.raises(ValueError,match='identiek'):quality.assess(p,brief())


def test_small_knob_changes_warn_without_claiming_hearing(monkeypatch):
    d,raw,_=plan(monkeypatch)
    raw['albums'][1]=deepcopy(raw['albums'][0]);raw['albums'][1]['amp']['mid']+=.2
    p=album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),4)
    audit=quality.assess(p,brief())
    assert audit['rows'][2]['small_variation'] and audit['warnings']
    assert not audit['audible_match_verified']


def test_cab_alias_and_equivalent_ir_mix_are_same_base():
    a=dict(base=dict(model='amp',amp=dict(gain=5.,level=-18),cab='Greenback'),effects={})
    b=deepcopy(a);b['base']['cab']=dict(irs=[dict(bank=1,slot=516,mode='normal',level_db=0,pan=0)])
    assert quality._signature(a)==quality._signature(b)
    b['base']['cab']['irs'][0]['pan']=70
    assert quality._base(a)==quality._base(b)
    assert quality._signature(a)!=quality._signature(b)


def test_flat_eq_and_cab_pan_cannot_fake_a_different_base_tone(monkeypatch):
    d,raw,p=plan(monkeypatch)
    a=dict(base=dict(model='amp',amp=dict(gain=5.,level=-18),cab='Greenback'),effects={})
    b=deepcopy(a);b['effects']['geq']=dict(active=True,gains=[0.]*10,level=0.,q=1.)
    assert quality._signature(a)==quality._signature(b)
    contract=brief();contract['scenes'][1]['difference']='base_tone'
    with pytest.raises(ValueError,match='amp/cab/voicing'):quality.assess(p,contract)
    d._write.assert_not_called()


def test_preamp_drive_level_is_not_confused_with_final_output_volume():
    a=dict(base=dict(model='amp',amp=dict(gain=5.,level=-18),cab='Greenback'),
        effects=dict(drive=dict(active=True,model='T808 Mod',gain=0.,tone=5.,level=1.,mix=100.)))
    b=deepcopy(a);b['effects']['drive']['level']=2.
    assert quality._base(a)!=quality._base(b)
    assert quality._signature(a)!=quality._signature(b)
    b=deepcopy(a);b['base']['amp']['level']=-24.
    assert quality._signature(a)==quality._signature(b)


def test_brief_features_are_mandatory_even_if_designer_drops_them(monkeypatch):
    _,_,p=plan(monkeypatch);contract=brief()
    contract['scenes'][0]['required_features']=['drive']
    assert not p['design']['scene_goals'][0].get('required_features')
    with pytest.raises(ValueError,match='vereist drive'):quality.assess(p,contract)


def test_wrong_cab_format_claim_rejected_but_unknown_names_not_guessed(monkeypatch):
    _,_,p=plan(monkeypatch)
    for cab in p['cab_choices']:cab['name']='2x12 Leggy 57'
    p['summary']='The chosen cabinet is a Leggy 4x12.'
    with pytest.raises(ValueError,match='Cab-omschrijving'):quality.assess(p)
    p['summary']='A 2x12 cabinet, not a 4x12.'
    quality.assess(p)


def test_cab_claim_is_checked_per_scene_not_only_against_the_whole_plan(monkeypatch):
    _,_,p=plan(monkeypatch)
    p['cab_choices'][0]['name']='2x12 Leggy 57'
    p['cab_choices'][1]['name']='4x12 Recto 57'
    p['design']['scene_goals'][0]['realization']='The chosen 4x12 cabinet gives this tone.'
    with pytest.raises(ValueError,match='Cab-omschrijving'):quality.assess(p)
    p['summary']='A 4x12 cabinet.'
    for cab in p['cab_choices']:cab['name']='User guitar IR without format metadata'
    quality.assess(p)


@pytest.fixture
def workspace(monkeypatch):
    d,raw,_=plan(monkeypatch)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None);monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock();monkeypatch.setattr(server.planner,'plan',ask)
    server._afx3_tone_reviews.clear()
    try:
        with TestClient(server.app) as client:yield client,d,ask,raw
    finally:
        server._afx3_tone_reviews.clear();server._afx3_tone_reviews.last_sent=None


BODY=dict(prompt='Four scenes for a complete song with useful tonal differences',expected_preset=322,mode='amp',scenes=4,scene_contract=True)


def sequence(ask,*replies):
    values=iter(replies)
    ask.side_effect=lambda *a,**kw:dict(**kw['validate'](deepcopy(next(values))),backend='cli',model='test')


def test_brief_precedes_design_and_is_not_replaced_by_design_goals(workspace):
    client,d,ask,raw=workspace
    sequence(ask,brief(),dict(proposal=raw,clarification=None))
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    audit=response.json()['scene_comparison']
    assert audit['contract']==brief() and not audit['exact_duplicates']
    assert 'models' not in json.loads(ask.call_args_list[0].args[2])
    assert json.loads(ask.call_args_list[1].args[2])['scene_contract']==brief()
    assert ask.call_count==2
    d._write.assert_not_called();d.store_preset.assert_not_called()


def test_copy_repairs_under_same_frozen_contract(workspace):
    client,d,ask,raw=workspace
    bad=deepcopy(raw);bad['scene_layout'][3]=dict(bad['scene_layout'][0],name='Cloned Outro')
    sequence(ask,brief(),bad,raw)
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    assert ask.call_count==3 and 'DESIGN SELF-CORRECTION' in ask.call_args.args[0]
    assert response.json()['scene_comparison']['contract']==brief()
    assert 'scene 4' in ask.call_args.args[0].lower()
    d._write.assert_not_called();d.store_preset.assert_not_called()


def test_wrong_cab_claim_is_repaired_using_real_selected_names(workspace):
    client,d,ask,raw=workspace
    irs=[dict(bank=1,slot=47,mode='normal' if i==0 else 'mute',level_db=0.,pan=0.) for i in range(4)]
    raw['albums'][0]['cab']=dict(irs=irs)
    raw['scene_goals'][0]['realization']='The selected 2x12 Leggy 57.'
    bad=deepcopy(raw);bad['scene_goals'][0]['realization']='The selected 4x12 Leggy 57.'
    sequence(ask,brief(),bad,raw)
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    assert ask.call_count==3
    assert response.json()['scene_comparison']['rows'][0]['cab_names']==['2x12 Leggy 57']
    d._write.assert_not_called()


def test_brief_question_has_no_review_token_or_actions(workspace):
    client,d,ask,_=workspace
    question=dict(proposal=None,clarification=dict(message='The outro role is unclear.',
        questions=[dict(id='outro',text='Moet het outro dezelfde klank hebben of een eigen variatie?')]))
    sequence(ask,question)
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    assert response.json()['needs_clarification'] and 'token' not in response.json()
    assert ask.call_count==1
    d._write.assert_not_called();d.store_preset.assert_not_called()


def test_brief_cannot_quote_its_own_system_or_question_as_user(workspace):
    client,d,ask,raw=workspace
    bad=brief();bad['scenes'][3].update(difference='shared',reference_scene=1,reuse_quote='Do not override these controller choices.')
    sequence(ask,bad,brief(),raw)
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    assert ask.call_count==3
    assert response.json()['scene_comparison']['contract']==brief()
    d._write.assert_not_called()


def test_brief_transport_failure_never_retries_or_changes_backend(workspace):
    client,d,ask,_=workspace;ask.side_effect=RuntimeError('Selected backend timed out')
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==409 and ask.call_count==1
    d._write.assert_not_called()


@pytest.mark.parametrize('audio',[False,True])
def test_successful_send_remembers_contract_and_resume_rechecks_it(monkeypatch,audio):
    d,_,p=plan(monkeypatch);p['scene_comparison']=quality.assess(p,brief())
    if audio:
        from tests.test_axefx3_audio_comparison import reading
        p['reference_measurements']=reading(url='https://private.invalid',file_name='private.wav')
    reviews=tone_review.Reviews();ready=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    result=reviews.send(d,ready['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'],result
    record=design_history.load(result['history']['id'])
    assert record['version']==3 and record['plan']['scene_contract']==brief()
    invalid=deepcopy(record);invalid['plan']['design']['scene_count']='4'
    with pytest.raises(ValueError):design_history.validate(invalid)
    if audio:
        assert 'url' not in record['plan']['reference_measurements']
        assert 'file_name' not in record['plan']['reference_measurements']
    fresh=tone_review.Reviews()
    resumed=fresh.resume(d,record['id'],expected_preset=322,target_confirmed=True,external_audio_muted=True)
    restored=fresh.refinement(d,resumed['refine_token'],tone_review.snapshot(d,include_nam=False))
    assert restored['scene_comparison']['contract']==brief()
    if audio:assert restored['reference_measurements']==record['plan']['reference_measurements']
    d.store_preset.assert_not_called()

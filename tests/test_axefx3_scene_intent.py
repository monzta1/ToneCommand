"""Musical intent checks use settings, not names or simulated hearing."""
from copy import deepcopy
import pytest
from pydantic import ValidationError
from devices.axefx3 import album_planning, album_build, scene_intent, tone_review, serial_build
from tests.test_axefx3_album_build import device, design
from tests.scene_intent_fixtures import with_goals
from unittest.mock import Mock
from fastapi.testclient import TestClient
import server


def compile(d, raw):
    return album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),8)


def goals():
    return with_goals(design())


def test_arbitrary_eight_scene_assignments_not_forced_album_pairs(monkeypatch):
    d=device(monkeypatch);raw=goals()
    amps=[0,1,2,3,0,2,1,3];cabs=[0,0,1,1,2,2,3,3]
    for item,a,c in zip(raw['scene_layout'],amps,cabs):
        item.update(amp_channel=a,cab_channel=c)
    p=compile(d,raw)
    album_build.validate_actions(d.reg,p['actions'],True)
    reviews=tone_review.Reviews();initial=tone_review.snapshot(d,include_nam=False)
    ready=reviews.prepare(d,p,initial)
    result=reviews.send(d,ready['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'],result
    for n,a,c in zip(range(1,9),amps,cabs):
        assert d._test_scenes[n][58].channel==a
        assert d._test_scenes[n][62].channel==c
    assert len(result['album_verification']['scene_fingerprints'])==8
    d.store_preset.assert_not_called()


@pytest.mark.parametrize('change',['name','level','delay'])
def test_promised_base_contrast_cannot_be_fake(monkeypatch,change):
    d=device(monkeypatch);raw=goals()
    raw['albums'][1]=deepcopy(raw['albums'][0])
    raw['scene_goals'][2].update(distinct_from=[1],distinction='base_tone')
    if change=='name':raw['scene_layout'][2]['name']='Totally Different'
    if change=='level':raw['albums'][1]['amp']['level']=-22.
    if change=='delay':raw['scene_layout'][2]['delay']=True
    with pytest.raises(ValueError,match='basisklank'):compile(d,raw)
    d._write.assert_not_called()


def test_small_eq_delta_warns_without_claiming_listening(monkeypatch):
    d=device(monkeypatch);raw=goals()
    raw['albums'][1]=deepcopy(raw['albums'][0]);raw['albums'][1]['amp']['mid']+=.2
    raw['scene_goals'][2].update(distinct_from=[1],distinction='base_tone')
    p=compile(d,raw)
    assert any('kleine knopverschillen' in w for w in p['warnings'])
    assert not p['scene_intent']['audible_match_verified']


def test_intentionally_shared_tones_are_allowed(monkeypatch):
    d=device(monkeypatch);raw=goals()
    raw['albums']=[deepcopy(raw['albums'][0]) for _ in range(4)]
    assert len(compile(d,raw)['scene_intent']['goals'])==8


def test_effect_contrast_checks_actual_scene_layout_not_legacy_role_names(monkeypatch):
    d=device(monkeypatch);raw=goals()
    raw['scene_layout'][1].update(delay=False,chorus=False)
    raw['scene_goals'][1].update(distinction='effects',distinct_from=[1])
    with pytest.raises(ValueError,match='actieve effectinstellingen'):compile(d,raw)
    raw['scene_layout'][1]['delay']=True
    assert compile(d,raw)['scene_intent']['comparisons'][0]['effects_changed']


@pytest.mark.parametrize('channel',[True,-1,4])
def test_new_scene_layout_cannot_invent_channels(monkeypatch,channel):
    d=device(monkeypatch);raw=goals();raw['scene_layout'][3]['amp_channel']=channel
    with pytest.raises(ValueError):compile(d,raw)
    d._write.assert_not_called()


@pytest.mark.parametrize('fault',['missing','duplicate','order','self','unknown','bool','shared_contrast'])
def test_goal_coverage_and_references_fail_closed(monkeypatch,fault):
    d=device(monkeypatch);raw=goals()
    if fault=='missing':raw['scene_goals'].pop()
    if fault=='duplicate':raw['scene_goals'][1]['scene']=1
    if fault=='order':raw['scene_goals'].reverse()
    if fault=='self':raw['scene_goals'][0].update(distinct_from=[1],distinction='base_tone')
    if fault=='unknown':raw['scene_goals'][0]['invented_write']='anything'
    if fault=='bool':raw['scene_goals'][0]['scene']=True
    if fault=='shared_contrast':raw['scene_goals'][0]['distinct_from']=[2]
    with pytest.raises((ValueError,ValidationError)):compile(d,raw)
    d._write.assert_not_called()


def test_no_goals_is_explicit_legacy_not_new_design(monkeypatch):
    d=device(monkeypatch);p=compile(d,design())
    assert not p['scene_intent']['goals']
    with pytest.raises(ValueError,match='klankdoel'):scene_intent.assess(p,require=True)


def test_shared_channel_tweak_protects_unselected_scene(monkeypatch):
    d=device(monkeypatch);raw=goals();original=compile(d,raw)
    raw['albums'][0]['amp']['gain']+=1
    candidate=compile(d,raw)
    with pytest.raises(ValueError,match='niet-gevraagde scenes 2'):
        scene_intent.preserve(original,candidate,[1])
    report=scene_intent.preserve(original,candidate,[1,2])
    assert report['changed_scenes']==[1,2]
    assert report['preserved_scenes']==[3,4,5,6,7,8]


def test_independent_role_can_use_available_voice_without_changing_other_scenes(monkeypatch):
    d=device(monkeypatch);raw=goals();before=compile(d,raw)
    raw['scene_layout'][1]['amp_channel']=2
    after=compile(d,raw)
    assert scene_intent.preserve(before,after,[2])['changed_scenes']==[2]


def test_shared_fx_setting_change_is_not_hidden_by_bypass(monkeypatch):
    d=device(monkeypatch);raw=goals();before=compile(d,raw)
    raw['delay']['time_ms']=420.
    with pytest.raises(ValueError,match='niet-gevraagde scenes'):
        scene_intent.preserve(before,compile(d,raw),[2])


@pytest.mark.parametrize('fault',['name','noop','bad_target','scene_name_only'])
def test_refinement_cannot_rename_or_report_only_prose_as_tweak(monkeypatch,fault):
    d=device(monkeypatch);raw=goals();before=compile(d,raw)
    if fault=='name':raw['name']='Unrequested name'
    if fault=='noop':raw['summary']='Only words changed'
    if fault=='scene_name_only':raw['scene_layout'][0]['name']='Only a new label'
    after=compile(d,raw)
    with pytest.raises(ValueError):scene_intent.preserve(before,after,[True] if fault=='bad_target' else [1])


def test_multi_scene_refinement_requires_complete_final_survey(monkeypatch):
    d=device(monkeypatch);p=compile(d,goals());reviews=tone_review.Reviews()
    ready=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    sent=reviews.send(d,ready['token'],target_confirmed=True,external_audio_muted=True)
    assert sent['refine_token']
    reviews.last_sent['proof']={}
    with pytest.raises(ValueError,match='laatste scenecontrole'):
        reviews.refinement(d,sent['refine_token'],tone_review.snapshot(d,include_nam=False))


def test_last_sent_baseline_bound_to_device_and_full_scene_state(monkeypatch):
    d=device(monkeypatch);p=compile(d,goals());reviews=tone_review.Reviews()
    with pytest.raises(ValueError):reviews.refinement(d,'unknown',tone_review.snapshot(d,include_nam=False))
    ready=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    result=reviews.send(d,ready['token'],target_confirmed=True,external_audio_muted=True)
    now=tone_review.snapshot(d,include_nam=False)
    assert result['refine_token']==ready['token']
    assert reviews.refinement(d,ready['token'],now)['design']==p['design']
    reviews.clear()  # UI discard/navigation does not authorize a different sound.
    d._test_bulk[58][17]+=1
    with pytest.raises(ValueError,match='gewijzigd'):reviews.refinement(d,ready['token'],tone_review.snapshot(d,include_nam=False))


@pytest.mark.parametrize('feature',['drive','post_eq','reverb','wah_controller','pitch'])
def test_required_but_unmeasured_tool_cannot_disappear(monkeypatch,feature):
    d=device(monkeypatch);raw=goals();raw['scene_goals'][0]['required_features']=[feature]
    with pytest.raises(ValueError,match=feature):compile(d,raw)
    d._write.assert_not_called()


def test_real_registered_refinement_flow_preserves_untargeted_sounds(monkeypatch):
    d=device(monkeypatch);raw=goals()
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None);monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock(side_effect=lambda *args,**kw:dict(**kw['validate'](deepcopy(raw)),backend='cli',model='synthetic'))
    monkeypatch.setattr(server.planner,'plan',ask)
    server._afx3_tone_reviews.clear();server._afx3_tone_reviews.last_sent=None
    body=dict(prompt='Eight requested sounds',expected_preset=322,mode='amp',scenes=8)
    with TestClient(server.app) as client:
        ready=client.post('/api/axefx3/plan',json=body)
        assert ready.status_code==200,ready.text
        sent=client.post('/api/axefx3/send',json=dict(token=ready.json()['token'],target_confirmed=True,external_audio_muted=True))
        assert sent.status_code==200 and sent.json()['ok'],sent.text
        d.set_scene(1)  # Explicit navigation, not a hidden planning write.
        d._write.reset_mock();d.set_param_display.reset_mock()
        raw['albums'][0]['amp']['gain']+=1
        request=dict(**body,refine_token=sent.json()['refine_token'],adjust_scenes=[1])
        refused=client.post('/api/axefx3/plan',json=request)
        assert refused.status_code==409 and 'niet-gevraagde scenes 2' in refused.text
        d._write.assert_not_called();d.set_param_display.assert_not_called()
        request['adjust_scenes']=[1,2]
        adjusted=client.post('/api/axefx3/plan',json=request)
        assert adjusted.status_code==200,adjusted.text
        assert adjusted.json()['adjustment']['preserved_scenes']==[3,4,5,6,7,8]
        assert 'Verified previous design' in ask.call_args.args[0]
        d._write.assert_not_called();d.set_param_display.assert_not_called();d.store_preset.assert_not_called()
    server._afx3_tone_reviews.clear();server._afx3_tone_reviews.last_sent=None

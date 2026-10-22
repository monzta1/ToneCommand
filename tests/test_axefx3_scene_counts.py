"""Bounded one-to-eight compiler prototype; native release is independent."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
import server
from devices.axefx3 import album_planning as planning,album_build,fw33_profile,tone_review,design_history,store_review
from test_axefx3_album_build import device,design
from tests.scene_intent_fixtures import with_goals


@pytest.fixture(autouse=True)
def synthetic_counts(monkeypatch):
    monkeypatch.setattr(fw33_profile,'ALBUM_SCENE_COUNTS',frozenset(range(1,9)))


def short_design(count):
    raw=design()
    raw['scene_count']=count
    raw['scene_layout']=planning.layout(raw)[:count]
    return with_goals(raw)


def successful(monkeypatch,count):
    d=device(monkeypatch);raw=short_design(count)
    plan=planning.compile_design(d.reg,raw,list(planning.serial_build.ROUTE),count)
    reviews=tone_review.Reviews();pending=reviews.prepare(d,plan,tone_review.snapshot(d,include_nam=False))
    result=reviews.send(d,pending['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'],result
    return d,plan,reviews,result


@pytest.mark.parametrize('count',range(1,9))
def test_normal_compiler_review_send_and_history_exact_scene_count(monkeypatch,count):
    d=device(monkeypatch);before=deepcopy(d._test_scenes)
    raw=short_design(count)
    plan=planning.compile_design(d.reg,raw,list(planning.serial_build.ROUTE),count)
    album_build.validate_actions(d.reg,plan['actions'],True)
    reviews=tone_review.Reviews();pending=reviews.prepare(d,plan,tone_review.snapshot(d,include_nam=False))
    sent=reviews.send(d,pending['token'],target_confirmed=True,external_audio_muted=True)
    assert sent['ok'] and d.current_scene()==count,sent
    assert len(plan['scenes'])==count and len(sent['album_verification']['scene_fingerprints'])==count
    assert [a['value'] for a in plan['actions'] if a['kind']=='rename_scene']==list(range(1,count+1))
    assert d._test_scenes=={**before,**{n:d._test_scenes[n] for n in range(1,count+1)}}
    assert design_history.load(sent['history']['id'])['plan']['design']['scene_count']==count
    d.store_preset.assert_not_called()


@pytest.mark.parametrize('count',(1,3,7,8))
def test_cold_history_resume_surveys_only_the_designed_scenes(monkeypatch,count):
    d,plan,old,sent=successful(monkeypatch,count)
    selections=d.set_scene.call_count;writes=d.set_param_display.call_count
    fresh=tone_review.Reviews()
    resumed=fresh.resume(d,sent['history']['id'],expected_preset=322,external_audio_muted=True,target_confirmed=True)
    assert resumed['ok'] and d.current_scene()==1
    assert d.set_scene.call_count-selections<=count+1
    assert d.set_param_display.call_count==writes
    assert fresh.refinement(d,resumed['refine_token'],tone_review.snapshot(d,include_nam=False))['design']==plan['design']


@pytest.mark.parametrize('count',(1,3,7))
def test_store_rechecks_every_designed_scene_and_keeps_separate_consent(monkeypatch,count):
    d,plan,reviews,sent=successful(monkeypatch,count)
    monkeypatch.setattr(store_review,'get_store_slots',lambda:{322})
    d.slot_name=Mock(return_value=SimpleNamespace(number=322,name='<EMPTY>'))
    d.store_preset=Mock(return_value=(322,plan['name']))
    stores=store_review.Stores();preview=stores.prepare(d,322)
    d.store_preset.assert_not_called()
    with pytest.raises(PermissionError):stores.send(d,preview['token'],False,True)
    assert stores.send(d,preview['token'],True,True)['stored']
    assert d.current_scene()==count and d.store_preset.call_count==1


@pytest.mark.parametrize('fault',('missing_layout','wrong_length','wrong_count','duplicate_scene','extra_scene','unreleased'))
def test_incomplete_or_unreleased_count_is_refused_before_writes(monkeypatch,fault):
    d=device(monkeypatch);raw=short_design(3)
    if fault=='missing_layout':raw.pop('scene_layout')
    if fault=='wrong_length':raw['scene_layout'].pop()
    if fault=='wrong_count':raw['scene_count']=4
    if fault=='unreleased':monkeypatch.setattr(fw33_profile,'ALBUM_SCENE_COUNTS',frozenset({8}))
    if fault in ('duplicate_scene','extra_scene'):
        plan=planning.compile_design(d.reg,raw,list(planning.serial_build.ROUTE),3)
        action=next(a for a in plan['actions'] if a['kind']=='rename_scene')
        if fault=='duplicate_scene':action['value']=2
        else:plan['actions'].append(dict(kind='rename_scene',value=4,type_name='Extra'))
        with pytest.raises(ValueError):album_build.validate_actions(d.reg,plan['actions'],True)
    else:
        with pytest.raises(ValueError):planning.compile_design(d.reg,raw,list(planning.serial_build.ROUTE),3)
    d._write.assert_not_called();d.store_preset.assert_not_called()


def test_history_resume_outside_designed_scene_fails_without_switch(monkeypatch):
    d,plan,reviews,sent=successful(monkeypatch,3)
    d.set_scene(5);selections=d.set_scene.call_count
    with pytest.raises(ValueError,match='differ'):
        tone_review.Reviews().resume(d,sent['history']['id'],expected_preset=322,external_audio_muted=True,target_confirmed=True)
    assert d.set_scene.call_count==selections


def test_older_eight_scene_design_without_new_count_stays_compatible(monkeypatch):
    d=device(monkeypatch);raw=design();raw.pop('scene_count')
    plan=planning.compile_design(d.reg,raw,list(planning.serial_build.ROUTE),8)
    assert len(plan['scenes'])==8 and plan['design']['scene_count']==8


@pytest.mark.parametrize('count',(True,False,0,9,1.,'1',None))
def test_scene_count_cannot_coerce_bool_float_string_or_outside_range(monkeypatch,count):
    d=device(monkeypatch)
    with pytest.raises(ValueError):planning.compile_design(d.reg,short_design(3),list(planning.serial_build.ROUTE),count)
    d._write.assert_not_called()


@pytest.mark.parametrize('raw',(None,[],True,'design'))
def test_invalid_structured_design_is_a_read_only_validation_error(monkeypatch,raw):
    d=device(monkeypatch)
    with pytest.raises(ValueError):planning.compile_design(d.reg,raw,list(planning.serial_build.ROUTE),3)
    d._write.assert_not_called()


@pytest.mark.parametrize('count',(1,3,7))
def test_registered_api_negotiates_released_count_and_normal_review(monkeypatch,count):
    d=device(monkeypatch)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None);monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock(side_effect=lambda *args,**kw:dict(**kw['validate'](short_design(count)),backend='cli',model='synthetic'))
    monkeypatch.setattr(server.planner,'plan',ask)
    server._afx3_tone_reviews.clear()
    try:
        with TestClient(server.app) as client:
            state=client.get('/api/axefx3/state').json()
            assert state['album_scene_counts']==list(range(1,9))
            r=client.post('/api/axefx3/plan',json=dict(prompt='Requested distinct guitar scenes',expected_preset=322,mode='amp',scenes=count))
            assert r.status_code==200,r.text
            prepared=r.json();assert len(prepared['scenes'])==count
            d._write.assert_not_called();d.store_preset.assert_not_called()
            sent=client.post('/api/axefx3/send',json=dict(token=prepared['token'],target_confirmed=True,external_audio_muted=True))
            assert sent.status_code==200 and sent.json()['ok'],sent.text
            assert d.current_scene()==count
    finally:server._afx3_tone_reviews.clear();server._afx3_tone_reviews.last_sent=None

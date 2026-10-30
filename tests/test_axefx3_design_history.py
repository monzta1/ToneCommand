"""Disk records do not preserve authorization or bypass fresh device checks."""
from copy import deepcopy
from dataclasses import replace
import json
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
import server
from devices.axefx3 import design_history as history, tone_review, executor
from test_axefx3_album_build import device, plan


def sent(monkeypatch):
    d=device(monkeypatch);p=plan(d);reviews=tone_review.Reviews()
    pending=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    result=reviews.send(d,pending['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'] and 'history' in result,result
    return d,p,reviews,result


def test_successful_send_persists_only_design_and_evidence(monkeypatch):
    d,p,reviews,result=sent(monkeypatch)
    record=history.load(result['history']['id'])
    assert record['plan']=={'mode':'album','design':p['design']}
    assert record['stamp']==tone_review.digest(tone_review.snapshot(d,include_nam=False))
    raw=(history.directory()/(record['id']+'.json')).read_text(encoding='utf-8')
    assert result['refine_token'] not in raw and 'access_token' not in raw
    assert 'actions' not in record['plan']
    entries=history.entries();assert len(entries['designs'])==1 and not entries['hardware_written']


def test_mk2_history_can_identify_upper_preset_without_enabling_mk1(monkeypatch):
    d,p,reviews,result=sent(monkeypatch)
    record=history.load(result['history']['id'])
    record['preset']=1023
    assert history.validate(record)['preset']==1023
    record['variant']='mk1'
    with pytest.raises(ValueError):history.validate(record)
    record['variant']='mk2';record['preset']=1024
    with pytest.raises(ValueError):history.validate(record)


def test_numeric_reference_survives_cold_resume_without_private_source_or_authority(monkeypatch):
    from test_axefx3_audio_comparison import reading
    d=device(monkeypatch);p=plan(d);reviews=tone_review.Reviews()
    p['reference_measurements']=reading(url='https://example.com/?secret=private',file_name='personal.wav')
    prepared=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    result=reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    record=history.load(result['history']['id'])
    assert record['version']==2
    evidence=record['plan']['reference_measurements']
    assert evidence['centroid_hz']==440 and evidence['analysis_method']=='channel-power-v2'
    assert 'url' not in evidence and 'file_name' not in evidence
    assert 'private' not in str(record) and 'personal' not in str(record)
    fresh=tone_review.Reviews()
    resumed=fresh.resume(d,record['id'],expected_preset=322,external_audio_muted=True,target_confirmed=True)
    assert fresh.refinement(d,resumed['refine_token'],tone_review.snapshot(d,include_nam=False))['reference_measurements']==evidence
    assert not resumed['stored'] and not resumed['parameters_written']


def test_version_two_cannot_hide_urls_or_actions_in_numeric_evidence(monkeypatch):
    from test_axefx3_audio_comparison import reading
    d,p,reviews,result=sent(monkeypatch)
    record=history.load(result['history']['id']);record['version']=2
    record['plan']['reference_measurements']=reading(url='https://private.invalid')
    with pytest.raises(ValueError,match='private numeric'):history.validate(record)
    record['plan']['reference_measurements']=dict(reading(),actions=[])
    with pytest.raises(ValueError):history.validate(record)


def test_refinement_reuses_numeric_reference_without_claiming_new_analysis(monkeypatch):
    from test_axefx3_audio_comparison import reading
    from tests.scene_intent_fixtures import with_goals
    d=device(monkeypatch);p=plan(d);reviews=server._afx3_tone_reviews
    p['reference_measurements']=reading()
    prepared=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    sent=reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    d.set_scene(1)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None);monkeypatch.setenv('PLANNER_BACKEND','cli')
    changed=deepcopy(p['design']);changed['albums'][0]['amp']['gain']+=.5
    ask=Mock(side_effect=lambda *args,**kw:dict(**kw['validate'](with_goals(changed)),backend='cli'))
    monkeypatch.setattr(server.planner,'plan',ask)
    try:
        response=TestClient(server.app).post('/api/axefx3/plan',json=dict(prompt='Scene 1 en 2 hebben iets meer gain nodig',
            expected_preset=322,mode='amp',scenes=8,refine_token=sent['refine_token'],adjust_scenes=[1,2]))
        assert response.status_code==200,response.text
        assert response.json()['reference_measurements']['centroid_hz']==440
        assert 'Previous user-supplied reference measurements reused' in ask.call_args.args[0]
        assert 'not a new recording' in ask.call_args.args[0]
        assert 'actions' not in response.json()['reference_measurements']
    finally:reviews.clear();reviews.last_sent=None


def test_new_review_service_can_resume_only_after_all_eight_scene_checks(monkeypatch):
    d,p,old,result=sent(monkeypatch)
    writes=d.set_param_display.call_count;models=d._write.call_count
    fresh=tone_review.Reviews()
    resumed=fresh.resume(d,result['history']['id'],expected_preset=322,
                         external_audio_muted=True,target_confirmed=True)
    assert resumed['ok'] and resumed['scene']==1 and not resumed['stored']
    assert not resumed['parameters_written'] and resumed['refine_token']!=result['refine_token']
    assert d.set_param_display.call_count==writes and d._write.call_count==models
    assert fresh.refinement(d,resumed['refine_token'],tone_review.snapshot(d,include_nam=False))['design']==p['design']
    d.store_preset.assert_not_called()


@pytest.mark.parametrize('fault',['mute','consent','target','firmware','variant','catalog','bulk','old_token'])
def test_mismatch_or_old_consent_cannot_resume(monkeypatch,fault):
    d,p,old,result=sent(monkeypatch);fresh=tone_review.Reviews()
    record_id=result['history']['id'];kw=dict(expected_preset=322,external_audio_muted=True,target_confirmed=True)
    if fault=='mute':kw['external_audio_muted']=False
    if fault=='consent':kw['target_confirmed']=False
    if fault=='target':kw['expected_preset']=328
    if fault=='firmware':d.reg.firmware='33.01'
    if fault=='variant':d.reg.hardware_variant='mk1'
    if fault=='catalog':d.reg.cab_catalog.names[2,99]='Changed catalog'
    if fault=='bulk':d._test_bulk[58][1]+=100
    if fault=='old_token':record_id=result['refine_token']
    selections=d.set_scene.call_count;writes=d._write.call_count
    with pytest.raises((ValueError,PermissionError)):fresh.resume(d,record_id,**kw)
    assert d.set_scene.call_count==selections and d._write.call_count==writes
    assert fresh.last_sent is None


def test_hidden_scene_drift_stops_survey_without_automatic_return(monkeypatch):
    d,p,old,result=sent(monkeypatch)
    d._test_scenes[3][94]=replace(d._test_scenes[3][94],bypassed=False)
    fresh=tone_review.Reviews();writes=d.set_param_display.call_count
    with pytest.raises(ValueError,match='Scene 3 changed'):
        fresh.resume(d,result['history']['id'],expected_preset=322,external_audio_muted=True,target_confirmed=True)
    assert d.current_scene()==3 and fresh.last_sent is None
    assert d.set_param_display.call_count==writes
    d.store_preset.assert_not_called()


def test_disk_failure_does_not_retry_a_successful_send(monkeypatch):
    monkeypatch.setattr(history,'remember',Mock(side_effect=OSError('Disk full')))
    d=device(monkeypatch);p=plan(d);reviews=tone_review.Reviews()
    prepared=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    result=reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'] and result['refine_token']==prepared['token']
    assert 'Disk full' in result['history_warning'] and 'history' not in result
    assert reviews.last_sent is not None
    with pytest.raises(ValueError):reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    d.store_preset.assert_not_called()


@pytest.mark.parametrize('identifier',['../private','a'*31,'A'*32,'b'*32+'.json','',None])
def test_path_traversal_and_unbounded_identifiers_rejected(identifier):
    with pytest.raises(ValueError):history.load(identifier)


def test_corrupt_record_is_not_deleted_or_resumed(monkeypatch):
    d,p,old,result=sent(monkeypatch)
    key=result['history']['id'];path=history.directory()/(key+'.json')
    envelope=json.loads(path.read_text(encoding='utf-8'))
    envelope['record']['plan']['design']['name']='Tampered'
    path.write_text(json.dumps(envelope),encoding='utf-8')
    with pytest.raises(ValueError,match='checksum'):history.load(key)
    assert history.entries()['unreadable']==1 and path.exists()


def test_registered_history_resume_and_request_validation(monkeypatch):
    d,p,old,result=sent(monkeypatch)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    server._afx3_tone_reviews.last_sent=None
    with TestClient(server.app) as client:
        listed=client.get('/api/axefx3/history').json()
        assert listed['designs'][0]['id']==result['history']['id']
        body=dict(record_id=result['history']['id'],expected_preset=322,external_audio_muted=True,target_confirmed=True)
        bad=client.post('/api/axefx3/history/resume',json={**body,'expected_preset':True})
        assert bad.status_code==422
        resumed=client.post('/api/axefx3/history/resume',json=body)
        assert resumed.status_code==200 and resumed.json()['scene']==1,resumed.text
        assert server._afx3_tone_reviews.last_sent['token']==resumed.json()['refine_token']
    server._afx3_tone_reviews.clear();server._afx3_tone_reviews.last_sent=None


def test_simulator_without_isolated_path_cannot_read_owner_history(monkeypatch):
    monkeypatch.delenv('TONECOMMAND_AXEFX3_STATE_DIR')
    with pytest.raises(ValueError,match='isolated'):history.entries()

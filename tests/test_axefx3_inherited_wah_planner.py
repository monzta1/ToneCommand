"""Inherited Wah must be usable through normal planning, review and SEND."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from fm9.device import SetResult
from devices.axefx3 import wah_voicing,album_planning,album_build,executor,tone_review,pedal_control,serial_build
from devices.axefx3 import request_intake,fw33_profile,protocol,inherited_controls_probe
from devices.axefx3.registry import Registry
from fm9 import protocol as shared
from test_axefx3_album_build import device,design
from fastapi.testclient import TestClient
from tests.scene_intent_fixtures import with_goals
import server


def voice():
    return dict(model='Cry Babe',frequency_min=350.,frequency_max=3000.,resonance=4.8,
        q_tracking=5.,fat=2.,drive=1.,inductor_bias=3.,low_cut=70.,level=0.)


def rig(monkeypatch):
    monkeypatch.setattr(wah_voicing,'RELEASED',True)
    d=device(monkeypatch);records=[[0]*25 for _ in range(32)]
    d.read_modifier=lambda slot:records[slot-1].copy()
    def bind(eid,source,auto):
        assert eid==94
        records[0]=pedal_control.default_words(94);records[0][0]=source
        if auto is not None:records[0][10]=pedal_control.MODES[auto]
        return SetResult(True,'Complete modifier readback matched',None,1)
    d.bind_pedal_control=Mock(side_effect=bind)
    raw=design();raw['wah']=voice()
    for i,a in enumerate(raw['albums']):
        a['lead']['wah']=False;a['solo']['wah']=True
    return d,raw,records


def test_normal_eight_scene_wah_and_controller_review_send(monkeypatch):
    d,raw,records=rig(monkeypatch)
    p=album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),8,'External 2','Fast Pos')
    album_build.validate_actions(d.reg,p['actions'],True)
    assert p['controller']==dict(source='External 2',auto_engage='Fast Pos')
    assert p['design']['wah']==voice()
    reviews=tone_review.Reviews();preview=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    d._write.assert_not_called();d.bind_pedal_control.assert_not_called()
    result=reviews.send(d,preview['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'],result
    assert not result['stored'] and len(result['album_verification']['scene_fingerprints'])==8
    assert records[0][0]==13 and records[0][8:11]==[94,5,6]
    assert all(d._test_scenes[n][94].bypassed==bool(n%2) for n in range(1,9))
    d.store_preset.assert_not_called()


@pytest.mark.parametrize('fault',['stage','final_level','wrong_model','missing_voice','binding_order','global_cc','controller_volume','missing_param'])
def test_corrupted_wah_grammar_refused_before_any_write(monkeypatch,fault):
    d,raw,_=rig(monkeypatch)
    p=album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),8,'External 1','Off')
    actions=p['actions']
    if fault=='stage':next(a for a in actions if a.get('param')=='WAH_LEVEL')['value']=0.
    if fault=='final_level':[a for a in actions if a.get('param')=='WAH_LEVEL'][-1]['value']=3.
    if fault=='wrong_model':next(a for a in actions if a['kind']=='set_type' and a['block']=='WAH')['type_name']='Clyde'
    if fault=='missing_voice':actions[:]=[a for a in actions if not(a.get('block')=='WAH' and a['kind']=='set_param')]
    if fault=='binding_order':actions.insert(0,actions.pop(next(i for i,a in enumerate(actions) if a['kind']=='bind_controller')))
    if fault=='global_cc':next(a for a in actions if a['kind']=='bind_controller')['cc']=7
    if fault=='controller_volume':next(a for a in actions if a['kind']=='bind_controller')['block']='VOLPAN'
    if fault=='missing_param':actions.pop(next(i for i,a in enumerate(actions) if a.get('param')=='WAH_FREQMAX'))
    with pytest.raises((ValueError,KeyError)):executor.prepare(d,actions,p['required_route'],322)
    d._write.assert_not_called();d.bind_pedal_control.assert_not_called()


def test_no_implicit_feature_release_or_pitch_claim(monkeypatch):
    d,raw,_=rig(monkeypatch)
    monkeypatch.setattr(wah_voicing,'RELEASED',False)
    with pytest.raises(ValueError,match='acceptance'):
        album_planning.compile_design(d.reg,raw,list(serial_build.ROUTE),8,'External 1')
    monkeypatch.setattr(wah_voicing,'RELEASED',True)
    intake=request_intake.analyze('4 scenes wah high pitch toe down external 2',d.reg,'amp',4)
    assert [q['id'] for q in intake['questions']]==['pitch_meaning']
    assert request_intake.explicit_wah_source('wah external 2')=='External 2'
    assert request_intake.explicit_wah_source('wah external 1 volume external 2') is None
    assert request_intake.explicit_wah_source('zonder wah external 2') is None


def test_exact_inherited_numeric_setters_match_captured_editor_frames():
    reg=Registry(fw33_profile.KEY)
    for literal in inherited_controls_probe.frames():
        eid=shared.decode14(*literal[8:10]);pid=shared.decode14(*literal[10:12])
        if eid==94 and pid in (0,12):continue
        family,_=inherited_controls_probe.LAYOUTS[eid];spec=reg.spec(family,pid)
        wire=shared.decode_f32_septets(literal[12:17])
        value=wire*spec.set_divisor
        assert protocol.set_parameter(reg,spec,value)==list(literal)


def test_registered_plan_takes_explicit_controller_from_user_text(monkeypatch):
    d,raw,_=rig(monkeypatch)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None);monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock(side_effect=lambda *a,**kw:dict(**kw['validate'](with_goals(raw)),backend='cli',model='synthetic'))
    monkeypatch.setattr(server.planner,'plan',ask);server._afx3_tone_reviews.clear()
    try:
        with TestClient(server.app) as c:
            response=c.post('/api/axefx3/plan',json=dict(prompt='8 scenes met wah op External 2 en auto engage',
                mode='amp',scenes=8,expected_preset=322))
            assert response.status_code==200,response.text
            preview=response.json();assert preview['controller']['source']=='External 2'
            assert preview['controller']['auto_engage']=='Fast Pos'
            d._write.assert_not_called()
            sent=c.post('/api/axefx3/send',json=dict(token=preview['token'],target_confirmed=True,external_audio_muted=True))
            assert sent.status_code==200 and sent.json()['ok'],sent.text
            d.bind_pedal_control.assert_called_once_with(94,13,'Fast Pos')
    finally:server._afx3_tone_reviews.clear();server._afx3_tone_reviews.last_sent=None

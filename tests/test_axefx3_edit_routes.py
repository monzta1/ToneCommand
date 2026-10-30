"""Registered production routes with independent fake ports, never real MIDI."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3 import edit_routes
from devices.axefx3.readonly_adapter import ReadOnlyRegistry
from devices.axefx3.amp_writer import AmpWriter
from tests.test_axefx3_amp_writer import AmpPorts


@pytest.fixture(autouse=True)
def forbid_physical_ports(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *a,**k:pytest.fail('Physical MIDI is forbidden in route tests'))


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP','1')
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *a,**k:pytest.fail('Physical MIDI opened'))
    monkeypatch.setattr('devices.axefx3.amp_writer.time.sleep',lambda _:None)
    monkeypatch.setattr(server.planner,'plan',lambda *a,**k:pytest.fail('Provider called'))
    ports=AmpPorts();dev=AmpWriter((ports.inp,ports.outp))
    ports.sent.clear()  # Constructor identity/current-preset GETs precede the request under test.
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',ReadOnlyRegistry(),dev,'Fractal Axe-Fx III'))
    monkeypatch.setattr(server,'_selected_kind',{'kind':'axefx3'})
    monkeypatch.setattr(server,'_gig_mode',{'on':False})
    monkeypatch.setattr(server,'_plan_revisions',{})
    server._afx3_edit_workflow.discard()
    client=TestClient(server.app)  # No lifespan/bus watcher.
    yield client,dev,ports
    client.close();server._afx3_edit_workflow.discard();dev.close()


def prepare(client):
    r=client.post('/api/axefx3/edit/prepare',json=dict(actions=[dict(kind='set_param',block='amp',param='DISTORT_DRIVE',value=3.3)],expected_preset=320,expected_scene=1))
    assert r.status_code==200,r.text
    return r.json()


def payload(view,consent=False):
    body={k:deepcopy(view[k]) for k in ('token','actions','plan_digest','expected_preset','expected_scene')}
    if consent:body.update(target_confirmed=True,external_audio_muted=True)
    return body


def arm(client):
    view=prepare(client)
    r=client.post('/api/axefx3/edit/review',json=payload(view));assert r.status_code==200,r.text
    r=client.post('/api/axefx3/edit/confirm',json=payload(r.json(),True));assert r.status_code==200,r.text
    return r.json()


def test_registered_stages_write_once_only_after_explicit_send(api):
    c,dev,p=api
    state=c.get('/api/axefx3/edit/state');assert state.json()['available']
    proposal=prepare(c);assert proposal['values']=={'DISTORT_DRIVE':proposal['change']['before']}
    view=arm(c);assert not p.writes and view['can_send']
    result=c.post('/api/axefx3/edit/send',json=payload(view,True))
    assert result.status_code==200,result.text
    assert result.json()['verified'] and not result.json()['stored'] and not result.json()['undo_available']
    assert len(p.writes)==1
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    assert len(p.writes)==1 and not dev.capabilities().verifies_writes


@pytest.mark.parametrize('field,value',[('expected_preset',True),('expected_scene',1.0),
    ('whole_rig',1),('unexpected','value')])
def test_strict_preparation_before_io(api,field,value):
    c,dev,p=api;body=dict(actions=[dict(kind='set_param',block='amp',param='DISTORT_DRIVE',value=3.3)],expected_preset=320,expected_scene=1)
    body[field]=value
    assert c.post('/api/axefx3/edit/prepare',json=body).status_code==422
    assert not p.sent


@pytest.mark.parametrize('change',[{'kind':'store','value':320},
    {'kind':'set_type','block':'amp','type_name':'Brit 800'},
    {'kind':'rename_preset','type_name':'Name'},
    {'kind':'set_param','block':'amp','param':'DISTORT_LEVEL','value':0},
    {'kind':'set_param','block':'amp','param':'DISTORT_DRIVE','value':True}])
def test_other_families_do_not_enter_generic_executor(api,change):
    c,dev,p=api
    r=c.post('/api/axefx3/edit/prepare',json=dict(actions=[change],expected_preset=320,expected_scene=1))
    assert r.status_code in (400,409) and not p.writes


@pytest.mark.parametrize('stage',['confirm','send'])
def test_cannot_skip_review_or_send_automatically(api,stage):
    c,dev,p=api;view=prepare(c)
    r=c.post('/api/axefx3/edit/'+stage,json=payload(view,True))
    assert r.status_code==409 and not p.writes


@pytest.mark.parametrize('field,value',[('external_audio_muted',False),('target_confirmed',False),
    ('external_audio_muted',1),('target_confirmed','yes')])
def test_explicit_consents_required(api,field,value):
    c,dev,p=api;view=arm(c);body=payload(view,True);body[field]=value
    assert c.post('/api/axefx3/edit/send',json=body).status_code in (409,422)
    assert not p.writes


@pytest.mark.parametrize('fault',['raise','ignore','other_channel','modifier','identity'])
def test_unknown_outcome_stops_without_retry_or_undo(api,fault):
    c,dev,p=api;view=arm(c);p.behavior=fault
    r=c.post('/api/axefx3/edit/send',json=payload(view,True))
    assert r.status_code==409,r.text
    assert r.json()['uncertain'] and not r.json()['retry_allowed'] and not r.json()['undo_available']
    assert dev._uncertain and len(p.writes)==1
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    assert len(p.writes)==1


@pytest.mark.parametrize('change',['preset','scene','gig','connection','bulk','modifier'])
def test_changed_context_never_sends(api,change,monkeypatch):
    c,dev,p=api;view=arm(c)
    if change=='preset':p.preset=321
    if change=='scene':p.scene=1
    if change=='gig':server._gig_mode['on']=True
    if change=='connection':monkeypatch.setattr(server,'_context',server._default_context)
    if change=='bulk':p.amp[21]+=1
    if change=='modifier':p.mods[34][9]+=1
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    assert not p.writes


def test_discard_and_replaced_prepare_disarm_old_token(api):
    c,dev,p=api;old=arm(c)
    assert c.post('/api/axefx3/edit/discard').status_code==200
    assert c.post('/api/axefx3/edit/send',json=payload(old,True)).status_code==409
    old=arm(c);prepare(c)
    assert c.post('/api/axefx3/edit/send',json=payload(old,True)).status_code==409
    assert not p.writes


def test_unknown_firmware_is_visible_blocked_without_set(api):
    c,dev,p=api
    p.identity=tuple([*p.identity[:-1],0])
    state=c.get('/api/axefx3/edit/state').json()
    assert state['configured'] and not state['available'] and state['reason']
    assert c.post('/api/axefx3/edit/prepare',json=dict(actions=[dict(kind='set_param',block='amp',param='DISTORT_DRIVE',value=3.3)],expected_preset=320,expected_scene=1)).status_code==409
    assert not p.writes


def test_default_and_wrong_device_remain_readonly(api,monkeypatch):
    c,dev,p=api;monkeypatch.delenv('TONECOMMAND_AXEFX3_REVIEWED_AMP')
    assert not c.get('/api/axefx3/edit/state').json()['available']
    for path in ('prepare','review','confirm','send'):
        body=dict(actions=[dict(kind='set_param',block='amp',param='DISTORT_DRIVE',value=3.3)],expected_preset=320,expected_scene=1)
        if path!='prepare':body.update(token='x',plan_digest='x')
        if path in ('confirm','send'):body.update(target_confirmed=True,external_audio_muted=True)
        assert c.post('/api/axefx3/edit/'+path,json=body).status_code==409
    assert not p.writes


def test_cross_origin_cannot_prepare_or_discard(api):
    c,dev,p=api;view=arm(c)
    assert c.post('/api/axefx3/edit/discard',headers={'Origin':'https://unrelated.example'}).status_code==403
    assert c.post('/api/axefx3/edit/send',json=payload(view,True),headers={'Origin':'https://unrelated.example'}).status_code==403
    assert not p.writes


def test_report_page_survives_broken_iii_ui_without_device_calls(api,monkeypatch):
    c,dev,p=api
    monkeypatch.setattr(server,'get_fm9',lambda:pytest.fail('Report requested device'))
    r=c.get('/report');assert r.status_code==200 and '<form' in r.text
    assert 'axefx3' in r.text.lower()
    r=c.post('/report',data={'note':'The reviewed Axe-Fx III page failed to load'})
    assert r.status_code==200 and 'The reviewed Axe-Fx III page failed to load' in r.text
    assert not p.sent


def test_javascript_is_static_and_does_not_open_midi(api):
    c,dev,p=api;r=c.get('/axefx3-reviewed-edit.js')
    assert r.status_code==200 and not p.sent


def test_reflected_non_loopback_origin_cannot_prepare_or_discard(api):
    c,dev,p=api
    headers={'host':'untrusted.example','origin':'http://untrusted.example'}
    body=dict(actions=[dict(kind='set_param',block='amp',param='DISTORT_DRIVE',value=3.3)],expected_preset=320,expected_scene=1)
    assert c.post('/api/axefx3/edit/prepare',json=body,headers=headers).status_code==403
    assert c.post('/api/axefx3/edit/discard',headers=headers).status_code==403
    assert not p.sent


def test_actual_loopback_browser_origin_can_prepare_without_a_write(api):
    c,dev,p=api
    headers={'host':'127.0.0.1:8909','origin':'http://127.0.0.1:8909'}
    body=dict(actions=[dict(kind='set_param',block='amp',param='DISTORT_DRIVE',value=3.3)],expected_preset=320,expected_scene=1)
    assert c.post('/api/axefx3/edit/prepare',json=body,headers=headers).status_code==200
    assert not p.writes


def test_normal_connection_factory_stays_readonly_unless_explicitly_enabled(monkeypatch):
    calls=[]
    monkeypatch.delenv('TONECOMMAND_AXEFX3_REVIEWED_AMP',raising=False)
    monkeypatch.setattr('devices.axefx3.readonly_adapter.AxeFxIII',lambda **kw:calls.append(kw) or 'readonly')
    assert edit_routes.connect('mk1')=='readonly' and calls==[{'chassis':'mk1'}]
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP','1')
    for chassis in ('mk1','turbo'):
        with pytest.raises(server.ReadOnly):edit_routes.connect(chassis)
    with pytest.raises(server.ReadOnly):edit_routes.connect('mk2')  # SIM never opens native MIDI.
    assert len(calls)==1  # No fallback/reconnection to another owner.


def test_disabling_optin_after_arm_invalidates_the_review(api,monkeypatch):
    c,dev,p=api;view=arm(c)
    monkeypatch.delenv('TONECOMMAND_AXEFX3_REVIEWED_AMP')
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    monkeypatch.setenv('TONECOMMAND_AXEFX3_REVIEWED_AMP','1')
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    assert not p.writes


def test_pending_normal_plan_is_not_silently_replaced(api):
    c,dev,p=api;view=arm(c)
    server._plan_revisions['pending']={}
    r=c.post('/api/axefx3/edit/prepare',json=dict(actions=[dict(kind='set_param',block='amp',param='DISTORT_DRIVE',value=3.3)],expected_preset=320,expected_scene=1))
    assert r.status_code==409 and 'pending plan' in r.json()['error']
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    assert not p.writes


@pytest.mark.parametrize('field,value',[('token','changed'),('plan_digest','changed'),
    ('expected_preset',321),('expected_scene',2),('actions',[dict(kind='set_param',block='amp',param='DISTORT_MID',value=5.3)])])
def test_altered_request_consumes_review_without_writes(api,field,value):
    c,dev,p=api;view=arm(c);body=payload(view,True);body[field]=value
    assert c.post('/api/axefx3/edit/send',json=body).status_code==409
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    assert not p.writes


def test_expired_ui_arm_does_not_reach_native_set(api,monkeypatch):
    c,dev,p=api;view=arm(c)
    flow=server._afx3_edit_workflow
    monkeypatch.setattr(flow,'_clock',lambda:flow._pending.armed_until+.001 if flow._pending else 10**12)
    assert c.post('/api/axefx3/edit/send',json=payload(view,True)).status_code==409
    assert not p.writes

"""Controller choices are reviewed data, never an immediate hardware write."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3.controller_review import Reviews, inspect
from tests.test_axefx3_pedal_control import rig


def test_read_and_review_do_not_write(rig):
    dev, _, _ = rig
    state = inspect(dev)
    assert [t['source_name'] for t in state['targets']] == ['External 1', 'External 2']
    reviews = Reviews()
    proposal = reviews.prepare(dev, dict(effect_id=95,source=13,auto_engage='Off'))
    assert proposal['before_source'] == 'External 1'
    assert proposal['after_source'] == 'External 2'
    assert not proposal['stored']
    dev._write.assert_not_called()


def test_fw33_existing_wah_can_be_reviewed_with_volume_release_disabled(rig,monkeypatch):
    from devices.axefx3.registry import Registry
    from devices.axefx3 import fw33_profile
    from devices.axefx3 import pedal_fw33
    monkeypatch.setattr(pedal_fw33,'VOLUME_RELEASED',False)
    dev,slots,_=rig
    dev.reg=Registry(fw33_profile.KEY);dev.reg.hardware_variant='mk2'
    dev.firmware_label.return_value=fw33_profile.KEY
    slots[0]=[0]*25
    dev.status_dump.return_value=[b for b in dev.status_dump() if b.effect_id==95]
    state=inspect(dev)
    assert len(state['targets'])==1 and state['targets'][0]['writable']
    assert state['targets'][0]['auto_engage']=='Fast Pos'
    proposal=Reviews().prepare(dev,dict(effect_id=95,source=13,auto_engage='Off'))
    assert proposal['after_source']=='External 2' and not proposal['new_binding']
    dev._write.assert_not_called()
    assert dev.reg.spec('WAH',5).name=='WAH_CONTROL'
    with pytest.raises(ValueError,match='Volume'):
        Reviews().prepare(dev,dict(effect_id=102,source=13,auto_engage='Off'))


def test_ticket_executes_once_and_readback_is_reported(rig):
    dev, slots, _ = rig
    reviews = Reviews()
    token = reviews.prepare(dev, dict(effect_id=95,source=13,auto_engage='Off'))['token']
    result = reviews.send(dev,token,external_audio_muted=True,target_confirmed=True)
    assert result['ok'] and not result['stored']
    assert slots[1][0] == 13 and slots[1][10] == 0
    with pytest.raises(ValueError,match='already used'):
        reviews.send(dev,token,external_audio_muted=True,target_confirmed=True)
    assert dev._write.call_count == 2


@pytest.mark.parametrize('change',['preset','scene','curve','other_slot','volume','grid','channel'])
def test_changed_state_invalidates_review_before_any_write(rig,change):
    dev,slots,volume = rig
    reviews = Reviews()
    token = reviews.prepare(dev,dict(effect_id=95,source=13))['token']
    if change == 'preset': dev.current_preset.return_value = (325,'Test')
    if change == 'scene': dev.current_scene.return_value = 2
    if change == 'curve': slots[1][13] += 1
    if change == 'other_slot': slots[31][1] = 2
    if change == 'volume': volume[0] -= 1
    if change == 'grid': dev.read_grid.return_value = []
    if change == 'channel': dev.status_dump.return_value[0].channel = 1
    with pytest.raises(ValueError,match='changed'):
        reviews.send(dev,token,external_audio_muted=True,target_confirmed=True)
    dev._write.assert_not_called()
    assert reviews.pending is None


@pytest.mark.parametrize('ack',[dict(external_audio_muted=False,target_confirmed=True),
                                dict(external_audio_muted=True,target_confirmed=False)])
def test_both_acknowledgements_required(rig,ack):
    dev,_,_ = rig
    reviews = Reviews()
    token = reviews.prepare(dev,dict(effect_id=102,source=12))['token']
    with pytest.raises(PermissionError): reviews.send(dev,token,**ack)
    dev._write.assert_not_called()


def test_expired_or_replaced_ticket_never_writes(rig):
    dev,_,_ = rig
    now = [0]
    reviews = Reviews(clock=lambda:now[0])
    old = reviews.prepare(dev,dict(effect_id=95,source=13))['token']
    new = reviews.prepare(dev,dict(effect_id=102,source=12))['token']
    with pytest.raises(ValueError): reviews.send(dev,old,external_audio_muted=True,target_confirmed=True)
    now[0] = 301
    with pytest.raises(ValueError,match='expired'):
        reviews.send(dev,new,external_audio_muted=True,target_confirmed=True)
    dev._write.assert_not_called()


@pytest.fixture
def api(rig,monkeypatch):
    dev,slots,volume = rig
    monkeypatch.setattr(server,'_context',server._default_context)
    monkeypatch.setattr(server,'_selected_kind',{'kind':None})
    monkeypatch.setattr(server,'_gig_mode',{'on':False})
    monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    drop = Mock()
    monkeypatch.setattr(server,'drop_fm9',drop)
    monkeypatch.setattr(server._controller_reviews,'connect_device',lambda:dev)
    server._controller_reviews.clear()
    with TestClient(server.app) as client:
        yield client,dev,slots
    server._controller_reviews.clear()


def test_explicit_connection_and_safe_state(api):
    client,dev,_=api
    assert client.get('/controllers').status_code == 200
    assert client.get('/controllers.js').status_code == 200
    assert not client.get('/api/controllers/state').json()['connected']
    dev.status_dump.assert_not_called()
    assert client.post('/api/controllers/connect').status_code == 200
    assert client.get('/api/controllers/state').json()['connected']
    assert server.device_context().registry is dev.reg
    dev._write.assert_not_called()
    assert client.post('/api/controllers/disconnect').status_code == 200
    dev.close.assert_called_once()
    assert server.device_context().kind == 'fm9'


def test_legacy_write_routes_and_generic_handle_stay_blocked(api):
    client,dev,_=api
    client.post('/api/controllers/connect')
    for route,body in [('/api/apply',{'actions':[]}),('/api/preset',{'preset':324}),
                       ('/api/plan',{'prompt':'anything'}),('/api/device/select',{'kind':'fm9'}),
                       ('/api/controllers/../apply',{'actions':[]})]:
        assert client.post(route,json=body).status_code == 409
    assert client.get('/',follow_redirects=False).headers['location'] == '/axefx3'
    with pytest.raises(server.CapabilityDeclined): server.get_fm9()
    dev._write.assert_not_called()


def test_browser_shaped_review_send_path(api):
    client,dev,slots=api
    client.post('/api/controllers/connect')
    review = client.post('/api/controllers/review',json={'effect_id':102,'source':12,'auto_engage':'Off'})
    assert review.status_code == 200,review.text
    dev._write.assert_not_called()
    body=dict(token=review.json()['token'],external_audio_muted=True,target_confirmed=True)
    result=client.post('/api/controllers/send',json=body)
    assert result.status_code == 200,result.text
    assert result.json()['ok'] and not result.json()['stored'] and slots[0][0]==12
    assert client.post('/api/controllers/send',json=body).status_code == 409
    assert dev._write.call_count == 1


def test_upstream_named_parameter_capability_does_not_enable_afx3_writes(api):
    from devices.axefx3.adapter import AxeFxIII
    client, dev, _ = api
    dev.capabilities.return_value = AxeFxIII.capabilities(dev)
    assert dev.capabilities().has_named_params is False
    client.post('/api/controllers/connect')
    errors, _ = server.validate_action(server.Action(kind='set_device_param', param='GAIN', value=96))
    assert errors and 'has no named parameters' in errors[0]
    assert client.post('/api/apply', json={'actions':[
        {'kind':'set_device_param','param':'GAIN','value':96}]}).status_code == 409
    dev._write.assert_not_called()


@pytest.mark.parametrize('body',[{'effect_id':True,'source':12},{'effect_id':102,'source':6},
    {'effect_id':58,'source':12},{'effect_id':95,'source':12,'auto_engage':'Slow Pos'},
    {'effect_id':102,'source':12,'auto_engage':'Fast Pos'},
    {'effect_id':95,'source':12,'cc':6},{'effect_id':95,'source':0}])
def test_unverified_or_coerced_choices_are_refused(api,body):
    client,dev,_=api
    client.post('/api/controllers/connect')
    assert client.post('/api/controllers/review',json=body).status_code in (409,422)
    dev._write.assert_not_called()


def test_gig_lock_and_pending_plan_refuse_connection(api):
    client,dev,_=api
    server._gig_mode['on']=True
    assert client.post('/api/controllers/connect').status_code == 423
    server._gig_mode['on']=False
    server._plan_revisions['pending']={}
    assert client.post('/api/controllers/connect').status_code == 409
    dev.status_dump.assert_not_called()


def test_connection_failure_never_falls_back_to_fm9(api,monkeypatch):
    client,dev,_=api
    monkeypatch.setattr(server._controller_reviews,'connect_device',Mock(side_effect=OSError('unplugged')))
    assert client.post('/api/controllers/connect').status_code == 503
    assert server.device_context().kind == 'axefx3' and server.device_context().adapter is None
    state = client.get('/api/controllers/state').json()
    assert not state['connected'] and state['controller_selected']
    assert client.get('/api/state').status_code == 409
    assert client.post('/api/controllers/disconnect').status_code == 200


def test_main_url_opens_tone_workspace_for_fx3_and_keeps_fm9_home(api):
    client,dev,_=api
    initial=client.get('/',follow_redirects=False)
    assert initial.status_code==200 and 'afx3-workspace' not in initial.text
    client.post('/api/controllers/connect')
    response=client.get('/',follow_redirects=False)
    assert response.status_code==307 and response.headers['location']=='/axefx3'
    dev._write.assert_not_called()


def test_no_automatic_retry_when_write_fails(api):
    client,dev,_=api
    client.post('/api/controllers/connect')
    token=client.post('/api/controllers/review',json={'effect_id':95,'source':13}).json()['token']
    dev._write.side_effect=OSError('disconnected after send')
    body=dict(token=token,external_audio_muted=True,target_confirmed=True)
    result=client.post('/api/controllers/send',json=body).json()
    assert not result['ok'] and not result['stored']
    assert client.post('/api/controllers/send',json=body).status_code == 409
    assert dev._write.call_count == 1


def test_active_audition_cannot_trigger_an_implicit_restore(api):
    client,dev,_=api
    server._audition['open']=True
    assert client.post('/api/controllers/connect').status_code == 409
    server.drop_fm9.assert_not_called()
    dev._write.assert_not_called()


def test_disconnect_discards_pending_controller_ticket(api):
    client,dev,_=api
    client.post('/api/controllers/connect')
    token=client.post('/api/controllers/review',json={'effect_id':95,'source':13}).json()['token']
    client.post('/api/controllers/disconnect')
    client.post('/api/controllers/connect')
    assert client.post('/api/controllers/send',json=dict(token=token,external_audio_muted=True,target_confirmed=True)).status_code == 409
    dev._write.assert_not_called()


def test_another_website_cannot_connect_or_discard(api):
    client,dev,_=api
    for path in ('connect','disconnect','review','send','discard'):
        assert client.post('/api/controllers/'+path,json={},headers={'Origin':'https://unrelated.example'}).status_code == 403
    assert server.device_context().kind == 'fm9'
    dev._write.assert_not_called()
    assert client.post('/api/controllers/connect',json={},headers={'Origin':'http://testserver'}).status_code == 200


@pytest.mark.parametrize('token',['', 'niet-geldig-\u00e9', 'x'*129, 42])
def test_malformed_tickets_are_validation_errors_not_server_errors(api,token):
    client,dev,_=api
    client.post('/api/controllers/connect')
    client.post('/api/controllers/review',json={'effect_id':95,'source':13})
    assert client.post('/api/controllers/send',json=dict(token=token,external_audio_muted=True,target_confirmed=True)).status_code == 422
    dev._write.assert_not_called()

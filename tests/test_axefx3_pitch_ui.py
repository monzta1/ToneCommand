"""Existing controller HTTP surface, scripted device only. No physical MIDI."""
import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3 import pitch_control as pitch
from devices.axefx3.controller_review import Reviews, inspect
from tests.test_axefx3_pitch_control import rig


@pytest.fixture
def api(rig,monkeypatch):
    monkeypatch.setattr(pitch,'RELEASED',True)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',rig.reg,rig,'Axe-Fx III'))
    monkeypatch.setattr(server,'_selected_kind',{'kind':'axefx3'})
    monkeypatch.setattr(server,'_gig_mode',{'on':False})
    monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    server._controller_reviews.clear()
    with TestClient(server.app) as client:yield client,rig
    server._controller_reviews.clear()


def review(client):
    response=client.post('/api/controllers/review',json={'effect_id':110,'source':13,'auto_engage':'Off'})
    assert response.status_code==200,response.text
    return response.json()


def send(client,proposal):
    return client.post('/api/controllers/send',json=dict(token=proposal['token'],external_audio_muted=True,target_confirmed=True))


def test_pitch_read_review_send_and_replay(api):
    client,rig=api
    state=client.get('/api/controllers/state')
    assert state.status_code==200,state.text
    assert state.json()['targets'][0]['operation']=='pitch_setup'
    proposal=review(client)
    assert proposal['expires_in']==60 and proposal['operation']=='pitch_setup'
    assert '0 to toe +12' in proposal['setup'] and not rig.frames
    result=send(client,proposal)
    assert result.status_code==200,result.text
    assert result.json()['ok'] and not result.json()['stored']
    assert rig.mods[0][0]==13 and rig.mods[0][17]==1
    count=len(rig.frames)
    assert send(client,proposal).status_code==409 and len(rig.frames)==count


@pytest.mark.parametrize('body',[
    {'effect_id':110,'source':12,'auto_engage':'Fast Pos'},
    {'effect_id':110,'source':12,'transpose':24},
    {'effect_id':110,'source':6}, {'effect_id':110,'source':True},
    {'effect_id':110,'source':12.0}, {'effect_id':111,'source':12}])
def test_unmeasured_choices_do_not_send(api,body):
    client,rig=api
    assert client.post('/api/controllers/review',json=body).status_code in (409,422)
    assert not rig.frames


def test_discard_invalidates_the_underlying_pitch_review(api):
    client,rig=api;proposal=review(client)
    writer=server._controller_reviews.pending['pitch_writer']
    assert client.post('/api/controllers/discard').status_code==200
    assert writer.pending is None and send(client,proposal).status_code==409
    assert not rig.frames


def test_pitch_failure_has_no_retry_and_blocks_a_fresh_writer(api):
    client,rig=api;proposal=review(client);rig.fault='other_block'
    result=send(client,proposal)
    assert result.status_code==409 and 'uncertain' in result.json()['detail']
    assert len(rig.frames)==1 and rig._pitch_uncertain
    assert send(client,proposal).status_code==409
    assert client.post('/api/controllers/review',json={'effect_id':110,'source':12}).status_code==409
    assert len(rig.frames)==1


@pytest.mark.parametrize('field,value',[('firmware','32.06'),('hardware_variant','mk1')])
def test_wrong_profile_remains_visible_but_blocked(api,field,value):
    client,rig=api;setattr(rig.reg,field,value)
    state=client.get('/api/controllers/state')
    assert state.status_code==200 and not state.json()['targets'][0]['writable']
    assert client.post('/api/controllers/review',json={'effect_id':110,'source':12}).status_code==409
    assert not rig.frames


def test_gig_lock_pending_plan_and_cross_origin_block_pitch(api):
    client,rig=api
    server._gig_mode['on']=True
    assert client.post('/api/controllers/review',json={'effect_id':110,'source':12}).status_code==423
    server._gig_mode['on']=False;server._plan_revisions['pending']={}
    assert client.post('/api/controllers/review',json={'effect_id':110,'source':12}).status_code==409
    assert client.post('/api/controllers/discard',headers={'Origin':'https://other.example'}).status_code==403
    assert not rig.frames


def test_no_free_slot_fails_during_review_not_after_staging(api):
    client,rig=api
    for w in rig.mods:w[0]=12;w[8]=94;w[9]=5
    assert client.post('/api/controllers/review',json={'effect_id':110,'source':12}).status_code==409
    assert not rig.frames

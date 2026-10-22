"""Navigation is explicit, state-bound and never a planner reload action."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from devices.axefx3 import navigation,fw33_profile,fw33,protocol
from tests.test_axefx3_text_planning import api,dev,design
import server


def setup(dev):
    dev._edit_target=None
    dev.slot_name.side_effect=lambda n:SimpleNamespace(number=n,name=f'Preset {n}',empty=False)
    dev.scan_slots.side_effect=lambda start,end:(dev.slot_name(n) for n in range(start,end+1))


def test_library_and_prepare_do_not_write(api,dev):
    client,_=api;setup(dev)
    r=client.get('/api/axefx3/navigation/presets?start=321&end=329')
    assert r.status_code==200 and len(r.json()['slots'])==9 and r.json()['readonly']
    r=client.post('/api/axefx3/navigation/prepare',json=dict(kind='preset',value=325,expected_preset=324,expected_scene=1))
    assert r.status_code==200 and not r.json()['hardware_written']
    assert r.json()['destination']==dict(number=325,name='Preset 325')
    dev._write.assert_not_called();dev.outp.send.assert_not_called()


@pytest.mark.parametrize('kind,value,discard',[('scene',2,False),('preset',325,True)])
def test_explicit_selection_is_single_use_and_requires_mute(api,dev,monkeypatch,kind,value,discard):
    client,_=api;setup(dev)
    switch=Mock(return_value=value if kind=='scene' else (value,'Loaded'))
    monkeypatch.setattr(navigation,'switch_'+kind,switch)
    def prepare():
        r=client.post('/api/axefx3/navigation/prepare',json=dict(kind=kind,value=value,expected_preset=324,expected_scene=1))
        assert r.status_code==200,r.text
        return r.json()['token']
    body=dict(token=prepare(),external_audio_muted=False,confirm_discard_edits=discard)
    assert client.post('/api/axefx3/navigation/select',json=body).status_code==403
    switch.assert_not_called()
    body['token']=prepare();body['external_audio_muted']=True
    r=client.post('/api/axefx3/navigation/select',json=body)
    assert r.status_code==200 and r.json()['ok'] and not r.json()['stored']
    assert client.post('/api/axefx3/navigation/select',json=body).status_code==409
    switch.assert_called_once()


def test_preset_discard_ack_is_mandatory_and_changed_state_stops(api,dev,monkeypatch):
    client,_=api;setup(dev)
    switch=Mock();monkeypatch.setattr(navigation,'switch_preset',switch)
    def prepare():return client.post('/api/axefx3/navigation/prepare',json=dict(kind='preset',value=325,expected_preset=324,expected_scene=1)).json()['token']
    body=dict(token=prepare(),external_audio_muted=True,confirm_discard_edits=False)
    assert client.post('/api/axefx3/navigation/select',json=body).status_code==403
    body.update(token=prepare(),confirm_discard_edits=True)
    dev.current_preset.return_value=(324,'Edited')
    assert client.post('/api/axefx3/navigation/select',json=body).status_code==409
    switch.assert_not_called()


@pytest.mark.parametrize('field,value',[('value',True),('value',512),('expected_preset',True),('value',0)])
def test_invalid_or_stale_scene_choice_does_not_write(api,dev,field,value):
    client,_=api;setup(dev)
    body=dict(kind='scene',value=2,expected_preset=324,expected_scene=1);body[field]=value
    assert client.post('/api/axefx3/navigation/prepare',json=body).status_code in (409,422)
    dev._write.assert_not_called()


def test_incomplete_scan_is_not_cached_as_complete(api,dev):
    client,_=api;setup(dev);dev.scan_slots.side_effect=lambda start,end:iter([])
    assert client.get('/api/axefx3/navigation/presets?start=321&end=329').status_code==409
    dev.outp.send.assert_not_called()


def test_unreadable_identity_and_scene_are_not_navigation_proof(api,dev):
    client,_=api;setup(dev)
    dev.firmware_label.return_value='unknown'
    assert client.get('/api/axefx3/navigation/presets').status_code==409
    dev.firmware_label.return_value=dev.reg.firmware
    dev.current_scene.return_value=True
    assert client.post('/api/axefx3/navigation/prepare',json=dict(
        kind='scene',value=2,expected_preset=324,expected_scene=1)).status_code==409
    dev._write.assert_not_called();dev.outp.send.assert_not_called()


@pytest.mark.parametrize('kind,value',[('scene',2),('preset',325)])
def test_gig_lock_and_other_plan_block_navigation(api,dev,monkeypatch,kind,value):
    client,_=api;setup(dev)
    body=dict(kind=kind,value=value,expected_preset=324,expected_scene=1)
    monkeypatch.setitem(server._gig_mode,'on',True)
    assert client.post('/api/axefx3/navigation/prepare',json=body).status_code==423
    monkeypatch.setitem(server._gig_mode,'on',False)
    monkeypatch.setitem(server._plan_revisions,'other',1)
    assert client.post('/api/axefx3/navigation/prepare',json=body).status_code==409
    dev._write.assert_not_called();dev.outp.send.assert_not_called()


def test_expired_or_changed_connection_ticket(dev):
    setup(dev);clock=Mock(return_value=0);reviews=navigation.Reviews(clock)
    body=navigation.Prepare(kind='preset',value=325,expected_preset=324,expected_scene=1)
    ticket=reviews.prepare(dev,body);clock.return_value=121
    with pytest.raises(ValueError,match='expired'):
        reviews.select(dev,navigation.Select(token=ticket['token'],external_audio_muted=True,confirm_discard_edits=True))
    dev.outp.send.assert_not_called()


def test_native_bank_pc_sequence_and_failed_readback_are_not_retried(dev,monkeypatch):
    setup(dev);monkeypatch.setattr(navigation.time,'sleep',lambda _:None)
    dev.current_preset.side_effect=[(324,'Empty'),(325,'Loaded')]
    assert navigation.switch_preset(dev,325,(324,'Empty'),external_audio_muted=True,confirm_discard_edits=True)==(325,'Loaded')
    messages=[c.args[0] for c in dev.outp.send.call_args_list]
    assert [(m.type,getattr(m,'control',None),getattr(m,'value',None),getattr(m,'program',None)) for m in messages]==[
        ('control_change',0,2,None),('program_change',None,None,69)]
    dev.outp.send.reset_mock();dev.current_preset.side_effect=None;dev.current_preset.return_value=(324,'Empty')
    with pytest.raises(RuntimeError,match='No retry'):
        navigation.switch_preset(dev,325,(324,'Empty'),external_audio_muted=True,confirm_discard_edits=True)
    assert dev.outp.send.call_count==2


def test_fw33_manual_scene_permit_does_not_promote_build_scope():
    device=SimpleNamespace(reg=SimpleNamespace(firmware=fw33_profile.KEY))
    frame=protocol.envelope(0x0c,[7])
    with pytest.raises(PermissionError):fw33.check_frame(device,frame)
    device._navigation_frame_permit=tuple(frame);fw33.check_frame(device,frame)
    with pytest.raises(PermissionError):fw33.check_frame(device,protocol.envelope(0x0c,[6]))
    assert fw33_profile.NAM_SCENES=={1,2}

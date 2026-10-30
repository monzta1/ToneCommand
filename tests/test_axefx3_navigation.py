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


@pytest.mark.parametrize('variant,count',[('mk1',512),('mk2',1024),(None,512)])
def test_default_api_library_and_state_report_documented_capacity(api,dev,variant,count):
    from devices.axefx3 import profile
    client,_=api;setup(dev);profile.apply(dev.reg,variant)
    result=client.get('/api/axefx3/navigation/presets')
    assert result.status_code==200,result.text
    assert result.json()['preset_count']==count
    assert [s['number'] for s in result.json()['slots']]==list(range(count))
    assert client.get('/api/axefx3/state').json()['profile']['preset_count']==count
    dev.outp.send.assert_not_called()


@pytest.mark.parametrize('variant,number,allowed',[('mk1',511,True),('mk1',512,False),
    ('mk2',512,True),('mk2',1023,True),('mk2',1024,False)])
def test_navigation_review_upper_bounds_are_chassis_bound(api,dev,variant,number,allowed):
    from devices.axefx3 import profile
    client,_=api;setup(dev);profile.apply(dev.reg,variant)
    result=client.post('/api/axefx3/navigation/prepare',json=dict(kind='preset',value=number,
        expected_preset=324,expected_scene=1))
    assert (result.status_code==200)==allowed,result.text
    if allowed:assert result.json()['destination']['number']==number
    dev.outp.send.assert_not_called()


@pytest.mark.parametrize('number,bank,pc',[(511,3,127),(512,4,0),(1023,7,127)])
def test_mk2_upper_bank_selection_is_one_cc_pc_pair_with_readback(dev,monkeypatch,number,bank,pc):
    from devices.axefx3 import profile
    setup(dev);profile.apply(dev.reg,'mk2');monkeypatch.setattr(navigation.time,'sleep',lambda _:None)
    dev.current_preset.side_effect=[(324,'Empty'),(number,'Loaded')]
    assert navigation.switch_preset(dev,number,(324,'Empty'),external_audio_muted=True,
                                    confirm_discard_edits=True)==(number,'Loaded')
    assert [(c.args[0].type,c.args[0].bytes()) for c in dev.outp.send.call_args_list]==[
        ('control_change',[0xb0,0,bank]),('program_change',[0xc0,pc])]


def test_switching_chassis_after_review_does_not_allow_mk1_upper_navigation(dev,monkeypatch):
    from devices.axefx3 import profile
    setup(dev);profile.apply(dev.reg,'mk2')
    reviews=navigation.Reviews()
    review=reviews.prepare(dev,navigation.Prepare(kind='preset',value=1023,expected_preset=324,expected_scene=1))
    profile.apply(dev.reg,'mk1')
    with pytest.raises(ValueError):
        reviews.select(dev,navigation.Select(token=review['token'],external_audio_muted=True,confirm_discard_edits=True))
    dev.outp.send.assert_not_called()


def test_capacity_does_not_authorize_store_to_an_unlisted_slot(dev):
    from devices.axefx3 import profile,store_review
    from fm9.device import get_store_slots
    setup(dev);profile.apply(dev.reg,'mk2')
    original=set(get_store_slots())
    assert 1023 not in original
    with pytest.raises(ValueError,match='allowlist'):store_review.Stores().prepare(dev,1023)
    assert set(get_store_slots())==original
    dev.outp.send.assert_not_called()

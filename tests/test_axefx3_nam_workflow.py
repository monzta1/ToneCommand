"""Complete offline NAM planning/review/Store boundary, no real AI or MIDI."""
from dataclasses import replace
from unittest.mock import Mock

import pytest
import server
from fm9.protocol import SlotName
from devices.axefx3.nam_memory import Capture
from devices.axefx3 import modifiers, fw33, store_review, tone_review
from tests.test_axefx3_fw33 import fake, design as nam_design
from tests.test_axefx3_text_planning import api


@pytest.fixture
def design():
    return nam_design(2)


@pytest.fixture
def dev(monkeypatch):
    d=fake(True)
    d.current_preset.return_value=(133,'AI-Test NAM')
    d.scene_name.side_effect=lambda number:(number,f'Scene {number}')
    d.slot_name.return_value=SlotName(133,'Old stored name')
    d.store_preset.return_value=(133,'AI-Test NAM')
    monkeypatch.setattr(modifiers,'inspect',lambda dev:[dict(active=False,words=[0]*25) for _ in range(32)])
    monkeypatch.setattr(fw33,'platform_supported',lambda:True)
    server._controller_reviews.clear()
    return d


BODY=dict(prompt='Damage Inc rhythm and solo with the installed capture',expected_preset=133,scenes=2)
CONSENT=dict(target_confirmed=True,external_audio_muted=True)


def test_nam_selected_provider_schema_review_send_without_cab_catalog(api,dev):
    client,ask=api
    assert not dev.reg.cab_catalog.names
    response=client.post('/api/axefx3/plan',json=BODY)
    assert response.status_code==200,response.text
    proposal=response.json()
    assert proposal['mode']=='nam' and len(proposal['scenes'])==2
    assert proposal['capture']['bytes']==65536
    assert 'Synthetic' in ask.call_args.args[2]
    assert 'nam' in ask.call_args.kwargs['schema']['$defs']['Scene']['properties']
    dev.set_param_display.assert_not_called()
    assert client.post('/api/axefx3/send',json=dict(token=proposal['token'],**CONSENT)).json()['ok']
    assert dev.set_param_display.called
    dev.install_nam_slot1.assert_not_called()
    dev.store_preset.assert_not_called()
    assert client.post('/api/axefx3/send',json=dict(token=proposal['token'],**CONSENT)).status_code==409


def test_explicit_installed_slot_is_in_design_review_and_send(api,dev):
    client,ask=api
    dev.read_nam_slot.side_effect=lambda slot:Capture('Chosen capture',slot,'b'*64,65536)
    proposal=client.post('/api/axefx3/plan',json=dict(**BODY,nam_slot=250))
    assert proposal.status_code==200,proposal.text
    plan=proposal.json()
    assert plan['capture']['slot']==250 and 'Chosen capture' in ask.call_args.args[2]
    assert [a['value'] for a in plan['actions'] if a['kind']=='select_nam']==[250,250]
    assert client.post('/api/axefx3/send',json=dict(token=plan['token'],**CONSENT)).json()['ok']
    assert [call.args[0] for call in dev.select_nam_slot.call_args_list]==[250,250]
    dev.install_nam_slot.assert_not_called();dev.store_preset.assert_not_called()


def test_selected_memory_change_after_review_stops_before_any_write(api,dev):
    client,_=api
    dev.read_nam_slot.side_effect=lambda slot:Capture('Chosen',slot,'a'*64,65536)
    plan=client.post('/api/axefx3/plan',json=dict(**BODY,nam_slot=256)).json()
    dev.read_nam_slot.side_effect=lambda slot:Capture('Chosen',slot,'b'*64,65536)
    result=client.post('/api/axefx3/send',json=dict(token=plan['token'],**CONSENT))
    assert result.status_code==409
    dev.select_nam_slot.assert_not_called();dev.edit_session.assert_not_called()


@pytest.mark.parametrize('slot',[0,257,True,250.0,'250'])
def test_invalid_selected_slot_never_calls_ai(api,dev,slot):
    client,ask=api
    assert client.post('/api/axefx3/plan',json=dict(**BODY,nam_slot=slot)).status_code==422
    ask.assert_not_called();dev.select_nam_slot.assert_not_called()


def test_empty_selected_slot_refuses_before_ai(api,dev):
    client,ask=api
    dev.read_nam_slot.return_value=Capture('<EMPTY>',250,'a'*64,65536,True)
    assert client.post('/api/axefx3/plan',json=dict(**BODY,nam_slot=250)).status_code==409
    ask.assert_not_called();dev.select_nam_slot.assert_not_called()


def test_snapshot_uses_actual_current_slot_and_fingerprints_all_channel_captures(dev):
    words=[0]*72;words[0]=249;words[18]=255
    base=dev.bulk_read.side_effect
    dev.bulk_read.side_effect=lambda eid: list(words) if eid==206 else base(eid)
    dev.read_nam_slot.side_effect=lambda slot:Capture('Chosen',slot,'b'*64,65536)
    state=tone_review.snapshot(dev)
    assert state['nam']['slot']==250
    assert set(state['nam_captures'])=={1,250,256}
    assert dev.read_nam_slot1.called


def test_measured_zero_choice_can_be_prepared_without_execution(dev):
    from devices.axefx3 import executor,nam_planning,fw33_profile
    words=[0]*72;words[0]=249
    base=dev.bulk_read.side_effect
    dev.bulk_read.side_effect=lambda eid: list(words) if eid==206 else base(eid)
    dev.read_nam_slot.side_effect=lambda slot:Capture('Chosen',slot,'b'*64,65536)
    plan=nam_planning.compile_design(dev.reg,nam_design(),list(fw33_profile.NAM_ROUTE),1,
                                    dict(name='Synthetic',slot=1,bytes=65536,sha256='a'*64))
    executor.prepare(dev,plan['actions'],plan['required_route'],133)
    dev.edit_session.assert_not_called();dev.select_nam_slot.assert_not_called()


def test_measured_zero_choice_is_available_in_review_from_nonzero_current_slot(api,dev):
    client,ask=api
    base=dev.bulk_read.side_effect
    words=[0]*72;words[0]=249
    dev.bulk_read.side_effect=lambda eid: list(words) if eid==206 else base(eid)
    dev.read_nam_slot.side_effect=lambda slot:Capture('Chosen',slot,'b'*64,65536)
    result=client.post('/api/axefx3/plan',json=dict(**BODY,nam_slot=1))
    assert result.status_code==200,result.text
    assert result.json()['capture']['slot']==1
    assert [a['value'] for a in result.json()['actions'] if a['kind']=='select_nam']==[1,1]
    assert ask.called
    dev.select_nam_slot.assert_not_called()
    sent=client.post('/api/axefx3/send',json=dict(token=result.json()['token'],**CONSENT))
    assert sent.status_code==200,sent.text
    assert sent.json()['ok']
    assert [c.args[0] for c in dev.select_nam_slot.call_args_list]==[1,1]
    dev.install_nam_slot1.assert_not_called();dev.store_preset.assert_not_called()


@pytest.mark.parametrize('change',['capture','preset','scene','bulk','variant'])
def test_nam_change_after_review_refuses_before_any_set(api,dev,change):
    client,_=api
    proposal=client.post('/api/axefx3/plan',json=BODY).json()
    if change=='capture':dev.read_nam_slot1.return_value=replace(dev.read_nam_slot1.return_value,payload_sha256='b'*64)
    if change=='preset':dev.current_preset.return_value=(134,'Other')
    if change=='scene':dev.current_scene.return_value=2
    if change=='bulk':dev.bulk_read.side_effect=lambda eid:[1]*72
    if change=='variant':dev.reg.hardware_variant='mk1'
    response=client.post('/api/axefx3/send',json=dict(token=proposal['token'],**CONSENT))
    assert response.status_code==409,response.text
    dev.edit_session.assert_not_called();dev.set_param_display.assert_not_called()


@pytest.mark.parametrize('variant',[None,'mk1'])
def test_fw33_unmeasured_variant_cannot_reach_ai(api,dev,variant):
    client,ask=api;dev.reg.hardware_variant=variant
    assert client.post('/api/axefx3/plan',json=BODY).status_code==409
    ask.assert_not_called();dev.read_nam_slot1.assert_not_called()


def test_empty_two_scene_request_refuses_before_ai(api,dev):
    client,ask=api;dev.read_grid.return_value=[];dev.status_dump.return_value=[]
    assert client.post('/api/axefx3/plan',json=BODY).status_code==409
    ask.assert_not_called();dev.set_param_display.assert_not_called()


def test_missing_capture_and_expired_review_are_not_send_authority(dev):
    before=tone_review.snapshot(dev)
    dev.read_nam_slot1.return_value=replace(dev.read_nam_slot1.return_value,byte_count=20)
    from devices.axefx3 import nam_planning,fw33_profile
    with pytest.raises(ValueError):nam_planning.compile_design(dev.reg,nam_design(),list(fw33_profile.NAM_ROUTE),1,tone_review.snapshot(dev)['nam'])
    dev.read_nam_slot1.return_value=replace(dev.read_nam_slot1.return_value,byte_count=65536)
    clock=Mock(return_value=0)
    reviews=tone_review.Reviews(clock)
    plan=nam_planning.compile_design(dev.reg,nam_design(),list(fw33_profile.NAM_ROUTE),1,before['nam'])
    proposal=reviews.prepare(dev,plan,before)
    clock.return_value=600
    with pytest.raises(ValueError,match='expired'):reviews.send(dev,proposal['token'],**CONSENT)
    dev.edit_session.assert_not_called()


def test_store_preview_is_readonly_and_needs_two_separate_acknowledgments(dev):
    stores=store_review.Stores()
    review=stores.prepare(dev,133)
    assert review['readonly'] and review['permanent'] and review['replaces']=='Old stored name'
    dev.store_preset.assert_not_called()
    for mute,flash in [(False,False),(True,False),(False,True),(1,True),(True,1)]:
        with pytest.raises(PermissionError):stores.send(dev,review['token'],mute,flash)
    result=stores.send(dev,review['token'],True,True)
    assert result['stored'] and not result['reloaded'] and not result['audio_verified']
    assert dev.store_preset.call_args.args==(133,)
    with pytest.raises(ValueError):stores.send(dev,review['token'],True,True)


@pytest.mark.parametrize('change',['capture','preset','stored','expiry','connection','variant'])
def test_store_stale_ticket_never_stores(dev,change):
    stores=store_review.Stores();review=stores.prepare(dev,133)
    selected=dev
    if change=='capture':dev.read_nam_slot1.return_value=replace(dev.read_nam_slot1.return_value,payload_sha256='c'*64)
    if change=='preset':dev.current_preset.return_value=(134,'Other')
    if change=='stored':dev.slot_name.return_value=SlotName(133,'Different stored name')
    if change=='expiry':stores.pending['expires']=0
    if change=='connection':selected=fake(True)
    if change=='variant':dev.reg.hardware_variant='mk1'
    with pytest.raises(ValueError):stores.send(selected,review['token'],True,True)
    dev.store_preset.assert_not_called();dev.edit_session.assert_not_called()


def test_store_api_rejects_wrong_acks_and_gig_lock(api,dev):
    client,_=api
    headers={'X-ToneCommand':'1'}
    response=client.post('/api/axefx3/store/prepare',json={'expected_preset':133},headers=headers)
    assert response.status_code==200,response.text
    token=response.json()['token']
    assert client.post('/api/axefx3/store',json={'token':token},headers=headers).status_code==409
    assert client.post('/api/axefx3/store',json=dict(token=token,external_audio_muted=1,confirm_permanent_write=True),headers=headers).status_code==422
    server._gig_mode['on']=True
    assert client.post('/api/axefx3/store',json=dict(token=token,external_audio_muted=True,confirm_permanent_write=True),headers=headers).status_code==423
    dev.store_preset.assert_not_called()

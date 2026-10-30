"""Synthetic occupancy/address tests. No private captures/model data."""
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from fm9 import protocol as p
from devices.axefx3 import nam_slots, nam_memory, fw33, tone3000 as t3
from tests.test_axefx3_nam_install import setup
from tests.test_axefx3_nam_conversion import compile_source
import server


def reply(name):
    raw=name.encode('ascii')+bytes(238-len(name))
    bits=''.join(f'{b:08b}' for b in raw)
    packed=[int(bits[i:i+7],2) for i in range(0,len(bits),7)]
    return p.envelope(1,[8,1,0,0,0,0,42,0,0,0,0,0,0,16,2,*packed,*([0]*39)],model=16)[1:-1]


@pytest.mark.parametrize('slot',range(1,257))
def test_all_name_and_memory_addresses_are_bounded_and_roundtrip(slot):
    frame=nam_slots.name_request(slot)
    assert nam_slots.is_name_request(frame)
    assert frame[12:14]==list(p.encode14(slot-1))
    assert nam_slots.memory_request(slot)==p.envelope(28,[0,*p.encode14(slot-1)],model=16)
    compiled=compile_source()
    frames=compiled.frames(slot)
    capture=nam_memory.parse_export(frames,slot=slot)
    assert capture.slot==slot and not capture.empty
    assert capture.payload_sha256==compiled.payload_sha256


@pytest.mark.parametrize('slot',[0,257,-1,True,1.0,'250',None])
def test_invalid_slot_never_builds_a_frame(slot):
    with pytest.raises(ValueError):nam_slots.name_request(slot)
    with pytest.raises(ValueError):nam_slots.memory_request(slot)
    with pytest.raises(ValueError):compile_source().frames(slot)


def test_name_empty_is_explicit_not_blank_timeout_or_named_empty():
    assert nam_slots.parse_name(reply('<EMPTY>'),250)==nam_slots.Slot(250,'<EMPTY>',False)
    assert nam_slots.parse_name(reply('EMPTY'),250).occupied
    assert nam_slots.parse_name(reply('Synthetic'),256).occupied
    assert nam_slots.parse_name(reply(''),250) is None
    assert nam_slots.parse_name(reply('x'*28),250) is None
    assert nam_slots.parse_name(reply('Synthetic')[:-1],250) is None


@pytest.mark.parametrize('context',[0,42,206])
def test_name_reply_context_is_not_the_slot_or_occupancy(context):
    data=reply('<EMPTY>')
    data[11:18]=[*p.encode14(context),0,0,0,0,0]
    data[-1]=p.checksum(data[:-1])
    assert nam_slots.parse_name(data,250)==nam_slots.Slot(250,'<EMPTY>',False)
    data[18]=15
    data[-1]=p.checksum(data[:-1])
    assert nam_slots.parse_name(data,250) is None


def test_inventory_stops_at_first_missing_reply_without_skipping():
    dev=Mock();dev._lock=__import__('threading').RLock()
    dev.reg.firmware=__import__('devices.axefx3.fw33_profile',fromlist=['KEY']).KEY
    dev.reg.hardware_variant='mk2';dev.firmware_label.return_value=dev.reg.firmware
    dev._request.side_effect=[nam_slots.Slot(1,'Synthetic',True),None]
    with pytest.raises(ValueError,match='002'):nam_slots.scan(dev)
    assert dev._request.call_count==2


def erased(slot):
    words=[0xffffffff]*16384
    frames=[p.envelope(84,nam_slots.header(slot),model=16)]
    for start in range(0,len(words),256):
        data=[0,2]
        for word in words[start:start+256]:data.extend((word>>(7*i))&127 for i in range(5))
        frames.append(p.envelope(85,data,model=16))
    frames.append(p.envelope(86,[0]*5,model=16))
    return frames


def test_empty_requires_full_erased_memory_and_correct_target():
    frames=erased(256)
    capture=nam_memory.parse_export(frames,slot=256,allow_empty=True)
    assert capture.empty and capture.name=='<EMPTY>' and capture.byte_count==65536
    with pytest.raises(ValueError):nam_memory.parse_export(frames,slot=256)
    with pytest.raises(ValueError):nam_memory.parse_export(frames,slot=250,allow_empty=True)
    with pytest.raises(ValueError):nam_memory.parse_export(frames[:-2],slot=256,allow_empty=True)
    assert nam_memory.parse_export(compile_source().frames(256),slot=256,allow_empty=True).empty is False


def inventory_rows(occupied):
    return [nam_slots.Slot(s,'Synthetic' if s in occupied else '<EMPTY>',s in occupied) for s in range(1,257)]


@pytest.mark.parametrize('occupied,first',[({1},2),(set(),1),(set(range(1,257)),None),({1,2,3,256},4)])
def test_first_free_is_suggestion_only_and_never_installs(setup,occupied,first):
    service,dev,*_=setup
    dev.scan_nam_slots.return_value=inventory_rows(occupied)
    result=service.inventory()
    assert result['first_available']==first and len(result['slots'])==256
    assert result['readonly'] and result['complete']
    dev.install_nam_slot.assert_not_called()


def test_inventory_incomplete_is_not_a_free_slot(setup):
    service,dev,*_=setup
    dev.scan_nam_slots.return_value=inventory_rows({1})[:-1]
    with pytest.raises(t3.ToneError,match='Incomplete'):service.inventory()


@pytest.mark.parametrize('slot',[250,256])
@pytest.mark.parametrize('occupied',[True,False])
def test_explicit_slot_preview_backup_commit_binds_exact_destination(setup,slot,occupied):
    service,dev,*_=setup
    frames=compile_source('Before').frames(slot) if occupied else erased(slot)
    before=nam_memory.parse_export(frames,slot=slot,allow_empty=True)
    dev.read_nam_slot.return_value=before;dev.export_nam_slot.return_value=(before,frames)
    result=service.prepare(456,326,slot)
    assert result['slot']==slot and result['existing_occupied']==occupied
    dev.install_nam_slot.assert_not_called()
    done=service.commit(result['prepared_id'],True,True,True)
    assert done['slot']==slot and done['installed']
    assert dev.install_nam_slot.call_args.args[0]==slot
    assert dev._nam_install_permit is None
    context=t3.client.planner_context()
    assert f'"slot": {slot}' in context
    assert 'does NOT select that capture in a preset' in context
    assert 'builder still requires independently read slot 001' in context


def test_changed_empty_slot_cannot_be_silently_occupied_or_retargeted(setup):
    service,dev,*_=setup
    before=nam_memory.parse_export(erased(250),slot=250,allow_empty=True)
    dev.read_nam_slot.return_value=before
    review=service.prepare(456,326,250)
    later=compile_source('Changed').frames(250)
    dev.export_nam_slot.return_value=(nam_memory.parse_export(later,slot=250),later)
    with pytest.raises(t3.ToneError,match='changed'):service.commit(review['prepared_id'],True,True,True)
    dev.install_nam_slot.assert_not_called()


def test_wrong_slot_readback_and_unreviewed_native_target_refused(setup):
    service,dev,*_=setup
    with pytest.raises(t3.ToneError,match='selected NAM'):service.prepare(456,326,250)


def test_route_requires_explicit_slot_and_local_header(setup,monkeypatch):
    service,dev,*_=setup
    monkeypatch.setattr(server._afx3_nam_installer,'inventory',service.inventory)
    dev.scan_nam_slots.return_value=inventory_rows({1})
    client=TestClient(server.app,base_url='http://127.0.0.1:8909',headers={'X-ToneCommand':'1'})
    path='/api/axefx3/tone3000/install/prepare'
    assert client.post(path,json=dict(model_id=456,expected_preset=326)).status_code==422
    for slot in (True,1.5,0,257,'250'):
        assert client.post(path,json=dict(model_id=456,expected_preset=326,slot=slot)).status_code==422
    assert client.get('/api/axefx3/tone3000/slots').json()['first_available']==2
    assert client.get('/api/axefx3/tone3000/slots',headers={'Origin':'https://evil.test'}).status_code==403


def test_native_write_cannot_use_an_unreviewed_slot(monkeypatch):
    from tests.test_axefx3_fw33 import fake
    dev=fake();dev._injected_ports=False
    compiled=compile_source()
    monkeypatch.setattr(fw33,'platform_supported',lambda:True)
    dev._nam_install_permit=(250,compiled.source_sha256,'a'*64)
    with pytest.raises(PermissionError,match='permit'):fw33.install(dev,compiled,'a'*64,slot=256)
    dev.outp.send.assert_not_called()

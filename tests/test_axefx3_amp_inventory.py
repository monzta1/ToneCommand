"""Firmware-specific factual inventory is not generic write authorization."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fm9 import protocol as shared
from devices.axefx3 import amp_inventory as inventory, amp_inventory_probe as fixture
from devices.axefx3 import amp_probe, fw33_profile, serial_build
from devices.axefx3.registry import Registry


def test_complete_exact_firmware_inventory():
    names=inventory.roster(fw33_profile.KEY)
    assert set(names)==set(range(336)) and len(set(names.values()))==336
    assert inventory.ordinal(fw33_profile.KEY,'59 Bassguy Bright')==0
    assert inventory.ordinal(fw33_profile.KEY,'Brit JVM Crunch Red')==335
    assert inventory.roster('33.00')=={} and inventory.roster('32.06')=={}
    with pytest.raises(ValueError):inventory.ordinal(fw33_profile.KEY,'Unknown amplifier')
    report=inventory.report(Registry(fw33_profile.KEY))
    assert report['count']==336 and not report['live_list_fetched']
    assert not report['generic_setter_enabled']


def test_all_models_are_available_to_schema_and_compiler():
    from devices.axefx3 import album_planning,album_build,executor
    reg=Registry(fw33_profile.KEY);reg.hardware_variant='mk2'
    raw=album_build.seed().model_dump()
    schema=album_planning.Album.model_json_schema()['properties']['amp_model']['enum']
    assert set(schema)==set(inventory.roster(reg.firmware).values())
    for ordinal,name in inventory.roster(reg.firmware).items():
        voice=album_planning.Album.model_validate({**raw['albums'][0],'amp_model':name})
        assert voice.amp_model==name
        resolved=executor.resolve(reg,dict(kind='set_type',block='DISTORT',instance=1,type_name=name))
        assert resolved.value==name
    with pytest.raises(ValueError):album_planning.Album.model_validate({**raw['albums'][0],'amp_model':'Unknown amplifier'})


def test_normal_review_send_accepts_zero_middle_and_last_models(monkeypatch):
    from test_axefx3_album_build import device,design
    from devices.axefx3 import album_planning,tone_review
    dev=device(monkeypatch);raw=design()
    ordinals=(0,100,200,335)
    for voice,ordinal in zip(raw['albums'],ordinals):voice['amp_model']=album_planning.MODELS[ordinal]
    plan=album_planning.compile_design(dev.reg,raw,list(serial_build.ROUTE),8)
    reviews=tone_review.Reviews()
    preview=reviews.prepare(dev,plan,tone_review.snapshot(dev,include_nam=False))
    dev._write.assert_not_called()
    result=reviews.send(dev,preview['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'] and not result['skipped']
    assert [dev._test_bulk[58][142*c] for c in range(4)]==list(ordinals)
    dev.store_preset.assert_not_called()


def test_full_inventory_does_not_authorize_unreviewed_raw_writes(monkeypatch):
    from test_axefx3_album_build import device
    from devices.axefx3.adapter import AxeFxIII
    dev=device(monkeypatch)
    for frame in fixture.frames():
        dev._approved_frame=frame
        assert not fixture.allowed(dev,frame)
        with pytest.raises((PermissionError,ValueError,KeyError)):
            AxeFxIII._send(dev,list(frame))
    dev.outp.send.assert_not_called()


@pytest.mark.parametrize('fault',['missing','duplicate','nonstring','nonascii','firmware','model','selector'])
def test_bad_inventory_fails_closed(monkeypatch,fault):
    data=json.loads(inventory.files('devices.axefx3').joinpath('data','fw33_amp_models.json').read_text(encoding='utf-8'))
    if fault=='missing':del data['models']['4']
    if fault=='duplicate':data['models']['4']=data['models']['5']
    if fault=='nonstring':data['models']['4']=[]
    if fault=='nonascii':data['models']['4']='\u2603'
    if fault=='firmware':data['firmware']='33.00'
    if fault=='model':data['model_byte']=17
    if fault=='selector':data['selector_pid']=1
    resource=Mock();resource.joinpath.return_value.read_text.return_value=json.dumps(data)
    monkeypatch.setattr(inventory,'files',lambda _:resource)
    with pytest.raises(ValueError):inventory.roster(fw33_profile.KEY)


def device(monkeypatch):
    reg=Registry(fw33_profile.KEY);reg.hardware_variant='mk2'
    state=dict(scene=1,grid=[shared.GridCell(r-1,c-1,e,s,m) for (r,c),(e,s,m)
        in serial_build.expected_grid().items()],bulk={58:[267]+[0]*567,42:[7]},
        modifiers=[dict(active=False)]*32,blocks=[shared.BlockStatus(58,True,0,4)],names=['intact'])
    dev=SimpleNamespace(reg=reg,_edit_target=322,_check_edit_target=Mock(),
        _amp_probe=None,_amp_probe_permit=None)
    displayed={'DISTORT_LEVEL':-20,'OUTPUT_LEVEL':-18}
    dev.get_param_display=lambda spec:displayed[spec.name]
    dev.get_bypass=lambda _:state['blocks'][0].bypassed
    monkeypatch.setattr(fixture.tone_review,'snapshot',lambda *a,**k:deepcopy(state))
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    return dev,state,displayed


def test_every_literal_model_including_zero_is_ordered_and_read_back(monkeypatch):
    dev,state,displayed=device(monkeypatch);probe=fixture.Probe(dev,fixture.frames())
    def write(frame):
        assert fixture.allowed(dev,frame) and amp_probe.allowed(dev,frame)
        state['bulk'][58][0]=probe.index
    dev._write=Mock(side_effect=write)
    for frame in fixture.frames():
        assert shared.checksum(frame[1:-2])==frame[-2]
        probe.write(frame)
    assert probe.index==336 and dev._write.call_count==336
    assert dev._amp_probe_permit is None and state['names']==['intact']
    with pytest.raises(PermissionError):probe.write(fixture.frames()[0])


@pytest.mark.parametrize('fault',['target','firmware','variant','grid','scene','bulk','channel','engaged','modifier','level','duplicate','sequence'])
def test_initial_fault_sends_nothing(monkeypatch,fault):
    dev,state,displayed=device(monkeypatch);dev._write=Mock();frames=fixture.frames()
    if fault=='target':dev._edit_target=326
    if fault=='firmware':dev.reg=Registry('32.06')
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='grid':state['grid']=[]
    if fault=='scene':state['scene']=2
    if fault=='bulk':state['bulk'][58]=[0]
    if fault=='channel':state['blocks']=[shared.BlockStatus(58,True,1,4)]
    if fault=='engaged':state['blocks']=[shared.BlockStatus(58,False,0,4)]
    if fault=='modifier':state['modifiers']=[dict(active=True)]
    if fault=='level':displayed['OUTPUT_LEVEL']=-6
    if fault=='duplicate':dev._amp_probe=object()
    if fault=='sequence':frames=frames[1:]
    with pytest.raises(PermissionError):fixture.Probe(dev,frames)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault',['literal','stale','send','readback','other_channel','grid','unbypass'])
def test_failure_consumes_measurement_without_retry(monkeypatch,fault):
    dev,state,displayed=device(monkeypatch);probe=fixture.Probe(dev,fixture.frames())
    def write(frame):
        if fault=='send':raise OSError('unknown send result')
        state['bulk'][58][0]=probe.index
        if fault=='readback':state['names']=['changed']
        if fault=='other_channel':state['bulk'][58][143]+=1
        if fault=='grid':state['grid']=[]
        if fault=='unbypass':state['blocks']=[shared.BlockStatus(58,False,0,4)]
    dev._write=Mock(side_effect=write)
    frame=fixture.frames()[fault=='literal']
    if fault=='stale':state['names']=['changed']
    with pytest.raises((PermissionError,ValueError,OSError)):probe.write(frame)
    count=dev._write.call_count
    with pytest.raises(PermissionError):probe.write(frame)
    assert dev._write.call_count==count and dev._amp_probe_permit is None


def test_quiet_level_is_reapplied_only_when_needed(monkeypatch):
    dev,state,displayed=device(monkeypatch);probe=fixture.Probe(dev,fixture.frames())
    displayed['DISTORT_LEVEL']=-6
    def stage(spec,value):
        assert value==-20 and probe.failed
        displayed[spec.name]=value;state['bulk'][58][21]=123
        return SimpleNamespace(ok=True)
    dev.set_param_display=Mock(side_effect=stage)
    dev._write=Mock(side_effect=lambda frame:state['bulk'][58].__setitem__(0,probe.index))
    probe.write(fixture.frames()[0])
    dev.set_param_display.assert_called_once()

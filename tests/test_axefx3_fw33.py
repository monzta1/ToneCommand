"""Offline port checks, synthetic state only. Not new hardware acceptance."""
from copy import deepcopy
from contextlib import nullcontext
from dataclasses import replace
import threading
from unittest.mock import Mock

import pytest
from fm9 import protocol as p, midi_transport
from fm9.device import SetResult
from devices.axefx3 import fw33, fw33_profile as profile, nam_planning, protocol, grid, route_guard, modifiers, executor
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from devices.axefx3.nam_memory import Capture


def design(count=1):
    return dict(name='AI-Damage Inc',summary='Interpretation, not a recording match',cab_active=False,
        delay=dict(active=True,time_ms=350.,feedback=22.,mix=17.),
        chorus=dict(active=True,rate_hz=.7,depth=25.,mix=10.),
        reverb=dict(active=True,time_s=.8,mix=6.),
        scenes=[dict(name=('Rhythm','Solo')[i],nam=dict(input_gain=0.,bass=4.2,mid=5.8,
            treble=5.5,level=(-16.,-13.)[i]),delay=bool(i),chorus=bool(i),reverb=bool(i)) for i in range(count)])


def fake(existing=False):
    dev=Mock();dev.reg=Registry(profile.KEY);dev._lock=threading.RLock()
    dev.reg.hardware_variant='mk2'
    ids=list(profile.NAM_ROUTE) if existing else []
    dev.firmware_label.return_value=profile.KEY
    dev.current_preset.return_value=(326,'Test');dev.current_scene.return_value=1
    dev.status_dump.return_value=[p.BlockStatus(e,False,0,4) for e in ids]
    dev.read_grid.return_value=[p.GridCell(2,i,e,False,8 if i else 0) for i,e in enumerate(ids)]
    dev.read_nam_slot1.return_value=Capture('Synthetic',1,'a'*64,65536)
    dev._channels={e:4 for e in ids}
    dev.bulk_read.side_effect=lambda eid:[0]*(4*profile.STRIDES.get(dev.reg.family_of_effect_id(eid)[0],12))
    dev.read_display_text.return_value='NONE';dev.edit_session.side_effect=lambda **kw:nullcontext()
    dev.set_param_display.return_value=SetResult(True,'display matched',None,0)
    dev.select_nam_slot.side_effect=lambda slot:SetResult(True,'selected bulk matched',None,slot)
    dev.set_scene.side_effect=lambda n:n;dev.set_channel.side_effect=lambda e,c:c
    dev.set_bypass.side_effect=lambda e,b:b;dev.rename_preset.side_effect=lambda n:(326,n)
    dev.rename_scene.side_effect=lambda n,name:(n,name)
    return dev


@pytest.fixture(autouse=True)
def empty_modifiers(monkeypatch):
    monkeypatch.setattr(modifiers,'inspect',lambda dev:[dict(active=False,words=[0]*25) for _ in range(32)])
    monkeypatch.setattr(fw33,'platform_supported',lambda:True)


def capture():
    return dict(name='Synthetic',slot=1,sha256='a'*64,bytes=65536)


def test_exact_identity_required_and_fm9_untouched():
    assert profile.identity_key(profile.IDENTITY)==profile.KEY
    for pos in range(len(profile.IDENTITY)):
        reply=list(profile.IDENTITY);reply[pos]^=1
        assert profile.identity_key(reply) is None
    assert p.envelope(8,[])[4]==p.MODEL_FM9
    assert protocol.envelope(8,[])[4]==16


def test_exact_83_controls_no_legacy_model_setters_or_extra_instance():
    reg=Registry(profile.KEY)
    assert len(reg.params)==83 and profile.CONTROL_COUNT==83 and not reg.selectable_amp_models()
    assert reg.resolve_block('NAM')==('NAM',206)
    assert reg.family_of_effect_id(78)==('CHORUS',1)
    with pytest.raises(ValueError):reg.resolve_block('NAM',2)
    with pytest.raises(ValueError):reg.spec('DISTORT',2,2)
    for name in ('set_type','set_cab','bind_controller','store'):
        with pytest.raises(ValueError):executor.resolve(reg,dict(kind=name,block='NAM',type_name='fake',value=0))


@pytest.mark.parametrize('family',profile.NAMES)
def test_all_measured_numeric_specs_encode_in_their_set_units(family):
    reg=Registry(profile.KEY)
    for name in profile.NAMES[family]:
        spec=reg.find_param(family,name)
        value=-12 if spec.unit=='dB' else max(spec.dmin, (spec.dmin+spec.dmax)/2)
        if name=='DELAY_FEED':value=20
        if name in profile.effect_controls.AUTO_OFF:value=0
        frame=protocol.set_parameter(reg,spec,value)
        assert frame[4:8]==[16,1,int(spec.set_opcode,16),0]
        assert abs(p.decode_f32_septets(frame[12:17])-value/spec.set_divisor)<.002
        if family in ('CABINET','FUZZ','COMP','GEQ'):
            with pytest.raises(PermissionError):fw33.check_frame(Mock(reg=reg),frame)
        else:fw33.check_frame(Mock(reg=reg),frame)
        with pytest.raises(ValueError):protocol.set_parameter(reg,replace(spec,effect_id=207),value)


@pytest.mark.parametrize('name',sorted(profile.ZERO_TYPED))
def test_exact_zero_is_typed_not_normalized(name):
    reg=Registry(profile.KEY);spec=reg.find_param(name.split('_')[0],name)
    assert protocol.set_parameter(reg,spec,0)[6]==9
    assert p.decode_f32_septets(protocol.set_parameter(reg,spec,0)[12:17])==0


def test_unmeasured_zero_positive_gain_and_high_feedback_refused():
    reg=Registry(profile.KEY)
    for family,name,value in [('NAM','NAM_BASS',0),('NAM','NAM_INPUT_GAIN',3),
                              ('DELAY','DELAY_FEED',61)]:
        with pytest.raises(ValueError):protocol.set_parameter(reg,reg.find_param(family,name),value)


def test_nam_foundation_is_one_scene_then_existing_a_b_two_scenes():
    reg=Registry(profile.KEY)
    plan=nam_planning.compile_design(reg,design(),[],1,capture())
    assert plan['name']=='AI-Damage Inc'
    assert plan['required_route']==['Input 1','NAM 1','Cab 1','Delay 1','Chorus 1','Reverb 1','Output 1']
    assert not any(a['kind'] in ('store','set_type','set_cab','bind_controller') for a in plan['actions'])
    assert next(a for a in plan['actions'] if a.get('block')=='NAM')['type_name']=='Synthetic'
    for count in (2,3,4):
        with pytest.raises(ValueError):nam_planning.compile_design(reg,design(),[],count,capture())
    two=nam_planning.compile_design(reg,design(2),list(profile.NAM_ROUTE),2,capture())
    assert [a['value'] for a in two['actions'] if a['kind']=='set_channel' and a['block']=='NAM']==[0,1]
    assert not any(a['kind']=='add_block' for a in two['actions'])
    assert [a['value'] for a in two['actions'] if a.get('param')=='DELAY_TIME']==[350]


def test_fw33_executor_readonly_preflight_and_verified_existing_execution():
    dev=fake(True);plan=nam_planning.compile_design(dev.reg,design(2),list(profile.NAM_ROUTE),2,capture())
    executor.prepare(dev,plan['actions'],plan['required_route'],326)
    dev._write.assert_not_called()
    assert executor.execute(dev,plan['actions'],plan['required_route'],expected_preset=326,external_audio_muted=True)['ok']
    dev.store_preset.assert_not_called();dev.install_nam_slot1.assert_not_called()


@pytest.mark.parametrize('fault',['identity','target','scene','channel','layout','tempo','capture','modifier','capture_name'])
def test_preflight_faults_cause_no_writes(fault,monkeypatch):
    dev=fake(fault!='capture_name');existing=bool(dev.read_grid.return_value)
    plan=nam_planning.compile_design(dev.reg,design(),list(profile.NAM_ROUTE) if existing else [],1,capture())
    if fault=='identity':dev.firmware_label.return_value='97.00'
    if fault=='target':dev.current_preset.return_value=(325,'Test')
    if fault=='scene':dev.current_scene.return_value=3
    if fault=='channel':dev.status_dump.return_value[2].channel=1
    if fault=='layout':dev.bulk_read.side_effect=lambda e:[0]*12
    if fault=='tempo':dev.read_display_text.return_value='1/4'
    if fault=='capture':dev.read_nam_slot1.return_value=Capture('EMPTY',1,'a'*64,65536)
    if fault=='capture_name':dev.read_nam_slot1.return_value=Capture('Changed',1,'a'*64,65536)
    if fault=='modifier':monkeypatch.setattr(modifiers,'inspect',lambda d:[dict(active=True,words=[0]*25)]*32)
    with pytest.raises((ValueError,KeyError)):executor.prepare(dev,plan['actions'],plan['required_route'],326)
    dev._write.assert_not_called();dev.set_scene.assert_not_called()


def test_drop_parameter_stops_rest_and_never_stores():
    dev=fake(True);plan=nam_planning.compile_design(dev.reg,design(),list(profile.NAM_ROUTE),1,capture())
    dev.set_param_display.return_value=SetResult(False,'mismatch',None,None)
    result=executor.execute(dev,plan['actions'],plan['required_route'],expected_preset=326,external_audio_muted=True)
    assert not result['ok'] and result['skipped']>0 and not result['stored']
    assert dev.set_param_display.call_count==1;dev.store_preset.assert_not_called()


def test_native_handoff_refuses_backend_before_closing_input(monkeypatch):
    dev=fake();dev._injected_ports=False;dev.inp=Mock();dev.inp.name='Axe-Fx III'
    monkeypatch.setattr(midi_transport,'backend',lambda:'supriya')
    with pytest.raises(RuntimeError):fw33.memory_read(dev,lambda out:None)
    dev.inp.close.assert_not_called()


@pytest.mark.parametrize('fails',[False,True])
def test_native_handoff_always_reopens_normal_input(monkeypatch,fails):
    dev=fake();dev._injected_ports=False;dev.inp=Mock();dev.inp.name='Axe-Fx III'
    original=dev.inp;reopened=Mock()
    monkeypatch.setattr(midi_transport,'backend',lambda:'mido')
    monkeypatch.setattr(fw33.mido,'open_input',lambda name:reopened)
    def read(out):
        original.close.assert_called_once()
        if fails:raise ValueError('truncated')
        return 'complete'
    if fails:
        with pytest.raises(ValueError):fw33.memory_read(dev,read)
    else:assert fw33.memory_read(dev,read)=='complete'
    assert dev.inp is reopened;dev._drain.assert_called_once()


def test_only_exact_nam_foundation_frames_pass_scoped_grid_gate():
    reg=Registry(profile.KEY);dev=Mock(reg=reg,_fw33_route_permit=None)
    frame=grid.reframe(p.build_set_grid_cell(3,2,206))
    assert grid.valid_write(frame,reg)
    with pytest.raises(PermissionError):fw33.check_frame(dev,frame)
    dev._fw33_route_permit=tuple(frame);fw33.check_frame(dev,frame)
    assert not grid.valid_write(grid.reframe(p.build_set_grid_cell(3,2,78)),reg)
    assert not grid.valid_write(grid.reframe(p.build_set_grid_cell(3,2,0)),reg)


def test_full_eight_bit_route_does_not_alias_nam_to_chorus():
    dev=fake(True)
    assert route_guard.serial_route(dev.read_grid(),dev.status_dump(),dev.reg)==list(profile.NAM_ROUTE)
    cells=deepcopy(dev.read_grid());cells[1].effect_id=78
    with pytest.raises(ValueError):route_guard.serial_route(cells,dev.status_dump(),dev.reg)


def test_store_frame_matches_captured_23_byte_frame(monkeypatch):
    dev=fake(True);dev.slot_name.return_value=p.SlotName(326,'Test')
    monkeypatch.setattr(fw33,'get_store_slots',lambda:{326})
    monkeypatch.setattr(fw33.time,'sleep',lambda _:None)
    assert fw33.store(dev,326)==(326,'Test')
    frame=dev._write.call_args.args[0]
    assert frame==[240,0,1,116,16,1,38,0,0,0,0,0,70,2,0,0,0,0,0,0,0,118,247]
    assert dev._store_permit is None
    with pytest.raises(PermissionError):fw33.store(dev,327)

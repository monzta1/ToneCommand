"""Firmware migration regression; synthetic cases are not hardware evidence."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fm9 import protocol as shared
from devices.axefx3 import pedal_fw33 as migrated,pedal_control as old,modifiers,fw33,tone_review
from devices.axefx3.registry import Registry


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(migrated.time,'sleep',lambda _:None)
    reg=Registry(migrated.fw33_profile.KEY);reg.hardware_variant='mk2'
    words=[dict(words=[0]*25) for _ in range(32)]
    words[0]['words']=old.default_words(95);words[0]['words'][0]=13
    words[1]['words']=old.default_words(94);words[1]['words'][0]=12
    state=dict(preset=(324,'Migration'),scene=1,firmware=reg.firmware,variant='mk2',
        blocks=[shared.BlockStatus(e,True,0,4) for e in (94,95)],
        grid=[(0,0,95),(0,1,94)],bulk={94:[0]*100,95:[0]*100},
        modifiers=words,scene_names=[(i,'') for i in range(1,9)],cabs=[])
    d=SimpleNamespace(reg=reg,firmware_label=lambda:reg.firmware,_edit_target=324,
        _check_edit_target=Mock(),_pedal_fw33_operation=None,_state=state)
    monkeypatch.setattr(tone_review,'snapshot',lambda dev,**kw:deepcopy(dev._state))
    def write(frame):
        assert migrated.allowed(d,frame)
        fw33.check_frame(d,frame)
        expected=migrated.expected_modifiers(d._state,frame, d._pedal_fw33_operation.target)
        d._state['modifiers']=[dict(words=w) for w in expected]
    d._write=Mock(side_effect=write)
    return d


def test_captured_fw33_literals_equal_existing_fw32_encoders():
    frames={bytes.fromhex(x) for x in migrated.CAPTURED}
    assert frames=={bytes(old.allocation_frame(e)) for e in (94,95)} | {
        bytes(modifiers.source_frame(slot,source)) for slot in (1,2) for source in (12,13)} | {
        bytes(old.auto_frame(slot,mode)) for slot in (1,2) for mode in (0,6)}


@pytest.mark.parametrize('index,target',[(2,95),(3,95),(4,95),(5,95),(6,94),(7,94),(8,94),(9,94)])
def test_exact_existing_writes_and_complete_preservation(rig,index,target):
    before=deepcopy(rig._state)
    frame=list(bytes.fromhex(migrated.CAPTURED[index]))
    op=migrated.Operation(rig,target)
    after=op.write(frame)
    assert after['modifiers']==[dict(words=w) for w in migrated.expected_modifiers(before,frame,target)]
    after['modifiers']=before['modifiers']
    assert after==before
    assert rig._pedal_fw33_operation is None and op.pending is None
    with pytest.raises(PermissionError,match='Consumed'):op.write(frame)
    assert rig._write.call_count==1


@pytest.mark.parametrize('target,index',[(94,1),(95,0)])
def test_device_native_creation_compares_not_transmits_complete_curve(rig,target,index):
    slot=1 if target==95 else 2
    rig._state['modifiers'][slot-1]['words']=[0]*25
    frame=list(bytes.fromhex(migrated.CAPTURED[index]))
    after=migrated.Operation(rig,target).write(frame)
    assert after['modifiers'][slot-1]['words']==old.default_words(target)
    assert len(frame)==23 and frame[6]==0x3a


@pytest.mark.parametrize('fault',['dropped','curve','bulk','other_bypass','channel','grid','scene','name'])
def test_failed_or_collateral_write_is_consumed_and_never_retried(rig,fault):
    original=rig._write.side_effect
    def broken(frame):
        if fault=='dropped':return
        original(frame)
        if fault=='curve':rig._state['modifiers'][0]['words'][1]=17
        if fault=='bulk':rig._state['bulk'][94][0]=1
        if fault=='other_bypass':rig._state['blocks'][0]=replace(rig._state['blocks'][0],bypassed=False)
        if fault=='channel':rig._state['blocks'][1]=replace(rig._state['blocks'][1],channel=1)
        if fault=='grid':rig._state['grid']=[]
        if fault=='scene':rig._state['scene']=2
        if fault=='name':rig._state['preset']=(324,'Unexpected')
    rig._write.side_effect=broken
    op=migrated.Operation(rig,95)
    with pytest.raises(ValueError):op.write(list(bytes.fromhex(migrated.CAPTURED[2])))
    assert op.consumed and rig._pedal_fw33_operation is None
    assert rig._write.call_count==1


def test_auto_engage_can_change_only_target_bypass(rig):
    original=rig._write.side_effect
    def bypass(frame):
        original(frame)
        rig._state['blocks'][1]=replace(rig._state['blocks'][1],bypassed=False)
    rig._write.side_effect=bypass
    assert migrated.Operation(rig,95).write(list(bytes.fromhex(migrated.CAPTURED[4])))


@pytest.mark.parametrize('fault',['firmware','variant','volume','missing','target','allocated','pid','value','encoding'])
def test_unmeasured_context_or_field_refuses_before_writes(rig,fault):
    frame=list(bytes.fromhex(migrated.CAPTURED[2]));target=95
    if fault=='firmware':rig.reg.firmware='33.01'
    if fault=='variant':rig.reg.hardware_variant='mk1'
    if fault=='volume':target=102
    if fault=='missing':rig._state['blocks']=[]
    if fault=='target':frame=list(bytes.fromhex(migrated.CAPTURED[6]))
    if fault=='allocated':frame=old.allocation_frame(95)
    if fault=='pid':frame=modifiers.protocol.param_frame(3,1,0,opcode=9)
    if fault=='value':frame=modifiers.protocol.param_frame(3,0,14,opcode=9)
    if fault=='encoding':frame=modifiers.protocol.param_frame(3,0,12,opcode=0x52)
    with pytest.raises((ValueError,PermissionError)):
        migrated.Operation(rig,target).write(frame)
    rig._write.assert_not_called()


def test_raw_frames_have_no_fw33_permission_outside_exact_operation(rig):
    for text in migrated.CAPTURED:
        frame=list(bytes.fromhex(text))
        assert not migrated.allowed(rig,frame)
        with pytest.raises((PermissionError,KeyError,ValueError)):fw33.check_frame(rig,frame)


def test_native_allocation_settles_independent_reads_without_repeating_write(rig,monkeypatch):
    rig._state['modifiers'][1]['words']=[0]*25
    reads=[]
    def snapshot(dev,**kw):
        state=deepcopy(dev._state);reads.append(state)
        if len(reads)==2:state['modifiers'][1]['words'][2]=0
        return state
    monkeypatch.setattr(tone_review,'snapshot',snapshot)
    result=migrated.Operation(rig,94).write(old.allocation_frame(94))
    assert result['modifiers'][1]['words']==old.default_words(94)
    assert len(reads)==3 and rig._write.call_count==1


def test_native_free_record_may_retain_an_old_parameter_ordinal(rig):
    rig._state['modifiers'][0]['words']=[0]*25
    rig._state['modifiers'][0]['words'][9]=103
    rig._state['modifiers'][1]['words']=[0]*25
    expected=migrated.expected_modifiers(rig._state,old.allocation_frame(94),94)
    assert expected[0]==old.default_words(94) and expected[1]==[0]*25


def test_fw33_wah_scalar_is_migrated_volume_remains_separate():
    reg=Registry(migrated.fw33_profile.KEY);reg.hardware_variant='mk2'
    observed=modifiers.observed_target(reg,old.default_words(94))
    assert observed['parameter']=='WAH_CONTROL'
    assert modifiers.observed_target(reg,old.default_words(102))['parameter']=='VOLUME_CONTROL'
    assert reg.spec('WAH',5).name=='WAH_CONTROL'
    reg.hardware_variant='mk1'
    assert modifiers.observed_target(reg,old.default_words(94)) is None


def test_controller_availability_respects_existing_platform_transport_boundary(rig,monkeypatch):
    monkeypatch.setattr(fw33,'runtime_write_error',lambda dev:'Unmeasured transport')
    assert not migrated.supported(rig,94)
    rig._write.assert_not_called()

"""Volume migration retains the old full-range/no-Auto-Engage contract."""
from copy import deepcopy
from dataclasses import replace
import pytest
from fm9 import protocol as shared
from devices.axefx3 import pedal_fw33 as migrated,pedal_control,modifiers
from test_axefx3_pedal_fw33 import rig


@pytest.fixture
def volume(rig):
    rig._edit_target=325;rig._state['preset']=(325,'Volume migration')
    rig._state['blocks']=[shared.BlockStatus(102,False,0,4)]
    rig._state['bulk']={102:[65534,32767,2,0,0,65534,52427,0,0,0,24575,32767,32767,32767,0]*4}
    rig._state['modifiers']=[dict(words=[0]*25) for _ in range(32)]
    return rig


def test_native_volume_allocation_and_source_changes_preserve_complete_state(volume):
    assert migrated.VOLUME_RELEASED
    before=deepcopy(volume._state)
    for literal in migrated.VOLUME_CAPTURED:
        migrated.Operation(volume,102).write(list(bytes.fromhex(literal)))
    wanted=deepcopy(before);wanted['modifiers'][0]['words']=[13]+pedal_control.default_words(102)[1:]
    assert volume._state==wanted
    assert volume._write.call_count==3 and volume._state['modifiers'][0]['words'][10]==0
    assert modifiers.observed_target(volume.reg,wanted['modifiers'][0]['words'])['parameter']=='VOLUME_CONTROL'


@pytest.mark.parametrize('fault',['type','positive_level','other_channel_level','curve','auto_engage','source','variant'])
def test_unsafe_or_unmeasured_volume_request_refused_before_write(volume,fault):
    volume._state['modifiers'][0]['words']=pedal_control.default_words(102)
    frame=list(bytes.fromhex(migrated.VOLUME_CAPTURED[1]))
    if fault=='type':volume._state['bulk'][102][2]=0
    if fault=='positive_level':volume._state['bulk'][102][6]=52428
    if fault=='other_channel_level':volume._state['bulk'][102][51]=52428
    if fault=='curve':volume._state['modifiers'][0]['words'][2]=0
    if fault=='auto_engage':frame=pedal_control.auto_frame(1,6)
    if fault=='source':frame=modifiers.protocol.param_frame(3,0,14,opcode=9)
    if fault=='variant':volume.reg.hardware_variant='mk1'
    with pytest.raises((ValueError,PermissionError)):migrated.Operation(volume,102).write(frame)
    volume._write.assert_not_called()


def test_volume_source_change_cannot_change_its_bypass(volume):
    volume._state['modifiers'][0]['words']=pedal_control.default_words(102)
    original=volume._write.side_effect
    def broken(frame):
        original(frame);volume._state['blocks'][0]=replace(volume._state['blocks'][0],bypassed=True)
    volume._write.side_effect=broken
    with pytest.raises(ValueError):migrated.Operation(volume,102).write(list(bytes.fromhex(migrated.VOLUME_CAPTURED[1])))
    assert volume._write.call_count==1

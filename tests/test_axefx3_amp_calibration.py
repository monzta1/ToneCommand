"""Developer measurement is literal-bound and never widens normal SEND."""
from copy import deepcopy
from dataclasses import replace
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fm9 import protocol as shared
from devices.axefx3 import amp_calibration as fixture, amp_probe, fw33_profile, serial_build, protocol
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry


def device(monkeypatch):
    reg=Registry(fw33_profile.KEY);reg.hardware_variant='mk2'
    bulk=[0]*568
    for c,m in enumerate((14,267,14,267)):bulk[142*c]=m
    for c in range(1,4):
        for pid,word in zip(fixture.PIDS,fixture.WORDS[c-1]):bulk[142*c+pid]=word
    state=dict(scene=1,grid=[shared.GridCell(r-1,c-1,e,s,m) for (r,c),(e,s,m)
        in serial_build.expected_grid().items()],bulk={58:bulk,42:[7]},
        modifiers=[dict(active=False)]*32,blocks=[shared.BlockStatus(58,True,0,4)],names=['intact'])
    dev=SimpleNamespace(reg=reg,_edit_target=328,_lock=RLock(),_check_edit_target=Mock(),
        _amp_probe=None,_amp_probe_permit=None,_approved_frame=None,guard=AxeFxIII.guard,outp=Mock())
    displayed={'DISTORT_LEVEL':-18,'OUTPUT_LEVEL':-18}
    dev.get_param_display=lambda spec:displayed.get(spec.name,0)
    monkeypatch.setattr(fixture.tone_review,'snapshot',lambda *a,**k:deepcopy(state))
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    return dev,state,displayed


def apply(dev,state,displayed,frame):
    assert fixture.allowed(dev,frame) and amp_probe.allowed(dev,frame)
    dev._approved_frame=tuple(frame)
    try:AxeFxIII._send(dev,list(frame))
    finally:dev._approved_frame=None
    step=dev._amp_probe.sequence[dev._amp_probe.index]
    if step.kind=='channel':state['blocks']=[replace(b,channel=step.channel) for b in state['blocks']]
    elif step.kind=='model':state['bulk'][58][142*step.channel]=int(step.value)
    else:
        state['bulk'][58][142*step.channel+step.pid]=step.word
        displayed[dev.reg.spec('DISTORT',step.pid,1).name]=step.value


def test_captured_nonzero_sequence_changes_and_restores_all_channels(monkeypatch):
    dev,state,displayed=device(monkeypatch);before=deepcopy(state)
    probe=fixture.Calibration(dev)
    dev._write=Mock(side_effect=lambda frame:apply(dev,state,displayed,frame))
    assert len(probe.sequence)==58
    for step in probe.sequence:
        assert shared.checksum(step.frame[1:-2])==step.frame[-2]
        probe.write(step.frame)
    assert state==before and probe.index==58 and dev.outp.send.call_count==58
    assert dev._amp_probe_permit is None
    with pytest.raises(PermissionError):probe.write(probe.sequence[0].frame)


@pytest.mark.parametrize('fault',['target','firmware','variant','grid','scene','bulk','channel','engaged','model','anchor','modifier','level','duplicate'])
def test_initial_fault_sends_nothing(monkeypatch,fault):
    dev,state,displayed=device(monkeypatch);dev._write=Mock()
    if fault=='target':dev._edit_target=326
    if fault=='firmware':dev.reg=Registry('32.06')
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='grid':state['grid']=[]
    if fault=='scene':state['scene']=2
    if fault=='bulk':state['bulk'][58]=[0]
    if fault=='channel':state['blocks']=[shared.BlockStatus(58,True,1,4)]
    if fault=='engaged':state['blocks']=[shared.BlockStatus(58,False,0,4)]
    if fault=='model':state['bulk'][58][0]=267
    if fault=='anchor':state['bulk'][58][143]=3
    if fault=='modifier':state['modifiers']=[dict(active=True)]
    if fault=='level':displayed['OUTPUT_LEVEL']=-6
    if fault=='duplicate':dev._amp_probe=object()
    with pytest.raises(PermissionError):fixture.Calibration(dev)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault',['literal','stale','detached','identity','send','readback','other_channel','grid','unbypass','loud','display'])
def test_failed_step_consumed_no_rollback_or_retry(monkeypatch,fault):
    dev,state,displayed=device(monkeypatch);probe=fixture.Calibration(dev)
    if fault=='display':probe.index=3;state['blocks']=[shared.BlockStatus(58,True,1,4)];probe.expected=deepcopy(state)
    frame=probe.sequence[probe.index].frame
    def write(frame):
        if fault=='send':raise OSError('unknown send result')
        apply(dev,state,displayed,frame)
        if fault=='readback':state['names']=['changed']
        if fault=='other_channel':state['bulk'][58][143]+=1
        if fault=='grid':state['grid']=[]
        if fault=='unbypass':state['blocks']=[shared.BlockStatus(58,False,0,4)]
        if fault=='loud':displayed['DISTORT_LEVEL']=-6
        if fault=='display':displayed['DISTORT_LEVEL']=-22
    dev._write=Mock(side_effect=write)
    if fault=='literal':frame=probe.sequence[1].frame
    if fault=='stale':state['names']=['changed']
    if fault=='detached':dev._amp_probe=None
    if fault=='identity':dev.reg.hardware_variant='mk1'
    with pytest.raises((PermissionError,ValueError,OSError)):probe.write(frame)
    count=dev._write.call_count
    with pytest.raises(PermissionError):probe.write(frame)
    assert dev._write.call_count==count and dev._amp_probe_permit is None


def test_normal_model_frame_still_rejected_without_measurement_permit(monkeypatch):
    dev,_,_=device(monkeypatch);probe=fixture.Calibration(dev)
    frame=probe.sequence[0].frame
    dev._approved_frame=frame
    with pytest.raises((PermissionError,ValueError,KeyError)):AxeFxIII._send(dev,list(frame))
    assert not fixture.allowed(dev,frame)
    dev.outp.send.assert_not_called()


def test_all_24_editor_numeric_literals_match_fw33_encoder():
    reg=Registry(fw33_profile.KEY)
    numeric=[step for step in fixture.steps() if step.kind=='numeric'][:24]
    for step in numeric:
        assert tuple(protocol.set_parameter(reg,reg.spec('DISTORT',step.pid,1),step.value))==step.frame


def test_fw32_numeric_encoding_is_not_changed():
    reg=Registry('32.06');spec=reg.find_param('DISTORT','DISTORT_DRIVE')
    raw=shared.display_to_normalized(4.6,spec.dmin,spec.dmax,spec.scale)
    assert spec.set_divisor is None
    assert protocol.set_parameter(reg,spec,4.6)==protocol.param_frame(58,spec.param_id,raw,opcode=int(spec.set_opcode,16))


def test_model_roundtrips_on_b_c_d_then_eight_numeric_restorations(monkeypatch):
    dev,state,displayed=device(monkeypatch);before=deepcopy(state)
    probe=fixture.ModelChannels(dev)
    dev._write=Mock(side_effect=lambda frame:apply(dev,state,displayed,frame))
    assert len(probe.sequence)==34
    assert [(s.channel,s.value) for s in probe.sequence if s.kind=='model']==[(1,14),(1,267),(2,267),(2,14),(3,14),(3,267)]
    for step in probe.sequence:probe.write(step.frame)
    assert state==before and probe.index==34 and dev.outp.send.call_count==34

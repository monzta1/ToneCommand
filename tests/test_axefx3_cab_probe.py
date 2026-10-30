"""Exact fixture does not enable generic Cab, mixer or IR install writes."""
from copy import deepcopy
from dataclasses import replace
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fm9 import protocol as shared
from devices.axefx3 import cab_probe as fixture,fw33_profile,serial_build,protocol
from devices.axefx3.registry import Registry
from devices.axefx3.adapter import AxeFxIII


def device(monkeypatch):
    reg=Registry(fw33_profile.KEY);reg.hardware_variant='mk2'
    words=[0]*424
    for c in range(4):
        words[106*c+8:106*c+12]=[65534]*4
        words[106*c+12:106*c+16]=[32767]*4
        words[106*c+24:106*c+28]=[0,1,1,1]
    words[0]=1;words[4]=840
    state=dict(scene=1,grid=[shared.GridCell(r-1,c-1,e,s,m) for (r,c),(e,s,m) in serial_build.expected_grid().items()],
        blocks=[shared.BlockStatus(58,True,0,4),shared.BlockStatus(62,False,0,4)],bulk={62:words,58:[7]*568},
        modifiers=[dict(active=False)]*32,names=['intact'])
    dev=SimpleNamespace(reg=reg,_edit_target=328,_lock=RLock(),_check_edit_target=Mock(),_cab_probe=None,
        _cab_probe_permit=None,_approved_frame=None,guard=AxeFxIII.guard,outp=Mock(),get_param_display=lambda _: -18)
    monkeypatch.setattr(fixture.tone_review,'snapshot',lambda *a,**k:deepcopy(state))
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    return dev,state


def apply(dev,state,frame):
    assert fixture.allowed(dev,frame)
    dev._approved_frame=tuple(frame)
    try:AxeFxIII._send(dev,list(frame))
    finally:dev._approved_frame=None
    step=dev._cab_probe.sequence[dev._cab_probe.index]
    if step.pid is None:state['blocks']=[replace(b,channel=step.channel) if b.effect_id==62 else b for b in state['blocks']]
    else:state['bulk'][62][106*step.channel+step.pid]=step.value


def test_exact_selector_zero_and_channel_sequence_preserves_all_other_state(monkeypatch):
    dev,state=device(monkeypatch);before=deepcopy(state);probe=fixture.Probe(dev)
    dev._write=Mock(side_effect=lambda frame:apply(dev,state,frame))
    assert len(probe.sequence)==21
    for step in probe.sequence:probe.write(step.frame)
    assert state['blocks']==before['blocks'] and state['bulk'][58]==before['bulk'][58]
    for c,ordinal in enumerate((515,799,515,799)):
        wanted=before['bulk'][62][106*c:106*(c+1)]
        wanted[0]=1;wanted[4]=ordinal
        assert state['bulk'][62][106*c:106*(c+1)]==wanted
    assert dev.outp.send.call_count==21 and dev._cab_probe_permit is None
    with pytest.raises(PermissionError):probe.write(probe.sequence[0].frame)


@pytest.mark.parametrize('fault',['target','firmware','variant','scene','grid','bulk','amp_active','amp_channel','cab_channel','dyna','mixer','ordinal','modifier','level','duplicate'])
def test_initial_fault_sends_nothing(monkeypatch,fault):
    dev,state=device(monkeypatch);dev._write=Mock()
    if fault=='target':dev._edit_target=326
    if fault=='firmware':dev.reg=Registry('32.06')
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='scene':state['scene']=2
    if fault=='grid':state['grid']=[]
    if fault=='bulk':state['bulk'][62]=[0]
    if fault=='amp_active':state['blocks'][0]=replace(state['blocks'][0],bypassed=False)
    if fault=='amp_channel':state['blocks'][0]=replace(state['blocks'][0],channel=1)
    if fault=='cab_channel':state['blocks'][1]=replace(state['blocks'][1],channel=1)
    if fault=='dyna':state['bulk'][62][31]=1
    if fault=='mixer':state['bulk'][62][25]=0
    if fault=='ordinal':state['bulk'][62][4]=799
    if fault=='modifier':state['modifiers']=[dict(active=True)]
    if fault=='level':dev.get_param_display=lambda _: -6
    if fault=='duplicate':dev._cab_probe=object()
    with pytest.raises(PermissionError):fixture.Probe(dev)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault',['literal','stale','send','readback','mixer','other_channel','detached','identity'])
def test_failure_consumes_one_use_permission_without_retry(monkeypatch,fault):
    dev,state=device(monkeypatch);probe=fixture.Probe(dev);frame=probe.sequence[0].frame
    def write(frame):
        if fault=='send':raise OSError('unknown outcome')
        apply(dev,state,frame)
        if fault=='readback':state['names']=['changed']
        if fault=='mixer':state['bulk'][62][25]=0
        if fault=='other_channel':state['bulk'][62][106]+=1
    dev._write=Mock(side_effect=write)
    if fault=='literal':frame=probe.sequence[1].frame
    if fault=='stale':state['names']=['changed']
    if fault=='detached':dev._cab_probe=None
    if fault=='identity':dev.reg.hardware_variant='mk1'
    with pytest.raises((PermissionError,ValueError,OSError)):probe.write(frame)
    count=dev._write.call_count
    with pytest.raises(PermissionError):probe.write(frame)
    assert dev._write.call_count==count and dev._cab_probe_permit is None


def test_unpermitted_selector_and_mixer_are_not_enabled(monkeypatch):
    dev,_=device(monkeypatch);probe=fixture.Probe(dev)
    for pid,value in ((0,0),(4,799),(25,0),(12,-1)):
        frame=protocol.param_frame(62,pid,value,opcode=9);dev._approved_frame=tuple(frame)
        assert not fixture.allowed(dev,frame)
        with pytest.raises((PermissionError,ValueError,KeyError)):AxeFxIII._send(dev,frame)
    dev.outp.send.assert_not_called()

"""Bounded developer row replay never enables general planner/transport writes."""
from types import SimpleNamespace
from threading import RLock
from unittest.mock import Mock
import pytest
from fm9 import protocol as shared
from devices.axefx3 import row_probe,row_fixture,fw33,fw33_profile,grid
from devices.axefx3.registry import Registry
from devices.axefx3.adapter import AxeFxIII


def cells(state):
    return [shared.GridCell(r-1,c-1,e,s,m) for (r,c),(e,s,m) in state.items()]


def device():
    reg=Registry(fw33_profile.KEY);reg.hardware_variant='mk2'
    return SimpleNamespace(reg=reg,_edit_target=320,_lock=RLock(),_row_probe_permit=None,
        _check_edit_target=Mock(),read_grid=lambda:[],_write=Mock())


def test_exact_removal_and_whole_grid_transitions():
    steps=row_fixture.steps()
    assert len(steps)==164
    assert tuple(f for f,_,_ in steps)==row_fixture.frames()+row_fixture.removal_frames()
    assert steps[0][1]==steps[-1][2]=={}
    assert steps[81][2]==row_fixture.expected_grid()
    assert sum(f[6]==0x33 for f,_,_ in steps)==28
    assert all(steps[i][2]==steps[i+1][1] for i in range(len(steps)-1))
    for row in (1,2):
        for col in range(1,14):
            a=row_fixture.connect(row,col);b=row_fixture.disconnect(row,col)
            assert a[:12]==b[:12] and a[13:-2]==b[13:-2] and b[12]==2
        for col in range(1,15):
            assert row_fixture.delete(row,col)[6]==0x33
            assert row_fixture.select(row,col)[7:-2]==row_fixture.delete(row,col)[7:-2]


@pytest.mark.parametrize('target',[None,319,321,324,True])
def test_other_presets_decline_without_writes(target):
    dev=device();dev._edit_target=target
    with pytest.raises(PermissionError):row_probe.Probe(dev)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault',['firmware','variant','occupied','session'])
def test_initial_identity_and_empty_grid_guard(fault):
    dev=device()
    if fault=='firmware':dev.reg=Registry('32.06')
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='occupied':dev.read_grid=lambda:cells({(6,14):(42,False,0)})
    if fault=='session':dev._check_edit_target.side_effect=PermissionError('No edit consent')
    with pytest.raises(PermissionError):row_probe.Probe(dev)
    dev._write.assert_not_called()


def test_all_164_frames_replay_only_in_exact_order_with_matching_state(monkeypatch):
    monkeypatch.setattr(row_probe.time,'sleep',lambda _:None)
    dev=device();probe=row_probe.Probe(dev);state={}
    dev.read_grid=lambda:cells(state)
    def write(frame):
        assert row_probe.allowed(dev,frame)
        fw33.check_frame(dev,frame)
        state.clear();state.update(probe.sequence[probe.index][2])
    dev._write=Mock(side_effect=write)
    for frame,_,_ in probe.sequence:probe.write(frame)
    assert probe.index==164 and state=={} and dev._row_probe_permit is None
    with pytest.raises(PermissionError):probe.write(probe.sequence[0][0])
    assert dev._write.call_count==164


@pytest.mark.parametrize('fault',['out_of_order','stale_grid','transport','readback','target_changed','variant_changed'])
def test_failed_probe_is_consumed_permits_cleared_no_retry_or_restore(monkeypatch,fault):
    monkeypatch.setattr(row_probe.time,'sleep',lambda _:None)
    dev=device();probe=row_probe.Probe(dev);frame=probe.sequence[0][0]
    if fault=='out_of_order':frame=probe.sequence[1][0]
    if fault=='stale_grid':dev.read_grid=lambda:cells({(1,1):(37,False,0)})
    if fault=='transport':dev._write.side_effect=OSError('Only one send attempt')
    if fault=='readback':dev._write.side_effect=lambda f:setattr(dev,'read_grid',lambda:cells({(1,1):(37,False,0)}))
    if fault=='target_changed':dev._edit_target=324
    if fault=='variant_changed':dev.reg.hardware_variant='mk1'
    with pytest.raises((PermissionError,OSError,ValueError)):probe.write(frame)
    count=dev._write.call_count
    with pytest.raises(PermissionError):probe.write(frame)
    assert dev._write.call_count==count and dev._row_probe_permit is None and probe.failed


def test_default_transport_still_blocks_all_fixture_frames():
    dev=device();dev._approved_frame=None;dev.outp=Mock();dev.guard=AxeFxIII.guard
    for frame,_,_ in row_fixture.steps():
        assert not row_probe.allowed(dev,frame) and not grid.valid_write(frame,dev.reg)
        with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
    dev.outp.send.assert_not_called()


def test_transport_requires_both_action_and_exact_row_permits():
    dev=device();dev.guard=AxeFxIII.guard;dev.outp=Mock()
    frame=row_fixture.frames()[0];dev._row_probe_permit=tuple(frame);dev._approved_frame=None
    with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
    dev._approved_frame=tuple(frame)
    AxeFxIII._send(dev,frame)
    assert dev.outp.send.call_count==1
    dev._edit_target=324
    with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
    assert dev.outp.send.call_count==1

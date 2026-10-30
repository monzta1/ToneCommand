"""Captured channel probe never enables arbitrary model/channel writes."""
from copy import deepcopy
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fm9 import protocol as shared
from devices.axefx3 import amp_probe as fixture, fw33, fw33_profile, serial_build
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry


def device(monkeypatch):
    reg = Registry(fw33_profile.KEY)
    reg.hardware_variant = 'mk2'
    state = dict(scene=1, grid=[shared.GridCell(r-1,c-1,e,s,m)
        for (r,c),(e,s,m) in serial_build.expected_grid().items()],
        bulk={58:[0]*568}, modifiers=[dict(active=False)]*32,
        blocks=[shared.BlockStatus(58,False,0,4)])
    dev = SimpleNamespace(reg=reg, _edit_target=328, _lock=RLock(),
        _check_edit_target=Mock(), _amp_probe=None, _amp_probe_permit=None,
        get_param_display=lambda _: -18, guard=AxeFxIII.guard,
        outp=Mock(), _approved_frame=None)
    monkeypatch.setattr(fixture.tone_review, 'snapshot', lambda *a, **k: deepcopy(state))
    monkeypatch.setattr(fixture.time, 'sleep', lambda _: None)
    return dev, state


def test_exact_capture_frames_and_full_state_roundtrip(monkeypatch):
    dev, state = device(monkeypatch)
    probe = fixture.Probe(dev)
    before = deepcopy(state)
    def write(frame):
        assert fixture.allowed(dev, frame)
        fw33.check_frame(dev, frame)
        dev._approved_frame = tuple(frame)
        try:
            AxeFxIII._send(dev, frame)
        finally:
            dev._approved_frame = None
        state['blocks'] = [shared.BlockStatus(58,False,frame[12],4)]
    dev._write = Mock(side_effect=write)
    for frame in fixture.frames():
        assert shared.checksum(frame[1:-2]) == frame[-2]
        probe.write(frame)
    assert state == before and probe.index == 4 and dev.outp.send.call_count == 4
    with pytest.raises(PermissionError):
        probe.write(fixture.frames()[0])
    assert dev._amp_probe_permit is None


@pytest.mark.parametrize('fault', ['target','firmware','variant','channel','grid','bulk','modifier','level','duplicate'])
def test_initial_fault_never_sends(monkeypatch, fault):
    dev, state = device(monkeypatch)
    dev._write = Mock()
    if fault == 'target': dev._edit_target = 326
    if fault == 'firmware': dev.reg = Registry('32.06')
    if fault == 'variant': dev.reg.hardware_variant = 'mk1'
    if fault == 'channel': state['blocks'] = [shared.BlockStatus(58,False,1,4)]
    if fault == 'grid': state['grid'] = []
    if fault == 'bulk': state['bulk'][58] = [0]
    if fault == 'modifier': state['modifiers'] = [dict(active=True)]
    if fault == 'level': dev.get_param_display = lambda _: -6
    if fault == 'duplicate': dev._amp_probe = object()
    with pytest.raises(PermissionError): fixture.Probe(dev)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault', ['order','stale','send','readback','detached','target','identity'])
def test_unknown_result_consumes_probe_without_retry(monkeypatch, fault):
    dev, state = device(monkeypatch)
    probe = fixture.Probe(dev)
    dev._write = Mock()
    frame = fixture.frames()[0]
    if fault == 'order': frame = fixture.frames()[1]
    if fault == 'stale': state['scene'] = 2
    if fault == 'send': dev._write.side_effect = OSError('Unknown result')
    if fault == 'detached': dev._amp_probe = None
    if fault == 'target': dev._edit_target = 329
    if fault == 'identity': dev.reg = Registry('32.06')
    with pytest.raises((PermissionError, ValueError, OSError)): probe.write(frame)
    count = dev._write.call_count
    with pytest.raises(PermissionError): probe.write(frame)
    assert dev._write.call_count == count and dev._amp_probe_permit is None


def test_exact_single_frame_and_action_permits_both_required(monkeypatch):
    dev, _ = device(monkeypatch)
    probe = fixture.Probe(dev)
    frame = list(fixture.frames()[0])
    dev._amp_probe_permit = tuple(frame)
    assert not fixture.allowed(dev, frame)
    probe.failed = True
    assert fixture.allowed(dev, frame)
    with pytest.raises(PermissionError): AxeFxIII._send(dev, frame)
    dev._approved_frame = tuple(frame)
    AxeFxIII._send(dev, frame)
    dev._edit_target = 326
    with pytest.raises(PermissionError): AxeFxIII._send(dev, frame)
    assert dev.outp.send.call_count == 1


def test_model_frame_never_passes_the_channel_probe(monkeypatch):
    from devices.axefx3 import protocol
    dev, _ = device(monkeypatch)
    fixture.Probe(dev)
    frame = protocol.param_frame(58,0,14,opcode=9)
    dev._amp_probe_permit = dev._approved_frame = tuple(frame)
    with pytest.raises((PermissionError, ValueError, KeyError)): AxeFxIII._send(dev,frame)
    dev.outp.send.assert_not_called()

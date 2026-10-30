"""Recorded calibration never grants a generic Cab writer."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
import pytest
from devices.axefx3 import cab_inventory_probe as probe, protocol
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_cab_probe import device as fixture_device


def device(monkeypatch):
    dev,state=fixture_device(monkeypatch)
    dev._edit_target=322
    dev.get_bypass=lambda _:True
    def shown(eid,p):
        c=next(b.channel for b in state['blocks'] if b.effect_id==62)
        word=state['bulk'][62][106*c+p]
        if p in range(8,12):return f'{-40+40*word/65534:.2f} dB'
        if p in range(12,16):return f'{-100+200*word/65534:.1f}'
        return ('--','MUTE','SOLO')[word]
    dev.read_display_text=shown
    return dev,state


def apply(dev,state,frame):
    assert probe.allowed(dev,frame)
    assert protocol.valid_reply(frame[1:-1])
    dev._approved_frame=tuple(frame)
    try:AxeFxIII._send(dev,list(frame))
    finally:dev._approved_frame=None
    c,p,v=dev._cab_probe.sequence[dev._cab_probe.index]
    if p is None:
        state['blocks']=[replace(b,channel=c) if b.effect_id==62 else b for b in state['blocks']]
    else:
        word=round((v+40)/40*65534) if p in range(8,12) else round((v+1)/2*65534) if p in range(12,16) else int(v)
        state['bulk'][62][106*c+p]=word


def test_exact_270_frame_sequence_preserves_other_blocks(monkeypatch):
    dev,state=device(monkeypatch)
    before=deepcopy(state)
    measurement=probe.Probe(dev)
    dev._write=Mock(side_effect=lambda f:apply(dev,state,f))
    for step in measurement.sequence:measurement.write(probe.frame_for(step))
    assert measurement.index==270 and not measurement.failed
    assert state['bulk'][58]==before['bulk'][58]
    assert state['blocks']==before['blocks']
    assert dev.outp.send.call_count==270
    with pytest.raises(PermissionError):measurement.write(probe.frame_for(measurement.sequence[0]))


@pytest.mark.parametrize('fault',['target','variant','amp_active','modifier','grid','legacy','level'])
def test_initial_safety_fault_sends_nothing(monkeypatch,fault):
    dev,state=device(monkeypatch);dev._write=Mock()
    if fault=='target':dev._edit_target=326
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='amp_active':state['blocks'][0]=replace(state['blocks'][0],bypassed=False)
    if fault=='modifier':state['modifiers']=[dict(active=True)]
    if fault=='grid':state['grid']=[]
    if fault=='legacy':state['bulk'][62][31]=1
    if fault=='level':dev.get_param_display=lambda _:0
    with pytest.raises(PermissionError):probe.Probe(dev)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault',['literal','stale','drop','collateral','display','send'])
def test_failed_measurement_cannot_retry_or_restore(monkeypatch,fault):
    dev,state=device(monkeypatch);measurement=probe.Probe(dev)
    # First numeric mixer field, so the independent display check is exercised.
    target=next(i for i,s in enumerate(measurement.sequence) if s[1] in range(8,16)) if fault=='display' else 0
    measurement.index=target
    def write(frame):
        if fault=='send':raise OSError('Unknown outcome')
        if fault!='drop':apply(dev,state,frame)
        if fault=='collateral':state['bulk'][58][0]=999
    dev._write=Mock(side_effect=write)
    if fault=='stale':state['names']=['changed']
    if fault=='display':dev.read_display_text=lambda *_:'wrong'
    frame=probe.frame_for(measurement.sequence[target])
    if fault=='literal':frame=protocol.param_frame(62,0,3,opcode=9)
    with pytest.raises((PermissionError,ValueError,OSError)):measurement.write(frame)
    count=dev._write.call_count
    with pytest.raises(PermissionError):measurement.write(frame)
    assert dev._write.call_count==count and dev._cab_probe_permit is None

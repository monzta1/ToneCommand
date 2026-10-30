"""Drive recording replay cannot open generic effect writes."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
import pytest
from devices.axefx3 import effect_probe as probe
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_album_build import device as fixture_device


def device(monkeypatch):
    d=fixture_device(monkeypatch)
    d._effect_probe_permit=None
    d._test_blocks[58]=replace(d._test_blocks[58],bypassed=True)
    d._test_blocks[118]=replace(d._test_blocks[118],bypassed=True)
    d._test_bulk[118]=([8,0,32767,0,65534]+[0]*39)*4
    def shown(eid,p):
        word=d._test_bulk[eid][44*d.get_channel(eid)+p]
        return f'{word/65534*(100 if p==4 else 10):.2f}'+(' %' if p==4 else '')
    d.read_display_text=shown
    return d


def apply(d,frame):
    assert probe.allowed(d,frame)
    d._approved_frame=tuple(frame)
    try:AxeFxIII._send(d,list(frame))
    finally:d._approved_frame=None
    c,p,v=d._effect_probe.sequence[d._effect_probe.index]
    if p is None:d._test_blocks[118]=replace(d._test_blocks[118],channel=c)
    else:d._test_bulk[118][44*c+p]=int(v) if p==0 else round(v*65534)


def test_ordered_recorded_sequence_preserves_all_other_effects(monkeypatch):
    d=device(monkeypatch);before=deepcopy(d._test_bulk)
    measurement=probe.Probe(d)
    d._write=Mock(side_effect=lambda f:apply(d,f))
    for s in measurement.sequence:measurement.write(probe.frame_for(s))
    assert measurement.index==171 and not measurement.failed
    assert all(v==d._test_bulk[e] for e,v in before.items() if e!=118)
    assert d._test_blocks[118].channel==0 and d.get_bypass(58) and d.get_bypass(118)
    assert d.outp.send.call_count==171
    with pytest.raises(PermissionError):measurement.write(probe.frame_for(measurement.sequence[0]))


@pytest.mark.parametrize('fault',['target','variant','amp_active','drive_active','modifier','grid','layout','level'])
def test_initial_fault_sends_nothing(monkeypatch,fault):
    d=device(monkeypatch);d._write=Mock()
    if fault=='target':d._edit_target=326
    if fault=='variant':d.reg.hardware_variant='mk1'
    if fault=='amp_active':d._test_blocks[58]=replace(d._test_blocks[58],bypassed=False)
    if fault=='drive_active':d._test_blocks[118]=replace(d._test_blocks[118],bypassed=False)
    if fault=='modifier':d.read_modifier=lambda _:[1]+[0]*24
    if fault=='grid':d._test_cells.clear()
    if fault=='layout':d._test_bulk[118]=[0]
    if fault=='level':d.get_param_display=lambda _:0
    with pytest.raises(PermissionError):probe.Probe(d)
    d._write.assert_not_called()


@pytest.mark.parametrize('fault',['literal','stale','collateral','send','drop'])
def test_unknown_result_stops_without_a_second_write(monkeypatch,fault):
    d=device(monkeypatch);measurement=probe.Probe(d)
    frame=probe.frame_for(measurement.sequence[0])
    def write(f):
        if fault=='send':raise OSError('Unknown outcome')
        if fault!='drop':apply(d,f)
        if fault=='collateral':d._test_bulk[62][0]=99
    d._write=Mock(side_effect=write)
    if fault=='literal':frame=probe.frame_for(measurement.sequence[1])
    if fault=='stale':d._test_bulk[62][0]=99
    with pytest.raises((ValueError,PermissionError,OSError)):measurement.write(frame)
    count=d._write.call_count
    with pytest.raises(PermissionError):measurement.write(frame)
    assert d._write.call_count==count and d._effect_probe_permit is None

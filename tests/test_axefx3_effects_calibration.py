"""Literal closed calibration is not a generic effect setter or planner flag."""
from dataclasses import replace
from copy import deepcopy
from unittest.mock import Mock
import pytest
from devices.axefx3 import effects_calibration as probe
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_album_build import device as fixture_device


def device(monkeypatch):
    d=fixture_device(monkeypatch)
    d._test_blocks[58]=replace(d._test_blocks[58],bypassed=True)
    for eid in (46,50,118):d._test_blocks[eid]=replace(d._test_blocks[eid],bypassed=True)
    d._test_bulk[50]=[0]*80;d._test_bulk[55]=[0]*132
    for c in range(4):d._test_bulk[50][20*c+15]=4
    d._test_bulk[118]=([8,0,32767,0,65534]+[0]*39)*4
    d._effects_calibration_permit=None
    d._test_shown={}
    d.read_display_text=lambda e,p:d._test_shown[e,p]
    monkeypatch.setattr(probe.time,'sleep',lambda _:None)
    return d


def apply(d,frame):
    assert probe.allowed(d,frame)
    d._approved_frame=tuple(frame)
    try:AxeFxIII._send(d,list(frame))
    finally:d._approved_frame=None
    kind,eid,c,p,_,value=d._effects_calibration.sequence[d._effects_calibration.index]
    stride,model=probe.LAYOUTS[eid]
    if kind=='channel':d._test_blocks[eid]=replace(d._test_blocks[eid],channel=c)
    elif kind=='bypass':d._test_blocks[eid]=replace(d._test_blocks[eid],bypassed=bool(value))
    elif p==model:d._test_bulk[eid][stride*c+p]=int(value)
    else:
        word,shown,_=probe.parameter(eid,p,value)
        d._test_bulk[eid][stride*c+p]=word;d._test_shown[eid,p]=str(shown)


def test_closed_379_steps_preserve_unrelated_effects(monkeypatch):
    d=device(monkeypatch);before=deepcopy(d._test_bulk);p=probe.Probe(d)
    d._write=Mock(side_effect=lambda f:apply(d,f))
    for step in p.sequence:p.write(probe.frame_for(step))
    assert p.index==379 and not p.failed and d.outp.send.call_count==379
    assert all(d._test_bulk[e]==v for e,v in before.items() if e not in (46,50))
    with pytest.raises(PermissionError):p.write(probe.frame_for(p.sequence[0]))


def test_geq_q_uses_observed_geometric_midpoint():
    word,shown,tolerance=probe.parameter(50,16,1.)
    assert word==32767 and shown==1. and tolerance==.011


def test_bypass_manifest_contains_only_captured_typed_commands():
    bypass=[s for s in probe.steps() if s[0]=='bypass']
    assert len(bypass)==24
    assert {(s[1],s[3]) for s in bypass}=={(118,7),(46,9),(50,18)}
    assert all(probe.frame_for(s)[5:8]==(1,9,0) for s in bypass)


@pytest.mark.parametrize('fault',['target','variant','amp_active','modifier','grid','layout','level','later_channel'])
def test_preflight_failure_is_read_only(monkeypatch,fault):
    d=device(monkeypatch);d._write=Mock()
    if fault=='target':d._edit_target=326
    if fault=='variant':d.reg.hardware_variant='mk1'
    if fault=='amp_active':d._test_blocks[58]=replace(d._test_blocks[58],bypassed=False)
    if fault=='modifier':d.read_modifier=lambda _:[1]+[0]*24
    if fault=='grid':d._test_cells.clear()
    if fault=='layout':d._test_bulk[46]=[0]
    if fault=='level':d.get_param_display=lambda _:0
    if fault=='later_channel':d._test_blocks[50]=replace(d._test_blocks[50],channel=2)
    with pytest.raises(PermissionError):probe.Probe(d)
    d._write.assert_not_called()


@pytest.mark.parametrize('fault',['literal','stale','collateral','send','drop','display'])
def test_unknown_result_never_retried(monkeypatch,fault):
    d=device(monkeypatch);p=probe.Probe(d)
    # Advance to the first ordinary numeric parameter for display-fault testing.
    d._write=Mock(side_effect=lambda f:apply(d,f))
    if fault=='display':
        while p.sequence[p.index][0]!='param':p.write(probe.frame_for(p.sequence[p.index]))
    frame=probe.frame_for(p.sequence[p.index])
    def write(f):
        if fault=='send':raise OSError('Unknown outcome')
        if fault!='drop':apply(d,f)
        if fault=='collateral':d._test_bulk[62][0]=99
        if fault=='display':d.read_display_text=lambda e,p:'unreadable'
    d._write=Mock(side_effect=write)
    if fault=='literal':frame=probe.frame_for(p.sequence[p.index+1])
    if fault=='stale':d._test_bulk[62][0]=99
    with pytest.raises((ValueError,PermissionError,OSError)):p.write(frame)
    count=d._write.call_count
    with pytest.raises(PermissionError):p.write(frame)
    assert d._write.call_count==count and d._effects_calibration_permit is None

"""Closed literal calibration cannot authorize a normal zero/tempo setter."""
from dataclasses import replace
from unittest.mock import Mock
import pytest
from fm9 import protocol as shared
from devices.axefx3 import zero_tempo_calibration as cal,protocol,fw33,fw33_profile
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_album_build import device


def fixture(monkeypatch):
    d=device(monkeypatch);old=d.get_param_display
    d._test_blocks[58]=replace(d._test_blocks[58],bypassed=True)
    for eid in (70,78):d._test_blocks[eid]=replace(d._test_blocks[eid],bypassed=True)
    d._test_bulk[78][0]=3
    for c in range(4):
        d._test_bulk[58][142*c]=14
        for p,value in ((1,4.),(2,4.),(3,5.),(4,5.),(5,4.),(16,2.),(20,4.)):
            d._test_bulk[58][142*c+p]=round(value/10*65534)
    def display(spec):
        if spec.family not in ('DISTORT','CHORUS','DELAY') or spec.param_id==21:return old(spec)
        stride=fw33_profile.STRIDES[spec.family]
        return shared.normalized_to_display(d._test_bulk[spec.effect_id][stride*d.get_channel(spec.effect_id)+spec.param_id]/65534,spec.dmin,spec.dmax,spec.scale)
    d.get_param_display=display
    d.read_display_text=lambda eid,p:'NONE' if d._test_bulk[eid][p]==0 else '1/4'
    def write(frame):
        d._approved_frame=tuple(frame)
        try:AxeFxIII._send(d,frame)
        finally:d._approved_frame=None
        step=d._zero_tempo_calibration.sequence[d._zero_tempo_calibration.index]
        kind,eid,c,p,opcode,raw,shown=step
        if kind=='channel':d._test_blocks[eid]=replace(d._test_blocks[eid],channel=c)
        elif kind=='tempo':d._test_bulk[eid][p]=int(raw)
        else:
            family='DISTORT' if eid==58 else 'CHORUS' if eid==78 else 'DELAY'
            spec=d.reg.spec(family,p)
            d._test_bulk[eid][fw33_profile.STRIDES[family]*c+p]=round(shared.display_to_normalized(shown,spec.dmin,spec.dmax,spec.scale)*65534)
    d._write=Mock(side_effect=write)
    monkeypatch.setattr(cal.time,'sleep',lambda _:None)
    return d


@pytest.mark.parametrize('mode,count',[('amp',60),('tempo',4),('fxzero',8)])
def test_closed_calibration_full_state_and_independent_display(monkeypatch,mode,count):
    d=fixture(monkeypatch);probe=cal.Probe(d,mode)
    assert len(probe.sequence)==count
    for step in probe.sequence:probe.write(cal.frame_for(step))
    assert probe.index==count and not probe.failed and d._write.call_count==count
    d.store_preset.assert_not_called()
    with pytest.raises(PermissionError):probe.write(cal.frame_for(probe.sequence[-1]))


@pytest.mark.parametrize('fault',['target','model','active','channel','modifier'])
def test_bad_fixture_refused_before_any_write(monkeypatch,fault):
    d=fixture(monkeypatch)
    if fault=='target':d._edit_target=328
    if fault=='model':d._test_bulk[58][0]=0
    if fault=='active':d._test_blocks[58]=replace(d._test_blocks[58],bypassed=False)
    if fault=='channel':d._test_blocks[58]=replace(d._test_blocks[58],channel=1)
    if fault=='modifier':d.read_modifier=lambda _:([1]+[0]*24)
    with pytest.raises(PermissionError):cal.Probe(d,'amp')
    d._write.assert_not_called()


@pytest.mark.parametrize('fault',['drop','unrelated'])
def test_unknown_result_consumes_without_retry_or_rollback(monkeypatch,fault):
    d=fixture(monkeypatch);original=d._write.side_effect
    def bad(frame):
        if fault!='drop':original(frame);d._test_bulk[70][50]+=1
    d._write.side_effect=bad;probe=cal.Probe(d,'amp');frame=cal.frame_for(probe.sequence[0])
    with pytest.raises(ValueError):probe.write(frame)
    assert probe.failed and d._write.call_count==1
    with pytest.raises(PermissionError):probe.write(frame)
    assert d._write.call_count==1


def test_only_current_literal_with_both_permits_may_reach_device(monkeypatch):
    d=fixture(monkeypatch);probe=cal.Probe(d,'amp');frame=cal.frame_for(probe.sequence[0])
    d._approved_frame=tuple(frame)
    with pytest.raises((ValueError,PermissionError)):AxeFxIII._send(d,frame)
    assert not cal.allowed(d,list(frame))
    d._zero_tempo_permit=tuple(frame);probe.failed=True
    assert cal.allowed(d,list(frame))
    AxeFxIII._send(d,list(frame))
    wrong=protocol.param_frame(58,2,0.,opcode=9)
    assert not cal.allowed(d,wrong)
    d._approved_frame=tuple(wrong)
    with pytest.raises((ValueError,PermissionError)):AxeFxIII._send(d,wrong)
    d._approved_frame=d._zero_tempo_permit=None


def test_normal_encoder_still_refuses_unreleased_amp_zero(monkeypatch):
    monkeypatch.setattr(fw33_profile,'AMP_ZERO_RELEASED',False)
    d=fixture(monkeypatch)
    with pytest.raises(ValueError,match='exact-zero'):
        protocol.set_parameter(d.reg,d.reg.find_param('DISTORT','DISTORT_DRIVE'),0.)
    d._write.assert_not_called()

"""Measured Amp knob zero prototype does not relax Amp/output level bounds."""
from copy import deepcopy
import pytest
from devices.axefx3 import album_planning as planning,executor,fw33_profile,protocol
from test_axefx3_album_build import device,design


@pytest.fixture(autouse=True)
def candidate(monkeypatch):monkeypatch.setattr(fw33_profile,'AMP_ZERO_RELEASED',True)


def raw():
    result=design()
    for a in result['albums']:
        for name in planning.KNOBS[:-1]:a['amp'][name]=0.
    return result


def test_all_seven_zero_knobs_four_voices_normal_send_and_full_proof(monkeypatch):
    d=device(monkeypatch);p=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result
    assert len(result['album_verification']['scene_fingerprints'])==8
    for c in range(4):
        for name in planning.KNOBS[:-1]:
            pid=d.reg.find_param('DISTORT','DISTORT_'+('DRIVE' if name=='gain' else name.upper())).param_id
            assert d._test_bulk[58][142*c+pid]==0
    d.store_preset.assert_not_called()


def test_gate_refuses_both_compile_and_executor_before_any_write(monkeypatch):
    d=device(monkeypatch);p=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    monkeypatch.setattr(fw33_profile,'AMP_ZERO_RELEASED',False)
    with pytest.raises(ValueError,match='await'):planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    with pytest.raises(ValueError):executor.prepare(d,p['actions'],p['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


def test_zero_setters_are_exact_typed_knob_frames_not_normalized_enums(monkeypatch):
    d=device(monkeypatch)
    for name in fw33_profile.NAMES['DISTORT'][:-1]:
        spec=d.reg.find_param('DISTORT',name)
        assert protocol.set_parameter(d.reg,spec,0.)==protocol.param_frame(58,spec.param_id,0.,opcode=9)
    for name in ('DISTORT_LEVEL',):
        spec=d.reg.find_param('DISTORT',name)
        assert protocol.set_parameter(d.reg,spec,0.)==protocol.param_frame(58,spec.param_id,0.,opcode=9)


@pytest.mark.parametrize('field,value',[('gain',-.01),('bass',True),('level',0.),('level',-11.9)])
def test_out_of_domain_knobs_or_loud_amp_levels_remain_refused(monkeypatch,field,value):
    d=device(monkeypatch);source=raw();source['albums'][0]['amp'][field]=value
    with pytest.raises(ValueError):planning.compile_design(d.reg,source,list(planning.serial_build.ROUTE),8)
    d._write.assert_not_called()

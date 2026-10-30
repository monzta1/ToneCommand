"""Measured zero scalar setters, not extra enum or level authority."""
import pytest
from fm9 import protocol as shared
from devices.axefx3 import album_planning as planning,executor,fw33_profile,protocol,fw33
from test_axefx3_album_build import device,design


@pytest.fixture(autouse=True)
def candidate(monkeypatch):monkeypatch.setattr(fw33_profile,'FX_ZERO_RELEASED',True)


def raw():
    result=design();result['delay'].update(feedback=0.,mix=0.)
    result['chorus'].update(depth=0.,mix=0.)
    return result


def test_four_scalar_zeros_normal_send_full_proof(monkeypatch):
    d=device(monkeypatch);d._test_bulk[78][0]=3
    p=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert result['ok'],result
    for name in fw33_profile.FX_ZERO_NAMES:
        family=name.split('_')[0];spec=d.reg.find_param(family,name)
        assert d._test_bulk[spec.effect_id][spec.param_id]==round(
            shared.display_to_normalized(0.,spec.dmin,spec.dmax,spec.scale)*65534)
        assert protocol.set_parameter(d.reg,spec,0.)==protocol.param_frame(spec.effect_id,spec.param_id,0,opcode=9)
    d.store_preset.assert_not_called()


def test_other_fx_models_refused_during_read_only_preflight(monkeypatch):
    d=device(monkeypatch);p=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    with pytest.raises(ValueError,match='measured first-instance model'):
        executor.prepare(d,p['actions'],p['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called()
    assert fw33.zero_control_error(d,d.reg.find_param('CHORUS','CHORUS_MIX'),0.)


def test_unreleased_scalar_zeros_refused_by_compiler_executor_and_encoder(monkeypatch):
    d=device(monkeypatch);p=planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    monkeypatch.setattr(fw33_profile,'FX_ZERO_RELEASED',False)
    with pytest.raises(ValueError):planning.compile_design(d.reg,raw(),list(planning.serial_build.ROUTE),8)
    with pytest.raises(ValueError):executor.prepare(d,p['actions'],p['required_route'],322)
    for name in fw33_profile.FX_ZERO_NAMES:
        with pytest.raises(ValueError):protocol.set_parameter(d.reg,d.reg.find_param(name.split('_')[0],name),0.)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


@pytest.mark.parametrize('family,field',[('delay','feedback'),('delay','mix'),('chorus','depth'),('chorus','mix')])
def test_negative_values_still_refused(monkeypatch,family,field):
    d=device(monkeypatch);data=raw();data[family][field]=-.01
    with pytest.raises(ValueError):planning.compile_design(d.reg,data,list(planning.serial_build.ROUTE),8)
    d._write.assert_not_called()

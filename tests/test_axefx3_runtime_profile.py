"""New shared FM9 runtimes cannot silently release unmeasured FX3 writes."""
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import pytest
from fastapi.testclient import TestClient
from devices.axefx3 import fw33,fw33_profile
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from test_axefx3_fw33 import fake
import server


def native():
    return SimpleNamespace(reg=Registry(fw33_profile.KEY),_injected_ports=False,
        _edit_target=322,_edit_owner=threading.get_ident(),firmware_label=Mock(return_value=fw33_profile.KEY),
        current_preset=Mock(return_value=(322,'Test')),outp=Mock())


@pytest.mark.parametrize('platform,version,backend,allowed',[
    ('win32',(3,12),'mido',True),('win32',(3,14),'supriya',False),
    ('win32',(3,11),'mido',False),('win32',(3,12),'supriya',False),
    ('darwin',(3,12),'mido',False),('linux',(3,12),'mido',False),
])
def test_runtime_pin_at_edit_boundary(monkeypatch,platform,version,backend,allowed):
    d=native()
    monkeypatch.setattr(fw33,'sys',SimpleNamespace(platform=platform,version_info=version))
    monkeypatch.setattr(fw33.midi_transport,'backend',lambda:backend)
    if allowed:
        assert fw33.runtime_write_error(d) is None
        AxeFxIII._check_edit_target(d)
    else:
        assert fw33.runtime_write_error(d)
        assert not AxeFxIII.capabilities(d).verifies_writes
        with pytest.raises(PermissionError):AxeFxIII._check_edit_target(d)
        d.current_preset.assert_not_called()
    d.outp.send.assert_not_called()


def test_unknown_backend_is_not_a_fallback(monkeypatch):
    d=native();monkeypatch.setattr(fw33,'sys',SimpleNamespace(platform='win32',version_info=(3,12)))
    def broken():raise fw33.midi_transport.TransportError('Missing backend')
    monkeypatch.setattr(fw33.midi_transport,'backend',broken)
    with pytest.raises(PermissionError,match='backend'):AxeFxIII._check_edit_target(d)
    d.outp.send.assert_not_called()


def test_explicit_scripted_ports_still_work_without_promoting_native(monkeypatch):
    d=native();d._injected_ports=True
    monkeypatch.setattr(fw33,'sys',SimpleNamespace(platform='linux',version_info=(3,14)))
    assert fw33.runtime_write_error(d) is None
    AxeFxIII._check_edit_target(d)
    d.outp.send.assert_not_called()


def test_connected_state_discloses_native_runtime_read_only(monkeypatch):
    d=fake(True);d._injected_ports=False
    monkeypatch.setattr(fw33,'sys',SimpleNamespace(platform='darwin',version_info=(3,12)))
    previous=server._context
    with server.use_device('axefx3',d,d.reg,'Axe-Fx III'),TestClient(server.app) as client:
        response=client.get('/api/axefx3/state')
    assert server._context is previous
    assert response.status_code==200
    data=response.json()
    assert data['connected'] and not data['profile']['write_supported']
    assert 'Windows/Python3.12' in data['route_problem']
    assert data['amp_refresh_supported']
    d.set_param_display.assert_not_called();d.set_bypass.assert_not_called()

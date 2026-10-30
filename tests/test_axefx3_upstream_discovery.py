"""Keep FX3 selection isolated while retaining upstream discovery helpers."""
from types import SimpleNamespace

import pytest

import server


@pytest.mark.parametrize("kind", ["fm9", "axefx3"])
@pytest.mark.parametrize("configured", [False, True])
def test_available_devices_preserves_fx3_context_and_upstream_helpers(monkeypatch, kind, configured):
    import mido

    def no_ports(*args, **kwargs):
        pytest.fail("Selection opened a MIDI port")

    monkeypatch.setattr(mido, "open_input", no_ports)
    monkeypatch.setattr(mido, "open_output", no_ports)
    monkeypatch.setattr(mido, "open_ioport", no_ports)
    monkeypatch.setattr(server, "_headrush_configured", lambda: configured)
    monkeypatch.setattr(server, "detected_devices", lambda: [])
    monkeypatch.setattr(server, "_tonex_configured", lambda: configured)
    monkeypatch.setattr(server, "_ir2_port_present", lambda: False)
    monkeypatch.setattr(server, "_fm3_port_present", lambda: False)
    for name in ("TONECOMMAND_HEADRUSH_HOST", "TONECOMMAND_HEADRUSH_SIM",
                 "TONECOMMAND_TONEX_PORT", "TONECOMMAND_TONEX_SIM",
                 "TONECOMMAND_IR2_SIM", "TONECOMMAND_FM3_SIM"):
        monkeypatch.delenv(name, raising=False)
    previous = server._context
    with server.use_device(kind, SimpleNamespace(), SimpleNamespace(), kind):
        devices = [entry["kind"] for entry in server.available_devices()]
    assert server._context is previous
    assert devices == (["fm9"] + (["axefx3"] if kind == "axefx3" else [])
                       + (["headrush", "tonex"] if configured else []))


def test_detected_iii_is_available_without_selecting_or_opening_it(monkeypatch):
    monkeypatch.setattr(server, 'detected_devices', lambda: [{'kind': 'axefx3'}])
    monkeypatch.setattr(server, '_headrush_configured', lambda: False)
    monkeypatch.setattr(server, '_tonex_configured', lambda: False)
    monkeypatch.setattr(server, '_ir2_port_present', lambda: False)
    monkeypatch.setattr(server, '_fm3_port_present', lambda: False)
    for name in ('TONECOMMAND_HEADRUSH_SIM', 'TONECOMMAND_TONEX_SIM',
                 'TONECOMMAND_IR2_SIM', 'TONECOMMAND_FM3_SIM'):
        monkeypatch.delenv(name, raising=False)
    with server.use_device('fm9', SimpleNamespace(), SimpleNamespace(), 'FM9'):
        assert 'axefx3' in [entry['kind'] for entry in server.available_devices()]

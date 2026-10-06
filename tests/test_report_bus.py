"""#212: Report a problem says what is on the MIDI bus, and connection
failures reach Recent diagnostics without a poll flooding the log."""
import sys

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import diagnostics, midi_transport

REAL_DETECTED = server.detected_devices


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "diag.jsonl"
    real = diagnostics.log_error
    monkeypatch.setattr(diagnostics, "log_error",
                        lambda scope, message, **ctx: real(scope, message, path=path, **ctx))
    monkeypatch.setattr(server, "_last_connection_failure", {"message": None})
    return path


def _logged(path):
    return [e["message"] for e in reversed(diagnostics.read_recent(path=path, limit=50))
            if e["scope"] == "connection"]


def test_environment_lists_ports_detections_and_the_device(monkeypatch):
    monkeypatch.setattr(server, "detected_devices", REAL_DETECTED)
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: ["FM3 MIDI In", "IAC Driver Bus 1"])
    monkeypatch.setattr(midi_transport, "output_names", lambda *a, **k: ["FM3 MIDI Out"])
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setattr(server, "_fm9", None)
    lines = diagnostics.environment()
    assert "MIDI in: 'FM3 MIDI In', 'IAC Driver Bus 1'" in lines
    assert "MIDI out: 'FM3 MIDI Out'" in lines
    assert "Detected: Fractal FM3 (read-only)" in lines
    assert "Device: Fractal FM9 (fm9), not connected" in lines


def test_environment_says_none_and_nothing_recognised_on_an_empty_bus(monkeypatch):
    monkeypatch.setattr(server, "detected_devices", REAL_DETECTED)
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: [])
    monkeypatch.setattr(midi_transport, "output_names", lambda *a, **k: [])
    lines = diagnostics.environment()
    assert "MIDI in: none" in lines and "MIDI out: none" in lines
    assert "Detected: nothing recognised" in lines


def test_environment_version_is_the_checkouts_not_stale_metadata():
    from fm9 import updates
    assert diagnostics.environment()[0].startswith(f"ToneCommand: {updates.current_version()}")


def test_a_repeat_failure_is_logged_once_a_different_one_again(log):
    for m in ("A", "A", "B", "A"):
        server.note_connection(False, m)
    assert _logged(log) == ["A", "B", "A"]


def test_a_success_resets_so_the_same_failure_is_logged_again(log):
    server.note_connection(False, "A")
    server.note_connection(True)
    server.note_connection(False, "A")
    assert _logged(log) == ["A", "A"]


def test_a_failed_poll_select_and_reconnect_reach_the_report(log, monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_context", server._default_context)
    client = TestClient(server.app)

    def gone():
        raise server.FM9NotFound("FM9 MIDI ports not found; is it connected and powered on?")
    monkeypatch.setattr(server, "get_fm9", gone)
    assert client.get("/api/state").json()["connected"] is False

    monkeypatch.setenv("TONECOMMAND_FM3_SIM", "1")

    def no_fm3(kind):
        raise RuntimeError("FM3 MIDI ports not found; is it connected and powered on?")
    monkeypatch.setattr(server, "_build_context", no_fm3)
    r = client.post("/api/device/select", json={"kind": "fm3"})
    assert r.status_code == 503 and "could not open the Fractal FM3" in r.json()["error"]
    assert server.device_context().kind == "fm9"             # left as it was

    monkeypatch.setattr(server, "_context", server.DeviceContext("ir2", server.FM9_REGISTRY, None, "BOSS IR-2"))
    monkeypatch.setattr(server, "_build_context", lambda kind: (_ for _ in ()).throw(RuntimeError("IR-2 port vanished")))
    assert client.post("/api/reconnect").json()["connected"] is False

    got = _logged(log)
    assert got[0] == "FM9 MIDI ports not found; is it connected and powered on?"
    assert "Fractal FM3: FM3 MIDI ports not found; is it connected and powered on?" in got
    assert "BOSS IR-2: IR-2 port vanished" in got
    body = diagnostics.package_for_sharing(path=log)["body"]
    assert "Fractal FM3: FM3 MIDI ports not found" in body
    assert "(no local diagnostics entries to include)" not in body


def test_the_transport_names_the_device_it_looked_for(monkeypatch):
    monkeypatch.setattr(midi_transport, "backend", lambda env=None: "mido")
    monkeypatch.setattr(midi_transport.mido, "get_input_names", lambda: [])
    monkeypatch.setattr(midi_transport.mido, "get_output_names", lambda: [])
    with pytest.raises(midi_transport.TransportError, match="^FM3 MIDI ports not found"):
        midi_transport.open_ports("fm3")
    with pytest.raises(midi_transport.TransportError, match="^FM9 MIDI ports not found"):
        midi_transport.open_ports("fm9")

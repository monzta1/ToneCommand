"""#212: Report a problem says what is on the MIDI bus, and connection
failures reach Recent diagnostics without a poll flooding the log."""
import sys

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import diagnostics, midi_transport

REAL_DETECTED = server.detected_devices
REAL_MIDI = diagnostics._midi


@pytest.fixture(autouse=True)
def _report_reads_the_patched_transport(monkeypatch):
    """Back to the real lookup, which reads midi_transport; each test below
    patches midi_transport itself, so no test touches the machine's bus."""
    monkeypatch.setattr(diagnostics, "_midi", REAL_MIDI)
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: [])
    monkeypatch.setattr(midi_transport, "output_names", lambda *a, **k: [])


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


# --- #216: the not-found message says what the bus shows ---------------------------

NO_INPUT = "this computer sees no MIDI input at all"
DRIVER = ("On Windows a Fractal FM3 or FM9 also needs Fractal's USB driver, "
          "the one FM3-Edit and FM9-Edit use, from fractalaudio.com.")


def _mido_bus(monkeypatch, ins, outs, system):
    monkeypatch.setattr(midi_transport, "backend", lambda env=None: "mido")
    monkeypatch.setattr(midi_transport.mido, "get_input_names", lambda: list(ins))
    monkeypatch.setattr(midi_transport.mido, "get_output_names", lambda: list(outs))
    monkeypatch.setattr(midi_transport, "_system", lambda: system)


def _why(hint):
    with pytest.raises(midi_transport.TransportError) as got:
        midi_transport.open_ports(hint)
    return str(got.value)


@pytest.mark.parametrize("hint", ["fm9"])
def test_empty_bus_on_windows_names_the_driver_mido(monkeypatch, hint):
    """The #216 report: no input at all, only the GS Wavetable Synth out."""
    _mido_bus(monkeypatch, [], ["Microsoft GS Wavetable Synth 0"], "Windows")
    why = _why(hint)
    assert why.startswith(f"{hint.upper()} MIDI ports not found: ")
    assert NO_INPUT in why and "USB cable that carries data" in why
    assert why.endswith(DRIVER)


class _NoPorts:
    def __init__(self, names):
        self.names = names

    def get_ports(self):
        return list(self.names)


class _Supriya:
    def __init__(self, ins, outs):
        self.ins, self.outs = ins, outs

    def MidiIn(self):
        return _NoPorts(self.ins)

    def MidiOut(self):
        return _NoPorts(self.outs)


@pytest.mark.parametrize("hint", ["fm9"])
def test_empty_bus_on_windows_names_the_driver_supriya(monkeypatch, hint):
    monkeypatch.setattr(midi_transport, "_system", lambda: "Windows")
    sm = _Supriya([], ["Microsoft GS Wavetable Synth 0"])
    with pytest.raises(midi_transport.TransportError) as got:
        midi_transport.SupriyaIn.open(sm, hint)
    why = str(got.value)
    assert why.startswith(f"{hint.upper()} MIDI ports not found: ")
    assert NO_INPUT in why and why.endswith(DRIVER)


def test_supriya_output_side_never_reports_empty_bus(monkeypatch):
    """The output side only ever sees outputs, which say nothing about the unit."""
    monkeypatch.setattr(midi_transport, "_system", lambda: "Darwin")
    with pytest.raises(midi_transport.TransportError) as got:
        midi_transport.SupriyaOut.open(_Supriya([], []), "fm9")
    assert str(got.value) == "FM9 MIDI ports not found; is it connected and powered on?"


def test_empty_bus_off_windows_has_no_driver_sentence(monkeypatch):
    _mido_bus(monkeypatch, [], [], "Darwin")
    why = _why("fm9")
    assert NO_INPUT in why and "driver" not in why


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_fm3_empty_bus_names_the_interface_route_never_a_driver(monkeypatch, system):
    """#221: the FM3 has no MIDI over USB (its USB is COM over USB for
    FM3-Edit), so #216's driver advice never applies to it."""
    _mido_bus(monkeypatch, [], ["Microsoft GS Wavetable Synth 0"], system)
    why = _why("fm3")
    assert why.startswith("FM3 MIDI ports not found. ")
    assert "MIDI interface" in why and "no MIDI over USB" in why
    assert "driver" not in why.lower() and DRIVER not in why


def test_other_ports_on_windows_keep_the_driver_but_not_the_empty_bus_clause(monkeypatch):
    _mido_bus(monkeypatch, ["USB Keyboard"], ["Microsoft GS Wavetable Synth 0"], "Windows")
    why = _why("fm9")
    assert why == "FM9 MIDI ports not found; is it connected and powered on? " + DRIVER
    assert NO_INPUT not in why


def test_other_ports_off_windows_are_unchanged(monkeypatch):
    _mido_bus(monkeypatch, ["IAC Driver Bus 1"], ["IAC Driver Bus 1"], "Linux")
    assert _why("fm9") == "FM9 MIDI ports not found; is it connected and powered on?"


@pytest.mark.parametrize("ins", [[], ["USB Keyboard"]])
def test_not_fractal_hint_gets_no_driver_sentence(monkeypatch, ins):
    """#216 review: an empty bus gave every device the new wording."""
    _mido_bus(monkeypatch, ins, [], "Windows")
    assert _why("ir-2") == "IR-2 MIDI ports not found; is it connected and powered on?"


def test_the_driver_advice_reaches_the_report(log, monkeypatch):
    """The real FM9 class raises the transport's message as FM9NotFound; the
    poll logs it for Report a problem."""
    from fm9.device import FM9
    _mido_bus(monkeypatch, [], ["Microsoft GS Wavetable Synth 0"], "Windows")
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setattr(server, "_fm9", None)
    monkeypatch.setattr(server, "get_fm9", lambda: FM9(server.reg))
    assert TestClient(server.app).get("/api/state").json()["connected"] is False
    body = diagnostics.package_for_sharing(path=log)["body"]
    assert NO_INPUT in body and DRIVER in body


def test_windows_doc_step_2_keeps_the_fm9_driver_and_routes_the_fm3_through_an_interface():
    """#221: the FM3 has no MIDI over USB, so step 2 gives it a MIDI interface,
    never Fractal's USB driver; the FM9's driver step stays."""
    from pathlib import Path
    doc = (Path(__file__).resolve().parent.parent / "docs" / "WINDOWS.md").read_text(encoding="utf-8")
    step2 = doc.split("## Step 2", 1)[1].split("\n## ", 1)[0]
    assert "https://www.fractalaudio.com/fm9-downloads/" in step2
    assert "https://www.fractalaudio.com/fm3-downloads/" not in step2
    assert "FM3" in step2.splitlines()[0]
    assert "no MIDI over USB" in step2 and "MIDI interface" in step2 and "5-pin" in step2
    assert chr(0x2014) not in doc


def test_a_failed_reconnect_leaves_no_dead_handle(log, monkeypatch):
    """Review: the closed adapter stayed in the context, so the report said
    'handle open' for a device that was gone."""
    monkeypatch.setenv("TONECOMMAND_FM3_SIM", "1")
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_context", server._default_context)
    client = TestClient(server.app)
    assert client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    monkeypatch.setattr(server, "_build_context", lambda kind: (_ for _ in ()).throw(RuntimeError("FM3 missing")))
    assert client.post("/api/reconnect").json() == {"connected": False, "why": "FM3 missing"}
    assert server.device_context().kind == "fm3" and server.device_context().adapter is None
    assert "Device: Fractal FM3 (fm3), not connected" in diagnostics.environment()
    assert client.get("/api/state").json()["connected"] is False


def test_a_named_device_read_failure_reaches_the_report(log, monkeypatch):
    class Dead:
        def capabilities(self):
            from fm9.adapter import Capabilities
            return Capabilities(has_named_params=True)

        def named_params(self):
            raise RuntimeError("IR-2 disconnected")
    monkeypatch.setattr(server, "_context", server.DeviceContext("ir2", server.FM9_REGISTRY, Dead(), "BOSS IR-2"))
    monkeypatch.setattr(server, "_named_param_state", lambda a, d: a.named_params())
    s = TestClient(server.app).get("/api/state").json()
    assert s["connected"] is False
    assert _logged(log) == ["IR-2 disconnected"]


def test_fm9_reconnect_logs_an_unexpected_failure_and_resets_on_success(log, monkeypatch):
    """Review: a RuntimeError on the FM9 reconnect path logged nothing, and a
    success did not reset, so A, success, A was logged once."""
    monkeypatch.setattr(server, "_context", server._default_context)
    client = TestClient(server.app)
    monkeypatch.setattr(server, "rescan_midi", lambda: None)
    monkeypatch.setattr(server, "get_fm9", lambda: (_ for _ in ()).throw(RuntimeError("MIDI disconnected")))
    assert client.post("/api/reconnect").json()["connected"] is False
    monkeypatch.setattr(server, "get_fm9", lambda: object())
    monkeypatch.setattr(server, "snapshot", lambda dev: {"preset": {"number": 1}})
    assert client.post("/api/reconnect").json()["connected"] is True
    monkeypatch.setattr(server, "get_fm9", lambda: (_ for _ in ()).throw(RuntimeError("MIDI disconnected")))
    client.post("/api/reconnect")
    assert _logged(log) == ["MIDI disconnected", "MIDI disconnected"]

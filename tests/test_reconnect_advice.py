"""#219: a failed reconnect says how to rule out FM3-Edit or FM9-Edit, and
only when that can be the cause.

A Windows FM3 owner's second report: the driver was installed, FM3-Edit saw
the unit, Report a problem still showed "MIDI in: none", and the page told
them to "check FM9-Edit is not holding the port", which they did not know how
to do. That line was fixed in the page for every device and every failure."""
import sys

sys.argv = ["x"]
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import midi_transport

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
SCRIPT = UI.split("<script>")[1]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """No test here reads the machine's MIDI bus or writes its diagnostics
    log; each sets the bus it means."""
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: [])
    monkeypatch.setattr(server, "rescan_midi", lambda: None)
    monkeypatch.setattr(server, "note_connection", lambda ok, message="": None)
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setattr(server, "_fm9", None)


def _bus(monkeypatch, names):
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: list(names))


def _fm9_fails(monkeypatch, exc):
    def gone():
        raise exc
    monkeypatch.setattr(server, "get_fm9", gone)


def _fm3_fails(monkeypatch, exc):
    monkeypatch.setattr(server, "_context",
                        server.DeviceContext("fm3", server.FM9_REGISTRY, None, "Fractal FM3"))

    def no_fm3(kind):
        raise exc
    monkeypatch.setattr(server, "_build_context", no_fm3)


def _reconnect():
    r = TestClient(server.app).post("/api/reconnect")
    assert r.status_code == 200
    return r.json()


# --- REQ-001: the advice, where an editor can be the cause --------------------

@pytest.mark.parametrize("exc", [server.FM9NotFound("FM9 port opened but the device did not answer"),
                                 RuntimeError("MidiInWinMM::openPort: error creating input port")])
def test_fm9_reconnect_with_inputs_gives_editor_advice(monkeypatch, exc):
    _bus(monkeypatch, ["FM9 MIDI In"])
    _fm9_fails(monkeypatch, exc)
    d = _reconnect()
    assert d["connected"] is False and d["why"] == str(exc)
    assert d["advice"] == midi_transport.EDITOR_ADVICE


def test_fm3_reconnect_with_inputs_gives_editor_advice(monkeypatch):
    _bus(monkeypatch, ["FM3 MIDI In"])
    _fm3_fails(monkeypatch, RuntimeError("FM3 port would not open"))
    d = _reconnect()
    assert d == {"connected": False, "why": "FM3 port would not open",
                 "advice": midi_transport.EDITOR_ADVICE}


def test_editor_advice_names_both_editors_and_how_to_check():
    a = midi_transport.EDITOR_ADVICE
    assert "FM3-Edit" in a and "FM9-Edit" in a and "close it" in a
    assert "Task Manager" in a and "Ctrl+Shift+Esc" in a
    assert chr(0x2014) not in a


def test_page_prints_the_servers_advice_not_a_fixed_fm9_edit_line():
    fn = SCRIPT.split("async function reconnect()")[1].split("\n}\n")[0]
    assert "still not connected" in fn and "d.advice" in fn
    assert "still no FM9" not in fn and "FM9-Edit" not in fn


# --- REQ-002: no advice where an editor cannot be the cause ------------------

def test_fm9_reconnect_on_an_empty_bus_has_no_advice(monkeypatch):
    _fm9_fails(monkeypatch, server.FM9NotFound("FM9 MIDI ports not found: this computer sees no MIDI input at all."))
    d = _reconnect()
    assert d["connected"] is False and "advice" not in d


def test_fm3_reconnect_on_an_empty_bus_has_no_advice(monkeypatch):
    _fm3_fails(monkeypatch, RuntimeError("FM3 MIDI ports not found"))
    assert _reconnect() == {"connected": False, "why": "FM3 MIDI ports not found"}


@pytest.mark.parametrize("kind,label", [("ir2", "BOSS IR-2"), ("tonex", "IK ToneX")])
def test_other_device_reconnect_has_no_advice(monkeypatch, kind, label):
    _bus(monkeypatch, ["IR-2", "ToneX Pedal"])
    monkeypatch.setattr(server, "_context", server.DeviceContext(kind, server.FM9_REGISTRY, None, label))
    monkeypatch.setattr(server, "_build_context",
                        lambda k: (_ for _ in ()).throw(RuntimeError(f"{label} port vanished")))
    assert _reconnect() == {"connected": False, "why": f"{label} port vanished"}


@pytest.mark.parametrize("hint", ["ir-2", "tonex", "helix"])
def test_other_hint_gets_no_advice_from_the_helper(monkeypatch, hint):
    _bus(monkeypatch, ["Anything In"])
    assert midi_transport.editor_advice(hint) is None


def _bus_raises(monkeypatch):
    def broken(*a, **k):
        raise OSError("rtmidi could not create a client")
    monkeypatch.setattr(midi_transport, "port_names", broken)


def test_fm9_reconnect_when_the_bus_raises_answers_without_advice(monkeypatch):
    _bus_raises(monkeypatch)
    _fm9_fails(monkeypatch, server.FM9NotFound("FM9 MIDI ports not found"))
    assert _reconnect() == {"connected": False, "why": "FM9 MIDI ports not found"}


def test_fm3_reconnect_when_the_bus_raises_answers_without_advice(monkeypatch):
    _bus_raises(monkeypatch)
    _fm3_fails(monkeypatch, RuntimeError("FM3 MIDI ports not found"))
    assert _reconnect() == {"connected": False, "why": "FM3 MIDI ports not found"}


# --- REQ-003: restart after the Windows driver; the silent-port message -------

RESTART = " After installing it, restart ToneCommand."
V159_EMPTY = ("FM3 MIDI ports not found: this computer sees no MIDI input at all. Is it "
              "connected and powered on, with a USB cable that carries data?")


@pytest.mark.parametrize("hint", ["fm9", "fm3"])
def test_windows_empty_bus_says_restart_after_the_driver(hint):
    msg = midi_transport._not_found(hint, inputs=[], system="Windows")
    assert msg.endswith("from fractalaudio.com." + RESTART)


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_no_restart_off_windows_and_text_unchanged_from_1_5_9(system):
    assert midi_transport._not_found("fm3", inputs=[], system=system) == V159_EMPTY


def test_no_restart_on_windows_when_the_bus_lists_inputs():
    msg = midi_transport._not_found("fm9", inputs=["USB Keyboard"], system="Windows")
    assert "restart" not in msg


def test_no_restart_for_another_device_on_windows():
    assert midi_transport._not_found("ir-2", inputs=[], system="Windows") == \
        "IR-2 MIDI ports not found; is it connected and powered on?"


@pytest.mark.parametrize("cls_name", ["FM9", "FM3"])
def test_silent_port_message_names_fm3_edit_and_fm9_edit(monkeypatch, cls_name):
    from fm9 import device
    cls = getattr(device, cls_name)
    monkeypatch.setattr(cls, "_drain", lambda self: None)
    monkeypatch.setattr(cls, "current_preset", lambda self: None)
    monkeypatch.setattr(cls, "close", lambda self: None)
    with pytest.raises(device.FM9NotFound) as got:
        cls(server.FM9_REGISTRY, ports=(object(), object()))
    why = str(got.value)
    assert why.startswith(f"{cls.LABEL} port opened but the device did not answer")
    assert "FM3-Edit or FM9-Edit is running" in why


# --- REQ-004: the Windows guide says how to check ---------------------------

def test_windows_docs_say_how_to_check_the_editor_and_what_none_means():
    doc = (ROOT / "docs" / "WINDOWS.md").read_text(encoding="utf-8")
    part = doc.split("cannot find the\nFM9 or FM3**", 1)[1].split("\n\n**", 1)[0]
    assert "FM3-Edit" in part and "FM9-Edit" in part
    assert "Task Manager" in part and "Ctrl+Shift+Esc" in part and "End task" in part
    assert '"MIDI in: none"' in part and "the editor is not the cause" in part
    assert "restart ToneCommand" in part
    assert chr(0x2014) not in doc

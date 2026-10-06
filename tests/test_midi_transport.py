"""Issue #172: the MIDI transport seam. Backend selection, the supriya-midi
adapters on a fake port pair, the never-brick guard above them, and the
packaging that keeps the Python ceiling until the hardware pass.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mido
import pytest

import server
from fm9 import midi_transport as T
from fm9 import protocol as p
from fm9.device import FM9, FM9NotFound
from fm9.sim import SimFM9

ROOT = Path(__file__).resolve().parent.parent


# --- REQ-001: selection and the seam ------------------------------------------------------------

def _imports(monkeypatch, available: set[str]):
    monkeypatch.setattr(T, "_importable", lambda name: name in available)


def test_select_auto_prefers_mido_then_supriya_then_refuses_with_the_install_line(monkeypatch):
    _imports(monkeypatch, {"rtmidi", "supriya_midi"})
    assert T.backend({}) == "mido"
    _imports(monkeypatch, {"supriya_midi"})
    assert T.backend({}) == "supriya"
    _imports(monkeypatch, set())
    with pytest.raises(T.TransportError, match="install python-rtmidi .* or supriya-midi"):
        T.backend({})
    _imports(monkeypatch, {"rtmidi"})
    assert T.backend({T.ENV: "mido"}) == "mido"
    with pytest.raises(T.TransportError, match="pip install supriya-midi"):
        T.backend({T.ENV: "supriya"})
    _imports(monkeypatch, {"supriya_midi"})
    with pytest.raises(T.TransportError, match="3.11 or 3.12, or set TONECOMMAND_MIDI_BACKEND=supriya"):
        T.backend({T.ENV: "mido"})
    with pytest.raises(T.TransportError, match="not one of"):
        T.backend({T.ENV: "pygame"})


def test_seam_the_device_layer_opens_ports_through_the_transport_only(monkeypatch):
    src = (ROOT / "fm9" / "device.py").read_text(encoding="utf-8")
    assert "mido.get_input_names" not in src and "mido.open_input" not in src
    assert "midi_transport.open_ports(port_hint or self.PORT_HINT)" in src
    # a missing device is still FM9NotFound with the one line
    monkeypatch.setattr(T, "open_ports", lambda hint, **k: (_ for _ in ()).throw(T.TransportError("FM9 MIDI ports not found; is it connected and powered on?")))
    with pytest.raises(FM9NotFound, match="not found"):
        FM9(server.reg)
    # rescan reloads mido's backend only when mido is the backend
    ssrc = (ROOT / "server.py").read_text(encoding="utf-8")
    assert 'if midi_transport.backend() == "mido"' in ssrc


def test_port_names_go_through_the_backend_and_presence_uses_them(monkeypatch):
    sm = FakeSupriya(names=("IAC Bus", "FM9 MIDI In"))
    _imports(monkeypatch, {"supriya_midi"})
    assert T.port_names({T.ENV: "supriya"}, supriya_module=sm) == ["IAC Bus", "FM9 MIDI In"]
    assert sm.inp.opened is None                        # enumeration opens nothing
    _imports(monkeypatch, set())
    assert T.port_names({}) == []                       # no backend: absent, not an error
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "midi_transport.port_names()" in src and "mido.get_input_names" not in src.split("def _fm9_port_present", 1)[1].split("\ndef ", 1)[0]
    monkeypatch.setattr(T, "port_names", lambda env=None, supriya_module=None: ["FM9 MIDI In"])
    monkeypatch.setattr(server, "_pump_coremidi", lambda: None)
    assert server._fm9_port_present() is True
    monkeypatch.setattr(T, "port_names", lambda env=None, supriya_module=None: [])
    assert server._fm9_port_present() is False


def test_sim_is_untouched_and_the_injected_ports_bypass_the_transport(monkeypatch):
    called = []
    monkeypatch.setattr(T, "open_ports", lambda hint, **k: called.append(hint) or (None, None))
    dev = SimFM9(server.reg)
    assert dev.status_dump() and called == []


# --- REQ-002: supriya adapters on a fake port pair ------------------------------------------------

class FakePort:
    """Enough of supriya_midi.MidiIn/MidiOut to prove the adapters."""

    def __init__(self, names):
        self.names, self.opened, self.sent, self.queue = names, None, [], []
        self.ignored, self.buffer, self.closed = None, None, False

    def get_ports(self):
        return list(self.names)

    def open_port(self, port_number=0, port_name="RtMidi"):
        self.opened = (port_number, port_name)
        return self

    def ignore_types(self, sysex=True, timing=True, active_sense=True):
        self.ignored = (sysex, timing, active_sense)

    def set_buffer_size(self, size=1024, count=4):
        self.buffer = (size, count)

    def get_message(self):
        return self.queue.pop(0) if self.queue else None

    def send_message(self, message):
        self.sent.append(list(message))

    def close_port(self):
        self.closed = True


class FakeSupriya:
    def __init__(self, names=("IAC Bus", "FM9 MIDI Out")):
        self.inp, self.out = FakePort(names), FakePort(names)

    def MidiIn(self):
        return self.inp

    def MidiOut(self):
        return self.out


def test_supriya_ports_open_by_name_with_sysex_enabled_and_a_big_buffer():
    sm = FakeSupriya()
    inp, out = T.open_ports("fm9", env={T.ENV: "supriya"}, supriya_module=sm) if T._importable("supriya_midi") \
        else (T.SupriyaIn.open(sm, "fm9"), T.SupriyaOut.open(sm, "fm9"))
    assert sm.inp.opened == (1, "ToneCommand in") and sm.out.opened == (1, "ToneCommand out")
    assert sm.inp.ignored == (False, True, True) and sm.inp.buffer == T.SUPRIYA_BUFFER
    inp.close(); out.close()
    assert sm.inp.closed and sm.out.closed
    with pytest.raises(T.TransportError, match="not found"):
        T.SupriyaIn.open(FakeSupriya(names=("IAC Bus",)), "fm9")


def test_supriya_sysex_round_trip_and_the_channel_messages():
    sm = FakeSupriya()
    inp, out = T.SupriyaIn.open(sm, "fm9"), T.SupriyaOut.open(sm, "fm9")
    frame = p.build_get_channel(62)
    out.send(mido.Message("sysex", data=frame[1:-1]))
    assert sm.out.sent == [frame] and sm.out.sent[0][0] == 0xF0 and sm.out.sent[0][-1] == 0xF7
    out.send(mido.Message("control_change", control=0, value=1))
    out.send(mido.Message("program_change", program=11))
    assert sm.out.sent[1:] == [[0xB0, 0, 1], [0xC0, 11]]
    with pytest.raises(T.TransportError, match="does not send"):
        out.send(mido.Message("note_on", note=60))
    # inbound: sysex without F0/F7, program and control change, other passed through
    sm.inp.queue = [(frame, 0.0), ([0xC0, 5], 0.0), ([0xB1, 7, 100], 0.0), ([0xF8], 0.0), (frame, 0.0)]
    msgs = list(inp.iter_pending())
    assert [m.type for m in msgs] == ["sysex", "program_change", "control_change", "other", "sysex"]
    assert msgs[0].data == frame[1:-1] and msgs[1].program == 5 and (msgs[2].control, msgs[2].value, msgs[2].channel) == (7, 100, 1)
    assert list(inp.iter_pending()) == []


def test_supriya_pair_drives_the_device_layer_end_to_end_with_the_sim_core_behind_it():
    """The supriya adapters in front of the SIMULATOR's core: every frame
    the device layer sends goes out as bytes through SupriyaOut, is
    answered by the sim core, and comes back through SupriyaIn. A status
    dump and a 2,100-frame bulk read both survive the trip."""
    sm = _wired_pair()
    dev = FM9(server.reg, ports=(T.SupriyaIn.open(sm, "fm9"), T.SupriyaOut.open(sm, "fm9")))
    assert dev.status_dump()
    values = dev.bulk_read(62)
    assert values and len(values) > 100
    assert dev.get_channel(62) == 0
    assert all(f[0] == 0xF0 and f[-1] == 0xF7 for f in sm.out.sent if f[0] == 0xF0)


def _wired_pair():
    """A fake supriya pair with the simulator's core answering behind it."""
    from fm9.sim import SimFM9Core
    core = SimFM9Core()
    core.st.reg = server.reg
    sm = FakeSupriya()

    def wire(message):
        frame = list(message)
        sm.out.sent.append(frame)
        for resp in core.handle(frame):
            sm.inp.queue.append((resp, 0.0))
    sm.out.send_message = wire
    return sm


def test_the_never_brick_guard_sits_above_the_transport():
    sm = _wired_pair()
    dev = FM9(server.reg, ports=(T.SupriyaIn.open(sm, "fm9"), T.SupriyaOut.open(sm, "fm9")))
    before = len(sm.out.sent)
    forbidden = p.envelope(0x7D, [0, 0, 0])            # not a decoded, user-data function id
    with pytest.raises(Exception):
        dev._send(forbidden)
    assert len(sm.out.sent) == before                   # nothing reached the port
    assert forbidden not in sm.out.sent


# --- REQ-003: packaging and docs ---------------------------------------------------------------------

def test_pyproject_markers_keep_the_cap_until_the_hardware_pass():
    src = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"python-rtmidi>=1.5,<2; python_version < \'3.13\'"' in src
    assert '"supriya-midi>=26.9b0; python_version >= \'3.13\'"' in src
    assert 'requires-python = ">=3.11,<3.13"' in src
    assert "#172" in src and "hardware pass" in src


def test_docs_say_the_ceiling_lifts_after_the_pass_and_name_the_backend_variable():
    setup = (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for text in (setup, readme):
        assert "TONECOMMAND_MIDI_BACKEND" in text
        assert re.search(r"hardware pass", text)
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "#172" in changelog.split("## 1.4.1", 1)[0]

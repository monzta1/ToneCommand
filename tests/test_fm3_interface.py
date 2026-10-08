"""#221 Part A: FM3 interface guidance and exact transport binding, no hardware."""
import json
import sys
from types import SimpleNamespace

import pytest

from fm9 import midi_transport as T
from fm9 import protocol as p
from fm9.device import FM3, FM9, FM9NotFound
from fm9.sim import SimFM9Core


@pytest.fixture(autouse=True)
def isolated_binding(monkeypatch, tmp_path):
    monkeypatch.delenv(T.FM3_PORT_ENV, raising=False)
    path = tmp_path / "fm3_port.json"
    monkeypatch.setattr(T, "fm3_binding_path", lambda: path)
    return path


class FakePort:
    """Both backend shapes with the model-specific simulator on the wire."""
    def __init__(self, names):
        self.names = list(names)
        self.opened = None
        self.closed = False
        self.queue = []
        self.sent = []

    def get_ports(self):
        return self.names

    def open_port(self, index, label):
        self.opened = self.names[index]

    def set_buffer_size(self, *args):
        self.buffer = args

    def ignore_types(self, **kwargs):
        self.ignored = kwargs

    def close_port(self):
        self.closed = True

    close = close_port

    def get_message(self):
        return (self.queue.pop(0), 0.0) if self.queue else None

    def iter_pending(self):
        while self.queue:
            yield T._decode(self.queue.pop(0))

    def send(self, msg):
        self.send_message(T._encode(msg))


def bus(monkeypatch, backend, ins, outs, *, silent=False, model=p.MODEL_FM3):
    inp, out = FakePort(ins), FakePort(outs)
    core = SimFM9Core(model=model)

    def send(frame):
        out.sent.append(frame)
        if not silent:
            inp.queue.extend(core.handle(frame))

    out.send_message = send
    sm = SimpleNamespace(MidiIn=lambda: inp, MidiOut=lambda: out)
    monkeypatch.setattr(T, "backend", lambda env=None: backend)
    # Inject only the library, so open_ports still resolves and selects names.
    monkeypatch.setitem(sys.modules, "supriya_midi", sm)
    monkeypatch.setattr(T.mido, "get_input_names", lambda: list(ins))
    monkeypatch.setattr(T.mido, "get_output_names", lambda: list(outs))

    def open_input(name):
        assert name in ins
        inp.opened = name
        return inp

    def open_output(name):
        assert name in outs
        out.opened = name
        return out

    monkeypatch.setattr(T.mido, "open_input", open_input)
    monkeypatch.setattr(T.mido, "open_output", open_output)
    return inp, out


def assert_fm3_guidance(text):
    assert "FM3" in text and "FM9" not in text
    for phrase in ("no MIDI over USB", "USB MIDI interface", "5-pin MIDI IN",
                   "MIDI OUT", "Devices", "Fractal-Bot", "Cab-Lab"):
        assert phrase in text
    for phrase in ("USB driver", "is running", "holding", "restart", "zombie"):
        assert phrase not in text


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_unbound_fm3_failure_guides_to_interface(monkeypatch, system):
    monkeypatch.setattr(T, "_system", lambda: system)
    monkeypatch.setattr(T, "backend", lambda env=None: "mido")
    monkeypatch.setattr(T.mido, "get_input_names", lambda: [])
    monkeypatch.setattr(T.mido, "get_output_names", lambda: [])
    with pytest.raises(FM9NotFound) as got:
        FM3()
    assert_fm3_guidance(str(got.value))


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_opened_but_silent_fm3_guides_to_interface(monkeypatch, system):
    monkeypatch.setattr(T, "_system", lambda: system)
    monkeypatch.setattr(FM3, "_drain", lambda self: None)
    monkeypatch.setattr(FM3, "current_preset", lambda self: None)
    class Port:
        closed = False

        def close(self):
            self.closed = True

    inp, out = Port(), Port()
    with pytest.raises(FM9NotFound) as got:
        FM3(ports=(inp, out))
    assert inp.closed and out.closed
    assert_fm3_guidance(str(got.value))


@pytest.mark.parametrize("backend", ["mido", "supriya"])
@pytest.mark.parametrize("system", ["Windows", "Darwin"])
@pytest.mark.parametrize("failure", ["unbound", "missing", "silent"])
def test_fm3_failure_matrix(monkeypatch, isolated_binding, backend, system, failure):
    monkeypatch.setattr(T, "_system", lambda: system)
    names = ["MIDI Interface 2"]
    if failure != "unbound":
        isolated_binding.write_text(json.dumps({"port": "MIDI Interface"}))
    if failure == "silent":
        names.append("MIDI Interface")
    inp, out = bus(monkeypatch, backend, names, names, silent=True)
    with pytest.raises(FM9NotFound) as got:
        FM3()
    assert_fm3_guidance(str(got.value))
    if failure == "silent":
        assert inp.opened == out.opened == "MIDI Interface"
        assert out.sent and inp.closed and out.closed
    else:
        assert inp.opened is None and out.opened is None and not out.sent


@pytest.mark.parametrize("backend", ["mido", "supriya"])
def test_binding_round_trip_and_exact_simulated_connection(monkeypatch, isolated_binding, backend):
    names = ["MIDI Interface 2", "midi interface", "MIDI Interface", "FM3 MIDI"]
    inp, out = bus(monkeypatch, backend, names, names)
    assert T.load_fm3_binding() == {"port": None, "source": "none"}
    assert T.port_names() == names and T.output_names() == names
    assert inp.opened is None and out.opened is None
    assert T.save_fm3_binding("MIDI Interface") == {"port": "MIDI Interface", "source": "file"}
    assert json.loads(isolated_binding.read_text()) == {"port": "MIDI Interface"}
    assert T.load_fm3_binding() == {"port": "MIDI Interface", "source": "file"}
    dev = FM3()
    try:
        assert inp.opened == out.opened == "MIDI Interface"
        assert dev.current_preset() and dev.status_dump()
        assert out.sent and all(frame[4] == p.MODEL_FM3 for frame in out.sent)
    finally:
        dev.close()


@pytest.mark.parametrize("backend", ["mido", "supriya"])
@pytest.mark.parametrize("missing_side", ["input", "output", "both"])
def test_missing_bound_name_never_falls_back(monkeypatch, isolated_binding, backend, missing_side):
    isolated_binding.write_text(json.dumps({"port": "MIDI Interface"}))
    other = ["MIDI Interface 2", "midi interface", "FM3 MIDI"]
    ins = other if missing_side in ("input", "both") else ["MIDI Interface", *other]
    outs = other if missing_side in ("output", "both") else ["MIDI Interface", *other]
    inp, out = bus(monkeypatch, backend, ins, outs)
    with pytest.raises(FM9NotFound) as got:
        FM3()
    assert_fm3_guidance(str(got.value))
    assert inp.opened is None and out.opened is None and not out.sent


@pytest.mark.parametrize("backend", ["mido", "supriya"])
@pytest.mark.parametrize("env_port", ["B", "missing", ""])
def test_environment_wins_and_refuses_save(monkeypatch, isolated_binding, backend, env_port):
    names = ["A", "B 2", "B", "FM3 MIDI"]
    inp, out = bus(monkeypatch, backend, names, names)
    T.save_fm3_binding("A")
    before = isolated_binding.read_bytes()
    monkeypatch.setenv(T.FM3_PORT_ENV, env_port)
    assert T.load_fm3_binding() == {"port": env_port, "source": "env"}
    with pytest.raises(T.TransportError, match=T.FM3_PORT_ENV):
        T.save_fm3_binding("A")
    assert isolated_binding.read_bytes() == before
    if env_port == "B":
        dev = FM3(port_hint="A")
        assert inp.opened == out.opened == "B"
        dev.close()
    else:
        with pytest.raises(FM9NotFound) as got:
            FM3()
        assert_fm3_guidance(str(got.value))
        assert inp.opened is None and out.opened is None


@pytest.mark.parametrize("backend", ["mido", "supriya"])
@pytest.mark.parametrize("port", ["unknown", "Input Only", "Output Only", "MIDI", "", None])
def test_save_refuses_names_not_in_both_lists(monkeypatch, isolated_binding, backend, port):
    bus(monkeypatch, backend, ["Input Only", "MIDI Interface"], ["Output Only", "MIDI Interface"])
    T.save_fm3_binding("MIDI Interface")
    before = isolated_binding.read_bytes()
    with pytest.raises(T.TransportError, match="both"):
        T.save_fm3_binding(port)
    assert isolated_binding.read_bytes() == before


@pytest.mark.parametrize("backend", ["mido", "supriya"])
def test_unbound_fm3_named_discovery_still_works(monkeypatch, backend):
    inp, out = bus(monkeypatch, backend, ["Other", "FM3 MIDI In"], ["Other", "FM3 MIDI Out"])
    dev = FM3()
    assert inp.opened == "FM3 MIDI In" and out.opened == "FM3 MIDI Out"
    assert dev.current_preset()
    dev.close()


@pytest.mark.parametrize("backend", ["mido", "supriya"])
def test_explicit_fm3_port_hint_is_exact_without_binding(monkeypatch, backend):
    inp, out = bus(monkeypatch, backend, ["Interface 2", "Interface"], ["Interface 2", "Interface"])
    dev = FM3(port_hint="Interface")
    assert inp.opened == out.opened == "Interface"
    dev.close()


@pytest.mark.parametrize("contents", ["{", "[]", '{"port": null}', '{"port": ""}'])
def test_damaged_binding_refuses_instead_of_discovering(monkeypatch, isolated_binding, contents):
    inp, out = bus(monkeypatch, "mido", ["FM3 MIDI"], ["FM3 MIDI"])
    isolated_binding.write_text(contents)
    with pytest.raises(FM9NotFound, match="binding"):
        FM3()
    assert inp.opened is None and out.opened is None


@pytest.mark.parametrize("backend", ["mido", "supriya"])
@pytest.mark.parametrize("system", ["Windows", "Darwin"])
@pytest.mark.parametrize("names", [[], ["USB Keyboard"]])
def test_fm9_missing_messages_byte_identical(monkeypatch, backend, system, names):
    bus(monkeypatch, backend, names, ["Microsoft GS Wavetable Synth 0"])
    monkeypatch.setattr(T, "_system", lambda: system)
    monkeypatch.setenv(T.FM3_PORT_ENV, "some interface")
    expected = "FM9 MIDI ports not found"
    if not names:
        expected += (": this computer sees no MIDI input at all. Is it connected "
                     "and powered on, with a USB cable that carries data?")
    else:
        expected += "; is it connected and powered on?"
    if system == "Windows":
        expected += (" On Windows a Fractal FM3 or FM9 also needs Fractal's USB "
                     "driver, the one FM3-Edit and FM9-Edit use, from fractalaudio.com.")
    with pytest.raises(FM9NotFound) as got:
        FM9()
    assert str(got.value) == expected


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_fm9_silent_message_byte_identical(monkeypatch, system):
    monkeypatch.setattr(T, "_system", lambda: system)
    monkeypatch.setattr(FM9, "_drain", lambda self: None)
    monkeypatch.setattr(FM9, "current_preset", lambda self: None)
    with pytest.raises(FM9NotFound) as got:
        FM9(ports=(FakePort([]), FakePort([])))
    assert str(got.value) == (
        "FM9 port opened but the device did not answer a preset-name "
        "query. Either it is still booting, FM9-Edit is running, or a "
        "zombie process is holding the MIDI port (ps aux | grep python).")

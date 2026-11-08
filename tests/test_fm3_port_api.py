"""#221 REQ-002: binding API and port replacement over simulated MIDI only."""
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import midi_transport as transport
from fm9 import protocol
from fm9.sim import SimFM9Core, _SimIn, _SimOut


@pytest.fixture
def rig(monkeypatch, tmp_path):
    for name in (transport.FM3_PORT_ENV, transport.FM3_PORT_OUT_ENV, "TONECOMMAND_FM3_SIM",
                 "TONECOMMAND_HEADRUSH_HOST", "TONECOMMAND_HEADRUSH_SIM",
                 "TONECOMMAND_TONEX_PORT", "TONECOMMAND_TONEX_SIM",
                 "TONECOMMAND_IR2_SIM"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "fm3_port.json"
    monkeypatch.setattr(transport, "fm3_binding_path", lambda: path)
    monkeypatch.setattr(transport, "backend", lambda env=None: "mido")
    ins = ["Interface A", "Interface B 2", "Interface B", "Input Only"]
    outs = ["Output Only", "Interface A", "Interface B 2", "Interface B"]
    monkeypatch.setattr(transport.mido, "get_input_names", lambda: list(ins))
    monkeypatch.setattr(transport.mido, "get_output_names", lambda: list(outs))
    events, pairs, notes = [], {}, []

    def open_input(name):
        assert server._lock.locked()
        assert name in ins
        inp = _SimIn()
        inp.close = lambda: events.append(("close_input", name))
        pairs[name] = pairs[None] = inp
        events.append(("open_input", name))
        return inp

    def open_output(name):
        assert server._lock.locked()
        assert name in outs
        # #255: a split pair answers on the input opened just before it
        out = _SimOut(SimFM9Core(model=protocol.MODEL_FM3), pairs.get(name, pairs[None]))
        out.close = lambda: events.append(("close_output", name))
        events.append(("open_output", name))
        return out

    monkeypatch.setattr(transport.mido, "open_input", open_input)
    monkeypatch.setattr(transport.mido, "open_output", open_output)
    monkeypatch.setattr(server, "rescan_midi", lambda: None)
    monkeypatch.setattr(server, "note_connection", lambda *args: notes.append(args))
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setattr(server, "_fm9", None)
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    client = TestClient(server.app)
    yield SimpleNamespace(client=client, path=path, ins=ins, outs=outs,
                          events=events, notes=notes)
    ctx = server.device_context()
    if ctx.kind == "fm3" and ctx.adapter is not None:
        ctx.adapter.close()
    client.close()


def test_get_unbound_lists_only_savable_ports_without_opening(rig):
    """A port in only one direction is never offered: saving it is refused,
    so the picker must not show it (seen live: a one-way MIDI Monitor port)."""
    response = rig.client.get("/api/fm3/port")
    assert response.status_code == 200
    assert response.json() == {
        "port": None, "port_in": None, "port_out": None, "source": None, "fixed": False,
        "inputs": ["Interface A", "Interface B 2", "Interface B", "Input Only"],
        "outputs": ["Output Only", "Interface A", "Interface B 2", "Interface B"],
        "ports": ["Interface A", "Interface B 2", "Interface B"],
    }
    assert not rig.path.exists() and not rig.events
    for name in response.json()["ports"]:
        assert rig.client.post("/api/fm3/port", json={"port": name}).status_code == 200


def test_save_persists_lists_fm3_and_connects_exact_port(rig):
    assert "fm3" not in [d["kind"] for d in rig.client.get("/api/device").json()["available"]]
    response = rig.client.post("/api/fm3/port", json={"port": "Interface B"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "port": "Interface B", "port_in": "Interface B",
                               "port_out": "Interface B", "source": "file", "reconnected": False}
    assert json.loads(rig.path.read_text(encoding="utf-8")) == {"port": "Interface B"}
    binding = rig.client.get("/api/fm3/port").json()
    assert (binding["port"], binding["source"], binding["fixed"]) == ("Interface B", "file", False)
    assert "fm3" in [d["kind"] for d in rig.client.get("/api/device").json()["available"]]
    assert not rig.events
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    assert rig.events == [("open_input", "Interface B"), ("open_output", "Interface B")]
    assert server.device_context().adapter.current_preset()


@pytest.mark.parametrize("value", ["Interface B", "missing", ""])
def test_environment_precedes_file_and_refuses_save(rig, monkeypatch, value):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    before = rig.path.read_bytes()
    monkeypatch.setenv(transport.FM3_PORT_ENV, value)
    binding = rig.client.get("/api/fm3/port").json()
    assert (binding["port"], binding["source"], binding["fixed"]) == (value, "env", True)
    response = rig.client.post("/api/fm3/port", json={"port": "Interface A"})
    assert response.status_code == 409
    assert response.json()["ok"] is False
    assert "TONECOMMAND_FM3_PORT" in response.json()["error"]
    assert rig.path.read_bytes() == before and not rig.events


@pytest.mark.parametrize("body", [{}, {"port": ""}, {"port": None}, {"port": 1},
                                  {"port": "unknown"}, {"port": "Interface"},
                                  {"port": "Input Only"}, {"port": "Output Only"}])
def test_invalid_name_refused_without_changing_binding(rig, body):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    before = rig.path.read_bytes()
    response = rig.client.post("/api/fm3/port", json=body)
    assert response.status_code == 400
    assert response.json()["ok"] is False and response.json()["error"]
    assert rig.path.read_bytes() == before and not rig.events


def test_save_connected_closes_a_and_opens_b_under_switch_lock(rig, monkeypatch):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    old = server.device_context().adapter
    original_save = transport.save_fm3_binding

    def save(port_in, port_out=None):
        assert server._lock.locked()
        return original_save(port_in, port_out)

    monkeypatch.setattr(transport, "save_fm3_binding", save)
    rig.events.clear()
    response = rig.client.post("/api/fm3/port", json={"port": "Interface B"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "port": "Interface B", "port_in": "Interface B",
                               "port_out": "Interface B", "source": "file", "reconnected": True}
    assert set(rig.events[:2]) == {("close_input", "Interface A"), ("close_output", "Interface A")}
    assert rig.events[2:] == [("open_input", "Interface B"), ("open_output", "Interface B")]
    assert server.device_context().adapter is not old
    assert server.device_context().adapter.current_preset()


def test_bound_port_disappears_without_fallback(rig):
    rig.path.write_text(json.dumps({"port": "Interface B"}), encoding="utf-8")
    rig.ins.remove("Interface B")
    rig.outs.remove("Interface B")
    response = rig.client.post("/api/device/select", json={"kind": "fm3"})
    assert response.status_code == 503
    assert "USB MIDI interface" in response.json()["error"]
    assert not rig.events


def test_failed_reconnect_drops_closed_adapter_and_keeps_new_binding(rig, monkeypatch):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    original_save = transport.save_fm3_binding

    def save_then_unplug(port, port_out=None):
        binding = original_save(port, port_out)
        rig.ins.remove(port)
        return binding

    monkeypatch.setattr(transport, "save_fm3_binding", save_then_unplug)
    rig.events.clear()
    response = rig.client.post("/api/fm3/port", json={"port": "Interface B"})
    assert response.status_code == 200
    assert response.json()["reconnected"] is False
    assert server.device_context().adapter is None
    assert json.loads(rig.path.read_text(encoding="utf-8")) == {"port": "Interface B"}
    assert set(rig.events) == {("close_input", "Interface A"), ("close_output", "Interface A")}
    assert "USB MIDI interface" in rig.notes[-1][1]
    # #221 review: the next state poll keeps the FM3 guidance for the report
    rig.notes.clear()
    rig.client.get("/api/state")
    polled = [note for note in rig.notes if note and note[0] is False]
    assert polled, rig.notes
    assert "USB MIDI interface" in polled[-1][1] and "no fm3 adapter" not in polled[-1][1]
    assert "driver" not in polled[-1][1].lower()


def test_no_midi_system_reads_as_no_ports_not_an_error(rig, monkeypatch):
    """CI without ALSA: the backend raises on enumeration. The port list is
    empty, GET still answers, and a save is refused in plain words."""
    def no_alsa():
        raise RuntimeError("MidiInAlsa::initialize: error creating ALSA sequencer client object.")
    monkeypatch.setattr(transport.mido, "get_input_names", no_alsa)
    monkeypatch.setattr(transport.mido, "get_output_names", no_alsa)
    assert transport.port_names() == [] and transport.output_names() == []
    response = rig.client.get("/api/fm3/port")
    assert response.status_code == 200 and response.json()["ports"] == []
    refused = rig.client.post("/api/fm3/port", json={"port": "Interface A"})
    assert refused.status_code == 400 and refused.json()["ok"] is False
    assert not rig.path.exists()


@pytest.mark.parametrize("names", ["port_names", "output_names"])
def test_supriya_enumeration_failure_reads_as_no_ports_and_closes(names):
    """#221 review: Supriya's get_ports() raising must not escape either."""
    closed = []

    class _Port:
        def get_ports(self):
            raise RuntimeError("enumeration failed")

        def delete(self):
            closed.append(True)

    module = SimpleNamespace(MidiIn=_Port, MidiOut=_Port)
    env = {"TONECOMMAND_MIDI_BACKEND": "supriya"}
    original = transport.backend
    try:
        transport.backend = lambda env=None: "supriya"
        assert getattr(transport, names)(env, supriya_module=module) == []
    finally:
        transport.backend = original
    assert closed == [True]


def test_split_pair_saved_from_its_own_lists_and_connects_exactly(rig):
    """#255: an adapter names its input and output differently ("MidiPort 1"
    in, "MidiPort 2" out); each is picked and saved from its own list."""
    response = rig.client.post("/api/fm3/port", json={"port_in": "Input Only", "port_out": "Output Only"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "port": None, "port_in": "Input Only",
                               "port_out": "Output Only", "source": "file", "reconnected": False}
    assert json.loads(rig.path.read_text(encoding="utf-8")) == {"port_in": "Input Only",
                                                                "port_out": "Output Only"}
    binding = rig.client.get("/api/fm3/port").json()
    assert (binding["port_in"], binding["port_out"], binding["fixed"]) == ("Input Only", "Output Only", False)
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    assert rig.events == [("open_input", "Input Only"), ("open_output", "Output Only")]


@pytest.mark.parametrize("body", [{"port_in": "Output Only", "port_out": "Output Only"},
                                  {"port_in": "Input Only", "port_out": "Input Only"},
                                  {"port_in": "Input Only", "port_out": "unknown"}])
def test_split_pair_refuses_a_direction_missing_from_its_list(rig, body):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    before = rig.path.read_bytes()
    response = rig.client.post("/api/fm3/port", json=body)
    assert response.status_code == 400
    assert rig.path.read_bytes() == before and not rig.events


@pytest.mark.parametrize("saved", [True, False])
def test_output_only_environment_fixes_output_and_refuses_save(rig, monkeypatch, saved):
    """TONECOMMAND_FM3_PORT_OUT alone: output from the environment, input from
    the saved file, or None; source env, Save refused, never a guessed input."""
    if saved:
        rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    before = rig.path.read_bytes() if saved else None
    monkeypatch.setenv(transport.FM3_PORT_OUT_ENV, "Interface B")
    binding = rig.client.get("/api/fm3/port").json()
    assert (binding["port_in"], binding["port_out"], binding["source"], binding["fixed"]) == (
        "Interface A" if saved else None, "Interface B", "env", True)
    response = rig.client.post("/api/fm3/port", json={"port_in": "Interface A", "port_out": "Interface A"})
    assert response.status_code == 409
    assert transport.FM3_PORT_OUT_ENV in response.json()["error"]
    assert (rig.path.read_bytes() if saved else rig.path.exists()) == (before if saved else False)
    if saved:
        assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
        assert rig.events == [("open_input", "Interface A"), ("open_output", "Interface B")]
    else:
        assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code != 200
        assert not rig.events


@pytest.mark.parametrize("body", [{"port_in": "Interface A"}, {"port_in": "Interface A", "port_out": ""},
                                  {"port_in": "Interface A", "port_out": None},
                                  {"port_out": "Interface A"}, {"port_in": None, "port_out": "Interface A"}])
def test_split_pair_with_a_missing_direction_is_refused(rig, body):
    """#255 review: a split request never fills one direction from the other."""
    rig.path.write_text(json.dumps({"port": "Interface B"}), encoding="utf-8")
    before = rig.path.read_bytes()
    response = rig.client.post("/api/fm3/port", json=body)
    assert response.status_code == 400
    assert rig.path.read_bytes() == before and not rig.events


# -- #308: the FM3 comes back by itself ------------------------------------------

def _poll_now(monkeypatch):
    """The next state poll may try to reconnect (no throttle in the way)."""
    monkeypatch.setattr(server, "_last_rescan", {"at": -1e9})


def test_unplugged_interface_reconnects_on_the_next_poll(rig, monkeypatch):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    rig.ins.remove("Interface A")                      # the interface is unplugged
    with server._lock:
        assert server._reconnect_device("fm3", lock_held=True)["connected"] is False
    assert server.device_context().adapter is None
    _poll_now(monkeypatch)
    assert rig.client.get("/api/state").json()["connected"] is False
    rig.ins.insert(0, "Interface A")                   # and plugged back in
    _poll_now(monkeypatch)
    state = rig.client.get("/api/state").json()
    assert state["connected"] is True, state
    assert server.device_context().adapter is not None


def test_reconnect_attempts_are_throttled(rig, monkeypatch):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    rig.ins.remove("Interface A")
    with server._lock:
        server._reconnect_device("fm3", lock_held=True)
    calls = []
    monkeypatch.setattr(server, "_reconnect_device",
                        lambda kind, lock_held=False: calls.append(kind) or {"connected": False})
    _poll_now(monkeypatch)
    rig.client.get("/api/state")
    rig.client.get("/api/state")                       # inside RESCAN_EVERY: no second try
    assert calls == ["fm3"]


def test_an_fm3_switched_off_behind_its_interface_reads_offline_then_returns(rig, monkeypatch):
    rig.path.write_text(json.dumps({"port": "Interface A"}), encoding="utf-8")
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    adapter = server.device_context().adapter
    adapter.outp.port.core.model = 0x7E                # switched off: the port stays, nothing answers
    monkeypatch.setattr(server, "_last_rescan", {"at": time.monotonic()})  # no retry this poll
    state = rig.client.get("/api/state").json()
    assert state["connected"] is False
    assert server.device_context().adapter is None     # dropped, like an unplug
    assert any(n and n[0] is False and "FM3 stopped answering" in n[1] for n in rig.notes), rig.notes
    _poll_now(monkeypatch)                             # switched back on: a fresh open answers
    state = rig.client.get("/api/state").json()
    assert state["connected"] is True, state

"""#221 REQ-002: binding API and port replacement over simulated MIDI only."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import midi_transport as transport
from fm9 import protocol
from fm9.sim import SimFM9Core, _SimIn, _SimOut


@pytest.fixture
def rig(monkeypatch, tmp_path):
    for name in (transport.FM3_PORT_ENV, "TONECOMMAND_FM3_SIM",
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
        pairs[name] = inp
        events.append(("open_input", name))
        return inp

    def open_output(name):
        assert server._lock.locked()
        assert name in outs
        out = _SimOut(SimFM9Core(model=protocol.MODEL_FM3), pairs[name])
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
        "port": None, "source": None, "fixed": False,
        "ports": ["Interface A", "Interface B 2", "Interface B"],
    }
    assert not rig.path.exists() and not rig.events
    for name in response.json()["ports"]:
        assert rig.client.post("/api/fm3/port", json={"port": name}).status_code == 200


def test_save_persists_lists_fm3_and_connects_exact_port(rig):
    assert "fm3" not in [d["kind"] for d in rig.client.get("/api/device").json()["available"]]
    response = rig.client.post("/api/fm3/port", json={"port": "Interface B"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "port": "Interface B",
                               "source": "file", "reconnected": False}
    assert json.loads(rig.path.read_text()) == {"port": "Interface B"}
    binding = rig.client.get("/api/fm3/port").json()
    assert (binding["port"], binding["source"], binding["fixed"]) == ("Interface B", "file", False)
    assert "fm3" in [d["kind"] for d in rig.client.get("/api/device").json()["available"]]
    assert not rig.events
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    assert rig.events == [("open_input", "Interface B"), ("open_output", "Interface B")]
    assert server.device_context().adapter.current_preset()


@pytest.mark.parametrize("value", ["Interface B", "missing", ""])
def test_environment_precedes_file_and_refuses_save(rig, monkeypatch, value):
    rig.path.write_text(json.dumps({"port": "Interface A"}))
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
    rig.path.write_text(json.dumps({"port": "Interface A"}))
    before = rig.path.read_bytes()
    response = rig.client.post("/api/fm3/port", json=body)
    assert response.status_code == 400
    assert response.json()["ok"] is False and response.json()["error"]
    assert rig.path.read_bytes() == before and not rig.events


def test_save_connected_closes_a_and_opens_b_under_switch_lock(rig, monkeypatch):
    rig.path.write_text(json.dumps({"port": "Interface A"}))
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    old = server.device_context().adapter
    original_save = transport.save_fm3_binding

    def save(port):
        assert server._lock.locked()
        return original_save(port)

    monkeypatch.setattr(transport, "save_fm3_binding", save)
    rig.events.clear()
    response = rig.client.post("/api/fm3/port", json={"port": "Interface B"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "port": "Interface B",
                               "source": "file", "reconnected": True}
    assert set(rig.events[:2]) == {("close_input", "Interface A"), ("close_output", "Interface A")}
    assert rig.events[2:] == [("open_input", "Interface B"), ("open_output", "Interface B")]
    assert server.device_context().adapter is not old
    assert server.device_context().adapter.current_preset()


def test_bound_port_disappears_without_fallback(rig):
    rig.path.write_text(json.dumps({"port": "Interface B"}))
    rig.ins.remove("Interface B")
    rig.outs.remove("Interface B")
    response = rig.client.post("/api/device/select", json={"kind": "fm3"})
    assert response.status_code == 503
    assert "USB MIDI interface" in response.json()["error"]
    assert not rig.events


def test_failed_reconnect_drops_closed_adapter_and_keeps_new_binding(rig, monkeypatch):
    rig.path.write_text(json.dumps({"port": "Interface A"}))
    assert rig.client.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    original_save = transport.save_fm3_binding

    def save_then_unplug(port):
        binding = original_save(port)
        rig.ins.remove(port)
        return binding

    monkeypatch.setattr(transport, "save_fm3_binding", save_then_unplug)
    rig.events.clear()
    response = rig.client.post("/api/fm3/port", json={"port": "Interface B"})
    assert response.status_code == 200
    assert response.json()["reconnected"] is False
    assert server.device_context().adapter is None
    assert json.loads(rig.path.read_text()) == {"port": "Interface B"}
    assert set(rig.events) == {("close_input", "Interface A"), ("close_output", "Interface A")}
    assert "USB MIDI interface" in rig.notes[-1][1]

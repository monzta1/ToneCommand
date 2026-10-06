"""#212: an FM3 through the FM9 module, read-only, on the simulator.

No FM3 is on the bench. The simulator answers only frames addressed to its
own model byte, which is how an FM3 treats an FM9 frame, so a frame that
still carried 0x12 would simply go unanswered here as it would there."""
import sys

sys.argv = ["x"]
import mido
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import protocol as p
from fm9.device import FM3, FM3_READ_ONLY, FM9, ReadOnly, ReadOnlyOut
from fm9.sim import SimFM3, SimFM9


def _wire(dev):
    """Every message that reaches the simulator's port, as sent."""
    sent = []
    port = dev.outp.port if isinstance(dev.outp, ReadOnlyOut) else dev.outp
    real = port.send

    def spy(msg):
        sent.append(msg)
        return real(msg)
    port.send = spy
    return sent


def _sysex(sent):
    return [[0xF0, *m.data, 0xF7] for m in sent if m.type == "sysex"]


# -- REQ-001: the FM3 model byte on every frame --------------------------------------

def test_model_byte_on_the_wire_is_the_fm3s_with_a_valid_checksum():
    dev = SimFM3()
    sent = _wire(dev)
    assert dev.current_preset() == (0, "Sim Preset 0")
    assert dev.scene_name()[0] == 1
    assert dev.status_dump()
    frames = _sysex(sent)
    assert frames and {f[4] for f in frames} == {p.MODEL_FM3}
    assert all(p.checksum(f[1:-2]) == f[-2] for f in frames)


def test_model_byte_unchanged_for_the_fm9_byte_for_byte():
    fm9, fm3 = SimFM9(), SimFM3()
    s9, s3 = _wire(fm9), _wire(fm3)
    fm9.current_preset()
    fm3.current_preset()
    f9, f3 = _sysex(s9)[0], _sysex(s3)[0]
    assert f9 == p.build_get_patch_name()                       # the FM9 sends exactly what it built
    assert f3 == p.readdress(f9, p.MODEL_FM3) and f3 != f9


def test_model_byte_mismatch_goes_unanswered_on_the_sim():
    """An FM3 sim ignores an FM9-addressed frame, as the hardware is expected to."""
    core = SimFM3().sim_core
    assert core.handle(p.build_get_patch_name()) == []
    assert core.handle(p.readdress(p.build_get_patch_name(), p.MODEL_FM3))


# -- REQ-002: read-only at the port, exact forms -----------------------------------------

ALLOWED = {
    "patch name, current": p.build_get_patch_name(),
    "patch name, by number": p.build_get_patch_name(130),
    "scene name, current": p.build_get_scene_name(),
    "scene name, scene 8": p.build_get_scene_name(8),
    "scene query": p.build_get_scene(),
    "scene switch": p.build_set_scene(3),
    "bypass query": p.build_get_bypass(46),
    "channel query": p.build_get_channel(46),
    "status dump": p.build_status_dump(),
    "firmware": p.build_get_firmware(),
    "tempo query": p.build_get_tempo(),
}


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_guard_passes_each_official_query_form(name):
    assert p.fm3_allowed(ALLOWED[name])
    assert p.fm3_allowed(p.readdress(ALLOWED[name], p.MODEL_FM3))


def _bad_checksum(f):
    g = list(f)
    g[-2] ^= 0x01
    return g


REFUSED = {
    "get param (a typed set)": p.build_get_param(46, 1),
    "set param": p.build_set_param_continuous(46, 1, 0.5),
    "type name read (fn 0x01)": p.build_get_type_name(46, 0),
    "grid layout read (fn 0x01)": p.build_request_grid_layout(),
    "bulk read": p.build_bulk_read_poll(46),
    "set bypass": p.build_set_bypass(46, True),
    "set channel": p.build_set_channel(46, 1),
    "set tempo": p.build_set_tempo(120),
    "store": p.build_store_preset(5),
    "rename": p.build_rename_preset("x"),
    "scene 9": p.envelope(p.FN_SCENE, [8]),
    "patch name truncated": p.envelope(p.FN_PATCH_NAME, [0x7F]),
    "status dump extended": p.envelope(p.FN_STATUS_DUMP, [0x00]),
    "bypass query extended": p.envelope(p.FN_BYPASS, [46, 0, 0x7F, 0]),
    "tempo half query": p.envelope(p.FN_TEMPO_BPM, [0x7F, 0x00]),
    "bad checksum": _bad_checksum(p.build_get_patch_name()),
    "Axe-Fx III model": p.readdress(p.build_get_patch_name(), 0x10),
    "no F7": p.build_get_patch_name()[:-1],
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_guard_refuses_every_other_form(name):
    assert not p.fm3_allowed(REFUSED[name])


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_refuse_at_the_port_with_nothing_on_the_wire(name):
    dev = SimFM3()
    sent = _wire(dev)
    with pytest.raises(ReadOnly, match="#40"):
        dev.outp.send(mido.Message("sysex", data=REFUSED[name][1:-1]))
    assert sent == []


def test_refuse_the_direct_senders_too(monkeypatch):
    """Three FM9 paths call outp.send themselves; the port stops them all,
    the cab read included with its own opt-in switched on."""
    monkeypatch.setenv("TONECOMMAND_ALLOW_CAB_READ", "1")
    dev = SimFM3()
    sent = _wire(dev)
    with pytest.raises(ReadOnly):
        FM9._send_await_dump_ack(dev, p.envelope(0x77, [0] * 8))
    with pytest.raises(ReadOnly):
        FM9._send_cab_frames(dev, [p.envelope(0x7A, [0] * 8)])
    with pytest.raises(ReadOnly):
        FM9.read_user_cab_addr(dev, 1, 0, timeout=0.1)
    with pytest.raises(ReadOnly):
        dev.outp.send(mido.Message("note_on", note=60))
    assert sent == []


def test_refuse_every_write_method_in_plain_words():
    dev = SimFM3()
    sent = _wire(dev)
    for name in ("set_param_display", "set_param_wire", "set_param_ordinal", "set_params_batch",
                 "set_bypass", "set_channel", "set_tempo", "rename_preset", "rename_scene",
                 "store_preset", "install_preset", "install_user_cab", "place_block",
                 "connect_cells", "bind_modifier", "clear_modifier"):
        with pytest.raises(ReadOnly) as e:
            getattr(dev, name)(1)
        assert str(e.value) == FM3_READ_ONLY, name
    assert sent == []
    assert dev.bulk_read(46) is None and sent == []              # a documented no-send


def test_guard_never_brick_still_applies_first():
    dev = SimFM3()
    with pytest.raises(PermissionError):
        dev._send(p.envelope(0x7D, []))                          # undecoded fn: the brick guard


def test_guard_lets_preset_and_scene_switching_through():
    dev = SimFM3()
    sent = _wire(dev)
    assert dev.select_preset(130)[0] == 130
    assert dev.set_scene(4) == 4
    kinds = [m.type for m in sent]
    assert "program_change" in kinds and "control_change" in kinds


# -- REQ-003: state, switching, plans, catalog and page --------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setenv("TONECOMMAND_FM3_SIM", "1")
    c = TestClient(server.app)
    assert c.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    return c


def test_state_reads_the_fm3_without_parameter_values(client):
    s = client.get("/api/state").json()
    assert s["connected"] is True and s["read_only"] is True
    assert s["device"]["active"] == "fm3" and s["device"]["label"] == "Fractal FM3"
    assert s["preset"]["name"] == "Sim Preset 0"
    assert len(s["scenes"]) == 8 and s["blocks"]
    assert s["values"] == {} and s["params"] == {}               # nothing read through the FM9 map


def test_select_preset_and_scene_through_the_existing_routes(client):
    assert client.post("/api/preset", json={"number": 3}).status_code == 200
    assert client.get("/api/state").json()["preset"]["number"] == 3
    # the scene strip posts set_scene through /api/apply, as on the FM9
    r = client.post("/api/apply", json={"actions": [{"kind": "set_scene", "value": 5}]})
    assert r.status_code == 200, r.text
    assert client.get("/api/state").json()["scene"]["number"] == 5


def test_plan_is_refused_in_words_before_any_model(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the planner was asked")
    monkeypatch.setattr(server.planner, "plan", boom)
    r = client.post("/api/plan", json={"prompt": "more gain"})
    assert r.status_code == 409 and r.json() == {"error": FM3_READ_ONLY, "read_only": True}
    r = client.post("/api/plan/stream", json={"prompt": "more gain"})
    assert FM3_READ_ONLY in r.text


def test_catalog_hands_the_fm3_to_the_fm9_module_read_only():
    from devices import catalog
    fm3 = catalog.recognise(["FM3 MIDI In"])[0]
    assert fm3["supported"] is True and fm3["read_only"] is True and fm3["issue"] == 40
    assert server.DEVICE_KINDS["fm3"] == "Fractal FM3"
    assert server._build_context.__doc__ is not None


def test_page_names_the_fm3_and_offers_no_sound_controls():
    from pathlib import Path
    page = (Path(server.__file__).resolve().parent / "ui" / "index.html").read_text(encoding="utf-8")
    assert "fm3: 'FM3'" in page
    assert "document.body.classList.toggle('readonly-device', !!s.read_only);" in page
    assert "body.readonly-device #auditionbtn," in page
    assert "'Connected, read-only for now: presets and scenes switch; nothing changes your sound.'" in page
    # the refusal reaches the player as written, never as "give it another go"
    assert "if (/is read-only in tonecommand/.test(m)) return String(msg);" in page
    assert "  fm3: [],\n" in page                                 # no request it would refuse

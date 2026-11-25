"""#334: the ToneX One over its USB serial link.

The fixtures are a real One's own frames (fw 1.3.17, 2026-11-25): a footswitch
push heard with nothing sent, and the replies to hello, request state and a
request for each of the twenty presets. The simulator is seeded from them, so
these tests run against what the pedal actually said."""
import json
import math
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from devices.tonex_one import params as P
from devices.tonex_one import protocol as p
from devices.tonex_one.adapter import ToneXOneAdapter
from devices.tonex_one.client import ToneXOneClient
from devices.tonex_one.sim import SimLink

FIX = Path(__file__).parent / "fixtures" / "tonex_one"
CAPTURE = Path(__file__).parents[1] / "devices" / "tonex_one" / "data" / "read_all_2026-11-25.bin"


def _client():
    c = ToneXOneClient(SimLink())
    c.SETTLE = (0.0,)
    return c


# -- the protocol, against the pedal's own frames ------------------------------

def test_every_captured_frame_checks_and_names_all_twenty_presets():
    payloads, _ = p.unframe_stream(CAPTURE.read_bytes())
    types = [p.parse(x).type for x in payloads]
    assert types.count(p.T_PRESET) == 20 and p.T_STATE in types and p.T_HELLO in types
    names = {}
    for x in payloads:
        m = p.parse(x)
        if m.type == p.T_PRESET:
            pr = p.parse_preset(m)
            names[pr.index] = pr.name
            assert len(pr.params) == 109
    assert names[0] == "MESACL" and names[13] == "64' Vox AC30" and names[19] == "BS XULTR"


def test_the_state_reads_as_the_pedal_showed_it():
    payloads, _ = p.unframe_stream(CAPTURE.read_bytes())
    m = next(p.parse(x) for x in payloads if p.parse(x).type == p.T_STATE)
    st = p.State(m.payload[m.body_at:])
    st.check()
    assert (st.slot_a, st.slot_b, st.slot_c) == (0, 13, 1)
    assert st.current_slot == 0 and not st.stomp_mode and st.tuning_ref == 440


def test_a_footswitch_push_arrives_unasked():
    """Heard with the port opened read-only: two taps, each a state and the
    newly playing preset, with the active slot flipping."""
    payloads, _ = p.unframe_stream((FIX / "footswitch_listen_2026-11-25.bin").read_bytes())
    states = [p.State(x[p.parse(x).body_at:]) for x in payloads if p.parse(x).type == p.T_STATE]
    assert [s.current_slot for s in states] == [1, 0]


def test_the_hello_frame_is_the_documented_one():
    assert p.frame(p.HELLO).hex() == "7eb90300820400800b01b902020b178c7e"


def test_a_corrupted_frame_is_dropped_not_misread():
    good = p.frame(p.HELLO)
    bad = bytearray(good)
    bad[5] ^= 0x01
    payloads, _ = p.unframe_stream(bytes(bad) + good)
    assert payloads == [p.HELLO]


# -- the send gate ---------------------------------------------------------------

@pytest.fixture
def gate():
    g = p.SendGate(P.WRITABLE)
    payloads, _ = p.unframe_stream(CAPTURE.read_bytes())
    m = next(p.parse(x) for x in payloads if p.parse(x).type == p.T_STATE)
    g.last_state = p.State(m.payload[m.body_at:])
    return g


def test_the_gate_passes_the_five_shapes(gate):
    gate.checked_frame(p.HELLO)
    gate.checked_frame(p.REQUEST_STATE)
    gate.checked_frame(p.request_preset(19))
    gate.checked_frame(p.set_param(P.BY_NAME["EQ_TREBLE"].index, 6.5))
    gate.checked_frame(p.write_state(gate.last_state.changed(slot_b=4, current_slot=1)))


@pytest.mark.parametrize("payload,needle", [
    (bytes([0xB9, 0x03, 0x81, 0x0F, 0x03, 0x82, 0x03, 0x00, 0x80, 0x19, 0x03, 0xB9, 0x01, 0x01]), "not a message"),
    (p.set_param(P.BY_NAME["MODEL_SW1"].index, 1.0), "not one ToneCommand may write"),
    (p.set_param(P.BY_NAME["VIR_CABINET_MODEL"].index, 1.0), "not one ToneCommand may write"),
    (p.set_param(P.BY_NAME["EQ_TREBLE"].index, 11.0), "outside"),
    (p.set_param(P.BY_NAME["EQ_TREBLE"].index, math.nan), "outside"),
    (p.request_preset(0)[:15] + bytes([20, 0]), "not a message"),
    (p.request_preset(0)[:15] + bytes([0, 1]), "not a message"),       # the 30 KB full form
])
def test_the_gate_refuses_everything_else(gate, payload, needle):
    with pytest.raises(p.ProtocolError, match=needle):
        gate.checked_frame(payload)


def test_a_state_write_may_change_only_the_known_fields(gate):
    raw = bytearray(gate.last_state.raw)
    raw[OFF := 30] ^= 0x01                       # a preset colour byte
    with pytest.raises(p.ProtocolError, match="may not change"):
        gate.checked_frame(p.write_state(p.State(bytes(raw))))
    with pytest.raises(p.ProtocolError, match="length"):
        gate.checked_frame(p.write_state(p.State(gate.last_state.raw + b"\x00")))
    assert OFF not in p.writable_state_bytes(gate.last_state.raw)


def test_a_state_write_is_refused_before_any_state_was_read():
    g = p.SendGate(P.WRITABLE)
    with pytest.raises(p.ProtocolError):
        g.checked_frame(bytes([0xB9, 0x03, 0x81, 0x06, 0x03]) + bytes(160))


# -- the client and adapter, on the simulator ---------------------------------------

def test_a_setting_lands_on_the_playing_preset_and_reads_back():
    c = _client()
    assert c.firmware == "1.3.17"
    idx = P.BY_NAME["EQ_TREBLE"].index
    other = c.read_preset(13).params
    assert c.set_param(idx, 6.5) == 6.5
    assert c.link.value(0, idx) == 6.5           # preset 1 is playing on A
    assert c.read_preset(13).params == other     # nothing else moved


def test_slot_and_mode_writes_read_back():
    c = _client()
    st = c.write_state(slot_b=4, current_slot=1)
    assert st.slot_b == 4 and st.active_preset == 4
    st = c.write_state(stomp_mode=True, current_slot=2)
    assert st.stomp_mode and st.active_preset == 1


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_TONEX_ONE_BACKUPS", str(tmp_path))
    return ToneXOneAdapter(_client())


def test_the_adapter_names_the_pedal_and_the_playing_preset(adapter):
    patch = adapter.patch()
    assert patch["SLOT_A"] == "1 MESACL" and patch["SLOT_B"] == "14 64' Vox AC30"
    assert patch["ACTIVE_SLOT"] == "A" and patch["MODE"] == "DUAL" and patch["CAB_SIM"] == "ON"
    assert adapter.current_preset() == (1, "MESACL")
    names = {r["name"] for r in adapter.named_params()}
    assert {"SLOT_A", "MODE", "EQ_TREBLE", "REVERB_MODEL"} <= names
    assert not names & {p_.name for p_ in P.PARAMS if p_.blocked}


def test_options_and_presets_are_taken_by_name(adapter):
    assert adapter.set_param("REVERB_MODEL", "plate")["label"] == "PLATE"
    assert adapter.set_param("SLOT_B", "CL DMBL")["label"] == "2 CL DMBL"
    assert adapter.set_param("SLOT_C", 18)["label"] == "18 MAXO 8O8"
    with pytest.raises(KeyError):
        adapter.set_param("SLOT_A", "No Such Amp")
    with pytest.raises(KeyError):
        adapter.set_param("MODEL_SW1", 1)
    with pytest.raises(ValueError):
        adapter.set_param("EQ_TREBLE", 12)


def test_the_first_change_writes_a_backup_of_every_preset_once(adapter, tmp_path):
    adapter.set_param("EQ_TREBLE", 6)
    adapter.set_param("EQ_BASS", 4)
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert len(data["presets"]) == 20
    # taken BEFORE the change: the playing preset's treble is still 5.0
    assert data["presets"]["1"]["settings"]["EQ_TREBLE"] == 5.0


def test_a_preset_pick_goes_into_the_slot_playing(adapter):
    adapter.set_param("ACTIVE_SLOT", "B")
    adapter.select_preset(6)
    assert adapter.patch()["SLOT_B"] == "6 Rockerverb Heavy Rhythm"


# -- through the server -------------------------------------------------------------

@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setenv("TONECOMMAND_TONEX_ONE_SIM", "1")
    monkeypatch.setenv("TONECOMMAND_TONEX_ONE_BACKUPS", str(tmp_path))
    c = TestClient(server.app, base_url="http://127.0.0.1")
    assert c.post("/api/device/select", json={"kind": "tonex_one"}).status_code == 200
    return c


def test_state_reports_the_pedal_grouped(api):
    s = api.get("/api/state").json()
    assert s["connected"] and s["preset"]["name"] == "MESACL"
    rows = {r["name"]: r for r in s["device_params"]}
    assert rows["SLOT_A"]["group"] == "Pedal" and rows["EQ_TREBLE"]["group"] == "EQ"
    assert len(rows["SLOT_A"]["options"]) == 20


def test_a_send_lands_reads_back_and_says_where_the_backup_is(api, tmp_path):
    r = api.post("/api/apply", json={"actions": [
        {"kind": "set_device_param", "param": "EQ_TREBLE", "value": 6}]}).json()
    res = [x for x in r["results"] if x.get("action")]
    assert res and res[0]["ok"] and res[0]["detail"] == "EQ_TREBLE = 6.0"
    assert r["backup"] and Path(r["backup"]).parent == tmp_path
    assert not any("snapshot" in str(x.get("detail")) for x in r["results"])


@pytest.mark.parametrize("act,needle", [
    ({"param": "MODEL_SW1", "value": 1}, "has no parameter"),
    ({"param": "EQ_TREBLE", "value": 11}, "takes 0.0 to 10.0"),
    ({"param": "MODE", "type_name": "SCENE"}, "has no setting"),
])
def test_validation_refuses_before_the_wire(api, act, needle):
    r = api.post("/api/apply", json={"actions": [dict(kind="set_device_param", **act)]}).json()
    assert not r["results"][0]["ok"] and needle in r["results"][0]["detail"]


def test_each_named_device_plans_with_its_own_vocabulary(api):
    one = server.named_planning(server.device_context().adapter)
    assert one.__name__ == "devices.tonex_one.planning"
    ref = one.param_reference(server.device_context().adapter)
    assert "20 BS XULTR  [STOMP - DISTORTION, Electric Bass]" in ref
    from devices.ir2.adapter import IR2Adapter
    assert server.named_planning(object.__new__(IR2Adapter)).__name__ == "devices.ir2.planning"


def test_the_one_is_recognised_by_its_usb_identity():
    from devices import catalog
    found = catalog.recognise([], [{"vid": 0x1963, "pid": 0x00D1, "interfaces": []}])
    assert [d["kind"] for d in found] == ["tonex_one"] and found[0]["supported"]


def test_the_page_draws_the_one_in_groups_with_its_own_examples():
    html = (Path(server.__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
    assert "function renderGroupedDevice(" in html and "tonex_one: [" in html
    assert "namedPresetParam(lastState)" in html


def test_the_settings_table_is_complete_and_names_are_unique():
    assert len(P.PARAMS) == 109 and len({x.name for x in P.PARAMS}) == 109
    assert set(P.WRITABLE) == {x.index for x in P.PARAMS if not x.blocked}
    assert P.WRITABLE[P.BY_NAME["REVERB_MODEL"].index][2] is True
    for x in P.PARAMS:
        assert x.lo <= x.hi and struct.pack("<f", x.lo)


# -- the review's findings (#335) -----------------------------------------------------

def test_a_setting_lands_on_the_preset_playing_after_a_footswitch_press():
    """A press since the last read moves the playing preset; the write must
    follow it, because the pedal saves to whichever preset plays."""
    c = _client()
    c.read_state()                                 # remembers A (preset 1)
    c.link.footswitch()                            # now B (preset 14) plays
    idx = P.BY_NAME["EQ_BASS"].index
    before_a = c.link.value(0, idx)
    assert c.set_param(idx, 3.0) == 3.0
    assert c.link.value(13, idx) == 3.0 and c.link.value(0, idx) == before_a


def test_read_back_is_exact_so_a_clamp_is_not_a_pass(monkeypatch):
    c = _client()
    idx = P.BY_NAME["EQ_MID_FREQ"].index
    real = c.link._set_param
    monkeypatch.setattr(c.link, "_set_param",
                        lambda preset, i, v4: real(preset, i, struct.pack("<f", 4999.0)))
    with pytest.raises(Exception, match="reports 4999"):
        c.set_param(idx, 5000.0)


@pytest.mark.parametrize("name,value", [("REVERB_MODEL", 2.5), ("DELAY_ENABLE", 0.5)])
def test_a_switch_or_choice_takes_whole_numbers_only(adapter, name, value):
    with pytest.raises(ValueError, match="whole number"):
        adapter.set_param(name, value)
    with pytest.raises(p.ProtocolError, match="whole number"):
        p.SendGate(P.WRITABLE).checked_frame(p.set_param(P.BY_NAME[name].index, value))


def test_validation_refuses_a_fraction_on_a_switch(api):
    r = api.post("/api/apply", json={"actions": [
        {"kind": "set_device_param", "param": "DELAY_ENABLE", "value": 0.5}]}).json()
    assert not r["results"][0]["ok"] and "whole number" in r["results"][0]["detail"]


def test_the_gate_bounds_trim_and_bypass_in_a_raw_state_write(gate):
    raw = bytearray(gate.last_state.raw)
    raw[p.OFF_INPUT_TRIM:p.OFF_INPUT_TRIM + 4] = struct.pack("<f", 40.0)
    with pytest.raises(p.ProtocolError, match="trim"):
        gate.checked_frame(p.write_state(p.State(bytes(raw))))


def test_an_unplugged_port_reads_as_not_found(tmp_path):
    from devices.tonex_one.client import SerialLink, ToneXOneNotFound
    link = object.__new__(SerialLink)
    r, w = __import__("os").pipe()
    __import__("os").close(w)                       # the other end is gone: EOF
    link.fd = r
    with pytest.raises(ToneXOneNotFound, match="unplugged"):
        link.read()
    link.close()


def test_two_backups_in_one_second_do_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_TONEX_ONE_BACKUPS", str(tmp_path))
    monkeypatch.setattr("time.strftime", lambda fmt, *a: "2026-11-25_120000")
    for _ in range(2):
        ToneXOneAdapter(_client()).set_param("EQ_BASS", 4)
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_the_page_never_sends_an_emptied_box():
    html = (Path(server.__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
    assert "el.value.trim() === ''" in html


def test_a_closed_link_never_touches_a_reused_descriptor():
    import os
    from devices.tonex_one.client import SerialLink, ToneXOneNotFound
    link = object.__new__(SerialLink)
    r, w = os.pipe()
    link.fd = r
    link.close()
    other_r, other_w = os.pipe()          # may reuse the closed number
    try:
        with pytest.raises(ToneXOneNotFound, match="closed"):
            link.read()
        with pytest.raises(ToneXOneNotFound, match="closed"):
            link.write(b"x")
    finally:
        for fd in (w, other_r, other_w):
            os.close(fd)


# -- the slot board ---------------------------------------------------------------------

def test_the_state_carries_twenty_preset_colours():
    payloads, _ = p.unframe_stream(CAPTURE.read_bytes())
    m = next(p.parse(x) for x in payloads if p.parse(x).type == p.T_STATE)
    colors = p.State(m.payload[m.body_at:]).colors()
    assert len(colors) == 20 and colors[0] == (255, 63, 0) and colors[3] == (255, 0, 255)


def test_slot_rows_carry_each_presets_character_and_a_visible_colour(adapter):
    adapter.state()
    row = next(r for r in adapter.named_params() if r["name"] == "SLOT_B")
    assert row["option_tags"]["14 64' Vox AC30"] == "CLEAN"
    assert row["option_tags"]["6 Rockerverb Heavy Rhythm"] == "HI-GAIN"
    assert row["option_colors"]["14 64' Vox AC30"] == "#ff00ff"      # stored dim: 10, 0, 10


def test_the_page_draws_dual_and_stomp_with_the_live_one_lit(api):
    rows = {r["name"]: r for r in api.get("/api/state").json()["device_params"]}
    assert rows["SLOT_A"]["option_colors"] and rows["SLOT_A"]["option_tags"]
    html = (Path(server.__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
    assert "DUAL MODE" in html and "STOMP MODE" in html and "slotcard" in html
    assert "param: 'ACTIVE_SLOT', type_name: c.dataset.slot" in html

"""#40: the FM3's measured settings on the page's knobs.

The snapshot reads each measured block once, at the FM3's own places, and
describes each setting on the FM3's measured scale; a knob writes through
/api/apply set_param, which the FM3 handle already maps and reads back."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import fm3_map
from fm9 import protocol as p


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setenv("TONECOMMAND_FM3_SIM", "1")
    monkeypatch.setattr(server, "_fm3_knob_backoff", {"skip": 0})
    c = TestClient(server.app)
    assert c.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    # every test below relies on the sim preset holding all three blocks
    assert set(fm3_map.EFFECT_IDS) <= _present(c.get("/api/state").json())
    return c


def _sim():
    return server.get_fm9().sim_core.st


def _put(family, pid, wire, channel=0):
    """Store a raw value at the FM3's own place for (family, FM9 pid)."""
    m = fm3_map.lookup(family, pid)
    _sim().buffer["params"][fm3_map.EFFECT_IDS[family]][channel][m.word] = wire


def _present(s):
    return {b["family"] for b in s["blocks"] if b["instance"] == 1}


def test_measured_settings_reach_the_page_with_the_fm3s_scale(client):
    _put("REVERB", 0, 13107)                    # Mix 20%, as on the tester's unit
    _put("DELAY", 12, 65534)                    # Time at the top: 16000 ms on an FM3
    _put("DISTORT", 11, 55507)                  # Gain 8.47
    s = client.get("/api/state").json()
    v, meta = s["values"], s["params"]
    assert v["REVERB_MIX"] == 20.0 and meta["REVERB_MIX"]["label"] == "Mix"
    assert v["DELAY_TIME"] == 16000.0 and meta["DELAY_TIME"]["max"] == 16000
    assert v["DISTORT_DRIVE"] == 8.47 and meta["DISTORT_DRIVE"]["label"] == "Gain"


def test_the_knob_order_and_units_read_like_the_unit(client):
    s = client.get("/api/state").json()
    meta = s["params"]
    amp = [k for k in meta if meta[k]["family"] == "DISTORT"]
    assert amp[0] == "DISTORT_DRIVE" and amp[-2:] == ["DISTORT_LEVEL", "DISTORT_PAN"]
    assert meta["REVERB_LEVEL"]["unit"] == "db"
    assert meta["REVERB_HICUT"]["scale"] == "log10"
    assert meta["DELAY_FEED"]["unit"] == "percent"


def test_zero_db_reads_as_zero_not_minus_zero(client):
    _put("REVERB", 1, 52427)                    # 0.0 dB
    s = client.get("/api/state").json()
    assert str(s["values"]["REVERB_LEVEL"]) == "0.0"


def test_a_knob_write_lands_and_the_next_poll_shows_it(client):
    s = client.get("/api/state").json()
    fam = next(f for f in ("REVERB", "DELAY", "DISTORT") if f in _present(s))
    key = {"REVERB": "REVERB_MIX", "DELAY": "DELAY_MIX", "DISTORT": "DISTORT_DRIVE"}[fam]
    want = 6.5 if fam == "DISTORT" else 35.0
    m = s["params"][key]
    r = client.post("/api/apply", json={"actions": [
        {"kind": "set_param", "block": m["family"], "instance": m["instance"],
         "param": m["param"], "value": want}]}).json()
    res = [x for x in r["results"] if x.get("action")]
    assert res and res[0]["ok"], r
    assert client.get("/api/state").json()["values"][key] == want


def test_one_block_read_per_measured_block_per_poll(client, monkeypatch):
    dev = server.device_context().adapter        # the FM3 itself, not the gated wrapper
    reads = []
    real = dev._fm3_read_block
    monkeypatch.setattr(dev, "_fm3_read_block", lambda eid: (reads.append(eid), real(eid))[1])
    s = client.get("/api/state").json()
    assert sorted(reads) == sorted(fm3_map.EFFECT_IDS[f] for f in _present(s) if f in fm3_map.EFFECT_IDS)


def test_a_value_lost_on_the_link_is_left_off_not_guessed(client, monkeypatch):
    dev = server.device_context().adapter        # the FM3 itself, not the gated wrapper
    real = dev._fm3_read_block

    def lossy(eid):
        vals, total = real(eid)
        return [None] * len(vals), total
    monkeypatch.setattr(dev, "_fm3_read_block", lossy)
    s = client.get("/api/state").json()
    assert s["connected"] and s["values"] == {} and s["params"] == {}


def test_channel_b_shows_channel_bs_values(client):
    st = _sim()
    st.buffer["scenes"][st.scene][fm3_map.EFFECT_IDS["REVERB"]]["channel"] = 1
    _put("REVERB", 0, 13107, channel=0)         # A: 20%
    _put("REVERB", 0, 45874, channel=1)         # B: 70%
    s = client.get("/api/state").json()
    rev = next(b for b in s["blocks"] if b["family"] == "REVERB")
    assert rev["channel"] == "B", rev
    assert s["values"]["REVERB_MIX"] == 70.0


def test_a_silent_block_read_backs_off_instead_of_stalling_every_poll(client, monkeypatch):
    dev = server.device_context().adapter        # the FM3 itself, not the gated wrapper
    reads = []
    monkeypatch.setattr(dev, "_fm3_read_block", lambda eid: reads.append(eid))   # no answer
    s = client.get("/api/state").json()
    assert s["connected"] and s["values"] == {} and len(reads) == 1             # stops at the first miss
    for _ in range(server._FM3_KNOB_SKIP):
        client.get("/api/state")
    assert len(reads) == 1                                                       # skipped polls read nothing
    client.get("/api/state")
    assert len(reads) == 2                                                       # then tries again


def test_the_page_offers_no_type_picker_on_a_read_only_device():
    page = (Path(server.__file__).resolve().parent / "ui" / "index.html").read_text(encoding="utf-8")
    assert "const pick = !s.read_only && TYPE_PICKERS[fam];" in page
    assert "      if (!dragging) renderParams(s);" in page
    assert "  if (lastState && lastState.read_only) return false;" in page    # no P2 button
    assert "body.readonly-device .fm9hint { display: none; }" in page     # no UNDO promise

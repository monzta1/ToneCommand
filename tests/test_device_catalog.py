"""#209 (phase 1 of #208): the device catalog, recognition by port name, the
detected list on /api/state and the link stream, the reconnect that a replug
needs, and the plug-in card, which runs here in node against fakes rather
than being read as source."""
import json
import subprocess
import sys
import threading
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from devices import catalog

ROOT = Path(__file__).resolve().parent.parent
# Captured at import, before the autouse fixture in conftest.py switches bus
# discovery off for every test; these tests put the real functions back.
REAL_DETECTED = server.detected_devices
REAL_IR2_PRESENT = server._ir2_port_present
PAGE = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_context", server._default_context)
    for var in ("TONECOMMAND_HEADRUSH_HOST", "TONECOMMAND_HEADRUSH_SIM",
                "TONECOMMAND_TONEX_PORT", "TONECOMMAND_TONEX_SIM", "TONECOMMAND_IR2_SIM"):
        monkeypatch.delenv(var, raising=False)
    return TestClient(server.app)


@pytest.fixture(autouse=True)
def _real_discovery(monkeypatch):
    monkeypatch.setattr(server, "detected_devices", REAL_DETECTED)
    monkeypatch.setattr(server, "_ir2_port_present", REAL_IR2_PRESENT)
    _ports(monkeypatch, [])          # never the real bus: a fixed, empty one


def _ports(monkeypatch, names):
    from fm9 import midi_transport
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: list(names))


# -- REQ-001: the catalog and recognise() ------------------------------------------

def test_catalog_entries_are_complete_and_point_somewhere():
    entries = catalog.load()
    kinds = [e["kind"] for e in entries]
    assert len(kinds) == len(set(kinds))
    for e in entries:
        assert set(catalog.FIELDS) <= set(e)
        if e["adapter"] is None:
            assert isinstance(e["issue"], int), e["kind"]
        else:
            # an adapter named here is one the server can actually build
            assert e["adapter"] in server.DEVICE_KINDS, e["kind"]
    # the two patterns seen on real hardware, and only those, are verified
    assert {e["kind"] for e in entries if e["verified"]} == {"fm9", "ir2"}


@pytest.mark.parametrize("names, kinds", [
    (["FM9 MIDI In 0"], ["fm9"]),                       # #193, a real FM9
    (["FM9 MIDI In 0", "FM9 MIDI In 1"], ["fm9"]),      # several ports, one device
    (["IR-2"], ["ir2"]),                                # the bench IR-2, 2026-10-04
    (["VP4 MIDI In"], ["vp4"]),
    (["AM4"], ["am4"]),
    (["FM3 MIDI In 0"], ["fm3"]),
    (["Axe-Fx III MIDI In"], ["axefx3"]),
    (["IAC Driver Bus 1"], []),
    (["CAM400 Out", "FM90 Synth"], []),                 # whole words only
    ([], []),
])
def test_recognise_maps_port_names_to_catalog_kinds(names, kinds):
    assert [d["kind"] for d in catalog.recognise(names)] == kinds


def test_recognise_names_unsupported_devices_with_their_issue():
    got = {d["kind"]: d for d in catalog.recognise(
        ["VP4 MIDI In", "AM4", "FM3", "Axe-Fx III"])}
    assert {k: d["issue"] for k, d in got.items()} == \
        {"vp4": 191, "am4": 41, "fm3": 40, "axefx3": 190}
    for d in got.values():
        assert d["supported"] is False and d["verified"] is False
        assert d["issue_url"] == f"https://github.com/monzta1/ToneCommand/issues/{d['issue']}"
    ir2 = catalog.recognise(["IR-2"])[0]
    assert ir2 == {"kind": "ir2", "label": "BOSS IR-2", "supported": True,
                   "verified": True, "issue": None, "issue_url": None}


# -- REQ-002: recognition sends nothing ------------------------------------------------

def test_nothing_sent_by_detection_or_the_state_block(monkeypatch):
    """Detection may enumerate names and do nothing else: any attempt to open
    a port, in or out, through either MIDI binding fails this test."""
    _ports(monkeypatch, ["VP4 MIDI In", "Axe-Fx III MIDI In", "FM9 MIDI In 0"])

    def opened(*a, **k):
        raise AssertionError("detection opened a MIDI port")
    import mido
    monkeypatch.setattr(mido, "open_input", opened)
    monkeypatch.setattr(mido, "open_output", opened)
    monkeypatch.setattr(mido, "open_ioport", opened)
    try:
        import rtmidi
        monkeypatch.setattr(rtmidi, "MidiOut", opened)
        monkeypatch.setattr(rtmidi, "MidiIn", opened)
    except ImportError:
        pass
    assert [d["kind"] for d in server.detected_devices()] == ["fm9", "vp4", "axefx3"]
    assert [d["kind"] for d in server.device_block()["detected"]] == ["fm9", "vp4", "axefx3"]


def test_nothing_sent_and_nothing_raised_when_the_bus_cannot_be_read(monkeypatch):
    from fm9 import midi_transport

    def boom(*a, **k):
        raise OSError("no MIDI binding")
    monkeypatch.setattr(midi_transport, "port_names", boom)
    assert server.detected_devices() == []
    assert server._ir2_port_present() is False


def test_nothing_sent_unverified_patterns_are_worded_looks_like():
    assert "title: dev.verified ? `${dev.label} connected` : `Looks like a ${dev.label}`," in PAGE


# -- REQ-003: the state block and the link stream ----------------------------------------

def test_state_block_carries_detected_devices(client, monkeypatch):
    _ports(monkeypatch, ["VP4 MIDI In"])
    s = client.get("/api/state").json()
    assert s["device"]["detected"] == [{
        "kind": "vp4", "label": "Fractal VP4", "supported": False, "verified": False,
        "issue": 191, "issue_url": "https://github.com/monzta1/ToneCommand/issues/191"}]
    # an unsupported device is named, never made available or selectable
    assert [d["kind"] for d in s["device"]["available"]] == ["fm9"]
    assert client.post("/api/device/select", json={"kind": "vp4"}).status_code == 404


def test_state_lists_the_ir2_through_the_catalog(client, monkeypatch):
    _ports(monkeypatch, ["IR-2"])
    s = client.get("/api/state").json()
    assert [d["kind"] for d in s["device"]["available"]] == ["fm9", "ir2"]
    assert [d["kind"] for d in s["device"]["detected"]] == ["ir2"]


def test_link_stream_emits_devices_at_start_and_on_change_only(monkeypatch):
    lists = iter([["FM9 MIDI In 0"], ["FM9 MIDI In 0"], ["FM9 MIDI In 0", "IR-2"],
                  ["FM9 MIDI In 0", "IR-2"], ["IR-2"]])
    current = {"names": []}
    from fm9 import midi_transport
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: current["names"])
    captured = {}
    monkeypatch.setattr(server, "_stream_response", lambda work, final: captured.setdefault("work", work))
    server.api_link_stream()

    class Ticks:
        def __init__(self):
            self.done = False
            self._advance()

        def _advance(self):
            try:
                current["names"] = next(lists)
            except StopIteration:
                self.done = True

        def is_set(self):
            return self.done

        def wait(self, _t):
            self._advance()
    events = []
    captured["work"](lambda kind, payload: events.append((kind, payload)), Ticks())
    devices = [[d["kind"] for d in p["detected"]] for k, p in events if k == "devices"]
    assert devices == [["fm9"], ["fm9", "ir2"], ["ir2"]]
    # the FM9 link event is unchanged: present, then absent when its port went
    assert [p for k, p in events if k == "link"] == [{"present": True}, {"present": False}]


# -- REQ-004 server half: /api/reconnect rebuilds a non-FM9 device -----------------------

def test_card_reconnect_rebuilds_the_active_ir2(client, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_IR2_SIM", "1")
    assert client.post("/api/device/select", json={"kind": "ir2"}).status_code == 200
    old = server.device_context().adapter
    closed = []
    monkeypatch.setattr(old, "close", lambda: closed.append(True))
    r = client.post("/api/reconnect").json()
    assert r == {"connected": True}
    assert closed == [True]
    assert server.device_context().kind == "ir2" and server.device_context().adapter is not old


def test_card_reconnect_reports_a_device_that_will_not_open(client, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_IR2_SIM", "1")
    client.post("/api/device/select", json={"kind": "ir2"})

    def gone(kind):
        raise RuntimeError("BOSS IR-2 not found on the MIDI bus")
    monkeypatch.setattr(server, "_build_context", gone)
    assert client.post("/api/reconnect").json() == {
        "connected": False, "why": "BOSS IR-2 not found on the MIDI bus"}


# -- REQ-004: the card, run in node ------------------------------------------------------

START = "let detectedKinds = null;"
END = "// A build refused because the device is ambiguous"
CARD_IDS = ("devcard", "devcardtitle", "devcardtext", "devcardlink", "devcardclose", "devcardbar")

HARNESS = r"""
import { readFileSync } from "fs";
const src = readFileSync(process.argv[2], "utf8");
const start = src.indexOf(process.argv[3]);
const end = src.indexOf(process.argv[4], start);
if (start < 0 || end < 0) { console.log("EXTRACT FAILED"); process.exit(1); }
const code = src.slice(start, end);
const sc = JSON.parse(process.argv[5]);
const known = JSON.parse(process.argv[6]);
const nodes = {};
for (const id of known) nodes[id] = { textContent: "", hidden: true, dataset: {}, className: "",
  style: {}, querySelector: () => ({ style: {} }) };
const $ = (id) => { if (!(id in nodes)) throw new Error("no element " + id); return nodes[id]; };
const store = {};
const sessionStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
let deviceGen = 0, deviceState = { active: sc.active || "fm9" };
const calls = [], paints = [];
const io = {
  claim: () => ++deviceGen,
  current: () => deviceGen,
  active: () => deviceState.active,
  paint: st => { paints.push(st); },
  later: () => {},
  select: async kind => { calls.push(["select", kind]);
    if (sc.pickDuring) deviceGen++;                 // the player picks something else mid-walk
    return sc.select || { ok: true }; },
  reconnect: async () => { calls.push(["reconnect"]); return sc.reconnect || { ok: true }; },
  refresh: async () => { calls.push(["refresh"]); return sc.read; },
};
const api = new Function("$", "sessionStorage", "deviceGen", "deviceState", "fetch", "refresh", "setTimeout",
  code + "\nreturn {runPlugCard, renderDetected, dismissKind};")(
  $, sessionStorage, deviceGen, deviceState, null, null, null);
const results = [];
if (sc.overlap) {
  // Card A's read is held open while card B arrives and finishes; then A's
  // read comes back late. Only the first refresh is deferred.
  let release, first = true;
  io.refresh = async () => { calls.push(["refresh"]);
    if (first) { first = false; await new Promise(r => { release = r; }); }
    return sc.read; };
  const a = api.runPlugCard(sc.card, io);
  await new Promise(r => setImmediate(r));
  const b = await api.runPlugCard(sc.overlap, io);
  release();
  results.push(await a, b);
} else if (sc.card) results.push(await api.runPlugCard(sc.card, io));
for (const list of sc.lists || []) {
  if (sc.dismiss) api.dismissKind(sc.dismiss);
  results.push(api.renderDetected(list, io));
  await new Promise(r => setImmediate(r));
}
console.log(JSON.stringify({ results, calls, paints }));
"""

IR2 = {"kind": "ir2", "label": "BOSS IR-2", "supported": True, "verified": True,
       "issue": None, "issue_url": None}
FM9 = dict(IR2, kind="fm9", label="Fractal FM9")
VP4 = {"kind": "vp4", "label": "Fractal VP4", "supported": False, "verified": False,
       "issue": 191, "issue_url": "https://github.com/monzta1/ToneCommand/issues/191"}
GOOD_READ = {"connected": True, "active": "ir2", "fresh": True}


def _card(tmp_path, **scenario) -> dict:
    for node_id in CARD_IDS:
        assert f'id="{node_id}"' in PAGE, f"the page declares no #{node_id}"
    h = tmp_path / "harness.mjs"
    h.write_text(HARNESS, encoding="utf-8")
    out = subprocess.run(["node", str(h), str(ROOT / "ui" / "index.html"), START, END,
                          json.dumps(scenario), json.dumps(list(CARD_IDS))],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "EXTRACT FAILED" not in out.stdout, "the card code moved; fix the slice"
    return json.loads(out.stdout.strip())


def _texts(r):
    return [p["text"] for p in r["paints"] if p]


def test_card_walks_to_ready_by_switching_to_a_new_device(tmp_path):
    r = _card(tmp_path, card=IR2, active="fm9", read=GOOD_READ)
    assert r["results"] == ["ready"]
    assert r["calls"] == [["select", "ir2"], ["refresh"]]
    assert _texts(r) == ["Getting support ready...", "Connecting to the BOSS IR-2...",
                         "Reading the BOSS IR-2...", "Ready. Ask for a tone."]
    assert r["paints"][0]["title"] == "BOSS IR-2 detected"
    assert [p["pct"] for p in r["paints"]] == [15, 40, 70, 100]


def test_card_reconnects_the_active_device_on_a_replug(tmp_path):
    r = _card(tmp_path, card=IR2, active="ir2", read=GOOD_READ)
    assert r["results"] == ["ready"] and r["calls"] == [["reconnect"], ["refresh"]]


def test_card_shows_the_servers_refusal_and_never_ready(tmp_path):
    why = "GIG LOCK is on: the target device cannot change"
    r = _card(tmp_path, card=IR2, active="fm9", read=GOOD_READ, select={"ok": False, "error": why})
    assert r["results"] == ["refused"] and ["refresh"] not in r["calls"]
    assert r["paints"][-1]["error"] is True and r["paints"][-1]["text"] == why
    assert "Ready. Ask for a tone." not in _texts(r)


def test_card_reports_a_failed_reconnect(tmp_path):
    r = _card(tmp_path, card=IR2, active="ir2", read=GOOD_READ,
              reconnect={"ok": False, "error": "BOSS IR-2 not found on the MIDI bus"})
    assert r["results"] == ["refused"]
    assert r["paints"][-1]["text"] == "BOSS IR-2 not found on the MIDI bus"


@pytest.mark.parametrize("read", [
    {"connected": False, "fresh": True, "error": "no link"},     # the read failed
    {"connected": True, "active": "fm9", "fresh": True},          # another device answered
    {"connected": True, "active": "ir2", "fresh": False},         # a stale poll
    None,
])
def test_card_is_never_ready_without_a_fresh_connected_read_of_that_device(tmp_path, read):
    r = _card(tmp_path, card=IR2, active="fm9", read=read)
    assert r["results"] == ["unread"]
    assert "Ready. Ask for a tone." not in _texts(r)
    assert r["paints"][-1]["text"].startswith("Could not read the BOSS IR-2")


def test_card_closes_when_the_player_picks_another_device_mid_walk(tmp_path):
    r = _card(tmp_path, card=IR2, active="fm9", read=GOOD_READ, pickDuring=True)
    assert r["results"] == ["superseded"]
    assert ["refresh"] not in r["calls"]
    assert r["paints"][-1] is None and "Ready. Ask for a tone." not in _texts(r)


def test_card_does_not_open_for_devices_already_there_at_load(tmp_path):
    r = _card(tmp_path, active="fm9", read=GOOD_READ,
              lists=[[FM9, IR2], [FM9, IR2], [FM9], [FM9, IR2]])
    # baseline, unchanged, unplugged, replugged: only the replug opens a card
    assert r["results"] == ["none", "none", "none", "plug"]
    assert r["calls"] == [["select", "ir2"], ["refresh"]]


def test_card_names_an_unsupported_device_at_load_with_its_issue(tmp_path):
    r = _card(tmp_path, lists=[[FM9, VP4]])
    assert r["results"] == ["unsupported"] and r["calls"] == []
    p = r["paints"][-1]
    assert p["title"] == "Looks like a Fractal VP4"
    assert p["text"] == "ToneCommand cannot control it yet."
    assert p["issue_url"] == "https://github.com/monzta1/ToneCommand/issues/191"


def test_card_stays_away_once_dismissed(tmp_path):
    r = _card(tmp_path, lists=[[FM9, VP4]], dismiss="vp4")
    assert r["results"] == ["none"] and r["paints"][-1] is None


# -- REQ-004: the page wiring --------------------------------------------------------------

def test_page_wires_the_card_into_the_poll_the_stream_and_dismiss():
    assert '<div id="devcard" class="devcard" hidden>' in PAGE
    assert "if (s.device && Array.isArray(s.device.detected)) renderDetected(s.device.detected);" in PAGE
    assert "if (ev === 'devices') { renderDetected(d.detected); continue; }" in PAGE
    assert "$('devcardclose').addEventListener('click', () => {" in PAGE
    # refresh() reports what the card needs, on success and on failure
    assert PAGE.count("return {connected: true, active: s.device && s.device.active, fresh: freshDevice};") == 2
    assert "return {connected: false, fresh: pollGen === deviceGen, error: String((e && e.message) || e)};" in PAGE
    # the real io goes through the same select and reconnect routes a click uses
    assert "const r = await fetch('/api/reconnect', {method: 'POST'});" in PAGE


def test_card_closes_when_a_manual_pick_meets_a_refused_switch(tmp_path):
    """Review F1: the refusal arrived after a manual pick and was painted
    anyway, leaving a dead card on screen for good."""
    r = _card(tmp_path, card=IR2, active="fm9", read=GOOD_READ, pickDuring=True,
              select={"ok": False, "error": "a reviewed plan is pending for the current device"})
    assert r["results"] == ["superseded"]
    assert r["paints"][-1] is None
    assert not any(p and p.get("error") for p in r["paints"])


def test_card_a_late_read_never_hides_a_newer_card(tmp_path):
    """Review F2: an older card finishing late cleared the card that had
    replaced it."""
    r = _card(tmp_path, card=IR2, overlap=dict(FM9), active="ir2",
              read={"connected": True, "active": "fm9", "fresh": True})
    assert r["results"] == ["superseded", "ready"]
    assert r["paints"][-1] is not None
    assert r["paints"][-1]["kind"] == "fm9" and r["paints"][-1]["text"] == "Ready. Ask for a tone."

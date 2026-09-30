"""Issues #155 (J2) and #164: one click installs an artist pack, relocating
its cabs when their slots are taken and repointing the preset before the
one store. Everything on the simulator; no network (conftest guard,
fetchers faked).
"""
import base64
import hashlib
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import gallery, gallery_install as gi, gift_of_tone
from fm9 import protocol as p
from fm9.sim import SimFM9
from tests.test_cabs import make_cab
from tests.test_install import make_file

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
FRACTAL = "https://www.fractalaudio.com/downloads/misc/_gift22/"
EMPTY = p.EMPTY_SLOT_NAME


# --- plan --------------------------------------------------------------------

def _member(kind, name, wanted=None, raw=b"x"):
    return {"kind": kind, "file": name + ".syx", "name": name, "raw": raw, "wanted": wanted}


ENTRY = {"id": "got-1", "artists": ["Steve Lukather"], "year": 2025,
         "kind": "preset plus cab bundle"}


def _names(table):
    return lambda slot: table.get(slot, EMPTY)


def test_plan_honours_the_maps_slot_when_free_and_whitelisted():
    pl = gi.plan(ENTRY, [_member("preset", "BT Luke 01"),
                         _member("cab", "BT_Rivero", wanted=11),
                         _member("cab", "BT_3VH4", wanted=12)],
                 cab_name=_names({}), store_name=_names({}),
                 cab_whitelist=set(range(0, 1024)), store_whitelist={139, 140})
    assert [(c.slot, c.moved, c.kept) for c in pl.cabs] == [(11, False, False), (12, False, False)]
    assert pl.store_slot == 139 and pl.moves == {}


def test_plan_relocates_a_taken_or_unlisted_slot_to_the_lowest_free_one():
    held = {11: "BT_Apocalypse_Ch2_A", 12: "BT_Apocalypse_Ch2_B", 512: "something"}
    pl = gi.plan(ENTRY, [_member("preset", "BT Luke 01"),
                         _member("cab", "BT_Rivero", wanted=11),
                         _member("cab", "BT_3VH4", wanted=12)],
                 cab_name=_names(held), store_name=_names({139: "Taken"}),
                 cab_whitelist=set(range(512, 1024)), store_whitelist={139, 140})
    assert [(c.wanted, c.slot, c.moved) for c in pl.cabs] == [(11, 513, True), (12, 514, True)]
    assert pl.moves == {11: 513, 12: 514}
    assert pl.store_slot == 140
    assert "moved from U1.0012" in gi.result_line(pl, "141 (wire 140)")


def test_plan_keeps_a_cab_already_there_by_name():
    pl = gi.plan(ENTRY, [_member("preset", "P"), _member("cab", "BT_Rivero", wanted=522)],
                 cab_name=_names({522: "BT_Rivero"}), store_name=_names({}),
                 cab_whitelist={522, 523}, store_whitelist={139})
    assert pl.cabs[0].kept is True and pl.cabs[0].slot == 522 and pl.moves == {}
    assert "(already there)" in gi.result_line(pl, "140 (wire 139)")


def test_plan_takes_the_lowest_whitelisted_store_slot_when_none_is_empty():
    pl = gi.plan(ENTRY, [_member("preset", "P")], cab_name=_names({}),
                 store_name=_names({133: "VH Balance FM9AI", 139: "Worship Core FM9AI"}),
                 cab_whitelist={512}, store_whitelist={133, 139})
    assert pl.store_slot == 133 and pl.replaced == "VH Balance FM9AI"
    assert "(replacing 'VH Balance FM9AI')" in gi.result_line(pl, "134 (wire 133)")
    # an empty one wins when there is one
    pl = gi.plan(ENTRY, [_member("preset", "P")], cab_name=_names({}),
                 store_name=_names({133: "VH Balance FM9AI"}),
                 cab_whitelist={512}, store_whitelist={133, 139})
    assert pl.store_slot == 139 and pl.replaced is None
    # a slot that does not answer its name is never overwritten
    with pytest.raises(gi.GalleryInstallError, match="did not answer its name"):
        gi.plan(ENTRY, [_member("preset", "P")], cab_name=_names({}),
                store_name=lambda s: None, cab_whitelist={512}, store_whitelist={133})


def test_plan_refuses_in_one_line_before_any_write():
    with pytest.raises(gi.GalleryInstallError, match="no store slots configured"):
        gi.plan(ENTRY, [_member("preset", "P")], cab_name=_names({}),
                store_name=_names({}), cab_whitelist={512}, store_whitelist=set())
    with pytest.raises(gi.GalleryInstallError, match="no free user-cab slot"):
        gi.plan(ENTRY, [_member("preset", "P"), _member("cab", "C", wanted=11)],
                cab_name=_names({512: "full"}), store_name=_names({}),
                cab_whitelist={512}, store_whitelist={139})
    with pytest.raises(gi.GalleryInstallError, match="effect blocks only"):
        gi.plan(dict(ENTRY, kind="effect blocks"), [_member("block", "B")],
                cab_name=_names({}), store_name=_names({}),
                cab_whitelist={512}, store_whitelist={139})
    with pytest.raises(gi.GalleryInstallError, match="no FM9 preset"):
        gi.plan(ENTRY, [_member("cab", "C", wanted=1)], cab_name=_names({}),
                store_name=_names({}), cab_whitelist={512}, store_whitelist={139})


# --- execute on the sim --------------------------------------------------------

@pytest.fixture
def sim(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_CAB_SLOTS", "512-1023")
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "139-141")
    dev = SimFM9(server.reg)
    dev.status_dump()
    # the sim's store slots read as presets; make 139-141 empty like a unit
    # with free space, so the plan can pick the lowest
    core = dev.outp.core
    for s in (139, 140, 141):
        core.st.empty_slots[s] = ""
    calls = []
    for name in ("install_user_cab_slot", "load_preset_buffer", "store_preset",
                 "select_preset", "set_param_ordinal"):
        real = getattr(dev, name)

        def wrap(*a, _n=name, _r=real, **k):
            calls.append(_n)
            return _r(*a, **k)
        monkeypatch.setattr(dev, name, wrap)
    dev.calls = calls
    return dev


def _pack(cab_slot_a=11, cab_slot_b=12):
    """A Lukather-shaped pack: one preset whose Cab block IR slot 2 points at
    USER cab_slot_a on channels A/B and cab_slot_b on C/D, and two cabs
    filed at those slots."""
    return [
        _member("preset", "BT Luke 01", raw=make_file(name="BT Luke 01")),
        _member("cab", "BT_Rivero", wanted=cab_slot_a, raw=make_cab()),
        _member("cab", "BT_3VH4", wanted=cab_slot_b, raw=make_cab(chunk_len=1281)),
    ]


def _point_cab_block(sim, slot_ab, slot_cd, dynacab=True):
    """Make the loaded preset reference user cabs the way the pack does,
    loaded as Dyna-Cab type the way a pre-Dyna-Cab pack loads on fw 11."""
    reg = server.reg
    for ch, slot in ((0, slot_ab), (1, slot_ab), (2, slot_cd), (3, slot_cd)):
        sim.set_channel(62, ch)
        sim.set_param_ordinal(reg.spec("CABINET", 1, 1), gi.USER_BANK)
        sim.set_param_ordinal(reg.spec("CABINET", 5, 1), slot)
        sim.set_param_ordinal(reg.spec("CABINET", gi.MODE_PARAM, 1),
                              gi.MODE_DYNACAB if dynacab else gi.MODE_LEGACY)
    sim.set_channel(62, 0)


def test_execute_order_is_cabs_then_buffer_then_repoint_then_one_store(sim, monkeypatch):
    # the pack's slots 11/12 are taken by the player's own cabs
    core = sim.outp.core
    core.user_cabs = {(11, 0x10): [[1]], (12, 0x10): [[2]]}
    pl = gi.plan(ENTRY, _pack(), cab_name=sim.read_user_cab_name,
                 store_name=lambda s: (lambda n: n.name if n else None)(sim.slot_name(s)),
                 cab_whitelist=set(range(512, 1024)), store_whitelist={139, 140, 141})
    assert pl.moves == {11: 512, 12: 513} and pl.store_slot == 139
    # the loaded preset in the sim gets the pack's references after the
    # buffer load; simulate the file carrying them by pointing after load
    real_load = sim.load_preset_buffer

    def load_then_point(raw, name=None):
        pf = real_load(raw, name)
        _point_cab_block(sim, 11, 12)
        return pf
    monkeypatch.setattr(sim, "load_preset_buffer", load_then_point)
    sim.calls.clear()
    out = gi.execute(pl, sim)
    assert out["ok"] is True
    order = [c for c in sim.calls if c != "set_param_ordinal"]
    assert order[:2] == ["install_user_cab_slot", "install_user_cab_slot"]
    assert order.count("store_preset") == 1
    assert order.index("store_preset") > order.index("install_user_cab_slot")
    assert order[-1] == "select_preset"           # the read-back
    assert sim.calls.index("store_preset") > sim.calls.index("set_param_ordinal")
    assert out["store_slot"] == 139 and out["read_back"] == "BT Luke 01"
    assert [c["editor"] for c in out["cabs"]] == ["U1.0513", "U1.0514"]
    assert [c["moved_from"] for c in out["cabs"]] == ["U1.0012", "U1.0013"]
    assert out["line"] == ("Steve Lukather's preset plus cab bundle is on slot 140 (wire 139); "
                           "cab BT_Rivero in user cab U1.0513 (moved from U1.0012); "
                           "cab BT_3VH4 in user cab U1.0514 (moved from U1.0013).")
    # repointed on every channel that referenced the moved slots, and each
    # of those channels switched from Dyna-Cab to Legacy type so the IR plays
    slots = [c for c in out["repointed"] if "ir_slot" in c]
    modes = [c for c in out["repointed"] if c.get("type") == "legacy"]
    assert sorted((c["channel"], c["from"], c["to"]) for c in slots) == \
        [("A", 11, 512), ("B", 11, 512), ("C", 12, 513), ("D", 12, 513)]
    assert sorted(c["channel"] for c in modes) == ["A", "B", "C", "D"]
    reg = server.reg
    for ch, want in ((0, 512), (1, 512), (2, 513), (3, 513)):
        assert sim.get_param_wire(reg.spec("CABINET", 5, 1), channel=ch) == want
        assert sim.get_param_wire(reg.spec("CABINET", gi.MODE_PARAM, 1), channel=ch) == gi.MODE_LEGACY


#: The settle window these two tests run under. Wide relative to the clock's
#: tick so "inside the window" has room, and the tick is derived from it so
#: the relationship between the two is visible rather than a pair of magic
#: numbers that drift apart.
SETTLE_TEST = 0.4


class _Clock:
    """A clock the test owns (#181).

    The simulator's settle window is measured against whatever
    `fm9.sim.SETTLE_CLOCK` returns. Using the wall clock made this test a
    race: under `-n auto` more than SETTLE seconds can pass between a write
    and the statement after it, the window closes, the simulator correctly
    answers the new value, and the test fails for the reason it exists to
    catch. It passed alone and on an idle machine every time.

    Every message the simulator handles moves this clock by one `tick`, so
    the product's own settle-and-retry crosses the window exactly where it
    would on hardware, and the test needs no `time.sleep` at all. Whether a
    read lands inside the window is now a fact about this object.
    """

    def __init__(self, tick):
        self.t = 0.0
        self.tick = tick

    def __call__(self):
        self.t += self.tick
        return self.t

    def jump(self, seconds):
        """Settle everything outstanding, explicitly."""
        self.t += seconds


def test_repoint_reads_back_after_the_settle_window_not_inside_it(sim, monkeypatch):
    """#169: the repoint read-back passed here only because parsing a
    CABINET bulk read (2,043 frames) took longer than the sim's 80 ms
    settle window, and failed on a faster machine every time. With the
    window widened past any host's parse time, an unsettled read-back
    returns the OLD value deterministically; the settle-and-retry reads
    the new one.

    #181: the widened window was still wall-clock time, so a loaded runner
    could cross it between two statements and the test failed on CI for a
    markdown-only commit. The clock is injected now, so "inside the window"
    is arranged rather than hoped for. The behaviour under test is
    unchanged: an unsettled read must return the old value, and
    `gi._read_back` must settle and retry until it sees the new one.
    """
    import fm9.sim as simmod
    clock = _Clock(tick=SETTLE_TEST / 4)
    monkeypatch.setattr(simmod, "SETTLE_CLOCK", clock)
    monkeypatch.setattr(simmod, "SETTLE", SETTLE_TEST)

    _point_cab_block(sim, 11, 12)
    clock.jump(1.0)                                         # the pointing has settled

    # the defect, reproduced on purpose: write, then read inside the window
    spec = server.reg.spec("CABINET", 5, 1)
    sim.set_param_ordinal(spec, 512)
    # Measured, and asserted so it cannot drift silently: the write leaves
    # exactly two ticks before the window shuts. The read below is one tick
    # in, so it is inside; the first settle-and-retry is the second tick, so
    # it is outside. If set_param_ordinal ever sends a different number of
    # frames this fails here, naming the reason, rather than further down
    # looking like the behaviour changed.
    headroom = round((sim.outp.core._snapshot_expire - clock.t) / clock.tick, 6)
    assert 1 < headroom <= 2, f"the window now leaves {headroom} ticks, not 2"
    assert sim.get_param_wire(spec, channel=0) == 11        # what the unit answers too soon
    assert gi._read_back(sim, spec, 0, 512) == 512          # what the product reads

    # and the whole repoint, under the wide window, lands on every channel
    sim.set_param_ordinal(spec, 11)
    clock.jump(1.0)
    changed = gi.repoint(sim, {11: 512, 12: 513})
    assert sorted((c["channel"], c["to"]) for c in changed if "ir_slot" in c) == \
        [("A", 512), ("B", 512), ("C", 513), ("D", 513)]
    assert gi.READ_BACK_SETTLE * gi.READ_BACK_TRIES > 0.4


def test_the_settle_window_test_still_fails_without_the_settle_and_retry(sim, monkeypatch):
    """The guard on the guard (#181 acceptance 1). If `_read_back` stopped
    settling and retrying, the test above must go red rather than quietly
    keep passing. A deterministic clock could otherwise be tuned until
    everything passes for the wrong reason."""
    import fm9.sim as simmod
    clock = _Clock(tick=SETTLE_TEST / 4)
    monkeypatch.setattr(simmod, "SETTLE_CLOCK", clock)
    monkeypatch.setattr(simmod, "SETTLE", SETTLE_TEST)
    _point_cab_block(sim, 11, 12)
    clock.jump(1.0)
    spec = server.reg.spec("CABINET", 5, 1)
    sim.set_param_ordinal(spec, 512)
    # one read, no settle, no retry: this is what removing the fix looks like
    assert sim.get_param_wire(spec, channel=0) == 11


def test_execute_leaves_an_untouched_preset_alone(sim, monkeypatch):
    pl = gi.plan(ENTRY, _pack(cab_slot_a=600, cab_slot_b=601),
                 cab_name=sim.read_user_cab_name,
                 store_name=lambda s: (lambda n: n.name if n else None)(sim.slot_name(s)),
                 cab_whitelist=set(range(512, 1024)), store_whitelist={139})
    assert pl.moves == {}
    sim.calls.clear()
    out = gi.execute(pl, sim)
    assert out["repointed"] == [] and "set_param_ordinal" not in sim.calls
    assert sim.calls.count("store_preset") == 1
    assert "moved" not in out["line"]


def test_execute_stops_at_a_cab_that_does_not_land(sim, monkeypatch):
    pl = gi.plan(ENTRY, _pack(cab_slot_a=600, cab_slot_b=601),
                 cab_name=sim.read_user_cab_name,
                 store_name=lambda s: (lambda n: n.name if n else None)(sim.slot_name(s)),
                 cab_whitelist=set(range(512, 1024)), store_whitelist={139})
    from fm9.device import CabInstall
    real = sim.install_user_cab_slot
    n = {"i": 0}

    def flaky(raw, slot, filename="", expect_name=None):
        n["i"] += 1
        if n["i"] == 2:
            return CabInstall(None, slot, False, "the unit did not answer", landed=False)
        return real(raw, slot, filename, expect_name)
    monkeypatch.setattr(sim, "install_user_cab_slot", flaky)
    with pytest.raises(gi.GalleryInstallError, match="stopped at cab BT_3VH4") as e:
        gi.execute(pl, sim)
    assert "Landed so far: U1.0601" in str(e.value)
    assert "store_preset" not in sim.calls and "load_preset_buffer" not in sim.calls


# --- the route -----------------------------------------------------------------

def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()


def _bundle(preset_raw, cabs):
    """A .fasBundle: the preset plus cabs pinned to USER bank slots."""
    buf = io.BytesIO()
    cab_xml = "".join(
        f'<CabData CabID="62" Bank="2" Number="{n}" Name="{name}" File="cabs/{name}.syx"/>'
        for n, name, _raw in cabs)
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(".bundle", '<Bundle-Map version="1"><Device deviceId="18" major="4" minor="0"/>'
                   '<Preset Location="410" Name="BT Luke 01" File="BT Luke 01.syx"/>'
                   + cab_xml + '</Bundle-Map>')
        z.writestr("BT Luke 01.syx", preset_raw)
        for n, name, raw in cabs:
            z.writestr(f"cabs/{name}.syx", raw)
    return buf.getvalue()


@pytest.fixture
def client(sim, monkeypatch, tmp_path):
    monkeypatch.setenv("TONECOMMAND_CACHE_DIR", str(tmp_path / "cache"))
    bundle = _bundle(make_file(name="BT Luke 01"),
                     [(11, "BT_Rivero", make_cab()), (12, "BT_3VH4", make_cab(chunk_len=1281))])
    z = _zip([("Luke/BT Steve Lukather 01.fasBundle", bundle), ("ReadMe.txt", b"hi")])
    entry = {"id": "got-luke", "artists": ["Steve Lukather"], "year": 2025, "number": "1",
             "kind": "preset plus cab bundle", "description": "Preset + Cab Bundle",
             "devices": [{"device": "FM9", "min_firmware": "4.0"}],
             "url": FRACTAL + "luke.zip", "sha256": hashlib.sha256(z).hexdigest(),
             "bytes": len(z),
             "contents": {"presets": [], "cabs": [], "blocks": [],
                          "other": ["ReadMe.txt"],
                          "bundles": [{"file": "Luke/BT Steve Lukather 01.fasBundle",
                                       "map": {}, "members": []}]}}
    blocks = dict(entry, id="got-blocks", artists=["Steve Vai"], kind="effect blocks",
                  contents={"presets": [], "cabs": [], "blocks": ["A.blk"], "other": [],
                            "bundles": []})
    monkeypatch.setattr(gift_of_tone, "fetch",
                        lambda timeout=6.0: ({"entries": [entry, blocks]}, "fixture", None))
    monkeypatch.setattr(gallery, "_download", lambda url: z)
    monkeypatch.setattr(server, "_fm9", sim)
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    return TestClient(server.app)


def test_route_installs_the_pack_and_names_where_it_landed(client, sim):
    sim.outp.core.user_cabs = {(11, 0x10): [[1]], (12, 0x10): [[2]]}   # taken
    r = client.post("/api/gift-of-tone/install", json={"id": "got-luke"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["store_slot"] == 139
    assert [c["editor"] for c in d["cabs"]] == ["U1.0513", "U1.0514"]
    assert d["line"].startswith("Steve Lukather's preset plus cab bundle is on slot 140 (wire 139); cab BT_Rivero in user cab U1.0513 (moved from U1.0012)")
    assert d["source"] == "fetched" and d["unexpected"] == []
    assert sim.calls.count("store_preset") == 1


def test_route_refuses_in_one_line(client, sim, monkeypatch):
    r = client.post("/api/gift-of-tone/install", json={"id": "got-blocks"})
    assert r.status_code == 409 and "effect blocks only" in r.json()["error"]
    assert sim.calls == []
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "")             # nothing listed
    monkeypatch.setattr(server, "get_store_slots", lambda: set())
    r = client.post("/api/gift-of-tone/install", json={"id": "got-luke"})
    assert r.status_code == 409 and "no store slots configured" in r.json()["error"]
    assert sim.calls == []
    monkeypatch.setattr(server, "get_store_slots", lambda: {139, 140, 141})
    monkeypatch.setattr(server, "_gig_mode", {"on": True})
    r = client.post("/api/gift-of-tone/install", json={"id": "got-luke"})
    assert r.status_code == 423
    r = client.post("/api/gift-of-tone/install", json={"id": "nope"})
    assert r.status_code == 404
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_connected_for_gallery", lambda: (None, ""))
    r = client.post("/api/gift-of-tone/install", json={"id": "got-luke"})
    assert r.status_code == 409 and r.json()["error"] == gallery.NO_DEVICE_LINE


def test_route_whitelist_never_written_outside(client, sim, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_CAB_SLOTS", "700-701")
    sim.outp.core.user_cabs = {(11, 0x10): [[1]], (12, 0x10): [[2]]}
    d = client.post("/api/gift-of-tone/install", json={"id": "got-luke"}).json()
    assert [c["slot"] for c in d["cabs"]] == [700, 701]
    assert set(k[0] for k in sim.outp.core.user_cabs) <= {11, 12, 700, 701}


# --- the page ------------------------------------------------------------------

def test_page_has_the_gallery_and_the_wiring():
    assert 'id="artistsrow"' in UI and 'id="artistcards"' in UI
    assert "async function renderArtists()" in UI
    assert "fetch('/api/gift-of-tone')" in UI
    # The INSTALL button is found by its data-id hook, not an `artistgo`
    # class: a class with no stylesheet rule is what test_ui_warning's class
    # audit exists to catch, and the id was already on the attribute.
    assert 'button[data-id]' in UI and "runArtistInstall(b.dataset.id, b)" in UI
    assert "fetch('/api/gift-of-tone/install'" in UI
    assert "chatNote(d.line);" in UI
    assert "if (name === 'storage') renderArtists();" in UI
    assert "effect blocks: not installable from here yet" in UI

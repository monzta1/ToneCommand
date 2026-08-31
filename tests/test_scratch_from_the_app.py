"""Building into an empty slot, without a terminal (issue #36).

An empty FM9 slot has no grid cells at all, not even pass-through cells
(finding 18), so add_block has nothing to replace and splice has nothing to
displace. Both refuse, correctly. The logic that CAN serve one has existed and
been hardware-proven for weeks in tools/build_from_scratch.py, and pyproject
ships `fm9` and `server`, not `tools`, so nothing shipped could import it:
selecting an empty slot in the app was a dead end by construction.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import scratch_build
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]
BODY = UI.split("</style>")[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


# --- one implementation, two front doors ----------------------------------

def test_the_cli_and_the_app_run_the_same_code():
    """Not a copy. A second implementation of a hardware sequence is a second
    thing to keep proven."""
    cli = Path("tools/build_from_scratch.py").read_text()
    assert "from fm9.scratch_build import" in cli
    assert "dev.place_block" not in cli, "the CLI must not build anything itself"
    assert "scratch_build.build(" in Path("server.py").read_text()


def test_it_is_importable_from_shipped_code():
    """The whole cause of #36: tools/ is not packaged, so the app could not
    reach the one function that solves this."""
    packaged = Path("pyproject.toml").read_text()
    assert "fm9" in packaged
    assert scratch_build.build.__module__ == "fm9.scratch_build"


# --- what it refuses -------------------------------------------------------

def test_it_only_ever_lands_on_a_slot_the_device_calls_empty(client):
    with server._fm9 as dev:
        r = scratch_build.build(dev, server.reg, slot=0)   # occupied
    assert not r["ok"]
    assert "refusing to build" in r["detail"]


def test_a_refusal_has_the_same_shape_as_a_success(client):
    """A report whose keys depend on its outcome makes every caller guess, and
    the CLI raised KeyError on three refusal paths because of exactly that."""
    with server._fm9 as dev:
        bad = scratch_build.build(dev, server.reg, slot=0)
        good = scratch_build.build(dev, server.reg)
    assert bad.keys() == good.keys()


def test_gig_mode_refuses(client):
    """It selects a different slot, which throws away the edit buffer. Not
    while someone is playing."""
    client.post("/api/gig", json={"on": True})
    try:
        r = client.post("/api/build-scratch", json={})
        assert r.status_code == 423
        assert "GIG MODE" in r.json()["error"]
    finally:
        client.post("/api/gig", json={"on": False})


def test_it_is_a_post(client):
    """It writes, and it discards the edit buffer. A GET can be prefetched by
    a browser or replayed by a refresh."""
    routes = {(r.path, tuple(sorted(r.methods))) for r in server.app.routes
              if getattr(r, "methods", None)}
    assert ("/api/build-scratch", ("POST",)) in routes


def test_nothing_here_stores(client):
    """The slot keeps reading <EMPTY> in flash until the owner saves it
    themselves, through the separately whitelisted store path."""
    import inspect
    src = inspect.getsource(scratch_build)
    for forbidden in ("store_preset", "build_store"):
        assert forbidden not in src, forbidden


# --- and it actually builds ------------------------------------------------

def test_it_builds_a_live_path(client):
    r = client.post("/api/build-scratch", json={}).json()
    assert r["ok"], r["detail"]
    assert r["alive"] is True
    assert "live signal path confirmed" in r["detail"]
    placed = {c["effect_id"] for c in r["cells"]}
    for eid, label in scratch_build.CHAIN:
        assert eid in placed, label


def test_the_reply_says_what_it_did_to_your_rig(client):
    """It switches the loaded preset out from under you."""
    r = client.post("/api/build-scratch", json={}).json()
    assert any("leaving preset" in s for s in r["steps"])
    assert any("target: slot" in s for s in r["steps"])


# --- what the browser offers ----------------------------------------------

def test_the_panel_appears_only_for_an_empty_slot():
    assert 'data-label="EMPTY SLOT"' in BODY and 'id="emptypanel"' in BODY
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "const emptySlot = lastState.connected !== false && !(s.blocks || []).length;" in render
    assert "$('emptypanel').style.display = emptySlot ? '' : 'none';" in render


def test_an_empty_slot_is_not_reported_as_a_missing_rig():
    """"awaiting link" over a slot the device is happily reporting as <EMPTY>
    sends people looking for a cable fault they do not have."""
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "This preset slot is empty" in render
    assert "lastState.connected !== false" in render


def test_the_button_confirms_and_says_what_it_costs():
    fn = SCRIPT.split("$('buildscratch').onclick")[1].split("\n};")[0]
    assert "window.confirm(" in fn
    assert "discards whatever is in the edit buffer" in fn
    assert "Nothing is stored" in fn
    assert "factory defaults" in fn


def test_the_refusal_points_at_the_button_not_a_terminal():
    """The refusal named tools/build_from_scratch.py, which was accurate and
    useless to anyone not in a shell. That WAS issue #36."""
    a = server.Action(kind="add_block", block="amp", instance=1, position="any")
    # the rendered sentence, not the source: the phrase is split over two
    # lines in the f-string and a source scan would miss it either way
    empty = server._no_placement_detail(a, "any", [])
    assert "BUILD A STARTING CHAIN" in empty
    assert "build_from_scratch.py" not in empty
    # and the other two walls are untouched by this
    assert "did not answer" in server._no_placement_detail(a, "any", None)


def test_the_route_does_not_reopen_an_already_open_device():
    """get_fm9() hands back a device that is already open, the way every other
    route uses it. Wrapping it in `with` re-enters the context and reopens a
    MIDI port on an endpoint that is already held.

    On hardware that took the entire server process down with no traceback and
    nothing in the log: not an exception the route could catch, a dead
    process. The simulator does not model it, so nothing here caught it and
    only the rig did. Pinned as source, because that is the only place the
    difference is visible.
    """
    import inspect
    src = inspect.getsource(server.api_build_scratch)
    assert "with get_fm9()" not in src and "with fm9:" not in src
    assert "scratch_build.build(get_fm9(), reg" in src


def test_no_free_slot_is_a_refusal_that_says_what_to_do(client, monkeypatch):
    """Observed on the owner's unit: all 512 slots occupied, so there is
    nowhere to build. The message has to name the way out, because 'no empty
    presets' on its own reads like a fault in the tool."""
    from fm9.device import NoEmptySlot
    monkeypatch.setattr(server._fm9, "first_empty_slot",
                        lambda *a, **k: (_ for _ in ()).throw(
                            NoEmptySlot("no empty presets to build on: every "
                                        "slot in 0-511 holds a preset")))
    r = client.post("/api/build-scratch", json={})
    assert r.status_code == 409
    assert "refusing to build" in r.json()["detail"]

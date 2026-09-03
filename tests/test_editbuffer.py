"""Undo and A/B: the two things that make a tone tool safe to play with.

Every plugin a guitarist has ever used has A/B compare and the FM9 does not.
The absence shapes behaviour: an edit you cannot take back is an edit you
think twice about, so the tool got reached for timidly, on changes people were
already sure of. The interesting prompts are the ones you are not sure of.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import editbuffer as eb
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setattr(server, "_snaps", {"undo": None, "a": None, "b": None})
    return TestClient(server.app)


# --- a snapshot is a read, and that is what makes it automatic ------------

def test_capturing_never_moves_the_scene():
    """The whole reason undo can be automatic. Reads of the LOADED buffer are
    free; reads that require changing what is loaded are not, which is why a
    health scan is a click and this is not."""
    dev = SimFM9(server.reg)
    with dev:
        dev.set_scene(4)
        eb.capture(dev, server.reg)
        assert dev.scene_name()[0] == 4


def test_a_snapshot_records_the_preset_it_came_from():
    dev = SimFM9(server.reg)
    with dev:
        snap = eb.capture(dev, server.reg)
    assert snap["preset"] is not None
    assert snap["blocks"] and all("values" in b for b in snap["blocks"])


def test_restoring_into_a_different_preset_is_refused():
    """Block layout, channel assignments and parameter meanings are all
    preset-specific. A snapshot applied to the wrong preset is not an undo, it
    is a corruption with a reassuring name."""
    dev = SimFM9(server.reg)
    with dev:
        snap = eb.capture(dev, server.reg)
        snap["preset"] = (snap["preset"] or 0) + 7
        with pytest.raises(ValueError, match="refusing to restore across presets"):
            eb.restore(dev, server.reg, snap)


# --- a restore is a diff, not a replay ------------------------------------

def test_only_what_differs_is_written():
    """Writing all three thousand values back would take minutes, flood the
    wire, and touch parameters nothing had changed, which is a wide blast
    radius for an operation whose only purpose is to be safe."""
    dev = SimFM9(server.reg)
    with dev:
        snap = eb.capture(dev, server.reg)
        spec = server.reg.find_param("DISTORT", "Mid")
        dev.set_param_display(spec, 7.0)

        written = []
        real = dev.set_param_wire
        dev.set_param_wire = lambda s, v: (written.append(s.name), real(s, v))[1]
        eb.restore(dev, server.reg, snap)
        assert written == ["DISTORT_MID"], written


def test_an_unchanged_buffer_restores_nothing():
    dev = SimFM9(server.reg)
    with dev:
        snap = eb.capture(dev, server.reg)
        res = eb.restore(dev, server.reg, snap)
        assert res.ok and not res.applied


def test_bypass_and_channel_come_back_too():
    """Those are what the scene itself stores, as against parameters, which
    live on the channel. Both have to be part of an undo.

    The sleeps are not padding. The FM9 applies writes asynchronously and a
    read fired inside that window returns the PRE-write value, which the
    simulator models faithfully (sim.SETTLE). Reading sooner tests the
    settle window rather than the restore.
    """
    import time
    dev = SimFM9(server.reg)
    with dev:
        eid = server.reg.effect_id("DELAY")
        was = {b.effect_id: b for b in dev.status_dump()}[eid]
        snap = eb.capture(dev, server.reg)
        dev.set_bypass(eid, not was.bypassed)
        time.sleep(0.15)
        assert bool({b.effect_id: b for b in dev.status_dump()}[eid].bypassed) \
            != bool(was.bypassed), "the toggle did not land, so nothing is proven"
        eb.restore(dev, server.reg, snap)
        time.sleep(0.15)
        now = {b.effect_id: b for b in dev.status_dump()}[eid]
        assert bool(now.bypassed) == bool(was.bypassed)


def test_restoring_a_channel_does_not_read_it_back_mid_write():
    """A status dump fired straight after set_channel reports where the block
    USED to be, so a restore that re-read between writes would move it back to
    the wrong place. Positions are tracked instead."""
    import inspect
    body = inspect.getsource(eb.restore)
    assert "status_dump" not in body, \
        "restore re-reads inside the write settle window"


def test_a_restore_that_could_not_finish_says_so():
    """"Undone" is a claim about the rig, not about what we intended. A write
    that did not verify has to surface, or the button lies."""
    dev = SimFM9(server.reg)
    with dev:
        snap = eb.capture(dev, server.reg)
        spec = server.reg.find_param("DISTORT", "Mid")
        dev.set_param_display(spec, 7.0)

        class Bad:
            ok, detail = False, "read-back mismatch"
        dev.set_param_wire = lambda s, v: Bad()
        res = eb.restore(dev, server.reg, snap)
        assert not res.ok and res.failed


def test_the_summary_says_what_pressing_undo_would_do():
    dev = SimFM9(server.reg)
    with dev:
        snap = eb.capture(dev, server.reg)
        assert "nothing to undo" in eb.summarise(eb.diff(server.reg, snap, snap))
        dev.set_param_display(server.reg.find_param("DISTORT", "Mid"), 7.0)
        text = eb.summarise(eb.diff(server.reg, snap, eb.capture(dev, server.reg)))
        assert "Mid" in text and "->" in text


# --- undo is always armed --------------------------------------------------

def test_a_snapshot_is_taken_before_a_write(client):
    """Not something you had to remember to arm. It costs a quarter second and
    is silent, which is exactly why it can be automatic."""
    assert server._snaps["undo"] is None
    client.post("/api/apply", json={"actions": [{
        "kind": "set_param", "block": "DISTORT", "instance": 1,
        "param": "DISTORT_MID", "value": 6.0}]})
    assert server._snaps["undo"] is not None


def test_a_scene_change_does_not_arm_an_undo(client):
    """The rig's own control surface. Undoing a scene change means pressing
    the other scene, and burning the undo slot on it would throw away the
    edit the owner actually wants back."""
    client.post("/api/apply", json={"actions": [
        {"kind": "set_param", "block": "DISTORT", "instance": 1,
         "param": "DISTORT_MID", "value": 6.0}]})
    first = server._snaps["undo"]
    client.post("/api/apply", json={"actions": [{"kind": "set_scene", "value": 2}]})
    assert server._snaps["undo"] is first


def test_a_failed_snapshot_does_not_block_the_edit_or_lie(client, monkeypatch):
    """An UNDO button pointing at some older state than the user assumes is
    worse than a disabled one."""
    monkeypatch.setattr(eb, "capture",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")))
    r = client.post("/api/apply", json={"actions": [{
        "kind": "set_param", "block": "DISTORT", "instance": 1,
        "param": "DISTORT_MID", "value": 6.0}]}).json()
    assert server._snaps["undo"] is None
    assert any("could not snapshot" in str(x.get("detail")) for x in r["results"])


# --- A/B is a round trip ---------------------------------------------------

def test_recalling_a_captures_b_first(client):
    """Otherwise A/B is a one-way trip and the comparison can be made once."""
    client.post("/api/snapshot", json={"slot": "a"})
    assert server._snaps["b"] is None
    client.post("/api/restore", json={"slot": "a"})
    assert server._snaps["b"] is not None, "where you were has been lost"


def test_recalling_an_empty_slot_is_a_refusal_not_a_crash(client):
    r = client.post("/api/restore", json={"slot": "b"})
    assert r.status_code == 409 and "nothing captured" in r.json()["error"]


def test_gig_mode_refuses_to_restore(client):
    """An undo writes parameters like any other change. Gig mode's position is
    that nothing but a scene change reaches hardware while someone plays, and
    a write is no less a write for being well intentioned."""
    client.post("/api/snapshot", json={"slot": "a"})
    client.post("/api/gig", json={"on": True})
    try:
        r = client.post("/api/restore", json={"slot": "a"})
        assert r.status_code == 423
    finally:
        client.post("/api/gig", json={"on": False})


# --- what the browser does with it ----------------------------------------

def test_the_undo_label_is_not_refreshed_on_the_poll():
    """Describing an undo means reading the whole buffer. On a five-second
    timer that is a quarter second of MIDI traffic, forever, to answer a
    question nothing had changed the answer to."""
    refresh = SCRIPT.split("async function refresh()")[1].split("\n}")[0]
    assert "refreshSnaps" not in refresh
    assert "/api/snapshots" not in refresh


def test_but_it_is_refreshed_after_anything_that_writes():
    for fn in ("async function blockAction", "async function apply"):
        body = SCRIPT.split(fn)[1].split("\n}")[0]
        assert "refreshSnaps" in body, fn


def test_nothing_here_can_touch_a_saved_preset():
    """The edit buffer is the scope, as everywhere else in this tool. A
    snapshot is not a backup and undo is not a revision history."""
    import inspect
    src = inspect.getsource(eb)
    for forbidden in ("build_store", "select_preset", "store_preset"):
        assert forbidden not in src, forbidden
    # The Compare panel's copy states its scope in three words now.
    assert "Edit buffer only; A/B is a round trip" in UI


# --- a restore writes wire values, never display numbers ------------------

def test_restores_write_the_exact_wire_value():
    """Display units lose any parameter whose meaning IS the raw wire.

    Found on hardware auditioning cabinets: a cab slot is an ordinal stored
    directly in the wire, so undoing a cab change wrote display 1.64 on a
    0-1023 scale, landed on cab 1 instead of cab 105, and quietly loaded the
    wrong cabinet while reporting the undo as done.
    """
    import inspect
    src = inspect.getsource(eb.restore)
    assert "set_param_wire" in src
    assert "set_param_display" not in src


def test_the_spec_survives_an_uncalibrated_parameter():
    """A parameter with no display range still has an exact wire value and is
    perfectly restorable. Dropping its spec would have made those silently
    unrestorable while the summary looked complete."""
    import inspect
    assert "return None, spec" in inspect.getsource(eb._display)


def test_the_writer_verifies_by_integer_equality():
    """There is one correct answer and we already know it, so a tolerance
    would only let a near miss through."""
    import inspect
    from fm9.device import FM9
    src = inspect.getsource(FM9.set_param_wire)
    assert "after == wire" in src
    # and it tries both encodings, because the spec does not say which one a
    # parameter uses: CABINET_TYPE1 declares float while holding an ordinal
    assert "continuous" in src and "ordinal" in src

"""The prebuilt starter template (issue #47, lever 1).

The template lays the blocks a build almost always wants ALL AT ONCE on the
empty grid, so no splice ever happens, and leaves the optional ones bypassed.
This suite protects the two claims that make it a speed win rather than a
regression: every template block lands with a live signal path, and it lays
them without ever calling the splice path.
"""
import pytest

from fm9 import scratch_build, starter_template as st
from fm9.device import FM9
from fm9.registry import Registry
from fm9.sim import SimFM9
from tools.path_audit import scene_alive


@pytest.fixture(autouse=True)
def _fast_settle(monkeypatch):
    # The sim models an 80ms write-settle window: a read inside it sees stale
    # state, exactly like hardware. Keep the settle just past that window so the
    # verify reads are correct, but far below the 0.4s hardware default so the
    # suite stays fast.
    monkeypatch.setattr(scratch_build, "SETTLE", 0.09)


def dev():
    return SimFM9(Registry())


def test_the_whole_roster_lands_in_order_and_the_path_is_live():
    with dev() as d:
        rep = st.lay(d, Registry(), slot=386)
        assert rep["ok"], rep["detail"]
        cells = {c.col + 1: c for c in d.read_grid() or []}
        assert [cells[c].effect_id for c in sorted(cells)] == \
            [eid for eid, _ in st.TEMPLATE_CHAIN], "roster or order wrong"
        # continuous cabling: input feeds nothing upstream, every other col fed
        assert cells[1].cable_in_mask == 0
        for col in range(2, len(st.TEMPLATE_CHAIN) + 1):
            assert cells[col].cable_in_mask != 0, f"col {col} not cabled"


def test_the_optional_blocks_are_bypassed_and_the_core_is_on():
    with dev() as d:
        st.lay(d, Registry(), slot=386)
        blocks = {b.effect_id: b for b in d.status_dump() or []}
        for eid in st.OPTIONAL_EIDS:
            assert blocks[eid].bypassed, f"optional eid {eid} should be bypassed"
        core = st.TEMPLATE_EIDS - st.OPTIONAL_EIDS
        for eid in core:
            assert not blocks[eid].bypassed, f"core eid {eid} should be on"


def test_a_live_path_holds_with_the_optional_blocks_bypassed():
    """Bypass is pass-through, so laying optional blocks bypassed must not
    break the signal path."""
    with dev() as d:
        st.lay(d, Registry(), slot=386)
        cells = d.read_grid() or []
        blocks = {b.effect_id: b for b in d.status_dump() or []}
        alive, why = scene_alive(cells, blocks, Registry())
        assert alive, why


def test_laying_the_template_never_splices(monkeypatch):
    """The point of the template: placing left to right on an empty grid, so the
    splice path is never taken."""
    calls = []
    if hasattr(FM9, "splice_block"):
        monkeypatch.setattr(FM9, "splice_block",
                            lambda self, *a, **k: calls.append(a))
    with dev() as d:
        st.lay(d, Registry(), slot=386)
    assert calls == [], f"the template must not splice, spliced: {calls}"


def test_it_stores_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(FM9, "store_preset",
                        lambda self, slot: calls.append(slot))
    with dev() as d:
        st.lay(d, Registry(), slot=386)
    assert calls == [], f"the template is edit-buffer only, stored: {calls}"


def test_has_block_matches_the_roster():
    assert st.has_block(58) and st.has_block(70)          # amp, delay
    assert not st.has_block(110) and not st.has_block(78)  # pitch, chorus


def test_roster_text_lists_blocks_and_forbids_adding_them():
    t = st.roster_text()
    assert "do not add_block" in t.lower()
    assert "amp" in t and "DELAY" in t and "bypassed" in t
    assert "add_block only for a block not in this list" in t.lower()


def test_the_default_build_is_unchanged_by_the_generalisation():
    """scratch_build.build with no chain still lays the original four blocks."""
    from fm9 import scratch_build
    with dev() as d:
        rep = scratch_build.build(d, Registry(), slot=386)
        placed = sorted(c.effect_id for c in (d.read_grid() or []))
        assert placed == sorted(eid for eid, _ in scratch_build.CHAIN)
        assert rep["ok"]


def test_into_current_clears_the_loaded_buffer_and_lays_the_template():
    """A full unit has no free slot, so NEW clears the loaded preset's edit
    buffer to a blank canvas and lays the template there instead."""
    with dev() as d:
        d.select_preset(0)                       # a loaded, non-empty preset
        assert len(d.read_grid() or []) > 0
        rep = st.lay(d, Registry(), into_current=True)
        assert rep["ok"] and rep["alive"], rep["detail"]
        placed = sorted(c.effect_id for c in (d.read_grid() or []))
        assert placed == sorted(e for e, _ in st.TEMPLATE_CHAIN)
        assert "edit buffer" in rep["detail"]


# --- used implicitly, not on request (2026-09-07) -----------------------
#
# "call the starter template implicitly! even if the user doesnt do it - what
# does he know? we should offer a better experience rather than keep him
# waiting 10 min". It was laid only on an EMPTY slot, so a whole-rig build
# onto an occupied one spliced block by block: the slow, timing-fragile path
# #47 was written to avoid, on the request most likely to need many blocks.

import server as _server
from fastapi.testclient import TestClient as _TC
from fm9.sim import SimFM9 as _Sim


def _client(monkeypatch, actions):
    monkeypatch.setattr(_server, "_fm9", _Sim(_server.reg))
    monkeypatch.setattr(_server.planner, "plan", lambda *a, **kw: {
        "summary": "a rig", "clarification": None, "actions": actions})
    return _TC(_server.app)


ADDS = [{"kind": "add_block", "block": "delay", "instance": 1},
        {"kind": "add_block", "block": "reverb", "instance": 1}]


def test_a_whole_rig_build_says_it_will_replace_the_grid(monkeypatch):
    """It replaces what is loaded, so it is said BEFORE the player confirms
    rather than discovered afterwards."""
    c = _client(monkeypatch, ADDS)
    d = c.post("/api/plan", json={"prompt": "build me a vai rig",
                                  "whole_rig": True}).json()
    warns = " ".join(w for a in d["actions"]
                     for w in (a.get("validation_warnings") or []))
    assert "replaces what is on the grid" in warns
    assert "EDIT BUFFER only" in warns, "must say it is recoverable"


def test_a_tweak_never_offers_to_replace_the_grid(monkeypatch):
    """THE safety property. 'add delay, reverb and a chorus' is also three
    add_blocks, and wiping the grid for it would destroy the player's amp."""
    c = _client(monkeypatch, ADDS)
    d = c.post("/api/plan", json={"prompt": "add a delay and reverb"}).json()
    warns = " ".join(w for a in d["actions"]
                     for w in (a.get("validation_warnings") or []))
    assert "replaces what is on the grid" not in warns
    assert d.get("whole_rig") is False


def test_the_intent_reaches_the_send(monkeypatch):
    """Apply decides whether to lay or splice, so a plan reviewed as a
    template build must not splice when it is sent."""
    c = _client(monkeypatch, ADDS)
    d = c.post("/api/plan", json={"prompt": "build a rig",
                                  "whole_rig": True}).json()
    assert d["whole_rig"] is True, "the send has no other way to know"


def test_the_ui_sends_its_routing_decision():
    """The server cannot recover intent from the actions, so the UI's own
    build-vs-modify routing has to travel with the request."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    assert "whole_rig: !!wholeRig" in ui
    assert "engage(instruction, null, null, route === 'build')" in ui
    assert "whole_rig: !!currentPlan.whole_rig" in ui, "the send must carry it"


def test_the_planner_is_told_the_template_blocks_exist():
    """roster_text() was written and tested for #47 and never called, so on an
    empty slot the planner emitted add_block for all seven template blocks and
    every one no-opped at apply. A longer plan for the model to write and a
    longer list for the player to read, for nothing."""
    import inspect
    src = inspect.getsource(_server._plan_for)
    assert "roster_text()" in src
    assert "_will_lay_template" in src

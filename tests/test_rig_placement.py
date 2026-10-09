"""Rig builds land where the rig says, or say before review that they cannot.

#248: a new block in a rig build is anchored next to its neighbour in the
compiled chain, instead of the planner's coarse pre/post/any.
#247: a plan's structural changes are rehearsed on a simulator seeded with
the loaded preset's real grid; a plan that would not land is refused before
anyone reviews it. The grid of preset 138 (three rows in parallel) is the
layout that stopped a real send at 4 of 48 on 2026-10-09."""
import json
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import planner, riggraph as rg, rigcompile as rc, starter_template
from fm9.protocol import BlockStatus, GridCell
from fm9.sim import SimFM9, sim_from_reading

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


def n(i, role="other", label=None):
    return {"id": i, "role": role, "label": label or i, "provenance": "observed"}


def e(f, t, **kw):
    return {"from": f, "to": t, "kind": "audio", "provenance": "observed", **kw}


#: Marco Sfogli's 2015-16 pedalboard, as the reader drew it on 2026-10-09
SFOGLI = {"schema_version": 1,
          "nodes": [n("g", "instrument", "Guitar"), n("w", "wah", "wah"), n("cp", "compressor", "compression"),
                    n("b", "drive", "boost"), n("d", "drive", "drive"), n("ch", "modulation", "chorus"),
                    n("dl", "delay", "delay"), n("a", "amp", "Victory V30 head"), n("c", "cab", "Marshall 4x12")],
          "edges": [e("g", "w"), e("w", "cp"), e("cp", "b"), e("b", "d"), e("d", "ch"), e("ch", "dl"),
                    e("dl", "a"), e("a", "c")], "unknowns": []}
SPEC = {"found": True, "summary": "Sfogli 2015-16 pedalboard", "scenes": [], "stated": [], "vague": [],
        "quotes": [], "rig": SFOGLI}


_TEMPLATE = {}


def slow_template_sim():
    """The starter template laid through the full-timing path."""
    dev = SimFM9(server.reg)
    starter_template.lay(dev, server.reg, into_current=True)
    return dev


def template_sim():
    """A fast copy of the laid template. Equivalent to the slow path, as
    test_the_rehearsal_twin_lands_exactly_what_the_slow_device_path_lands
    proves; laying the template once keeps this file quick."""
    if not _TEMPLATE:
        dev = slow_template_sim()
        _TEMPLATE["cells"], _TEMPLATE["status"] = dev.read_grid(), dev.status_dump()
    return sim_from_reading(server.reg, _TEMPLATE["cells"], _TEMPLATE["status"])


def live_row(dev):
    g = server._grid_reading(dev)
    return [c["label"] for c in sorted([c for c in g["cells"] if c.get("live") and c["label"]],
                                       key=lambda c: c["col"])], g["alive"]


def add(block, inst, position=None, ref=None):
    return server.Action(kind="add_block", block=block, instance=inst, position=position, ref=ref)


# -- REQ-001: the anchor ---------------------------------------------------------------

def test_anchor_before_and_after_splice_next_to_the_named_block():
    dev = template_sim()
    assert server.run_action(dev, add("wah", 1, "before", "drive 1"))["ok"]
    assert server.run_action(dev, add("drive", 2, "after", "drive 1"))["ok"]
    assert server.run_action(dev, add("chorus", 1, "after", "drive 2"))["ok"]
    row, alive = live_row(dev)
    assert alive and row[:6] == ["Input 1", "Wah 1", "Drive 1", "Drive 2", "Chorus 1", "Amp 1"]


def test_anchor_onto_a_free_pass_through_places_without_a_splice():
    dev = SimFM9(server.reg)                 # default sim preset: a shunt right of Input 1
    res = server.run_action(dev, add("wah", 1, "after", "input 1"))
    assert res["ok"] and "spliced" not in res and res["detail"].startswith("placed after input 1")
    assert live_row(dev)[0][:2] == ["Input 1", "Wah 1"]


def test_anchor_not_on_the_grid_writes_nothing():
    dev = template_sim()
    before = [(c.row, c.col, c.effect_id) for c in dev.read_grid()]
    res = server.run_action(dev, add("wah", 1, "after", "chorus 1"))
    assert res["ok"] is False and "is not on the grid" in res["detail"] and "nothing written" in res["detail"]
    assert [(c.row, c.col, c.effect_id) for c in dev.read_grid()] == before


def test_anchor_validation_and_old_positions_unchanged():
    assert server.validate_action(add("wah", 1, "after", None))[0] == ["add_block after needs a ref block to sit next to"]
    assert server.validate_action(add("wah", 1, "after", "nothing"))[0][0].startswith("add_block anchor:")
    assert server.validate_action(add("wah", 1, "sideways"))[0][0].startswith("position must be")
    dev = template_sim()                       # 'pre' still splices just before the amp
    server.run_action(dev, add("wah", 1, "pre"))
    assert live_row(dev)[0][:4] == ["Input 1", "Drive 1", "Wah 1", "Amp 1"]


# -- REQ-002: a rig build anchors its additions -----------------------------------------

def test_rig_build_lands_in_the_rigs_order_and_compares_clean(monkeypatch):
    dev = template_sim()
    monkeypatch.setattr(server, "_fm9", dev)
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": [
        {"kind": "add_block", "block": "drive", "instance": 2, "position": "pre"},
        {"kind": "set_param", "block": "drive", "instance": 2, "param": "FUZZ_DRIVE", "value": 5},
        {"kind": "add_block", "block": "wah", "instance": 1, "position": "pre"},
        {"kind": "add_block", "block": "chorus", "instance": 1, "position": "pre"}]})
    c = TestClient(server.app)
    d = c.post("/api/describe/build", json={"spec": SPEC}).json()
    kinds = [(a["kind"], a.get("block"), a.get("instance"), a.get("position"), a.get("ref")) for a in d["actions"]]
    assert kinds[:3] == [("add_block", "wah", 1, "before", "drive 1"),
                         ("add_block", "drive", 2, "after", "drive 1"),
                         ("add_block", "chorus", 1, "after", "drive 2")]
    assert ("set_param", "drive", 2, None, None) in kinds[3:]          # configured after it exists
    acts = [{k: v for k, v in a.items() if k not in ("validation_errors", "validation_warnings")}
            for a in d["actions"]]
    digest = c.post("/api/plan/revise", json={"actions": acts}).json()["plan_digest"]
    out = c.post("/api/apply", json={"actions": acts, "plan_digest": digest}).json()
    assert all(r["ok"] for r in out["results"] if (r.get("action") or {}).get("kind") == "add_block")
    row, alive = live_row(dev)
    assert alive and row[:6] == ["Input 1", "Wah 1", "Drive 1", "Drive 2", "Chorus 1", "Amp 1"]
    cmp_ = c.post("/api/rig/compare", json={"graph": SFOGLI}).json()
    # none of the ADDED blocks is out of order (the template's own delay sits
    # after its cab, which only a reorder moves; not this issue's promise)
    assert not [x for x in cmp_["out_of_order"] if x["what"] in ("wah", "drive", "chorus")]


def test_interleaved_plan_puts_every_addition_first():
    compiled = rc.compile(SFOGLI)
    present = {37, 118, 58, 62, 70, 66, 42}        # the starter template's blocks
    plan = [{"kind": "add_block", "block": "drive", "instance": 2, "position": "pre"},
            {"kind": "set_param", "block": "drive", "instance": 2, "param": "FUZZ_DRIVE", "value": 5},
            {"kind": "add_block", "block": "wah", "instance": 1, "position": "pre"}]
    out = server._anchor_rig_adds(compiled, plan, present)
    assert [(a["kind"], a["block"]) for a in out] == [("add_block", "wah"), ("add_block", "drive"),
                                                      ("set_param", "drive")]


def test_a_block_only_in_scene_two_goes_after_its_scene_two_neighbour():
    two = {"nodes": [n("g", "instrument"), n("sw", "switcher"), n("ts", "drive", "TS"), n("a", "amp", "Amp"),
                     n("ph", "modulation", "Phase 90"), n("c", "cab", "4x12")],
           "edges": [e("g", "sw"), e("sw", "ts", route="A"), e("ts", "a", route="A"), e("a", "c", route="A"),
                     e("sw", "ph", route="B"), e("ph", "a", route="B"), e("a", "c", route="B")]}
    compiled = rc.compile(two)
    order = server._merged_chain(compiled)
    assert order.index(("phaser", 1)) < order.index(("amp", 1))
    out = server._anchor_rig_adds(compiled, [{"kind": "add_block", "block": "phaser", "instance": 1}],
                                  {37, 118, 58, 62, 42})
    assert (out[0]["position"], out[0]["ref"]) in (("after", "drive 1"), ("before", "amp 1"))


# -- REQ-003: the fit rehearsal -----------------------------------------------------------

def preset138():
    raw = json.loads((ROOT / "tests" / "fixtures" / "grid_preset138.json").read_text(encoding="utf-8"))
    cells = [GridCell(c["row"], c["col"], c["effect_id"], bool(c["shunt"]), sum(1 << (r + 1) for r in c["feeds"]))
             for c in raw["cells"]]
    status = [BlockStatus(c["effect_id"], bool(c["bypassed"]), "ABCD".index(c["channel"]), 4)
              for c in raw["cells"] if c["effect_id"]]
    return sim_from_reading(server.reg, cells, status)


def _fit_planner(monkeypatch):
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": [
        {"kind": "add_block", "block": "wah", "instance": 1, "position": "pre"},
        {"kind": "add_block", "block": "drive", "instance": 2, "position": "pre"},
        {"kind": "add_block", "block": "chorus", "instance": 1, "position": "pre"}]})


def test_dry_run_refuses_a_preset_whose_routing_cannot_take_the_rig(monkeypatch):
    dev = preset138()
    monkeypatch.setattr(server, "_fm9", dev)
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    _fit_planner(monkeypatch)
    before = [(c.row, c.col, c.effect_id, c.cable_in_mask) for c in dev.read_grid()]
    r = TestClient(server.app).post("/api/describe/build", json={"spec": SPEC})
    assert r.status_code == 409, r.text
    d = r.json()
    assert "actions" not in d and d["fit_failures"]
    assert any("fed from another row" in f["detail"] for f in d["fit_failures"])
    assert d["error"].endswith("Load a preset whose signal runs on one row, then build again.")
    assert [(c.row, c.col, c.effect_id, c.cable_in_mask) for c in dev.read_grid()] == before   # nothing written


def test_dry_run_refusal_on_the_stream_ends_with_the_same_refusal(monkeypatch):
    dev = preset138()
    monkeypatch.setattr(server, "_fm9", dev)
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    _fit_planner(monkeypatch)
    before = [(c.row, c.col, c.effect_id) for c in dev.read_grid()]
    body = TestClient(server.app).post("/api/describe/build/stream", json={"spec": SPEC}).text
    plan = json.loads(body.split("event: plan\ndata: ")[1].split("\n\n")[0])
    assert plan["fit_failures"] and plan["error"].startswith("This preset's routing cannot take that rig:")
    assert "actions" not in plan
    assert [(c.row, c.col, c.effect_id) for c in dev.read_grid()] == before


def test_dry_run_passes_a_plan_that_fits(monkeypatch):
    dev = template_sim()
    monkeypatch.setattr(server, "_fm9", dev)
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    _fit_planner(monkeypatch)
    before = [(c.row, c.col, c.effect_id) for c in dev.read_grid()]
    r = TestClient(server.app).post("/api/describe/build", json={"spec": SPEC})
    assert r.status_code == 200 and "fit_failures" not in r.json()
    assert [(c.row, c.col, c.effect_id) for c in dev.read_grid()] == before      # the rehearsal used a copy


def test_page_shows_a_fit_refusal_with_no_review():
    # the build stream's terminal plan carrying an error is thrown before showPlan
    start = PAGE.index("else if (ev === 'plan') { plan = d; break; }")
    tail = PAGE[start:start + 400]
    assert "if (plan.error) throw new Error(plan.error);" in tail
    assert tail.index("throw new Error(plan.error)") < tail.index("showPlan(plan)")


def test_the_rehearsal_twin_lands_exactly_what_the_slow_device_path_lands():
    """The twin skips the unit's settle waits and the simulator's emulated
    settle window together; its result must equal the full-timing path."""
    key = lambda d: sorted((c.row, c.col, c.effect_id, c.is_shunt, c.cable_in_mask) for c in d.read_grid())
    slow = slow_template_sim()
    cells, status = slow.read_grid(), slow.status_dump()
    twin = sim_from_reading(server.reg, cells, status)
    assert twin.settle_scale == 0 and twin.sim_core.settle_window == 0.0
    acts = [add("wah", 1, "before", "drive 1"), add("drive", 2, "after", "drive 1"), add("chorus", 1, "after", "drive 2")]
    assert [server.run_action(twin, a)["ok"] for a in acts] == [server.run_action(slow, a)["ok"] for a in acts]
    assert key(twin) == key(slow)


def test_a_real_device_handle_keeps_its_settle_waits():
    from fm9 import device
    assert device.FM9.settle_scale == 1.0
    class StandIn:                      # a duck-typed device without the attribute waits in full
        pass
    waited = []
    import time
    real = time.sleep
    time.sleep = waited.append
    try:
        device._settle(StandIn(), 0.3)
    finally:
        time.sleep = real
    assert waited == [0.3]
    assert SimFM9(server.reg).settle_scale == 1.0 and SimFM9(server.reg).sim_core.__dict__.get("settle_window") is None


def test_a_reorder_relative_to_itself_is_invalid_not_a_fit_failure():
    a = server.Action(kind="reorder", block="drive", instance=1, ref="drive", position="before")
    assert server.validate_action(a)[0] == ["reorder moves drive 1 relative to itself (ref 'drive' is the same block)"]
    # the rehearsal leaves invalid actions to validation: they are shown in review, never sent
    assert server._rehearse_fit([{"kind": "reorder", "block": "drive", "instance": 1, "ref": "drive",
                                  "position": "before", "validation_errors": ["self"]}],
                                template_sim().read_grid(), template_sim().status_dump()) == []

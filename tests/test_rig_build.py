"""#228: building from a rig view. The brief comes from the compiled chain, a
faithful build that cannot be faithful is refused before any model runs, and
the result carries a fidelity report grounded in the plan's own actions."""
import json
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import describe, planner, rigcompile as rc
from fm9.sim import SimFM9

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


def n(i, role="other", label=None):
    return {"id": i, "role": role, "label": label or i, "provenance": "observed"}


def e(f, t, kind="audio", **kw):
    return {"from": f, "to": t, "kind": kind, "provenance": "observed", **kw}


RIG = {"schema_version": 1,
       "nodes": [n("gtr", "instrument", "Guitar"), n("ts", "drive", "TS808"), n("klon", "drive", "Klon"),
                 n("amp", "amp", "JCM800"), n("cab", "cab", "V30 4x12")],
       "edges": [e("gtr", "ts"), e("ts", "klon"), e("klon", "amp"), e("amp", "cab")], "unknowns": []}
PARALLEL = {"schema_version": 1,
            "nodes": [n("gtr", "instrument"), n("jcm", "amp", "JCM800"), n("twin", "amp", "Twin"),
                      n("aby", "other", "ABY"), n("cab", "cab", "V30")],
            "edges": [e("gtr", "jcm"), e("gtr", "twin"), e("jcm", "aby"), e("twin", "aby"), e("aby", "cab")],
            "unknowns": []}
SPEC = {"found": True, "summary": "TS808 and Klon into a JCM800", "scenes": [{"n": 1, "name": "Rhythm", "describes": "crunch"}],
        "stated": ["amp gain 7"], "vague": ["tight low end"], "quotes": [], "rig": RIG}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    return TestClient(server.app)


# -- REQ-002: brief, modes, blocker, store ---------------------------------------------

def test_brief_names_each_piece_with_its_block_and_instance():
    c = rc.compile(RIG)
    brief = describe.brief_from_rig(SPEC, c, name="Board")
    assert brief.startswith("Build this rig as a SINGLE scene, scene 1")
    assert ("Scene 1: the TS808 as drive 1, then the Klon as drive 2, then the JCM800 as amp 1, "
            "then the V30 4x12 as cab 1, in that order.") in brief
    assert "Use these settings exactly where they are given: amp gain 7." in brief
    assert brief.endswith("Do not store to any preset slot.")
    assert "\n- " not in brief and "\n* " not in brief           # prose, never a list


def test_brief_without_a_rig_is_exactly_todays():
    flat = {k: v for k, v in SPEC.items() if k != "rig"}
    seen = []
    def fake_plan(prompt, *a, **k):
        seen.append(prompt)
        return {"summary": "s", "actions": []}
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(planner, "plan", fake_plan)
    try:
        TestClient(server.app).post("/api/describe/build", json={"spec": flat, "scenes": 1, "name": "N"})
    finally:
        mp.undo()
    assert seen == [describe.brief_from(flat, scenes=1, name="N")]           # byte for byte


def _capture_plan(monkeypatch, actions):
    seen = []
    def fake_plan(prompt, *a, **k):
        seen.append(prompt)
        return {"summary": "s", "actions": json.loads(json.dumps(actions))}
    monkeypatch.setattr(planner, "plan", fake_plan)
    return seen


def test_mode_defaults_to_closest_and_the_rig_brief_is_used(client, monkeypatch):
    seen = _capture_plan(monkeypatch, [])
    r = client.post("/api/describe/build", json={"spec": SPEC})
    assert r.status_code == 200, r.text
    assert "the TS808 as drive 1" in seen[0]


def test_blocker_refuses_a_faithful_parallel_build_before_any_planner_call(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the planner was asked")
    monkeypatch.setattr(planner, "plan", boom)
    r = client.post("/api/describe/build", json={"spec": {**SPEC, "rig": PARALLEL}, "mode": "faithful"})
    assert r.status_code == 409
    d = r.json()
    assert d["error"].startswith("That rig cannot be built faithfully on the FM9 yet:") and "#16" in d["error"]
    assert d["blockers"]


def test_store_is_still_dropped_from_a_rig_build(client, monkeypatch):
    _capture_plan(monkeypatch, [{"kind": "store", "block": "PRESET", "instance": 1, "value": 5}])
    d = client.post("/api/describe/build", json={"spec": SPEC}).json()
    assert d["dropped"] == ["store"] and not any(a["kind"] == "store" for a in d["actions"])


# -- REQ-003: fidelity -----------------------------------------------------------------

def act(kind, block=None, instance=1, **kw):
    return {"kind": kind, "block": block, "instance": instance, "validation_errors": [], **kw}


def test_fidelity_two_drives_each_get_their_own_model():
    c = rc.compile(RIG)
    actions = [act("set_type", "drive", 1, type_name="T808 OD"), act("set_type", "drive", 2, type_name="Klone Chiron"),
               act("set_type", "amp", 1, type_name="Brit 800 2204 High"), act("set_cab", "cab", 1, cab_name="4x12 V30")]
    f = rc.fidelity(c, RIG, actions, [])
    models = {k["what"]: k["model"] for k in f["kept"]}
    assert models == {"TS808": "T808 OD", "Klon": "Klone Chiron", "JCM800": "Brit 800 2204 High",
                      "V30 4x12": "4x12 V30"}
    assert [k["actions"] for k in f["kept"]] == [[0], [1], [2], [3]]


def test_fidelity_an_invalid_or_missing_action_names_no_model():
    c = rc.compile(RIG)
    bad = act("set_type", "drive", 1, type_name="Imaginary")
    bad["validation_errors"] = ["unknown model name"]
    f = rc.fidelity(c, RIG, [bad], [])
    assert all(k["model"] is None and k["actions"] == [] for k in f["kept"])
    assert f["chosen"]["count"] == 0                                 # an invalid action is not a choice made


def test_fidelity_chosen_by_us_needs_name_and_number_together():
    c = rc.compile(RIG)
    actions = [act("set_param", "amp", 1, param="GAIN", value=7),       # stated: 'amp gain 7'
               act("set_param", "amp", 1, param="BASS", value=7),       # same number, other param
               act("set_param", "amp", 1, param="GAIN", value=6),       # same param, other number
               act("set_tempo", value=120), act("set_type", "amp", 1, type_name="Plexi")]
    f = rc.fidelity(c, RIG, actions, ["amp gain 7"])
    assert f["chosen"]["count"] == 4 and f["chosen"]["stated_used"] == 1
    assert f["chosen"]["actions"] == [1, 2, 3, 4]


def test_fidelity_rides_on_the_build_result(client, monkeypatch):
    _capture_plan(monkeypatch, [{"kind": "set_type", "block": "drive", "instance": 1, "type_name": "T808 OD"}])
    d = client.post("/api/describe/build", json={"spec": SPEC}).json()
    f = d["fidelity"]
    assert f["kept"][0]["what"] == "TS808" and f["kept"][0]["effect_id"] is not None
    assert set(f) == {"kept", "changed", "not_reproduced", "chosen"}
    assert "score" not in json.dumps(f).lower()


# -- REQ-004: the page ---------------------------------------------------------------------

def test_page_offers_modes_and_shows_the_report_and_read_back():
    assert "${spec.rig ? `<div class=\"q\">\n      <label>How faithful?</label>" in PAGE
    assert "['closest', 'Closest tone'," in PAGE and "['faithful', 'Faithful routing'," in PAGE
    assert "['simplified', 'Simplified live rig'," in PAGE
    assert "name: srcAnswers.name, mode: srcAnswers.mode || 'closest'})});" in PAGE
    assert "+ fidelityHtml(plan.fidelity);" in PAGE
    assert "const fidLine = currentPlan.fidelity ? fidelityReadBack(currentPlan.fidelity, acted) : '';" in PAGE
    # said in the transcript too: the plan pane is hidden at the send stage
    assert "if (fidLine) chatNote(fidLine);" in PAGE
    assert "const word = ok === mine.length ? 'verified' : (ok ? 'partly verified' : 'not verified');" in PAGE
    # matched on block names and instance: send results carry no effect id
    assert "return names.includes(String(a.block || '').trim().toLowerCase())" in PAGE


def test_fidelity_names_the_cab_from_the_plans_set_cab(client, monkeypatch):
    _capture_plan(monkeypatch, [{"kind": "set_cab", "block": "cab", "instance": 1, "bank": 3, "value": 61}])
    d = client.post("/api/describe/build", json={"spec": SPEC}).json()
    cab = next(k for k in d["fidelity"]["kept"] if k["block"] == "cab")
    assert cab["model"] and cab["model"] == server.cab_label(3, 61)
    assert d["actions"][-1]["cab_name"] == cab["model"]


def test_no_route_is_defined_after_the_main_guard():
    """`python server.py` blocks in main(); a route below the guard was never
    registered (/api/plan/revise answered 404 from a server started that way)."""
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    tail = src[src.index('if __name__ == "__main__":'):]
    assert "@app." not in tail
    assert src.rstrip().endswith("main()")


def test_fidelity_kept_items_carry_every_name_their_block_answers_to():
    c = rc.compile(RIG)
    f = rc.fidelity(c, RIG, [], [])
    amp = next(k for k in f["kept"] if k["block"] == "amp")
    assert {"amp", "amplifier", "distort"} <= set(amp["names"])
    drive = next(k for k in f["kept"] if k["block"] == "drive")
    assert "drive" in drive["names"] and drive["instance"] == 1

"""#229: is the loaded preset the same as this rig? A rig compiled to a scene
is compared with the loaded scene's grid, read-only, and the differences
come back in words; closing them is the ordinary build."""
import sys

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import rigcompile as rc
from fm9.sim import SimFM9
from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(encoding="utf-8")


def n(i, role="other", label=None):
    return {"id": i, "role": role, "label": label or i, "provenance": "observed"}


def e(f, t, kind="audio", **kw):
    return {"from": f, "to": t, "kind": kind, "provenance": "observed", **kw}


RIG = {"nodes": [n("gtr", "instrument", "Guitar"), n("ts", "drive", "TS808"), n("klon", "drive", "Klon"),
                 n("amp", "amp", "JCM800"), n("cab", "cab", "V30"), n("dly", "delay", "Carbon Copy")],
       "edges": [e("gtr", "ts"), e("ts", "klon"), e("klon", "amp"), e("amp", "cab"), e("cab", "dly")]}

FRIENDLY = {"FUZZ": "Drive", "DISTORT": "Amp", "CABINET": "Cab", "DELAY": "Delay", "REVERB": "Reverb",
            "INPUT": "Input", "OUTPUT": "Output", "COMP": "Compressor", "CHORUS": "Chorus"}


def cell(row, col, family=None, inst=1, feeds=None, live=True, bypassed=False):
    shunt = family is None
    return {"row": row, "col": col, "shunt": shunt, "effect_id": None if shunt else 100 + 10 * row + col,
            "family": family, "instance": None if shunt else inst,
            "label": None if shunt else f"{FRIENDLY[family]} {inst}",
            "bypassed": None if shunt else bypassed, "feeds": [row] if feeds is None else feeds, "live": live}


def serial(*fams, row=0):
    """Input, the families in order on one row, Output."""
    cells = [cell(row, 0, "INPUT", feeds=[])]
    counts = {}
    for i, f in enumerate(fams, start=1):
        counts[f] = counts.get(f, 0) + 1
        cells.append(cell(row, i, f, counts[f]))
    cells.append(cell(row, len(fams) + 1, "OUTPUT"))
    return {"cells": cells, "alive": True, "why": "alive"}


def diff(grid, rig=RIG):
    return rc.compare(rc.compile(rig), grid)


def closed_set(d, grid, rig=RIG):
    chain = rc.compile(rig)["scenes"][0]["chain"]
    assert len(d["matches"]) + len(d["missing"]) == len(chain)
    live = [c for c in grid["cells"] if c["live"] and c["family"] and c["family"] not in ("INPUT", "OUTPUT")]
    assert len(d["matches"]) + len(d["extra"]) == len(live)
    for k in ("missing", "extra", "out_of_order", "routing"):
        assert all(x["why"] for x in d[k])


# -- REQ-001: compare --------------------------------------------------------------

def test_compare_a_preset_that_matches_says_so():
    g = serial("FUZZ", "FUZZ", "DISTORT", "CABINET", "DELAY")
    d = diff(g)
    closed_set(d, g)
    assert d["summary"] == "The loaded scene already matches this rig."
    assert [(m["rig"], m["live"]) for m in d["matches"]] == [
        ("TS808", "Drive 1"), ("Klon", "Drive 2"), ("JCM800", "Amp 1"), ("V30", "Cab 1"), ("Carbon Copy", "Delay 1")]


def test_compare_missing_and_extra():
    g = serial("FUZZ", "DISTORT", "CABINET", "REVERB")
    d = diff(g)
    closed_set(d, g)
    assert [x["what"] for x in d["missing"]] == ["Klon", "Carbon Copy"]      # the second drive, the delay
    assert [x["what"] for x in d["extra"]] == ["Reverb 1"]
    assert d["summary"] == "3 differences between this rig and the loaded scene."


def test_compare_matches_two_drives_by_order_not_instance_number():
    g = serial("FUZZ", "DISTORT", "CABINET", "DELAY")
    g["cells"][1]["instance"], g["cells"][1]["label"] = 2, "Drive 2"         # the only drive is Drive 2
    d = diff(g)
    assert d["matches"][0] == {"rig": "TS808", "block": "drive", "live": "Drive 2"}
    assert [x["what"] for x in d["missing"]] == ["Klon"]


def test_compare_out_of_order_names_the_fewest_moves():
    g = serial("DELAY", "FUZZ", "FUZZ", "DISTORT", "CABINET")                # the delay moved to the front
    d = diff(g)
    closed_set(d, g)
    assert [x["what"] for x in d["out_of_order"]] == ["Carbon Copy"]
    assert d["out_of_order"][0]["why"] == ("the Carbon Copy is Delay 1, which comes first on the preset; "
                                           "the rig has it after the V30")
    assert d["missing"] == [] and d["extra"] == []


def test_compare_a_serial_path_that_changes_rows_is_not_a_difference():
    g = serial("FUZZ", "FUZZ", "DISTORT")
    g["cells"] += [cell(1, 4, "CABINET", feeds=[0]), cell(1, 5, "DELAY", feeds=[1]),
                   cell(1, 6, "OUTPUT", feeds=[1])]
    g["cells"] = [c for c in g["cells"] if not (c["row"] == 0 and c["col"] == 4)]      # row 0 ends at the amp
    d = diff(g)
    closed_set(d, g)
    assert d["routing"] == [] and d["summary"] == "The loaded scene already matches this rig."


def test_compare_a_true_fork_and_merge_are_routing_differences():
    # Drive 2 (column 3) feeds the amp AND a chorus on the row below; both
    # come back together at the cab (column 5)
    g = {"alive": True, "why": "alive", "cells": [
        cell(0, 0, "INPUT", feeds=[]), cell(0, 1, "FUZZ", 1), cell(0, 2, "FUZZ", 2),
        cell(0, 3, "DISTORT"), cell(1, 3, "CHORUS", feeds=[0]),
        cell(0, 4, "CABINET", feeds=[0, 1]), cell(0, 5, "DELAY"), cell(0, 6, "OUTPUT")]}
    d = diff(g)
    closed_set(d, g)
    whys = [x["why"] for x in d["routing"]]
    assert whys == ["the loaded scene's signal splits into 2 paths after column 3; the rig is one path",
                    "2 paths join at column 5 of the loaded scene; the rig is one path"]
    assert [x["what"] for x in d["extra"]] == ["Chorus 1"]


def test_compare_bypassed_and_dead_path():
    g = serial("FUZZ", "FUZZ", "DISTORT", "CABINET", "DELAY")
    g["cells"][1]["bypassed"] = True
    g["alive"], g["why"] = False, "the Output block has no input cable"
    whys = [x["why"] for x in diff(g)["routing"]]
    assert "Drive 1 (the TS808) is bypassed in this scene" in whys
    assert "no signal reaches the output: the Output block has no input cable" in whys


def test_compare_a_bypassed_extra_is_listed_but_not_a_difference():
    g = serial("FUZZ", "FUZZ", "DISTORT", "CABINET", "DELAY", "COMP")
    g["cells"][-2]["bypassed"] = True                     # the compressor, before Output
    d = diff(g)
    closed_set(d, g)
    assert d["extra"] == [{"what": "Compressor 1", "bypassed": True,
                           "why": "Compressor 1 is on the loaded scene's path but bypassed, so it does not change the sound"}]
    assert d["summary"] == "The loaded scene already matches this rig."
    g["cells"][-2]["bypassed"] = False
    assert diff(g)["summary"] == "1 difference between this rig and the loaded scene."


def test_compare_ignores_blocks_off_the_live_path():
    g = serial("FUZZ", "FUZZ", "DISTORT", "CABINET", "DELAY")
    g["cells"].append(cell(3, 4, "REVERB", feeds=[], live=False))
    d = diff(g)
    assert d["extra"] == [] and d["summary"] == "The loaded scene already matches this rig."


# -- REQ-002: the route ------------------------------------------------------------

class Spy:
    """The simulator, recording every method the route calls on it."""
    def __init__(self, dev):
        self._dev, self.calls = dev, []

    def __getattr__(self, name):
        attr = getattr(self._dev, name)
        if callable(attr):
            def call(*a, **k):
                self.calls.append(name)
                return attr(*a, **k)
            return call
        return attr


@pytest.fixture
def spy(monkeypatch):
    s = Spy(SimFM9(server.reg))
    monkeypatch.setattr(server, "_fm9", s)
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    return s


def test_route_makes_exactly_three_reads_and_no_write(spy):
    before = spy._dev.read_grid(), [(b.effect_id, b.bypassed, b.channel) for b in spy._dev.status_dump()]
    r = TestClient(server.app).post("/api/rig/compare", json={"graph": RIG})
    assert r.status_code == 200, r.text
    assert spy.calls == ["scene_name", "read_grid", "status_dump"]
    after = spy._dev.read_grid(), [(b.effect_id, b.bypassed, b.channel) for b in spy._dev.status_dump()]
    assert repr(before) == repr(after)
    d = r.json()
    assert set(d) >= {"scene", "matches", "missing", "extra", "out_of_order", "routing", "summary", "note"}
    assert d["note"] == f"Compared with scene {d['loaded_scene']}, the scene loaded now."


def test_route_compares_the_first_scene_when_the_rig_lacks_the_loaded_one(spy):
    spy._dev.set_scene(3)
    spy.calls.clear()
    d = TestClient(server.app).post("/api/rig/compare", json={"graph": RIG}).json()
    assert d["scene"] == 1 and d["loaded_scene"] == 3
    assert d["note"] == "The loaded scene is 3; the rig has no scene 3, so its first scene is compared."


def test_route_refuses_a_device_without_a_grid(monkeypatch):
    from devices.ir2.adapter import IR2Adapter
    from devices.ir2.sim import SimIR2
    monkeypatch.setattr(server, "_context", server.DeviceContext(
        "ir2", server.FM9_REGISTRY, IR2Adapter(client=SimIR2()), "BOSS IR-2"))
    r = TestClient(server.app).post("/api/rig/compare", json={"graph": RIG})
    assert r.status_code == 409 and r.json()["error"] == "The BOSS IR-2 has no routing grid to compare a rig with."


def test_route_refuses_a_bad_graph_in_words(spy):
    r = TestClient(server.app).post("/api/rig/compare", json={"graph": RIG, "mode": "loud"})
    assert r.status_code == 400 and r.json()["error"].startswith("that rig cannot be compared: mode 'loud'")
    assert spy.calls == []                                      # refused before any read


# -- REQ-003: the page ---------------------------------------------------------------

def test_page_offers_compare_and_build_to_match():
    assert "${devNamed() ? '' : `<div class=\"rigcmp\"><button id=\"rigcmpgo\">COMPARE WITH THE LOADED PRESET</button></div>" in PAGE
    assert "const r = await fetch('/api/rig/compare', {method: 'POST'," in PAGE
    assert "+ list('Missing', d.missing) + list('Extra', d.extra)" in PAGE
    assert "+ (d.extra || []).filter(x => !x.bypassed).length;" in PAGE
    assert "+ list('Out of order', d.out_of_order) + list('Routing', d.routing)" in PAGE
    assert "(n ? `<button class=\"go\" id=\"rigmatch\">BUILD A PLAN TO MATCH</button>" in PAGE
    # build-to-match is the ordinary build: plan, review, confirm, send
    start = PAGE.index("if ($('rigmatch')) $('rigmatch').onclick = () => {")
    assert "runBuild(spec, note);" in PAGE[start:start + 300]
    assert "fetch('/api/apply" not in PAGE[PAGE.index("function rigCompareHtml(d)"):PAGE.index("const go = $('rigfixgo');")]


# -- #240: a scene where no signal reaches the output ---------------------------------

def _dead(g, why="INPUT bypassed or missing"):
    g = {**g, "alive": False, "why": why}
    g["cells"] = [dict(c, live=False) for c in g["cells"]]
    return g


def test_compare_on_a_dead_scene_matches_the_cabled_gear_and_leads_with_the_dead_path():
    g = serial("FUZZ", "FUZZ", "DISTORT", "CABINET", "DELAY")
    g["cells"][0]["bypassed"] = True                       # Input 1 bypassed
    d = diff(_dead(g))
    assert d["missing"] == [] and d["extra"] == []
    assert [m["live"] for m in d["matches"]] == ["Drive 1", "Drive 2", "Amp 1", "Cab 1", "Delay 1"]
    assert d["routing"][0] == {"what": "path", "why": "no signal reaches the output: INPUT bypassed or missing"}
    assert d["summary"] == "1 difference between this rig and the loaded scene."


def test_compare_on_a_dead_scene_ignores_a_block_cabled_to_nothing():
    g = serial("FUZZ", "FUZZ", "DISTORT", "CABINET", "DELAY")
    g["cells"].append(cell(3, 4, "REVERB", feeds=[]))      # an orphan, no cable in
    d = diff(_dead(g))
    assert d["extra"] == []


def test_compare_on_a_dead_scene_still_reports_what_is_missing():
    g = serial("DISTORT", "CABINET")
    d = diff(_dead(g, "Output cable severed"))
    assert [x["what"] for x in d["missing"]] == ["TS808", "Klon", "Carbon Copy"]
    assert d["routing"][0]["why"] == "no signal reaches the output: Output cable severed"

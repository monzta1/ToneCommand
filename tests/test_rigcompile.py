"""#228: a rig graph compiled to FM9 scenes. Every node and every edge id gets
exactly one state with a reason; routes become scenes; parallel paths are
disclosed or, in faithful mode, a blocker."""
import pytest

from fm9 import rigcompile as rc, riggraph as rg


def n(i, role="other", label=None):
    return {"id": i, "role": role, "label": label or i, "provenance": "observed"}


def e(f, t, kind="audio", **kw):
    return {"from": f, "to": t, "kind": kind, "provenance": "observed", **kw}


LINEAR = {"nodes": [n("gtr", "instrument", "Guitar"), n("wah", "wah", "Cry Baby"), n("ts", "drive", "TS808"),
                    n("klon", "drive", "Klon"), n("amp", "amp", "JCM800"), n("cab", "cab", "V30 4x12"),
                    n("dly", "delay", "Carbon Copy")],
          "edges": [e("gtr", "wah"), e("wah", "ts"), e("ts", "klon"), e("klon", "amp"), e("amp", "cab"),
                    e("cab", "dly")]}

PARALLEL = {"nodes": [n("gtr", "instrument"), n("ts", "drive", "TS808"), n("jcm", "amp", "JCM800"),
                      n("twin", "amp", "Twin"), n("aby", "other", "ABY mixer"), n("cab", "cab", "V30"),
                      n("midi", "controller", "MIDI")],
            "edges": [e("gtr", "ts"), e("ts", "jcm"), e("ts", "twin"), e("jcm", "aby"), e("twin", "aby"),
                      e("aby", "cab"), e("midi", "twin", kind="control")]}

SWITCHED = {"nodes": [n("gtr", "instrument"), n("sw", "switcher", "Switcher"), n("trx", "preamp", "Triaxis"),
                      n("mk4", "amp", "Mark IV"), n("pwr", "power_amp", "Simul 2:95"), n("cabL", "cab", "Rect L"),
                      n("cabR", "cab", "Rect R"), n("phs", "modulation", "MXR Phase 90")],
            "edges": [e("gtr", "phs"), e("phs", "sw"), e("sw", "trx", route="A"), e("sw", "mk4", route="B"),
                      e("trx", "pwr", route="A"), e("mk4", "pwr", route="B"),
                      e("pwr", "cabL", kind="audio_stereo", channel="L"),
                      e("pwr", "cabR", kind="audio_stereo", channel="R")]}

# two amps in parallel INSIDE route A, a single amp on route B
PARALLEL_IN_ROUTE = {"nodes": [n("gtr", "instrument"), n("sw", "switcher"), n("a1", "amp", "Plexi"),
                               n("a2", "amp", "AC30"), n("b1", "amp", "Recto"), n("cab", "cab", "4x12")],
                     "edges": [e("gtr", "sw"), e("sw", "a1", route="A"), e("sw", "a2", route="A"),
                               e("a1", "cab", route="A"), e("a2", "cab", route="A"),
                               e("sw", "b1", route="B"), e("b1", "cab", route="B")]}

LOOPY = {"nodes": [n("gtr", "instrument"), n("amp", "amp"), n("fx1", "delay"), n("fx2", "reverb"),
                   n("lonely", "drive", "Spare pedal")],
         "edges": [e("gtr", "amp"), e("fx1", "fx2"), e("fx2", "fx1")]}

ALL = {"linear": LINEAR, "parallel": PARALLEL, "switched": SWITCHED,
       "parallel_in_route": PARALLEL_IN_ROUTE, "loopy": LOOPY}


def chains(c):
    return [[(s["label"], s["block"], s["instance"]) for s in sc["chain"]] for sc in c["scenes"]]


@pytest.mark.parametrize("name", sorted(ALL))
@pytest.mark.parametrize("mode", rc.MODES)
def test_every_node_and_edge_id_gets_exactly_one_state(name, mode):
    g = rg.load(ALL[name])
    c = rc.compile(g, mode)
    assert set(c["status"]["nodes"]) == {x["id"] for x in g["nodes"]}
    assert set(c["status"]["edges"]) == {x["id"] for x in g["edges"]}
    for state, why in list(c["status"]["nodes"].values()) + list(c["status"]["edges"].values()):
        assert state in ("kept", "changed", "not_reproduced") and why


def test_roles_become_blocks_with_instances_in_order():
    c = rc.compile(LINEAR)
    assert chains(c) == [[("Cry Baby", "wah", 1), ("TS808", "drive", 1), ("Klon", "drive", 2),
                          ("JCM800", "amp", 1), ("V30 4x12", "cab", 1), ("Carbon Copy", "delay", 1)]]
    assert c["status"]["nodes"]["gtr"][0] == "kept" and c["blockers"] == []


def test_modulation_picks_its_block_from_the_label_and_power_amp_joins_the_amp():
    c = rc.compile(SWITCHED)
    assert chains(c)[0][0] == ("MXR Phase 90", "phaser", 1)
    assert c["status"]["nodes"]["pwr"] == ["changed", "part of the Triaxis amp block's power section"]


def test_routes_become_scenes_and_stereo_becomes_mono():
    c = rc.compile(SWITCHED)
    assert [(s["n"], s["name"]) for s in c["scenes"]] == [(1, "A"), (2, "B")]
    assert chains(c)[1][1] == ("Mark IV", "amp", 1)
    st = rg.load(SWITCHED)
    ids = {(x["from"], x["to"]): x["id"] for x in st["edges"]}
    assert c["status"]["edges"][ids[("pwr", "cabL")]][0] == "changed"
    assert c["status"]["edges"][ids[("pwr", "cabR")]] == ["changed", "the second side of a stereo pair; built as one mono path (#16)"]


def test_scene_count_caps_routes_and_says_so():
    c = rc.compile(SWITCHED, scenes=1)
    assert [s["name"] for s in c["scenes"]] == ["A"]
    assert c["status"]["nodes"]["mk4"] == ["not_reproduced", "more routes than scenes asked for (1)"]


def test_parallel_amps_closest_keeps_the_first_and_discloses_the_other():
    c = rc.compile(PARALLEL, "closest")
    assert chains(c) == [[("TS808", "drive", 1), ("JCM800", "amp", 1), ("V30", "cab", 1)]]
    assert c["status"]["nodes"]["twin"][0] == "not_reproduced" and "#16" in c["status"]["nodes"]["twin"][1]
    assert c["status"]["nodes"]["midi"][0] == "changed" and c["blockers"] == []


def test_parallel_amps_faithful_is_a_blocker_naming_16():
    c = rc.compile(PARALLEL, "faithful")
    assert len(c["blockers"]) == 1 and "#16" in c["blockers"][0] and "Twin" in c["blockers"][0]


def test_parallel_inside_one_route_is_still_parallel():
    c = rc.compile(PARALLEL_IN_ROUTE, "faithful")
    assert len(c["blockers"]) == 1 and c["blockers"][0].startswith("Route A runs two signal paths")
    c = rc.compile(PARALLEL_IN_ROUTE, "closest")
    assert [s["name"] for s in c["scenes"]] == ["A", "B"] and chains(c)[0][0] == ("Plexi", "amp", 1)
    assert c["status"]["nodes"]["a2"][0] == "not_reproduced"


def test_simplified_is_one_scene_and_one_block_per_family():
    c = rc.compile(LINEAR, "simplified")
    assert chains(c) == [[("Cry Baby", "wah", 1), ("TS808", "drive", 1), ("JCM800", "amp", 1),
                          ("V30 4x12", "cab", 1), ("Carbon Copy", "delay", 1)]]
    assert c["status"]["nodes"]["klon"] == ["not_reproduced", "simplified: one drive block kept"]
    c = rc.compile(SWITCHED, "simplified")
    assert [s["name"] for s in c["scenes"]] == ["A"]
    assert c["status"]["nodes"]["mk4"] == ["not_reproduced", "simplified: only the first route is built"]


def test_loops_and_disconnected_gear_are_listed_not_dropped():
    c = rc.compile(LOOPY)
    st = rg.load(LOOPY)
    ids = {(x["from"], x["to"]): x["id"] for x in st["edges"]}
    assert c["status"]["edges"][ids[("fx1", "fx2")]][0] == "not_reproduced"
    assert c["status"]["nodes"]["lonely"] == ["not_reproduced", "not connected to the signal path"]


def test_an_unknown_mode_is_refused_in_words():
    with pytest.raises(rg.RigGraphError, match="mode 'loud'"):
        rc.compile(LINEAR, "loud")


def test_summary_lists_kept_gear_and_reasons():
    c = rc.compile(PARALLEL)
    s = rc.summary(c, PARALLEL)
    assert [k["what"] for k in s["kept"]] == ["TS808", "JCM800", "V30"]
    assert {"what": "Twin", "why": "runs in parallel with the kept path; one serial path is built (#16)"} in s["not_reproduced"]

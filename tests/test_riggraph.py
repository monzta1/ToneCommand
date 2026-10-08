"""#225: the rig graph. Typed edges, honest provenance, routes that never
combine, cycles reported rather than looped, edits all or nothing."""
import pytest

from fm9 import riggraph as rg


def n(i, role="other", prov="observed", label=None):
    return {"id": i, "role": role, "label": label or i, "provenance": prov}


def e(f, t, kind="audio_mono", prov="observed", **kw):
    return {"from": f, "to": t, "kind": kind, "provenance": prov, **kw}


LINEAR = {"schema_version": 1,
          "nodes": [n("gtr", "instrument", label="Guitar"), n("ts", "drive", label="Tube Screamer"),
                    n("amp", "amp", label="Victory V30"), n("cab", "cab", label="Marshall 4x12")],
          "edges": [e("gtr", "ts"), e("ts", "amp"), e("amp", "cab")],
          "unknowns": ["amp settings"]}


# -- schema, normalize, validate --------------------------------------------------

def test_a_linear_graph_validates_and_gets_edge_ids():
    g = rg.load(LINEAR)
    assert [x["id"] for x in g["edges"]] == ["e1", "e2", "e3"]
    assert rg.validate(g) == []


def test_missing_provenance_is_unresolved_never_observed():
    g = rg.normalize({"nodes": [{"id": "a", "role": "amp"}], "edges": [{"from": "a", "to": "a"}]})
    assert g["nodes"][0]["provenance"] == "unresolved"
    assert g["edges"][0]["provenance"] == "unresolved" and g["edges"][0]["kind"] == "unknown"


def test_another_schema_version_is_refused():
    with pytest.raises(rg.RigGraphError, match="schema_version 2"):
        rg.load({**LINEAR, "schema_version": 2})


@pytest.mark.parametrize("bad, words", [
    ({"edges": [e("gtr", "nowhere")]}, "is not a node"),
    ({"edges": [e("gtr", "ts", kind="laser")]}, "has kind 'laser'"),
    ({"edges": [e("gtr", "ts", channel="L")]}, "not audio_stereo"),
    ({"edges": [e("gtr", "ts", kind="audio_stereo", channel="C")]}, "not L or R"),
    ({"nodes": LINEAR["nodes"] + [n("ts")]}, "used twice"),
    ({"nodes": [n("gtr", role="spaceship"), n("ts")]}, "has role 'spaceship'"),
])
def test_validate_names_each_problem_in_words(bad, words):
    g = rg.normalize({**LINEAR, **bad})
    assert any(words in p for p in rg.validate(g)), rg.validate(g)


# -- audio paths: typed edges, branches, routes, cycles ----------------------------

def test_a_control_edge_is_never_in_an_audio_path():
    g = {**LINEAR, "nodes": LINEAR["nodes"] + [n("ctl", "controller", label="MIDI controller")],
         "edges": LINEAR["edges"] + [e("ctl", "amp", kind="control"), e("ctl", "ts", kind="expression")]}
    paths = rg.audio_paths(g)["paths"]
    assert paths == [{"route": None, "nodes": ["gtr", "ts", "amp", "cab"]}]
    assert all("ctl" not in p["nodes"] for p in paths)


def test_branches_and_merges_are_each_a_path():
    g = {"nodes": [n("gtr"), n("split"), n("dly"), n("rev"), n("mix")],
         "edges": [e("gtr", "split"), e("split", "dly"), e("split", "rev"), e("dly", "mix"), e("rev", "mix")]}
    paths = [p["nodes"] for p in rg.audio_paths(g)["paths"]]
    assert sorted(paths) == [["gtr", "split", "dly", "mix"], ["gtr", "split", "rev", "mix"]]


def test_stereo_channels_keep_their_identity():
    g = rg.load({"nodes": [n("pre"), n("pwr")],
                 "edges": [e("pre", "pwr", kind="audio_stereo", channel="L"),
                           e("pre", "pwr", kind="audio_stereo", channel="R")]})
    assert sorted(x["channel"] for x in g["edges"]) == ["L", "R"]
    assert len({x["id"] for x in g["edges"]}) == 2


def test_switcher_alternatives_that_merge_and_split_again_never_combine():
    """Triaxis or Mark IV through a switcher, merging into one power amp,
    then splitting to two cabs per route: a Triaxis path must never continue
    on the Mark IV's cab edge."""
    g = {"nodes": [n("gtr"), n("sw", "switcher"), n("trx", "preamp"), n("mk4", "amp"),
                   n("pwr", "power_amp"), n("cabA", "cab"), n("cabB", "cab")],
         "edges": [e("gtr", "sw"),
                   e("sw", "trx", route="A"), e("sw", "mk4", route="B"),
                   e("trx", "pwr", route="A"), e("mk4", "pwr", route="B"),
                   e("pwr", "cabA", route="A"), e("pwr", "cabB", route="B")]}
    paths = rg.audio_paths(g)["paths"]
    got = sorted((p["route"], tuple(p["nodes"])) for p in paths)
    assert got == [("A", ("gtr", "sw", "trx", "pwr", "cabA")),
                   ("B", ("gtr", "sw", "mk4", "pwr", "cabB"))]


def test_a_cycle_is_reported_not_looped():
    g = {"nodes": [n("a"), n("b"), n("c")],
         "edges": [e("a", "b"), e("b", "c"), e("c", "b")]}
    out = rg.audio_paths(g)
    assert out["cycles"] == [["b", "c", "b"]]
    assert out["paths"] == [{"route": None, "nodes": ["a", "b", "c"]}]


def test_send_return_is_audio_and_unknown_is_not():
    g = {"nodes": [n("amp"), n("loop"), n("x")],
         "edges": [e("amp", "loop", kind="send_return"), e("loop", "x", kind="unknown")]}
    assert rg.audio_paths(g)["paths"] == [{"route": None, "nodes": ["amp", "loop"]}]


# -- edits: by id, in order, all or nothing ------------------------------------------

def test_one_of_two_parallel_stereo_edges_is_changed_by_id():
    g = rg.load({"nodes": [n("pre"), n("pwr")],
                 "edges": [e("pre", "pwr", kind="audio_stereo", channel="L"),
                           e("pre", "pwr", kind="audio_stereo", channel="R")]})
    new, changed = rg.apply_ops(g, [{"op": "set_edge", "id": "e2", "kind": "audio_mono", "channel": None}])
    assert [x["kind"] for x in new["edges"]] == ["audio_stereo", "audio_mono"]
    assert new["edges"][1]["provenance"] == "user_confirmed" and new["edges"][0]["provenance"] == "observed"
    assert changed == ["pre -> pwr is now audio_mono"]


def test_a_valid_edit_then_an_invalid_one_leaves_the_graph_unchanged():
    g = rg.load(LINEAR)
    before = rg.load(LINEAR)
    with pytest.raises(rg.RigGraphError, match="there is no node 'phaser'"):
        rg.apply_ops(g, [{"op": "set_node", "id": "ts", "label": "Klon"},
                         {"op": "set_node", "id": "phaser", "label": "x"}])
    assert g == before


def test_an_edit_that_leaves_the_graph_invalid_is_refused():
    with pytest.raises(rg.RigGraphError, match="would leave the rig invalid"):
        rg.apply_ops(LINEAR, [{"op": "add_edge", "from": "amp", "to": "cab", "kind": "audio_mono", "channel": "L"}])


def test_edits_mark_what_they_touch_user_confirmed():
    new, changed = rg.apply_ops(LINEAR, [{"op": "set_node", "id": "ts", "label": "Klon", "role": "drive"},
                                         {"op": "add_edge", "from": "gtr", "to": "amp", "kind": "control"}])
    ts = next(x for x in new["nodes"] if x["id"] == "ts")
    assert ts["label"] == "Klon" and ts["provenance"] == "user_confirmed"
    assert new["edges"][-1]["provenance"] == "user_confirmed" and new["edges"][-1]["id"] == "e4"
    assert changed == ["Klon updated", "connected Guitar -> Victory V30 (control)"]


def test_audio_of_unstated_format_is_walked_and_unknown_is_not():
    """The live extract (2026-10-08): switcher cables whose mono or stereo the
    text never said. As 'audio' both routes are walked; 'unknown' is not."""
    g = {"nodes": [n("ocd"), n("sw", "switcher"), n("trx", "preamp"), n("mk4", "amp"),
                   n("pwr", "power_amp"), n("cab", "cab")],
         "edges": [e("ocd", "sw"), e("sw", "trx", kind="audio", route="triaxis"),
                   e("trx", "pwr", kind="audio", route="triaxis"),
                   e("sw", "mk4", kind="audio", route="mark4"),
                   e("mk4", "pwr", kind="audio", route="mark4"), e("pwr", "cab", kind="audio_stereo", channel="L")]}
    got = sorted((p["route"], tuple(p["nodes"])) for p in rg.audio_paths(g)["paths"])
    assert got == [("mark4", ("ocd", "sw", "mk4", "pwr", "cab")),
                   ("triaxis", ("ocd", "sw", "trx", "pwr", "cab"))]
    unknown = {**g, "edges": [{**x, "kind": "unknown"} if x["from"] == "sw" else x for x in g["edges"]]}
    # unknown is not walked: no path runs from the switcher into either amp
    for p in rg.audio_paths(unknown)["paths"]:
        assert not ("sw" in p["nodes"] and ("trx" in p["nodes"] or "mk4" in p["nodes"])), p


# -- review findings ---------------------------------------------------------------------

@pytest.mark.parametrize("bad, words", [
    ({"nodes": 7}, "nodes is not a list"),
    ({"nodes": ["amp"]}, "node 1 is not an object"),
    ({"nodes": [n("a")], "edges": [{"from": [], "to": "a", "kind": "audio"}]}, "edge 1 from is not a node id"),
    ({"nodes": [{"role": "amp"}]}, "node 1 has no text id"),
])
def test_malformed_graphs_are_refused_not_emptied(bad, words):
    with pytest.raises(rg.RigGraphError, match=words):
        rg.load(bad)


def test_a_loop_in_a_part_not_connected_to_the_guitar_is_reported():
    g = {"nodes": [n("gtr"), n("amp"), n("fx1"), n("fx2")],
         "edges": [e("gtr", "amp"), e("fx1", "fx2"), e("fx2", "fx1")]}
    out = rg.audio_paths(g)
    assert out["cycles"] == [["fx1", "fx2", "fx1"]]
    assert {"route": None, "nodes": ["gtr", "amp"]} in out["paths"]
    assert any(l.startswith("Unresolved loop: fx1 -> fx2 -> fx1") for l in rg.explain(g))


def test_a_missing_node_op_cannot_be_hidden_by_a_later_op():
    with pytest.raises(rg.RigGraphError, match="edit 2: there is no node 'ghost'"):
        rg.apply_ops(LINEAR, [{"op": "set_node", "id": "ts", "label": "Klon"},
                              {"op": "add_edge", "from": "amp", "to": "ghost", "kind": "audio"},
                              {"op": "remove_edge", "id": "e4"}])


@pytest.mark.parametrize("op, words", [
    ({"op": "set_edge", "id": "e1", "kind": None}, "None is not a kind"),
    ({"op": "set_edge", "id": "e1", "kind": "laser"}, "'laser' is not a kind"),
    ({"op": "set_node", "id": "ts", "role": "toaster"}, "'toaster' is not a role"),
    ({"op": "set_node", "id": "ts", "label": ""}, "needs a name"),
])
def test_bad_op_fields_are_refused_in_words(op, words):
    with pytest.raises(rg.RigGraphError, match=words):
        rg.apply_ops(LINEAR, [op])

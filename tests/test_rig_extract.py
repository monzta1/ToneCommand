"""#225: the describe extract pass returns a rig graph beside the flat spec,
keeps only a graph that validates, and leaves the build unchanged."""
import json
import sys

sys.argv = ["x"]
import pytest

from fm9 import describe

# A linear pedalboard written out as text: no artist imagery in the repo.
SOURCE = ("My board: guitar into a wah, then a Tube Screamer, into a Victory V30 "
          "head and a Marshall 4x12. A MIDI controller switches the amp channels.")

RIG = {"schema_version": 1,
       "nodes": [{"id": "gtr", "role": "instrument", "label": "guitar", "provenance": "observed"},
                 {"id": "wah", "role": "wah", "label": "wah", "provenance": "observed"},
                 {"id": "ts", "role": "drive", "label": "Tube Screamer", "provenance": "observed"},
                 {"id": "amp", "role": "amp", "label": "Victory V30", "provenance": "observed"},
                 {"id": "cab", "role": "cab", "label": "Marshall 4x12", "provenance": "observed"},
                 {"id": "midi", "role": "controller", "label": "MIDI controller", "provenance": "observed"}],
       "edges": [{"from": "gtr", "to": "wah", "kind": "audio_mono", "provenance": "observed"},
                 {"from": "wah", "to": "ts", "kind": "audio_mono", "provenance": "observed"},
                 {"from": "ts", "to": "amp", "kind": "audio_mono", "provenance": "observed"},
                 {"from": "amp", "to": "cab", "kind": "audio_mono", "provenance": "observed"},
                 {"from": "midi", "to": "amp", "kind": "control", "provenance": "observed"}],
       "unknowns": ["amp settings", "mic"]}

FLAT = {"found": True, "summary": "wah and Tube Screamer into a Victory V30",
        "scenes": [{"n": 1, "name": "Rhythm", "describes": "crunch"}],
        "stated": ["Tube Screamer before the amp"], "vague": ["tight low end"], "quotes": []}


def _reader(answer, seen=None):
    def ask(prompt, cancel=None):
        if seen is not None:
            seen.append(prompt)
        return "here it is: " + json.dumps(answer)
    return ask


def test_the_fixture_extracts_to_the_expected_graph(monkeypatch):
    seen = []
    monkeypatch.setattr(describe, "_ask", _reader({**FLAT, "rig": RIG}, seen))
    spec = describe.extract(SOURCE)
    assert spec["rig"]["schema_version"] == 1
    assert [n["id"] for n in spec["rig"]["nodes"]] == ["gtr", "wah", "ts", "amp", "cab", "midi"]
    assert [e["id"] for e in spec["rig"]["edges"]] == ["e1", "e2", "e3", "e4", "e5"]
    from fm9 import riggraph
    assert riggraph.audio_paths(spec["rig"])["paths"] == [
        {"route": None, "nodes": ["gtr", "wah", "ts", "amp", "cab"]}]
    # the flat fields are exactly what the reader said
    assert {k: spec[k] for k in FLAT} == FLAT
    # the prompt asks for the graph and its honesty rule
    assert '"rig": {' in seen[0] and 'are "observed"; anything you concluded is' in seen[0]
    assert seen[0].endswith(SOURCE)


@pytest.mark.parametrize("bad, words", [
    ({**RIG, "schema_version": 2}, "schema_version 2"),
    ({**RIG, "edges": RIG["edges"] + [{"from": "amp", "to": "ghost", "kind": "audio_mono"}]}, "is not a node"),
    ({**RIG, "edges": [{"from": "gtr", "to": "wah", "kind": "laser"}]}, "has kind 'laser'"),
    ("not a graph", "not an object"),
])
def test_a_bad_graph_is_dropped_with_reasons_and_the_flat_fields_kept(monkeypatch, bad, words):
    monkeypatch.setattr(describe, "_ask", _reader({**FLAT, "rig": bad}))
    spec = describe.extract(SOURCE)
    assert spec["rig"] is None
    assert any(words in p for p in spec["rig_problems"]), spec["rig_problems"]
    assert {k: spec[k] for k in FLAT} == FLAT


def test_no_gear_means_no_graph_and_no_problem(monkeypatch):
    monkeypatch.setattr(describe, "_ask", _reader({**FLAT, "rig": None}))
    spec = describe.extract(SOURCE)
    assert spec["rig"] is None and "rig_problems" not in spec


def test_missing_provenance_from_the_reader_is_unresolved(monkeypatch):
    rig = {**RIG, "nodes": [{**n, "provenance": None} if n["id"] == "ts" else n for n in RIG["nodes"]]}
    monkeypatch.setattr(describe, "_ask", _reader({**FLAT, "rig": rig}))
    ts = next(n for n in describe.extract(SOURCE)["rig"]["nodes"] if n["id"] == "ts")
    assert ts["provenance"] == "unresolved"


def test_the_build_brief_is_identical_with_or_without_the_graph():
    with_rig = {**FLAT, "rig": RIG, "rig_explain": ["x"]}
    for scenes in (None, 1):
        assert describe.brief_from(with_rig, scenes=scenes, name="N") == \
            describe.brief_from(FLAT, scenes=scenes, name="N")

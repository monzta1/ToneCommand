"""#226: a rig explained in plain words, corrected by conversation, shown in
the describe card, and never touching a device."""
import json
import subprocess
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import describe, riggraph as rg

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


def n(i, role="other", label=None, prov="observed"):
    return {"id": i, "role": role, "label": label or i, "provenance": prov}


def e(f, t, kind="audio_mono", prov="observed", **kw):
    return {"from": f, "to": t, "kind": kind, "provenance": prov, **kw}


LINEAR = {"nodes": [n("gtr", "instrument", "Guitar"), n("ts", "drive", "Tube Screamer"),
                    n("amp", "amp", "Victory V30"), n("cab", "cab", "Marshall 4x12")],
          "edges": [e("gtr", "ts"), e("ts", "amp"), e("amp", "cab")], "unknowns": ["amp settings"]}

SWITCHED = {"nodes": [n("gtr", "instrument", "Guitar"), n("sw", "switcher", "Switcher"),
                      n("trx", "preamp", "Triaxis"), n("mk4", "amp", "Mark IV", prov="inferred"),
                      n("pwr", "power_amp", "Simul 2:95"), n("cab", "cab", "Rectifier 4x12"),
                      n("ctl", "controller", "MIDI controller")],
            "edges": [e("gtr", "sw"), e("sw", "trx", route="A"), e("sw", "mk4", route="B"),
                      e("trx", "pwr", kind="audio_stereo", channel="L", route="A"),
                      e("mk4", "pwr", route="B", prov="inferred"), e("pwr", "cab"),
                      e("ctl", "sw", kind="control")],
            "unknowns": ["speaker models"]}


# -- explain -----------------------------------------------------------------------

def test_explain_a_linear_rig_in_order_with_what_is_unknown():
    assert rg.explain(LINEAR) == [
        "Signal: Guitar -> Tube Screamer -> Victory V30 -> Marshall 4x12",
        "Not stated: amp settings"]


def test_explain_routes_control_stereo_and_inferred_items():
    lines = rg.explain(SWITCHED)
    assert "Route A: Guitar -> Switcher -> Triaxis -> Simul 2:95 -> Rectifier 4x12" in lines
    assert "Route B: Guitar -> Switcher -> Mark IV -> Simul 2:95 -> Rectifier 4x12" in lines
    assert "Control: MIDI controller controls Switcher (not in the audio path)" in lines
    assert "Stereo: Triaxis -> Simul 2:95" in lines
    assert "Inferred, not shown in the source: Mark IV; Mark IV -> Simul 2:95" in lines
    assert "Not stated: speaker models" in lines


def test_explain_branches_and_unclear_connections():
    g = {"nodes": [n("a"), n("b"), n("c"), n("d")],
         "edges": [e("a", "b"), e("a", "c"), e("c", "d", kind="unknown")]}
    lines = rg.explain(g)
    assert "Signal: a -> b" in lines and "Signal: a -> c" in lines
    assert "Unclear: c -> d" in lines


# -- correct (fake reader) -------------------------------------------------------------

def _reader(ops):
    return lambda prompt, cancel=None: "sure: " + json.dumps({"ops": ops})


def test_correct_applies_the_edits_and_marks_them_confirmed(monkeypatch):
    monkeypatch.setattr(describe, "_ask", _reader([{"op": "set_node", "id": "ts", "label": "Klon"}]))
    g, changed = describe.correct(LINEAR, "that pedal is a Klon, not a Tube Screamer")
    ts = next(x for x in g["nodes"] if x["id"] == "ts")
    assert ts["label"] == "Klon" and ts["provenance"] == "user_confirmed"
    assert changed == ["Klon updated"]


def test_correct_refuses_a_missing_id_and_leaves_the_graph(monkeypatch):
    monkeypatch.setattr(describe, "_ask", _reader([{"op": "set_edge", "id": "e9", "kind": "control"}]))
    before = json.dumps(LINEAR, sort_keys=True)
    with pytest.raises(rg.RigGraphError, match="there is no connection 'e9'"):
        describe.correct(LINEAR, "the last cable is MIDI")
    assert json.dumps(LINEAR, sort_keys=True) == before


def test_correct_with_nothing_understood_says_so(monkeypatch):
    monkeypatch.setattr(describe, "_ask", _reader([]))
    with pytest.raises(rg.RigGraphError, match="no edits were understood"):
        describe.correct(LINEAR, "make it sound like 1987")
    monkeypatch.setattr(describe, "_ask", lambda p, cancel=None: "I cannot do that")
    with pytest.raises(rg.RigGraphError, match="could not understand that"):
        describe.correct(LINEAR, "?")


# -- the route never touches a device ------------------------------------------------

class Tripwire:
    def __getattr__(self, name):
        raise AssertionError(f"the rig route touched the device: {name}")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", Tripwire())
    monkeypatch.setattr(server, "get_fm9", lambda: Tripwire())
    return TestClient(server.app)


def test_route_corrects_and_explains_without_a_device(client, monkeypatch):
    monkeypatch.setattr(describe, "_ask", _reader([{"op": "add_edge", "from": "gtr", "to": "amp", "kind": "control"}]))
    r = client.post("/api/rig/correct", json={"graph": LINEAR, "text": "the guitar's switch changes amp channel"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["changed"] == ["connected Guitar -> Victory V30 (control)"]
    assert "Control: Guitar controls Victory V30 (not in the audio path)" in d["explain"]


def test_route_refuses_in_words_and_returns_the_graph_unchanged(client, monkeypatch):
    monkeypatch.setattr(describe, "_ask", _reader([{"op": "set_node", "id": "nope", "label": "x"}]))
    r = client.post("/api/rig/correct", json={"graph": LINEAR, "text": "x"})
    assert r.status_code == 400
    assert r.json()["error"] == "edit 1: there is no node 'nope'" and r.json()["graph"] == LINEAR


def test_route_read_results_carry_the_explanation(monkeypatch):
    monkeypatch.setattr(describe, "read_source", lambda raw, on_stage=None: {
        "text": "t", "kind": "text", "url": None, "title": "", "notes": []})
    monkeypatch.setattr(describe, "_ask", lambda p, cancel=None: json.dumps(
        {"found": True, "summary": "s", "scenes": [], "stated": [], "vague": [], "quotes": [],
         "rig": LINEAR}))
    d = TestClient(server.app).post("/api/describe/read", json={"source": "some rig text"}).json()
    assert d["rig_explain"][0] == "Signal: Guitar -> Tube Screamer -> Victory V30 -> Marshall 4x12"


# -- the page ------------------------------------------------------------------------

def test_page_shows_the_rig_card_in_the_build_question():
    assert "$('srcask').innerHTML = `<div id=\"rigcard\">${rigCardHtml(spec)}</div>" in PAGE
    assert "wireRigCard(spec, note);" in PAGE
    assert "const r = await fetch('/api/rig/correct', {method: 'POST'," in PAGE
    assert "Corrections change the rig shown here, and BUILD IT builds the corrected rig." in PAGE


def test_ui_draws_audio_solid_and_control_dashed(tmp_path):
    """Run the page's own rigSvg in node on the switched rig."""
    start = PAGE.index("const RIG_AUDIO = new Set(")
    end = PAGE.index("function rigCardHtml(spec)")
    script = tmp_path / "rig.mjs"
    script.write_text(
        "const esc = s => String(s);\n" + PAGE[start:end]
        + f"\nconsole.log(rigSvg({json.dumps(rg.load(SWITCHED))}));\n", encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    svg = out.stdout
    assert svg.count('class="rgline ctl"') == 1                    # the one control link, dashed
    assert '>Mark IV ?<' in svg and 'rgbox guess' in svg            # inferred, marked
    assert '>A<' in svg and '>B<' in svg and '>control<' in svg     # routes labelled, control row


def test_route_refuses_a_cleared_kind_in_words_not_a_500(client, monkeypatch):
    monkeypatch.setattr(describe, "_ask", _reader([{"op": "set_edge", "id": "e1", "kind": None}]))
    r = client.post("/api/rig/correct", json={"graph": LINEAR, "text": "x"})
    assert r.status_code == 400 and "is not a kind of connection" in r.json()["error"]
    assert r.json()["graph"] == LINEAR


def test_page_keeps_the_build_note_beside_the_status():
    assert '<p class="rignote" id="rigfixsaid" hidden></p>' in PAGE
    # #228 made BUILD IT follow the rig, so the note says so (#229)
    assert ("<p class=\"rignote\">Corrections change the rig shown here, and BUILD IT builds the "
            "corrected rig.</p>") in PAGE
    assert "$('rigfixsaid').textContent = `" not in PAGE        # status goes through rigSaid only


@pytest.mark.parametrize("op", [{"op": "add_edge", "from": [], "to": "amp", "kind": "audio"},
                                {"op": "set_edge", "id": "e1", "route": ["A"]}])
def test_route_refuses_wrong_typed_edits_in_words_not_a_500(client, monkeypatch, op):
    monkeypatch.setattr(describe, "_ask", _reader([op]))
    r = client.post("/api/rig/correct", json={"graph": LINEAR, "text": "x"})
    assert r.status_code == 400 and "is not text" in r.json()["error"]
    assert r.json()["graph"] == LINEAR


def test_extract_drops_a_wrong_typed_route_and_keeps_the_flat_fields(monkeypatch):
    bad = {**LINEAR, "edges": [{**LINEAR["edges"][0], "route": ["A"]}] + LINEAR["edges"][1:]}
    monkeypatch.setattr(describe, "_ask", lambda p, cancel=None: json.dumps(
        {"found": True, "summary": "s", "scenes": [], "stated": ["x"], "vague": [], "quotes": [], "rig": bad}))
    spec = describe.extract("text")
    assert spec["rig"] is None and "route is not text" in spec["rig_problems"][0]
    assert spec["summary"] == "s" and spec["stated"] == ["x"]

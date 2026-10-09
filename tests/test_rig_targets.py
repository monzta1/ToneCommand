"""#230: one rig graph, more than one device. On a device that names its
parameters (the BOSS IR-2) the rig is evaluated from what that device
publishes: the amp becomes its voicing, the reverb its ambience, and the
gear it has no place for is said, never imitated."""
import json
import subprocess
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from devices.ir2 import planning as devplan
from devices.ir2.adapter import IR2Adapter
from devices.ir2.sim import SimIR2
from fm9 import describe, planner, rigcompile as rc, riggraph as rg

PAGE = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(encoding="utf-8")
DEVICE = "BOSS IR-2"


def n(i, role="other", label=None):
    return {"id": i, "role": role, "label": label or i, "provenance": "observed"}


def e(f, t, kind="audio", **kw):
    return {"from": f, "to": t, "kind": kind, "provenance": "observed", **kw}


BOARD = {"schema_version": 1,
         "nodes": [n("gtr", "instrument", "Guitar"), n("ts", "drive", "TS808"), n("amp", "amp", "JCM800"),
                   n("cab", "cab", "V30 4x12"), n("dly", "delay", "Carbon Copy"), n("rev", "reverb", "Hall"),
                   n("exp", "controller", "Expression")],
         "edges": [e("gtr", "ts"), e("ts", "amp"), e("amp", "cab"), e("cab", "dly"), e("dly", "rev"),
                   e("exp", "dly", "expression")], "unknowns": []}
TWO_AMPS = {"nodes": [n("gtr", "instrument"), n("sw", "switcher"), n("a1", "amp", "Plexi"), n("a2", "amp", "Recto"),
                      n("cab", "cab", "4x12")],
            "edges": [e("gtr", "sw"), e("sw", "a1", route="A"), e("sw", "a2", route="B"),
                      e("a1", "cab", route="A"), e("a2", "cab", route="B")]}
STEREO = {"nodes": [n("gtr", "instrument"), n("amp", "amp", "JCM800"), n("cabL", "cab", "L"), n("cabR", "cab", "R")],
          "edges": [e("gtr", "amp"), e("amp", "cabL", "audio_stereo", channel="L"),
                    e("amp", "cabR", "audio_stereo", channel="R")]}
SERIAL_AMPS = {"nodes": [n("gtr", "instrument"), n("pre", "preamp", "Triaxis"), n("a2", "amp", "Mark IV"),
                         n("pwr", "power_amp", "2:90")],
               "edges": [e("gtr", "pre"), e("pre", "a2"), e("a2", "pwr")]}
SPEC = {"found": True, "summary": "TS808 into a JCM800, Carbon Copy and a hall", "scenes": [],
        "stated": ["gain 96"], "vague": ["tight low end"], "quotes": [], "rig": BOARD}


def params():
    return IR2Adapter(client=SimIR2()).named_params()


def states(c):
    return {k: v[0] for k, v in c["status"]["nodes"].items()}


@pytest.fixture
def ir2(monkeypatch):
    ctx = server.DeviceContext("ir2", server.FM9_REGISTRY, IR2Adapter(client=SimIR2()), DEVICE)
    monkeypatch.setattr(server, "_context", ctx)
    return ctx.adapter


# -- REQ-004: compile for a device's own parameters ----------------------------------

ALL = {"board": BOARD, "two_amps": TWO_AMPS, "stereo": STEREO, "serial_amps": SERIAL_AMPS}


@pytest.mark.parametrize("name", sorted(ALL))
@pytest.mark.parametrize("mode", rc.MODES)
def test_compile_every_node_and_edge_id_gets_exactly_one_state(name, mode):
    g = rg.load(ALL[name])
    c = rc.compile_for_params(g, params(), DEVICE, mode)
    assert set(c["status"]["nodes"]) == {x["id"] for x in g["nodes"]}
    assert set(c["status"]["edges"]) == {x["id"] for x in g["edges"]}
    for state, why in list(c["status"]["nodes"].values()) + list(c["status"]["edges"].values()):
        assert state in ("kept", "changed", "not_reproduced") and why


def test_target_one_graph_two_devices_two_transparent_results():
    fm9 = rc.compile(BOARD)
    ir2 = rc.compile_for_params(BOARD, params(), DEVICE)
    assert [s["block"] for s in fm9["scenes"][0]["chain"]] == ["drive", "amp", "cab", "delay", "reverb"]
    assert [(s["label"], s["param"]) for s in ir2["scenes"][0]["chain"]] == [("JCM800", "AMP"), ("Hall", "AMBIENCE")]
    assert ir2["scenes"][0]["chain"][0]["params"] == ["AMP", "GAIN", "BASS", "MIDDLE", "TREBLE"]
    assert states(fm9)["ts"] == "kept" and states(ir2)["ts"] == "not_reproduced"
    assert ir2["status"]["nodes"]["ts"][1] == "the BOSS IR-2 has no drive block"
    assert ir2["status"]["nodes"]["dly"][1] == "the BOSS IR-2 has no delay block"
    assert ir2["status"]["nodes"]["cab"] == ["changed", "the BOSS IR-2's amp voicing brings its own cab"]
    assert ir2["target"] == DEVICE and fm9["blockers"] == ir2["blockers"] == []


def test_target_cab_is_not_reproduced_without_option_cabs():
    bare = [{k: v for k, v in p.items() if k != "option_cabs"} for p in params()]
    c = rc.compile_for_params(BOARD, bare, DEVICE)
    assert c["status"]["nodes"]["cab"] == ["not_reproduced", "the BOSS IR-2 has no cab block"]


def test_target_a_device_without_ambience_keeps_no_reverb():
    c = rc.compile_for_params(BOARD, [p for p in params() if p["name"] != "AMBIENCE"], DEVICE)
    assert c["status"]["nodes"]["rev"] == ["not_reproduced", "the BOSS IR-2 has no reverb block"]


def test_target_routes_second_amp_and_power_amp():
    c = rc.compile_for_params(TWO_AMPS, params(), DEVICE)
    assert c["status"]["nodes"]["a2"] == ["not_reproduced", "the BOSS IR-2 has no scenes; one route is built"]
    c = rc.compile_for_params(SERIAL_AMPS, params(), DEVICE)
    assert c["status"]["nodes"]["a2"] == ["not_reproduced", "the BOSS IR-2 has one amp; the Triaxis took it"]
    assert c["status"]["nodes"]["pwr"] == ["changed", "part of the Triaxis voicing"]


def test_faithful_blocks_lost_gear_and_stereo_but_closest_does_not():
    assert rc.compile_for_params(BOARD, params(), DEVICE, "faithful")["blockers"] == [
        "The BOSS IR-2 has no place for TS808, Carbon Copy."]
    st = rc.compile_for_params(STEREO, params(), DEVICE, "faithful")["blockers"]
    assert st == ["This rig runs in stereo; the BOSS IR-2 is one mono path."]
    assert rc.compile_for_params(STEREO, params(), DEVICE, "closest")["blockers"] == []


# -- REQ-005: the build on the IR-2 ------------------------------------------------

def test_build_brief_names_parameters_and_the_gear_the_device_lacks():
    c = rc.compile_for_params(BOARD, params(), DEVICE)
    b = describe.brief_for_device(SPEC, c, DEVICE)
    assert b.startswith("On the BOSS IR-2, build the closest sound to this rig: TS808 into a JCM800")
    assert ("Use the JCM800 as AMP (with GAIN, BASS, MIDDLE, TREBLE), and the Hall as AMBIENCE.") in b
    assert "The BOSS IR-2 has no place for TS808, Carbon Copy; do not propose anything for them." in b
    assert "Use these settings exactly where they are given: gain 96." in b
    assert "\n- " not in b


def _fake_plan(monkeypatch, actions):
    seen = {}
    def fake(prompt, device_state, param_reference, **kw):
        seen.update(prompt=prompt, **kw)
        return {"summary": "s", "actions": json.loads(json.dumps(actions))}
    monkeypatch.setattr(planner, "plan", fake)
    return seen


def test_build_on_the_ir2_uses_its_own_planner_and_never_reads_an_fm9(ir2, monkeypatch):
    def no_fm9(*a, **k):
        raise AssertionError("the FM9 was read")
    monkeypatch.setattr(server, "snapshot", no_fm9)
    seen = _fake_plan(monkeypatch, [
        {"kind": "set_device_param", "param": "AMP", "type_name": "BROWN"},
        {"kind": "set_device_param", "param": "GAIN", "value": 96},
        {"kind": "set_device_param", "param": "BASS", "value": 50},
        {"kind": "set_device_param", "param": "AMBIENCE", "value": 20}])
    r = TestClient(server.app).post("/api/describe/build", json={"spec": SPEC})
    assert r.status_code == 200, r.text
    assert seen["system"] == devplan.SYSTEM and seen["schema"] == devplan.SCHEMA
    assert seen["prompt"] == describe.brief_for_device(SPEC, rc.compile_for_params(BOARD, params(), DEVICE), DEVICE)
    d = r.json()
    assert all(a["validation_errors"] == [] for a in d["actions"])
    f = d["fidelity"]
    amp = next(k for k in f["kept"] if k["what"] == "JCM800")
    assert amp["model"] == "BROWN" and amp["param"] == "AMP" and amp["actions"] == [0, 1, 2]
    rev = next(k for k in f["kept"] if k["what"] == "Hall")
    assert rev["actions"] == [3] and rev["model"] is None
    assert {x["what"] for x in f["not_reproduced"]} >= {"TS808", "Carbon Copy"}
    # GAIN 96 was stated; AMP, BASS and AMBIENCE were chosen
    assert f["chosen"]["count"] == 3 and f["chosen"]["stated_used"] == 1


def test_build_faithful_on_the_ir2_is_refused_naming_it_before_any_planner_call(ir2, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the planner was asked")
    monkeypatch.setattr(planner, "plan", boom)
    r = TestClient(server.app).post("/api/describe/build", json={"spec": SPEC, "mode": "faithful"})
    assert r.status_code == 409
    assert r.json()["error"].startswith("That rig cannot be built faithfully on the BOSS IR-2: "
                                        "The BOSS IR-2 has no place for TS808, Carbon Copy.")


def test_build_without_a_rig_on_the_ir2_takes_the_old_path(ir2, monkeypatch):
    called = []
    monkeypatch.setattr(server, "_describe_build_for_device", lambda *a, **k: called.append(1))
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": []})
    # the old path, unchanged, whatever it answers on this device
    TestClient(server.app, raise_server_exceptions=False).post(
        "/api/describe/build", json={"spec": {k: v for k, v in SPEC.items() if k != "rig"}})
    assert called == []


# -- REQ-006: the page ------------------------------------------------------------------

def test_page_kept_items_carry_their_parameters():
    assert '+ ` data-params="${esc((k.params || []).join(\' \'))}">${esc(k.what)}: `' in PAGE
    assert "? (a || {}).kind === 'set_device_param' && params.includes(String((a || {}).param || '').toUpperCase())" in PAGE


def _readback(tmp_path, kept, acted, planned):
    start = PAGE.index("function fidelityReadBack(f, acted, planned) {")
    end = PAGE.index("\n}\n", start) + 3
    script = tmp_path / "rb.mjs"
    script.write_text(
        "const els = {}; const $ = id => els[id];\n"
        "els.fidreadback = {hidden: true, textContent: ''};\n"
        f"const kept = {json.dumps(kept)};\n"
        "const lis = kept.map(k => ({dataset: {names: (k.names || []).join(' '), inst: String(k.instance),"
        " what: k.what, params: (k.params || []).join(' ')}, tag: {textContent: ''},"
        " querySelector() { return this.tag; }}));\n"
        "const document = {querySelectorAll: () => lis};\n" + PAGE[start:end]
        + f"\nconst line = fidelityReadBack({{}}, {json.dumps(acted)}, {json.dumps(planned)});\n"
        "console.log(JSON.stringify({line, tags: lis.map(l => l.tag.textContent)}));\n", encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_readback_on_the_ir2_matches_results_by_parameter(tmp_path):
    kept = [{"what": "JCM800", "instance": 1, "params": ["AMP", "GAIN", "BASS", "MIDDLE", "TREBLE"]},
            {"what": "Hall", "instance": 1, "params": ["AMBIENCE"]}]
    dp = lambda p: {"kind": "set_device_param", "param": p, "block": None, "instance": 1}
    planned = [dp("AMP"), dp("GAIN"), dp("AMBIENCE")]
    acted = [{"ok": True, "action": planned[0]}, {"ok": False, "action": planned[1]},
             {"ok": True, "action": planned[2]}]
    r = _readback(tmp_path, kept, acted, planned)
    assert r["tags"] == [" (partly verified)", " (verified)"]
    assert r["line"] == ("Read back from the unit, gear kept from the rig: 1 verified, 1 partly "
                         "(JCM800 partly verified).")

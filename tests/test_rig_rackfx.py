"""Rig build honesty, three fixes found building Marco Sfogli's rigs on the
FM9 (2026-10-09): a rack effects unit is never built as a delay it was not
named as (#243); a build name is cut to what the unit stores (#246); a tempo
change, which cannot be read back, is sent unverified, not failed (#249)."""
import json
import subprocess
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from devices.ir2.adapter import IR2Adapter
from devices.ir2.sim import SimIR2
from fm9 import rigcompile as rc
from fm9.sim import SimFM9

PAGE = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(encoding="utf-8")


def n(i, role="other", label=None):
    return {"id": i, "role": role, "label": label or i, "provenance": "observed"}


def e(f, t):
    return {"from": f, "to": t, "kind": "audio", "provenance": "observed"}


def rig(label):
    return {"nodes": [n("g", "instrument", "Guitar"), n("x", "rack_fx", label), n("a", "amp", "Amp"),
                      n("c", "cab", "4x12")],
            "edges": [e("g", "x"), e("x", "a"), e("a", "c")]}


# -- REQ-001 (#243): rack effects ---------------------------------------------------

UNNAMED = ["Fractal Audio FX1", "Eventide effects", "TC effects", "chain of rack effects", "Marshall JFX-1"]
NAMED = {"TC Electronic delay": "delay", "Lexicon reverb": "reverb", "Eventide H3000 harmonizer": "pitch",
         "MXR Phase 90 rack": "phaser", "Echoplex": "delay", "Eventide H9 chorus": "chorus"}


@pytest.mark.parametrize("label", UNNAMED)
def test_rack_unit_with_no_named_effect_is_not_reproduced(label):
    c = rc.compile(rig(label))
    assert c["status"]["nodes"]["x"] == ["not_reproduced",
                                         f"the source names the {label} but not which effects it provides"]
    assert [s["block"] for s in c["scenes"][0]["chain"]] == ["amp", "cab"]
    f = rc.fidelity(c, rig(label), [], [])
    assert label not in [k["what"] for k in f["kept"]]
    assert {"what": label, "why": f"the source names the {label} but not which effects it provides"} \
        in f["not_reproduced"]


@pytest.mark.parametrize("label,block", sorted(NAMED.items()))
def test_rack_unit_whose_label_names_an_effect_becomes_that_block(label, block):
    c = rc.compile(rig(label))
    assert c["status"]["nodes"]["x"] == ["kept", f"{block} 1"]
    assert c["scenes"][0]["chain"][0]["block"] == block


def test_a_stem_counts_only_at_a_word_start():
    assert rc._block_for({"role": "rack_fx", "label": "Marshall JFX-1"}) is None      # not "hall"
    assert rc._block_for({"role": "rack_fx", "label": "Roland Space Echo"}) == "delay"


def test_rack_units_on_a_named_parameter_device():
    params = IR2Adapter(client=SimIR2()).named_params()
    c = rc.compile_for_params(rig("Fractal Audio FX1"), params, "BOSS IR-2")
    assert c["status"]["nodes"]["x"] == ["not_reproduced",
                                         "the source names the Fractal Audio FX1 but not which effects it provides"]
    c = rc.compile_for_params(rig("Lexicon reverb"), params, "BOSS IR-2")
    assert c["status"]["nodes"]["x"] == ["kept", "AMBIENCE on the BOSS IR-2"]
    c = rc.compile_for_params(rig("TC Electronic delay"), params, "BOSS IR-2")
    assert c["status"]["nodes"]["x"] == ["not_reproduced", "the BOSS IR-2 has no delay block"]
    assert all("rack_fx" not in why for _, why in c["status"]["nodes"].values())


# -- REQ-002 (#246): the build name the unit will store ---------------------------------

LONG = "Marco Sfogli's 2015-2016 touring"          # 32: failed on the unit 2026-10-09


def test_stored_preset_name_is_tagged_cut_to_31_and_stripped():
    assert server.stored_preset_name(LONG) == "FM9AI-Marco Sfogli's 2015-2016"
    assert server.stored_preset_name("Short") == "FM9AI-Short"
    assert server.stored_preset_name("FM9AI-" + "x" * 40) == "FM9AI-" + "x" * 25
    assert len(server.stored_preset_name("y" * 25)) == 31
    assert server.BUILD_NAME_ROOM == 25


def test_rename_of_a_long_name_lands_on_the_simulator():
    dev = SimFM9(server.reg)
    got = server.run_action(dev, server.Action(kind="rename_preset", block="PRESET", type_name=LONG))
    assert got == {"ok": True, "detail": "preset renamed to \"FM9AI-Marco Sfogli's 2015-2016\""}
    assert dev.current_preset()[1] == "FM9AI-Marco Sfogli's 2015-2016"


def test_the_simulator_keeps_31_characters_of_a_preset_name_and_scene_names_as_sent():
    dev = SimFM9(server.reg)
    dev.rename_preset("A" * 32)
    assert dev.current_preset()[1] == "A" * 31
    dev.rename_scene(2, "B" * 32)
    assert dev.scene_name(2)[1] == "B" * 32


def test_a_planner_rename_and_the_players_name_are_cut_before_review():
    acts = [{"kind": "rename_preset", "block": "PRESET", "instance": 1, "type_name": LONG}]
    server._fit_planned_renames(acts)
    assert acts[0]["type_name"] == LONG[:25].rstrip()
    assert server._fit_build_name(LONG) == "Marco Sfogli's 2015-2016"   # 25, trailing space gone


def test_name_page_field_and_suggestion_fit_25():
    assert '<input type="text" id="qname" maxlength="25"' in PAGE
    assert "return out.join(' ').slice(0, 25).trim();" in PAGE


# -- REQ-003 (#249): tempo, sent and unverified -----------------------------------------

def test_tempo_is_sent_unverified_never_ok():
    dev = SimFM9(server.reg)
    got = server.run_action(dev, server.Action(kind="set_tempo", value=120))
    assert got["ok"] is False and got["sent"] is True and got["verified"] is False


def _tally(tmp_path, acted):
    start = PAGE.index("function sendTally(acted) {")
    end = PAGE.index("\n}\n", start) + 3
    script = tmp_path / "t.mjs"
    script.write_text(PAGE[start:end] + f"\nconsole.log(JSON.stringify(sendTally({json.dumps(acted)})));\n",
                      encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_tally_counts_a_sent_unverified_change_apart_from_failures(tmp_path):
    ok = {"ok": True, "action": {"kind": "set_param"}}
    tempo = {"ok": False, "sent": True, "action": {"kind": "set_tempo"}}
    bad = {"ok": False, "action": {"kind": "add_block"}}
    t = _tally(tmp_path, [ok] * 49 + [tempo])
    assert (t["verified"], t["unverified"], t["failed"]) == (49, 1, 0)
    t = _tally(tmp_path, [ok, tempo, bad])
    assert (t["verified"], t["unverified"], t["failed"]) == (1, 1, 1)
    assert [r["action"]["kind"] for r in t["failedResults"]] == ["add_block"]


def test_page_names_only_failed_changes_and_says_sent_unverified():
    assert "const tally = sendTally(acted);" in PAGE
    assert "const failures = tally.failedResults.slice(0, 3).map(r =>" in PAGE
    assert "+ (unverified ? ` · ${unverified} SENT UNVERIFIED` : ''));" in PAGE
    assert "cards[card].classList.add(res.ok ? 'done' : (res.sent ? 'unverified' : 'fail'));" in PAGE
    assert "sent but cannot be read back to verify: " in PAGE

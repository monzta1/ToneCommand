"""Review renders the PLAN's listening set, and never searches on its own.

Reported 2026-09-07: a Steve Vai build offered a Soldano SLO30 capture as a
cab. The cause was not the matcher. Review issued its own
`fetch('/api/ir/recommend?need=' + intent)`, so everything the planner had
established was discarded at the last step: no reference cab, no preserve
constraint, and the player's raw words instead of the planner's gear
translation. The server built a constrained listening set that nothing read.

These run the real `renderCabPanel` in node rather than reading its source.
A source scan would pass on a file that merely MENTIONS cab_selection while
still fetching, and that is exactly the bug being pinned here.
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT / "ui" / "index.html").read_text()

# The panel's own code, lifted verbatim: cabRow, renderBlend, cabAnchorNote
# and renderCabPanel. Everything else it touches is stubbed, so what runs
# here is the shipped implementation and not a paraphrase of it.
START = "function cabRow(r, chosen) {"
END = "// --- CONFIRM stage"

HARNESS = r"""
import { readFileSync } from "fs";
const src = readFileSync(process.argv[2], "utf8");
const start = src.indexOf(process.argv[3]);
const end = src.indexOf(process.argv[4], start);
if (start < 0 || end < 0) { console.log("EXTRACT FAILED"); process.exit(1); }
const panelCode = src.slice(start, end);
const input = JSON.parse(readFileSync(process.argv[5], "utf8"));

const fetched = [];
const nodes = {};
function node() {
  return { textContent: "", innerHTML: "", hidden: false,
           querySelectorAll: () => [] };
}
const $ = (id) => (nodes[id] = nodes[id] || node());
const esc = (s) => String(s);
const matchWord = () => "close";
const stopCabAudio = () => {};
const playCab = () => {};
const cabActions = (p) => (p.actions || []).filter(a => a.kind === "set_cab");
const fetch = async (u) => { fetched.push(u); throw new Error("no network"); };
let cabDrive = "lead";
let lastCab = input.lastCab || { ordinal: null, name: null };
let currentPlan = input.plan;

const run = new Function(
  "$", "esc", "matchWord", "stopCabAudio", "playCab", "cabActions",
  "fetch", "cabDrive", "lastCab", "currentPlan",
  panelCode + "\nreturn renderCabPanel;");

await run($, esc, matchWord, stopCabAudio, playCab, cabActions,
          fetch, cabDrive, lastCab, currentPlan)();
console.log(JSON.stringify({
  fetched,
  note: $("cabnote").textContent,
  alts: $("cabalts").innerHTML,
  chosen: $("cabchosen").innerHTML,
  hidden: $("cabpanel").hidden,
}));
"""


def _render(tmp_path, plan, last_cab=None) -> dict:
    h = tmp_path / "harness.mjs"
    h.write_text(HARNESS)
    payload = tmp_path / "input.json"
    payload.write_text(json.dumps({"plan": plan, "lastCab": last_cab}))
    out = subprocess.run(
        ["node", str(h), str(ROOT / "ui" / "index.html"), START, END,
         str(payload)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "EXTRACT FAILED" not in out.stdout, "renderCabPanel moved; fix the slice"
    return json.loads(out.stdout.strip())


PLAN = {
    "actions": [{"kind": "set_cab", "block": "cab", "bank": 1, "value": 12,
                 "cab_name": "4x12 RECTO SM57", "why": "the build's cab"}],
    "intent": "steve vai lead tone",
    "cab_need": "4x12 v30 bright cutting lead",
    "cab_selection": {
        "anchor": "gear_anchored",
        "current": "4x12 BRIT V30 SM57 (FACTORY 1)",
        "preserved": "4x12 BRIT V30 SM57",
        "reference": None,
        "candidates": [
            {"name": "OwnHammer Brit V30 SM57 Cap", "path": "/l/a.wav",
             "pack": "OwnHammer", "match": 0.81, "why": ["4x12", "v30"],
             "measured": None, "distance_from_current": None},
            {"name": "York Audio BRIT V30 R121", "path": "/l/b.wav",
             "pack": "York", "match": 0.74, "why": ["4x12", "v30"],
             "measured": None, "distance_from_current": None},
        ],
    },
}


def test_the_panel_never_searches_for_itself(tmp_path):
    """The whole bug in one assertion."""
    r = _render(tmp_path, PLAN)
    assert not [u for u in r["fetched"] if "ir/recommend" in u], (
        "Review issued its own IR search. Whatever it passed, it cannot have "
        "carried the plan's reference and preserve constraints: those live on "
        "the server. Render currentPlan.cab_selection instead.")


def test_the_plans_own_candidates_are_what_is_shown(tmp_path):
    r = _render(tmp_path, PLAN)
    assert "OwnHammer Brit V30 SM57 Cap" in r["alts"]
    assert "York Audio BRIT V30 R121" in r["alts"]


def test_a_gear_anchored_current_claims_no_measured_distance(tmp_path):
    """Brief 21.5.1. Gear identity constrains the search; it proves nothing
    about distance, because nothing measured the loaded cab."""
    r = _render(tmp_path, PLAN)
    assert "4x12 BRIT V30 SM57 (FACTORY 1)" in r["note"]
    assert "gear only" in r["note"]
    assert "dB from current" not in r["alts"]


def test_a_measured_current_may_state_a_distance(tmp_path):
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"].update(anchor="measured", preserved=None,
                                 reference="/l/current.wav")
    plan["cab_selection"]["candidates"][0]["distance_from_current"] = 1.8
    r = _render(tmp_path, plan)
    assert "which is measured" in r["note"]
    assert "1.8 dB from current" in r["alts"]


def test_an_unresolved_current_says_so_rather_than_implying_a_comparison(tmp_path):
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"].update(anchor="unresolved", current=None,
                                 preserved=None)
    r = _render(tmp_path, plan)
    assert "Nothing is loaded to compare against" in r["note"]


def test_the_servers_reason_for_an_empty_set_reaches_the_player(tmp_path):
    """'Not understood' must never surface as silence, which reads as
    'nothing was considered'."""
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"] = {"anchor": "unresolved", "current": None,
                             "candidates": [],
                             "why": "the IR library is not connected"}
    r = _render(tmp_path, plan)
    assert r["note"] == "the IR library is not connected"
    assert r["alts"] == ""


def test_no_selection_on_the_plan_leaves_the_panel_quiet(tmp_path):
    """An older plan, or IR off entirely. The build's own cab still shows."""
    plan = json.loads(json.dumps(PLAN))
    del plan["cab_selection"]
    r = _render(tmp_path, plan)
    assert r["alts"] == ""
    assert "4x12 RECTO SM57" in r["chosen"]

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
START = "function cabActions(plan) {"
END = "// --- CONFIRM stage"

# Every id the panel writes to must EXIST in the page, or a test that creates
# nodes on demand passes against markup that has none of them. These are read
# straight out of the HTML rather than listed here by hand.
PANEL_IDS = ("cabpanel", "cabnote", "cabchosen", "cablink", "cabalts",
             "cabblend", "cabfoot")

HARNESS = r"""
import { readFileSync } from "fs";
const src = readFileSync(process.argv[2], "utf8");
const start = src.indexOf(process.argv[3]);
const end = src.indexOf(process.argv[4], start);
if (start < 0 || end < 0) { console.log("EXTRACT FAILED"); process.exit(1); }
const panelCode = src.slice(start, end);
const input = JSON.parse(readFileSync(process.argv[5], "utf8"));

const fetched = [];
// Only ids the PAGE declares get a node. An unknown id throws, so the panel
// cannot quietly write into somewhere that does not exist in the markup.
const known = JSON.parse(process.argv[6]);
const nodes = {};
for (const id of known) {
  nodes[id] = { textContent: "", innerHTML: "", hidden: false,
                querySelectorAll: () => [] };
}
// An id resolves if the PAGE declares it, or if the panel has already
// written it into some node's innerHTML, which is what a browser would do.
// Anything else throws, so the panel cannot quietly address an element that
// exists nowhere.
const $ = (id) => {
  if (!(id in nodes)) {
    const written = Object.values(nodes).some(
      (n) => typeof n.innerHTML === "string"
             && n.innerHTML.includes(`id="${id}"`));
    if (!written) {
      throw new Error("no element with id " + id + " on the page");
    }
    nodes[id] = { textContent: "", innerHTML: "", hidden: false,
                  value: "", onclick: null, onkeydown: null,
                  querySelectorAll: () => [] };
  }
  return nodes[id];
};
// The slice carries the real cabActions, stopCabAudio, playCab, matchWord,
// cabRow, cabAnchorNote and renderCabPanel. Only what the BROWSER supplies is
// provided here, so a change in any of those functions reaches these tests.
const esc = (s) => String(s);
let cabAudio = null;
const document = { querySelectorAll: () => [] };
const fetch = async (u) => { fetched.push(u); throw new Error("no network"); };
let cabDrive = "lead";
let lastCab = input.lastCab || { ordinal: null, name: null };
let currentPlan = input.plan;

// cabActions is NOT stubbed: it is part of the slice, so a change that
// stops recognising a cab action fails these tests instead of passing them.
const run = new Function(
  "$", "esc", "document", "cabAudio", "fetch", "cabDrive", "lastCab",
  "currentPlan", panelCode + "\nreturn renderCabPanel;");

await run($, esc, document, cabAudio, fetch, cabDrive, lastCab,
          currentPlan)();
console.log(JSON.stringify({
  fetched,
  note: $("cabnote").textContent,
  alts: $("cabalts").innerHTML,
  chosen: $("cabchosen").innerHTML,
  link: $("cablink").innerHTML,
  hidden: $("cabpanel").hidden,
}));
"""


def _render(tmp_path, plan, last_cab=None) -> dict:
    h = tmp_path / "harness.mjs"
    h.write_text(HARNESS)
    payload = tmp_path / "input.json"
    payload.write_text(json.dumps({"plan": plan, "lastCab": last_cab}))
    for node_id in PANEL_IDS:
        assert f'id="{node_id}"' in UI, \
            f"the page declares no #{node_id}; the harness would invent it"
    out = subprocess.run(
        ["node", str(h), str(ROOT / "ui" / "index.html"), START, END,
         str(payload), json.dumps(list(PANEL_IDS))],
        capture_output=True, text=True)
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
                                 relative=True, reference="/l/current.wav")
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


# --- a listening set is never hidden (2026-09-08) -------------------------
#
# The panel returned before reading cab_selection whenever the plan had no
# cab action, no amp-voice action, and no readable loaded cab. The planner is
# allowed to name a cab TARGET without choosing an exact asset, so a plan can
# carry a real, constrained listening set and no set_cab. Hiding it is the
# reported complaint again in a different shape: the reasoning existed and
# the player never saw it.

def test_a_plan_with_no_cab_action_still_shows_its_listening_set(tmp_path):
    plan = json.loads(json.dumps(PLAN))
    plan["actions"] = [{"kind": "set_param", "block": "reverb",
                        "param": "MIX", "value": 12}]
    r = _render(tmp_path, plan, last_cab={"ordinal": None, "name": None})
    assert r["hidden"] is False, "a real listening set was hidden"
    assert "OwnHammer Brit V30 SM57 Cap" in r["alts"]
    assert r["note"], "shown with no word about what it is relative to"


def test_the_panel_still_hides_when_there_is_genuinely_nothing(tmp_path):
    """The fix must not turn the panel into permanent furniture."""
    plan = json.loads(json.dumps(PLAN))
    plan["actions"] = [{"kind": "set_param", "block": "reverb",
                        "param": "MIX", "value": 12}]
    del plan["cab_selection"]
    r = _render(tmp_path, plan, last_cab={"ordinal": None, "name": None})
    assert r["hidden"] is True


def test_a_cab_action_is_recognised_by_the_pages_own_rule(tmp_path):
    """cabActions is part of the slice now, not a stub. A plan that changes a
    cab parameter without a set_cab is still a cab decision."""
    plan = json.loads(json.dumps(PLAN))
    plan["actions"] = [{"kind": "set_param", "block": "Cab 1",
                        "param": "CABINET LEVEL", "value": -2,
                        "why": "matches the new voice"}]
    r = _render(tmp_path, plan)
    assert r["hidden"] is False
    # Not `or "cab" in chosen.lower()`: the class names cabrow and cabname
    # are in every non-empty render, so that disjunct was satisfied by any
    # output at all and only the empty string could fail it.
    assert "CABINET LEVEL" in r["chosen"]
    assert "matches the new voice" in r["chosen"]


def test_a_measured_current_with_no_direction_does_not_claim_least_change(
        tmp_path):
    """"Least change" describes the relative pass. With no requested
    direction there is no movement to be least of, and the sentence would
    describe an algorithm that did not run on this request."""
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"].update(anchor="measured", relative=False,
                                 reference="/l/current.wav")
    r = _render(tmp_path, plan)
    assert "least change" not in r["note"].lower()
    assert "is measured" in r["note"]


def test_the_legacy_distance_field_is_not_accepted_from_a_candidate(tmp_path):
    """`distance_from_reference` is the RAW service field and is not filtered
    by anchor state. Reading it as a fallback would reinstate exactly the
    claim the server strips for a gear-anchored Current."""
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"]["candidates"][0]["distance_from_reference"] = 2.4
    r = _render(tmp_path, plan)
    assert "2.4 dB from current" not in r["alts"]
    assert "dB from current" not in r["alts"]


# --- moved here from test_cab_selection.py, where they were substring scans

def test_the_review_names_the_cab_rather_than_numbering_it(tmp_path):
    """A player does not recognise "bank 1 ordinal 12". The action carries a
    cab_name for exactly this, and the panel has to prefer it."""
    r = _render(tmp_path, PLAN)
    assert "4x12 RECTO SM57" in r["chosen"]
    assert "ordinal" not in r["chosen"]


def test_a_build_that_changes_the_amp_never_goes_quiet_about_the_cab(tmp_path):
    """A plan that sets no cab has still MADE a cab decision: to keep the one
    loaded. Hiding the panel made that silent, and silence reads as "cabs were
    never considered", which is the sentence that started this work."""
    plan = json.loads(json.dumps(PLAN))
    plan["actions"] = [{"kind": "set_type", "block": "Amp 1",
                        "value": "USA IIC+ LEAD"}]
    del plan["cab_selection"]
    r = _render(tmp_path, plan,
                last_cab={"ordinal": 12, "name": "4x12 BRIT V30 SM57"})
    assert r["hidden"] is False
    assert "UNCHANGED" in r["chosen"]
    assert "4x12 BRIT V30 SM57" in r["chosen"]


def test_an_unrelated_build_with_no_cab_context_stays_hidden(tmp_path):
    """The other side of it: not every plan is a cab plan."""
    plan = json.loads(json.dumps(PLAN))
    plan["actions"] = [{"kind": "set_param", "block": "reverb",
                        "param": "MIX", "value": 12}]
    del plan["cab_selection"]
    r = _render(tmp_path, plan, last_cab={"ordinal": 12, "name": "A cab"})
    assert r["hidden"] is True


# --- offering the link that makes `measured` reachable (2026-09-08) -------
#
# A player with 7,000 analysed IRs and one of their own cabs loaded was
# permanently told "nothing is loaded to compare against", because no install
# path records which file a slot holds and this page had no client for the
# user-cabs API at all. The panel that reports the problem is where the fix
# belongs.

def test_an_unresolved_user_slot_is_offered_the_link(tmp_path):
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"] = {"anchor": "unresolved", "current": None,
                             "candidates": [], "linkable": True,
                             "bank": 2, "ordinal": 26,
                             "why": "this cab is not one of yours"}
    r = _render(tmp_path, plan)
    assert "search your IR library" in r["link"]
    assert "no comparison can be made" in r["link"]


def test_a_resolved_current_is_not_offered_a_link(tmp_path):
    """The offer is a repair, not furniture."""
    r = _render(tmp_path, PLAN)              # gear_anchored
    assert r["link"] == ""


def test_an_unresolved_factory_slot_is_not_offered_a_link(tmp_path):
    """Only the USER bank. A factory slot's identity is the manufacturer's
    own label, and overriding that by hand is the brief 26.1 boundary error,
    so the panel must not invite it."""
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"] = {"anchor": "unresolved", "current": None,
                             "candidates": [], "linkable": False,
                             "bank": 3, "ordinal": 42}
    r = _render(tmp_path, plan)
    assert r["link"] == ""


def test_an_empty_selection_still_shows_the_reason_it_is_empty(tmp_path):
    """Caught by the third review. The panel required CANDIDATES to stay
    visible, so a plan whose cab search failed with a real explanation showed
    nothing at all, which is the silence this whole panel exists to end."""
    plan = json.loads(json.dumps(PLAN))
    plan["actions"] = [{"kind": "set_param", "block": "reverb",
                        "param": "MIX", "value": 12}]
    plan["cab_selection"] = {"anchor": "unresolved", "current": None,
                             "candidates": [],
                             "why": "the IR library did not answer"}
    r = _render(tmp_path, plan, last_cab={"ordinal": None, "name": None})
    assert r["hidden"] is False, "the reason was hidden with the panel"
    assert r["note"] == "the IR library did not answer"


def test_an_unreadable_target_reaches_the_player(tmp_path):
    """A fault in the BUILD must not be delivered as a report about the
    player's library."""
    plan = json.loads(json.dumps(PLAN))
    plan["actions"] = []
    plan["cab_selection"] = {
        "anchor": "unresolved", "candidates": [], "target_unreadable": True,
        "why": "this build described the cab as 'steve vai lead', and steve, "
               "vai is not gear a library can be searched for. Your library "
               "was not the problem."}
    r = _render(tmp_path, plan, last_cab={"ordinal": None, "name": None})
    assert r["hidden"] is False
    assert "Your library was not the problem" in r["note"]


def test_an_unreadable_target_is_said_even_when_rows_came_back(tmp_path):
    """Found by the fourth review. The server sets `why` and
    `target_unreadable` regardless of whether rows returned, and the panel
    showed `why` ONLY on an empty list. The text fallback matches filename
    fragments ("vai" inside a pack folder), so an unreadable target usually
    DOES return rows, and the panel presented those fragments as the answer
    under the ordinary anchor note."""
    plan = json.loads(json.dumps(PLAN))
    plan["cab_selection"]["target_unreadable"] = True
    plan["cab_selection"]["why"] = (
        "this build described the cab as 'steve vai signature lead', and "
        "steve, vai is not gear a library can be searched for. Your library "
        "was not the problem.")
    r = _render(tmp_path, plan)
    assert "Your library was not the problem" in r["note"]
    assert "Ranked against" not in r["note"], \
        "filename fragments were presented as a ranked answer"
    assert "NAME MATCHES ONLY" in r["alts"], \
        "the rows still read as alternatives that answer the request"


def test_a_readable_target_still_gets_the_ordinary_note(tmp_path):
    r = _render(tmp_path, PLAN)
    assert "NAME MATCHES ONLY" not in r["alts"]
    assert "Ranked against" in r["note"]


def test_the_page_actually_calls_the_panel(tmp_path):
    """Every test in this file calls renderCabPanel itself. Nothing asserted
    the PAGE calls it, so deleting the call site left all of them green while
    the panel never rendered, which is the original symptom: a build that
    said nothing about the cab."""
    body = UI.split("function renderReviewStage", 1)
    assert len(body) == 2, "renderReviewStage moved; this check is stale"
    assert "renderCabPanel()" in body[1][:4000], \
        "the review stage no longer renders the cab panel"


def test_the_link_offer_is_gated_on_the_user_bank_in_the_server(monkeypatch):
    """`linkable` arrives from the server and every panel test supplies it as
    a literal, so the USER-bank boundary itself had no test anywhere. Brief
    26.1: a factory slot's identity is the roster's, and inviting a hand
    link over it is the boundary error."""
    import sys
    sys.argv = ["x"]
    import server
    from fm9 import ir_service
    monkeypatch.setattr(ir_service, "enabled", lambda: True)
    monkeypatch.setattr(ir_service, "recommend",
                        lambda *a, **k: (k.get("detail") or {}).update(
                            understood=True) or [])

    user = server.cab_listening_set(
        {"cab_need": "4x12 v30"},
        {"state": "unresolved", "bank": server.USER_CAB_BANK, "ordinal": 26})
    assert user["linkable"] is True

    factory = server.cab_listening_set(
        {"cab_need": "4x12 v30"},
        {"state": "unresolved", "bank": 3, "ordinal": 42})
    assert factory["linkable"] is False, \
        "the panel would invite a hand link over the factory roster"

    resolved = server.cab_listening_set(
        {"cab_need": "4x12 v30"},
        {"state": "gear_anchored", "bank": server.USER_CAB_BANK,
         "ordinal": 26, "gear": "4x12 RECTO SM57"})
    assert resolved["linkable"] is False, "a repair offered where none is needed"

"""The TONE panel: grouped, in the unit's own words, and adjustable.

It used to be AMP TELEMETRY, a wall of right-aligned numbers under a heading
no guitarist says, and it was a readout. The one question it invited, "so
nudge the mid up a bit", it could not answer, which is the whole complaint
behind issue #34: a panel you can only look at sends you to FM9-Edit, and a
tool you leave in the middle of a session is one you stop opening.

Three things had to be true to fix it, and these pin all three:

  the ranges are the registry's, not a table in the browser
  a value we cannot back up is not drawn at all
  one drag puts one write on the wire, not one per pixel
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9.sim import SimFM9

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


# --- ranges belong to the registry ---------------------------------------

def test_the_state_payload_describes_every_value_it_sends(client):
    """The browser used to carry its own table of maxima, so it could only
    draw the seven amp knobs it had heard of and drew each as though it ran
    0-10. Threshold runs -100 to 0 and delay time to 16000ms."""
    s = client.get("/api/state").json()
    assert s["params"], "no metadata, so the UI is back to guessing"
    for key, m in s["params"].items():
        assert key in s["values"], f"{key} described but not sent"
        for field in ("family", "instance", "param", "min", "max", "label"):
            assert field in m, f"{key} missing {field}"


def test_the_metadata_is_enough_to_write_the_value_back(client):
    """Every field set_param needs comes from the same payload that drew the
    slider, so the UI never has to reconstruct a block name."""
    s = client.get("/api/state").json()
    m = s["params"]["DISTORT_DRIVE"]
    r = client.post("/api/apply", json={"actions": [{
        "kind": "set_param", "block": m["family"], "instance": m["instance"],
        "param": m["param"], "value": (m["min"] + m["max"]) / 2}]}).json()
    assert r["results"][0]["ok"], r


def test_labels_are_the_ones_the_unit_uses(client):
    """DISTORT_DRIVE is our name for it. The amp calls it Gain."""
    p = client.get("/api/state").json()["params"]
    assert p["DISTORT_DRIVE"]["label"] == "Gain"
    assert "_" not in p["DISTORT_DRIVE"]["label"]


def test_the_browser_keeps_no_table_of_its_own():
    assert "KNOB_LABELS" not in SCRIPT, \
        "ranges hardcoded in the browser drift from the registry silently"


# --- a number we cannot back up is not drawn -----------------------------

def test_parameters_with_an_unverified_range_are_left_out():
    """FUZZ_TYPE is a model selector whose ordinal arrives scaled to 0.08. A
    row reading TYPE 0.08 states nothing true, and it would sit there looking
    exactly as authoritative as Gain 1.2."""
    assert "unit !== 'unverified'" in SCRIPT


def test_a_parameter_with_no_span_stays_a_readout():
    """Not every missing range is worth hiding, but none of them is worth a
    slider: a control we cannot map back would look as trustworthy as one we
    can."""
    assert "if (!(span > 0))" in SCRIPT
    assert "read only" in SCRIPT


# --- one drag, one write --------------------------------------------------

def test_the_write_happens_on_change_not_on_input():
    """input fires for every pixel of travel. Writing there would put a SysEx
    message on the wire for each one, which is how a MIDI port is flooded."""
    change = SCRIPT.split("eachBox(box => box.addEventListener('change'")[1].split("\n}));")[0]
    inp = SCRIPT.split("eachBox(box => box.addEventListener('input'")[1].split("\n}));")[0]
    assert "set_param" in change, "nothing is transmitted when the drag ends"
    assert "set_param" not in inp and "fetch" not in inp, \
        "the input handler must only move the track fill"


def test_the_poll_does_not_repaint_under_a_moving_thumb():
    """State refreshes every five seconds. Re-rendering mid-drag would replace
    the element being dragged and drop the gesture."""
    assert "if (!dragging) renderParams(s)" in SCRIPT
    inp = SCRIPT.split("eachBox(box => box.addEventListener('input'")[1].split("\n}));")[0]
    assert "dragging = true" in inp


def test_the_control_is_a_real_range_input():
    """Draggable, keyboard reachable and screen-reader labelled without
    reinventing any of it on a div and a mousemove handler."""
    assert 'type="range"' in SCRIPT
    assert "aria-label" in SCRIPT.split("function knobRow")[1].split("\n}")[0]


# --- what the panel leads with -------------------------------------------

def test_the_amp_model_and_cab_are_shown(client):
    """Both were read on every poll and then thrown away. They are the two
    facts a player leads with, and neither appeared anywhere on the page."""
    s = client.get("/api/state").json()
    assert "AMP_MODEL" in s["values"]
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "AMP_MODEL" in render and "values.cab" in render


def test_the_panel_is_grouped_by_block():
    """A flat list of thirty values is a wall. The question always arrives
    attached to a block: the delay a little wetter, the gate tighter.

    The groups are no longer a hardcoded list, so this checks the naming and
    ordering tables that replaced it rather than the list that is gone.
    """
    names = SCRIPT.split("const GROUP_NAMES = {")[1].split("};")[0]
    order = SCRIPT.split("const GROUP_ORDER = [")[1].split("];")[0]
    for fam in ("DISTORT", "INPUT", "DELAY", "REVERB"):
        assert fam in names and f"'{fam}'" in order


def test_it_is_not_called_telemetry():
    # the heading itself, not the comment that records why it changed
    assert 'data-label="AMP TELEMETRY"' not in UI
    assert 'data-label="AMP &amp; CAB"' in UI


def test_both_control_surfaces_say_what_they_do():
    """Nothing else on the page announces itself, and a control that looks
    like a readout is a control nobody finds."""
    assert "click a block to open it" in UI
    assert "its letter to change channel" in UI
    # and the one thing a player needs to know before touching either
    assert "Edit buffer only" in UI


# --- the signal chain is the actual grid ---
# It was a wrapped list of block names, which tells you what is in the preset
# but not how any of it is wired, and the wiring is the part that goes wrong:
# a severed cable and a bypassed Return both leave every block present and
# correct while the scene makes no sound.

def test_the_grid_endpoint_resolves_the_cables(client):
    """The browser is handed the source rows that feed each cell, not the
    bitmask they arrived in. How the cable mask is packed is a protocol fact
    and belongs on this side of the wire."""
    g = client.get("/api/grid").json()
    assert g["cells"] and "error" not in g
    for c in g["cells"]:
        assert isinstance(c["feeds"], list)
        assert all(isinstance(r, int) for r in c["feeds"])
        assert "live" in c


def test_the_walk_is_shared_with_the_audit_not_reimplemented():
    """Five silent-scene classes were found the hard way getting this
    traversal right. A second copy in the browser would drift from it."""
    from tools import path_audit
    assert hasattr(path_audit, "walk")
    alive, why = path_audit.scene_alive.__doc__, path_audit.walk.__doc__
    assert alive and why
    import inspect
    assert "walk(" in inspect.getsource(path_audit.scene_alive), \
        "scene_alive must delegate, so both answers come from one traversal"


def test_shunts_are_drawn_as_wire_not_as_blocks():
    """A shunt is a piece of cable. Drawing it as a box would imply the preset
    contains something it does not."""
    render = SCRIPT.split("function renderGrid")[1].split("\nfunction ")[0]
    assert "if (c.shunt)" in render and "line class=\"shunt" in render.replace("`", "")


def test_a_cable_is_lit_only_when_both_ends_are():
    """A live block fed from a dead one is not being reached through THIS
    cable, and lighting it would draw a path the signal does not take."""
    render = SCRIPT.split("function renderGrid")[1].split("\nfunction ")[0]
    assert "c.live && from && from.live" in render


def test_the_glow_filter_is_in_user_space():
    """objectBoundingBox is the default, and a horizontal line has a bounding
    box zero pixels tall, so a percentage filter region collapses and the
    element renders blank. Every straight wire in the chain was invisible
    while its computed stroke read as cyan."""
    assert 'filterUnits="userSpaceOnUse"' in SCRIPT


def test_empty_leading_rows_are_trimmed():
    """The device numbers rows on its own full grid. A preset using rows 1 to
    4 drawn at absolute coordinates wastes a row of panel on nothing."""
    render = SCRIPT.split("function renderGrid")[1].split("\nfunction ")[0]
    assert "Math.min(...g.cells.map(c => c.row))" in render


def test_bypassed_is_shown_by_dash_not_by_colour():
    """Colour here already means live versus dead. One signal must not carry
    two meanings, and a bypassed block still passes signal through."""
    assert "svg.grid .cell.byp > rect { stroke-dasharray" in UI


def test_a_dead_wire_is_still_legible():
    """A severed path is information. Drawn too dark it reads as empty space
    rather than as a fault."""
    assert "#22303a" not in UI, "the old near-invisible wire colour is back"


# --- auditioning amps and cabs ---
# The thing the device is worst at. On the FM9 you turn a knob through 1024
# cabinets one at a time because there is nowhere to type.

def test_the_rosters_are_served_whole(client):
    """Paging 2237 cabs would make the search feel like the unit's own list,
    which is the thing this is trying to beat."""
    amps = client.get("/api/models?kind=amp").json()
    cabs = client.get("/api/models?kind=cab").json()
    assert len(amps["banks"][0]["models"]) > 300
    assert sum(len(b["models"]) for b in cabs["banks"]) > 2000
    assert all("name" in b for b in cabs["banks"]), "banks must be named"


def test_a_cab_carries_its_description_for_searching(client):
    """"Vibrolux" is in the description, not in the name. Searching only names
    would miss the amp the cab was modelled on, which is how anyone actually
    looks for one."""
    cabs = client.get("/api/models?kind=cab").json()
    models = cabs["banks"][0]["models"]
    assert any(m.get("detail") for m in models)


def test_setting_a_cab_verifies_and_names_what_landed(client):
    c = client.get("/api/state").json()["cab_sel"]
    assert c and "bank" in c and "ordinal" in c
    r = client.post("/api/apply", json={"actions": [{
        "kind": "set_cab", "block": "CABINET", "instance": 1,
        "value": 200, "bank": 0}]}).json()
    res = r["results"][-1]
    assert res["ok"] and "cab ->" in res["detail"]


def test_a_cab_outside_the_bank_is_refused(client):
    r = client.post("/api/apply", json={"actions": [{
        "kind": "set_cab", "block": "CABINET", "instance": 1,
        "value": 99999, "bank": 0}]}).json()
    assert not r["results"][-1]["ok"]


def test_auditioning_goes_through_the_same_apply_path():
    """So it inherits undo, gig mode and read-back verification rather than
    reimplementing all three on a side channel."""
    load = SCRIPT.split("async function audLoad")[1].split("\n}")[0]
    assert "'/api/apply'" in load
    assert "refreshSnaps" in load, "an audition you cannot undo is a trap"


def test_stepping_is_on_the_arrow_keys():
    """The whole point: keep both hands on the guitar and step the shortlist
    without hunting for a button."""
    assert "ArrowDown" in SCRIPT and "ArrowUp" in SCRIPT
    assert "function audStep" in SCRIPT


def test_the_search_narrows_rather_than_widens():
    """Every word must match. An OR would make a second word return MORE
    results, which is the opposite of what typing more means."""
    assert "words.every(" in SCRIPT


def test_the_ordinal_is_accepted_directly():
    """The audition list already knows exactly which model it means and should
    not round trip through a name. Checked after the exact-name match so an
    amp actually called "59" still wins over ordinal 59."""
    import inspect
    src = inspect.getsource(server.resolve_type_ordinal)
    assert "needle.isdigit()" in src
    exact = src.index("str(label).lower() == needle")
    assert exact < src.index("needle.isdigit()")


# --- the picker has to survive the panel it is anchored to ---

def test_the_popover_is_never_parented_into_a_repainting_panel():
    """The bug behind "the dropdowns don't always open".

    It was appended to the button's own wrapper, and the five-second poll
    rewrites that panel's innerHTML, so the popover was destroyed on the next
    tick. It opened once, then threw for the rest of the session. Anchoring is
    by measurement now, not by parentage.
    """
    open_fn = SCRIPT.split("async function openAud")[1].split("\n}")[0]
    assert "appendChild" not in open_fn, \
        "a child of the panel does not outlive the panel's next repaint"
    assert "positionAud()" in open_fn
    assert "#audpop { position: fixed" in UI


def test_the_popover_follows_the_button_after_a_repaint():
    """Repainting moves the button under it, so the anchor has to be
    recomputed or the list ends up somewhere the eye is not."""
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "positionAud()" in render


def test_the_list_aligns_to_the_left_edge_of_its_button():
    pos = SCRIPT.split("function positionAud")[1].split("\n}")[0]
    assert "r.left" in pos and "r.bottom" in pos
    # and it is nudged back on screen rather than running off the right edge
    assert "window.innerWidth" in pos


def test_both_the_control_and_the_list_say_what_they_are():
    """An unlabelled control showing a cab description is just a sentence in a
    box: nothing says it is a cabinet, and nothing says it can be changed."""
    # "MODEL" beside "CABINET" read as a category rather than a name
    assert '<div class="picklabel">CABINET</div>' in UI
    assert '<div class="picklabel">AMP MODEL</div>' in UI
    assert "'AMP MODEL' : 'CABINET'" in SCRIPT or "'CABINET'" in SCRIPT
    assert 'id="audtitle"' in UI


def test_the_grid_scales_to_fit_rather_than_scrolling():
    """A fourteen column preset is 1276 user units wide and the page is capped
    at 1100, so at natural size the chain always overflowed and you had to
    scroll sideways to reach your own output blocks. An SVG with a viewBox
    scales for free."""
    style = UI.split("<style>")[1].split("</style>")[0]
    rule = style.split("svg.grid {")[1].split("}")[0]
    assert "width: 100%" in rule and "height: auto" in rule
    # never blown up past natural size, which would fur the text on wide screens
    assert 'style="max-width:${W}px"' in SCRIPT
    # and a floor, because below some size scrolling beats illegibility
    assert "min-width:" in rule


def test_block_text_is_sized_for_being_scaled_down():
    """Text in an SVG shrinks with the drawing. Sized for the natural width it
    would be unreadable at the 0.8 the grid usually renders at."""
    style = UI.split("<style>")[1].split("</style>")[0]
    nm = style.split("svg.grid .nm {")[1].split("}")[0]
    size = float(re.search(r"font-size: ([\d.]+)px", nm).group(1))
    assert size >= 12, "too small once the grid is scaled to fit"


def test_long_block_names_have_short_forms():
    """"Graphic EQ 2" does not fit a 74px cell, and a name clipped mid-word is
    worse than one shortened on purpose."""
    short = SCRIPT.split("const SHORT = {")[1].split("};")[0]
    for name in ("Graphic EQ", "Compressor", "Volume"):
        assert name in short, name


def test_cab_descriptions_are_not_clipped():
    """The description is how anyone actually finds a cab: "Vibrolux" is in
    the description, not in the name. Clipped to one line it was unreadable
    exactly where it mattered."""
    style = UI.split("<style>")[1].split("</style>")[0]
    det = style.split(".prow .det {")[1].split("}")[0]
    assert "white-space: normal" in det
    # No clamp at all. Two lines still cut the long ones: the longest entry in
    # the catalogue runs to 268 characters, and the median is 56, so most rows
    # stay short and only the rare verbose one is tall.
    assert "line-clamp" not in det
    sub = style.split(".model.sub .audbtn .l {")[1].split("}")[0]
    assert "white-space: normal" in sub
    # and the full text on hover for anything past two lines
    assert 'title="${esc(m.name)}' in SCRIPT


def test_the_amp_and_cab_pickers_sit_side_by_side():
    """Stacked inside a 340px column they were a lopsided tower down one edge,
    and the cab description had nowhere to go. They are the two facts anyone
    looks for first, so they get the full width of the panel and read as a
    pair."""
    style = UI.split("<style>")[1].split("</style>")[0]
    picks = re.search(r"^\s*\.picks \{([^}]*)\}", style, re.M).group(1)
    assert "grid-template-columns: 1fr 1fr" in picks
    # and they fill their cells equally, which the shrink-to-fit wrapper
    # prevented until it was told to be a block
    assert ".pick .aud { display: block; }" in style
    assert ".pick .audbtn { width: 100%; }" in style
    # one column when there is genuinely not room for two
    assert "max-width: 820px) { .picks { grid-template-columns: 1fr; }" in style


def test_the_pickers_are_above_the_parameter_columns():
    """Not inside one of them, which is what made the tower."""
    assert UI.index('<div id="picks">') < UI.index('<div class="knobs" id="knobs-amp">')


# --- every block in the preset, not a hardcoded six ---

def test_the_panel_shows_whatever_the_preset_has(client):
    """The server already read chorus, phaser, flanger, rotary, wah and the
    EQs on every poll. The panel filtered them out with a list of six family
    names, so a preset with a chorus in it offered no way to touch it."""
    assert "PARAM_GROUPS" not in SCRIPT
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "Object.values(meta).map(m => m.family)" in render


def test_an_unnamed_family_still_appears():
    """Hiding a block that IS in the preset is worse than showing it with a
    plain label."""
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "GROUP_NAMES[fam]" in render and "||" in render
    order = SCRIPT.split("const GROUP_ORDER = [")[1].split("];")[0]
    assert "'CHORUS'" in order and "'PHASER'" in order and "'FLANGER'" in order
    # anything not in the order follows rather than vanishing
    assert "!GROUP_ORDER.includes(f)" in render


def test_a_type_picker_appears_only_where_the_names_are_real(client):
    """Chorus, phaser, flanger and pitch each have a type enum (27, 17, 31 and
    16 entries) with NO roster. The catalogue carries none, the ordering is
    undocumented, and the display-name query returns a stale constant rather
    than the current type. "Type 14" is a number pretending to be a choice."""
    pickers = SCRIPT.split("const TYPE_PICKERS = {")[1].split("}")[0]
    assert "DISTORT" in pickers and "REVERB" in pickers and "FUZZ" in pickers
    for blind in ("CHORUS", "PHASER", "FLANGER", "PITCH"):
        assert blind not in pickers, blind


def test_the_named_rosters_are_served(client):
    for kind, least in (("amp", 300), ("drive", 80), ("reverb", 70)):
        d = client.get(f"/api/models?kind={kind}").json()
        assert len(d["banks"][0]["models"]) >= least, kind
        assert all(m["name"] for m in d["banks"][0]["models"]), kind


def test_the_current_type_is_read_from_the_wire_not_the_name_query(client):
    """docs/PROTOCOL.md finding 5: the display-name query returns the roster's
    first entry or a stale constant, verified on two firmware versions by two
    people. Read the wire value and map through a roster."""
    import inspect
    import server
    src = inspect.getsource(server.snapshot)
    assert "_TYPE_NAME" in src and "roster.get" in src
    assert "get_type_name" not in src


def test_setting_a_reverb_type_lands(client):
    before = client.get("/api/state").json()["values"].get("REVERB_TYPE_NAME")
    r = client.post("/api/apply", json={"actions": [{
        "kind": "set_type", "block": "REVERB", "instance": 1,
        "type_name": "8"}]}).json()
    assert r["results"][-1]["ok"]
    after = client.get("/api/state").json()["values"].get("REVERB_TYPE_NAME")
    assert after and after != before


# --- putting a level back ------------------------------------------------

def test_zero_is_only_offered_where_zero_means_something():
    """Two cases and only two: decibels, where 0 is unity, and a range
    symmetric about zero, where 0 is flat or centre. Gain, Mix and Depth all
    run 0 to 10 or 0 to 100, where zero is the BOTTOM and not a default at
    all: offering to reset a gain to 0 would be offering to turn the amp off.
    """
    fn = SCRIPT.split("function neutralOf")[1].split("\n}")[0]
    assert "m.unit === 'db'" in fn
    assert "m.min < 0" in fn and "Math.abs(m.min + m.max)" in fn


def test_the_value_itself_is_the_reset():
    """Dragging a slider onto exactly 0.0 dB is a fiddle nobody should have to
    do, and it is the single most common thing anyone wants a level to be."""
    row = SCRIPT.split("function knobRow")[1].split("\n}")[0]
    assert "neutralOf(m)" in row
    assert 'button class="v reset' in row
    # and it says so rather than relying on the reader guessing
    assert "'set to '" in row


def test_a_value_already_at_zero_offers_nothing():
    row = SCRIPT.split("function knobRow")[1].split("\n}")[0]
    assert "atZero" in row and "' at'" in row
    assert ".knob button.v.at { cursor: default;" in UI


def test_the_reset_goes_through_the_same_verified_write():
    """Not a shortcut around the path everything else uses, so it is read back
    and covered by undo like a drag."""
    handler = SCRIPT.split("button.v.reset")[1].split("\n});")[0]
    assert "blockAction(" in handler and "set_param" in handler


def test_the_button_does_not_inherit_the_global_button_padding():
    """The global rule is 9px 20px, which is right for ENGAGE and blows
    "-15 dB" straight out of a narrow value column. Every default the button
    element brings has to be reset here."""
    style = UI.split("<style>")[1].split("</style>")[0]
    rule = re.search(r"^\s*\.knob button\.v \{([^}]*)\}", style, re.M).group(1)
    for prop in ("padding:", "border:", "background:", "font-family:",
                 "font-size:", "letter-spacing:"):
        assert prop in rule, prop
    # and the column has room for a boxed value
    knob = re.search(r"^\s*\.knob \{ display: grid;([^}]*)\}", style, re.M).group(1)
    assert int(re.search(r"1fr (\d+)px", knob).group(1)) >= 80

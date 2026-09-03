"""One panel per job, instead of one column-flow you have to hunt through.

Moncy's proposal was two sections: amps/cabs/drives, and mod/delay/reverb.
The split here is three, because two does not cover the rig. A noise gate, a
compressor and a volume block are not effects in the sense a player means, and
filing them under EFFECTS to make a two-way split come out even would be a
tidy-looking lie about what those blocks are.
"""
import html
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]
BODY = UI.split("</style>")[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


def _sections():
    block = SCRIPT.split("const SECTIONS = [")[1].split("\n];")[0]
    out = []
    for m in re.finditer(r"\['(\w+)',\s*'([\w-]+)',\s*\[([^\]]*)\]", block):
        fams = re.findall(r"'(\w+)'", m.group(3))
        out.append((m.group(1), m.group(2), fams))
    return out


def _panel_order():
    return [html.unescape(x) for x in re.findall(r'data-label="([^"]+)"', BODY)]


# --- the split itself ------------------------------------------------------

def test_there_are_panels_for_each_job():
    order = _panel_order()
    for label in ("AMP & CAB", "GRAPHIC EQ", "EFFECTS", "DYNAMICS & LEVELS"):
        assert label in order, label


def test_they_read_in_signal_order():
    """What makes the sound, then what shapes it, then what sits around it."""
    order = _panel_order()
    assert order.index("AMP & CAB") < order.index("GRAPHIC EQ") \
        < order.index("EFFECTS") < order.index("DYNAMICS & LEVELS")


def test_the_amp_section_is_the_amp_the_cab_and_the_drive():
    """Moncy's ask, exactly. The cab is not a family of its own: it is the
    CABINET picker in the #picks row, which lives in this panel."""
    amp = dict((box, fams) for _, box, fams in _sections())["knobs-amp"]
    assert set(amp) == {"FUZZ", "DISTORT"}
    picks = BODY.split('id="amppanel"')[1].split("</div>\n\n")[0]
    assert '<div id="picks">' in picks


def test_the_effects_section_is_what_a_player_calls_a_pedal():
    fx = dict((box, fams) for _, box, fams in _sections())["knobs-fx"]
    for fam in ("CHORUS", "FLANGER", "PHASER", "ROTARY", "TREMOLO", "PITCH",
                "DELAY", "MULTITAP", "REVERB", "WAH", "FILTER"):
        assert fam in fx, fam


def test_gates_and_levels_are_not_filed_as_effects():
    """The reason this is three sections and not two."""
    fx = dict((box, fams) for _, box, fams in _sections())["knobs-fx"]
    util = dict((box, fams) for _, box, fams in _sections())["knobs-util"]
    for fam in ("INPUT", "GATE", "COMP", "VOLUME", "PEQ"):
        assert fam in util and fam not in fx, fam


def test_every_family_the_ui_can_name_has_a_home():
    """A block with no section would vanish from the page entirely, which is a
    worse failure than being in the wrong panel."""
    names = re.findall(r"^\s*(\w+): '", SCRIPT.split("const GROUP_NAMES = {")[1]
                       .split("\n};")[0], re.M)
    placed = {f for _, _, fams in _sections() for f in fams} | {"GEQ"}
    assert set(names) - placed == set(), set(names) - placed


def test_an_unknown_family_lands_somewhere_rather_than_nowhere():
    assert "const FALLBACK_BOX = 'knobs-util';" in SCRIPT
    assert "SECTION_OF[fam] || FALLBACK_BOX" in SCRIPT


def test_an_empty_section_does_not_draw():
    """An EFFECTS heading over nothing says this preset has effects and they
    are all at default. For a four-block preset that is simply untrue."""
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "$(panel).style.display = show ? '' : 'none';" in render


# --- the bug the split exposed --------------------------------------------

def test_every_control_container_is_wired_the_same_way():
    """The graphic EQ moved into its own panel and its faders went dead: the
    listeners were bound to one element by id, and #geqbox is not that
    element. The markup was right, the write path was right, the API call was
    right, and the control did nothing. Found by dragging one in a real
    browser, which is the only place it was visible.
    """
    assert "$('knobs')" not in SCRIPT, "no handler may be bound to one box by id"
    boxes = re.search(r"const CONTROL_BOXES = \[([^\]]*)\]", SCRIPT).group(1)
    for box in ("picks", "knobs-amp", "geqbox", "knobs-fx", "knobs-util"):
        assert f"'{box}'" in boxes, box
    # and every listener over a control goes through it, so adding a panel is
    # one entry in CONTROL_BOXES rather than five listeners to remember
    assert SCRIPT.count("eachBox(box => box.addEventListener(") >= 5
    for box in ("knobs-amp", "geqbox", "knobs-fx", "knobs-util", "picks"):
        assert f"$('{box}').addEventListener" not in SCRIPT, box


def test_the_boxes_all_exist_in_the_markup():
    """A typo'd id would silently drop a whole panel's controls, because
    eachBox skips what it cannot find."""
    boxes = re.findall(r"'([\w-]+)'",
                       re.search(r"const CONTROL_BOXES = \[([^\]]*)\]", SCRIPT).group(1))
    for box in boxes:
        assert f'id="{box}"' in BODY, box


def test_a_band_label_never_reaches_the_log_either():
    """describe() fell back to the catalogue's displayLabel, so a fader that
    deliberately shows no frequency was recorded in the log as "250: 2". The
    log is the record of what was written to the rig; a wrong name there is
    the same wrong number in the one place it is kept."""
    fn = SCRIPT.split("function describe(a)")[1].split("\n}\n")[0]
    assert "geqKeys.indexOf(a.param)" in fn
    assert "Graphic EQ band ${band + 1}" in fn
    assert fn.index("geqKeys.indexOf") < fn.index("lastParams[a.param]"), \
        "the fallback must not get there first"


# --- and it still shows whatever the preset actually has -------------------

def test_the_sections_between_them_show_every_block(client):
    """Nothing may be lost in the split."""
    meta = client.get("/api/state").json()["params"]
    fams = {m["family"] for m in meta.values()}
    placed = {f for _, _, fams_ in _sections() for f in fams_} | {"GEQ"}
    assert fams <= placed, fams - placed


# --- the signal chain says what is loaded, not just what kind of block ----

def test_a_block_cell_shows_the_model_in_it():
    """"Amp 1" tells you nothing you could not read off the unit. "JP IIC+
    Red" is the thing you opened the page to check."""
    assert "function blockModel(family)" in SCRIPT
    fn = SCRIPT.split("function blockModel(family)")[1].split("\n}\n")[0]
    assert "v.AMP_MODEL" in fn and "v.cab" in fn
    assert "_TYPE_NAME" in fn
    assert 'class="sub"' in SCRIPT


def test_an_unresolved_ordinal_is_never_shown_as_a_name():
    """values.cab is a description when the cabinet is in the roster and a
    bare number when it is not. "6" under a Cab block looks like a setting and
    means nothing, which is the same rule this project follows everywhere: an
    unresolved ordinal is not a name. Observed live on preset 511."""
    fn = SCRIPT.split("function blockModel(family)")[1].split("\n}\n")[0]
    assert "test(text)" in fn and "\\d+" in fn
    assert "ordinal " in fn


def test_the_cab_sentence_is_cut_at_its_own_name():
    """A cab description is a sentence: "2x12 SANTIAGO EJ1250 = 12in Eminence
    ... in a Fender closed-back cabinet". The half before the equals sign is
    the cab's name, and that is what fits on a 74px cell."""
    fn = SCRIPT.split("function blockModel(family)")[1].split("\n}\n")[0]
    assert "split(' = ')[0]" in fn


def test_the_model_fits_the_cell_rather_than_overflowing_it():
    """The channel badge starts at x + CW - 19, so the text has 45px. Measured
    rather than guessed."""
    fn = SCRIPT.split("function fitCell(text)")[1].split("\n}\n")[0]
    assert "CELL_CHARS" in fn
    assert "USA|UK" in fn, "the marque is not the identifying part"


def test_the_tooltip_carries_the_full_name():
    """The cell is truncated; hovering should give the whole thing."""
    assert "${model ? ': ' + esc(model) : ''}" in SCRIPT


# --- the command box is the product and should look like it ---------------

def test_the_command_panel_is_set_apart():
    """Every other panel reports on the rig or acts on one block. This is the
    one that does the thing the tool exists for, and it was styled identically
    to the log."""
    # The command surface is the Request stage pane now: its own stage,
    # not a panel competing with the log for styling.
    assert '<section class="stagepane" id="pane-request">' in BODY
    style = UI.split("<style>")[1]
    assert re.search(r"^\s*#engage \{", style, re.M)


def test_it_shows_what_it_can_do_rather_than_claiming_it():
    """Placeholder text teaches one example. Six loadable ones teach the
    vocabulary, and are the fastest way for somebody who just cloned this to
    see it work."""
    assert "const EXAMPLES = [" in SCRIPT
    block = SCRIPT.split("const EXAMPLES = [")[1].split("\n];")[0]
    assert block.count("['") >= 6
    for phrase in ("drop C", "JCM800", "expression pedal", "scene 2"):
        assert phrase in block, phrase


def test_an_example_loads_but_does_not_send():
    """Seeing the sentence is half of what the examples teach, and pressing
    ENGAGE stays the player's move."""
    fn = SCRIPT.split("$('egs').addEventListener('click'")[1].split("\n});")[0]
    assert "$('prompt').value = EXAMPLES" in fn
    assert "fetch(" not in fn
    assert "$('engage').click" not in fn and "planPrompt" not in fn


# --- the chain, big enough to actually read -------------------------------

def test_the_enlarged_view_is_a_clone_not_a_second_renderer():
    """One drawing means the enlarged view cannot disagree with the small one,
    which is the entire point of opening it."""
    fn = SCRIPT.split("function openGrid()")[1].split("\n}\n")[0]
    assert "svg.cloneNode(true)" in fn
    assert "renderGrid" not in fn


def test_a_block_click_selects_and_the_space_around_it_expands():
    """The small drawing is an overview, but a block on it now SELECTS: the
    Inspector opens on what was clicked, which is how manual control attaches
    to the signal chain. The space around the chain still opens the enlarged
    review, where bypass and channel have readable targets."""
    fn = SCRIPT.split("$('blocks').addEventListener('click', e => {")[1] \
               .split("\n});")[0]
    assert "selectBlock(cell.dataset.fam)" in fn
    assert "openGrid();" in fn


def test_bypass_and_channel_move_into_the_enlarged_view():
    """They are not lost, they move to where the target is twice the size and
    you can read what you are about to switch off. Same handler, different
    container, so there is no second copy to keep in step."""
    fn = SCRIPT.split("$('gridbig').addEventListener('click', e => {")[1].split("\n});")[0]
    assert "set_bypass" in fn and "set_channel" in fn
    assert "data-cyc" in fn


def test_clicking_off_the_chain_closes_it():
    """In a view opened to read the chain, the space around the chain is the
    obvious way out."""
    fn = SCRIPT.split("$('gridbig').addEventListener('click', e => {")[1].split("\n});")[0]
    assert "if (!btn) { closeGrid(); return; }" in fn


def test_it_is_drawn_at_twice_size_and_allowed_to_scroll():
    """Fitting the width was the wrong trade once this became the view you ACT
    in: a block you can read is worth more than a whole chain at a size you
    cannot aim at."""
    fn = SCRIPT.split("function openGrid()")[1].split("\n}\n")[0]
    assert "naturalW * 2" in fn
    style = UI.split("<style>")[1]
    assert re.search(r"#gridbig \{[^}]*overflow-x: auto", style)


def test_the_scroll_gesture_cannot_escape_to_the_os():
    """A two-finger swipe past the end of the container drags macOS
    Notification Centre in instead of moving the chain. It bites hardest on a
    SHORT chain, where there is no scroll to absorb the gesture at all, so a
    long one feeling fine proves nothing."""
    style = UI.split("<style>")[1]
    assert re.search(r"#gridbig \{[^}]*overscroll-behavior: contain", style)


def test_the_enlarged_copy_follows_the_rig_while_it_is_open():
    """It is the view being acted in now, so a bypass toggled there has to
    redraw there. A copy showing the state from before your own click is worse
    than no copy."""
    assert "if (gridOpen) openGrid();" in SCRIPT
    assert "gridOpen = true;" in SCRIPT and "gridOpen = false;" in SCRIPT


def test_there_are_three_ways_out():
    assert "$('gridclose').onclick = closeGrid;" in SCRIPT
    assert "e.target === $('gridmodal')" in SCRIPT     # the backdrop
    assert "e.key === 'Escape'" in SCRIPT


def test_closing_does_not_leave_a_stale_rig_behind():
    """A clone is a photograph. Kept around, it shows a preset that may since
    have changed."""
    fn = SCRIPT.split("function closeGrid()")[1].split("\n}\n")[0]
    assert "$('gridbig').innerHTML = '';" in fn

"""Two ways to work, one at a time.

Saying what you want and turning a knob are different activities. One wants
room to read a conversation back, the other wants every control at once, and
they were competing for the same screen: the loser was whichever you happened
to want that day.

What stays OUTSIDE both tabs is the load-bearing decision here, not the split
itself.
"""
import re
from pathlib import Path

UI = (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text()


def _panel_owner(label):
    """Which tab a panel lives in: 'ai', 'manual' or '' for neither."""
    at = UI.index(f'data-label="{label}"')
    ai = UI.index('<div id="tab-ai"')
    mid = UI.index('<div id="tab-manual"')
    end = UI.index("</div>", UI.index('data-label="PRESET HEALTH"'))
    if ai < at < mid:
        return "ai"
    if mid < at < UI.index('data-label="UNDO / COMPARE"'):
        return "manual"
    return ""


def test_asking_and_knobs_are_separated():
    assert _panel_owner("COMMAND") == "ai"
    assert _panel_owner("PROPOSED CHANGES") == "ai"
    for knobs in ("AMP &amp; CAB", "GRAPHIC EQ", "EFFECTS",
                  "DYNAMICS &amp; LEVELS"):
        assert _panel_owner(knobs) == "manual", knobs


def test_what_you_are_looking_at_is_in_neither():
    """SCENES and the chain are the subject in BOTH modes. Tabbing away from
    the picture of your own signal path would be a loss, not a simplification.
    """
    for shared in ("SCENES", "SIGNAL CHAIN"):
        assert _panel_owner(shared) == "", shared
    assert UI.index('data-label="SCENES"') < UI.index('<div class="tabs"')


def test_undo_and_save_are_never_behind_a_tab():
    """Hiding undo behind a tab would be actively unsafe: it covers what
    EITHER half just did, and you reach for it when something went wrong."""
    for always in ("UNDO / COMPARE", "SAVE TO PRESET", "LOG"):
        assert _panel_owner(always) == "", always


def test_a_pending_plan_is_never_left_behind_a_tab():
    """Nothing transmits without the button, so a hidden panel is not
    dangerous in itself. But a proposal you cannot see is one you cannot
    refuse either, and it would sit there looking like nothing happened."""
    fn = UI.split("function showPlan(plan)")[1].split("\n}\n")[0]
    assert "showTab('ai')" in fn


def test_the_choice_is_remembered():
    assert "const TAB_KEY = 'tonecommand.tab.v1';" in UI
    fn = UI.split("function showTab(which)")[1].split("\n}\n")[0]
    assert "localStorage.setItem(TAB_KEY, on)" in fn
    assert "catch" in fn, "a private window must not break the tabs"


def test_an_unknown_stored_tab_falls_back_rather_than_showing_nothing():
    fn = UI.split("function showTab(which)")[1].split("\n}\n")[0]
    assert "which === 'manual' ? 'manual' : 'ai'" in fn


def test_both_panels_and_both_buttons_exist_exactly_once():
    for ident in ("tab-ai", "tab-manual", "tab-ai-btn", "tab-manual-btn"):
        assert UI.count(f'id="{ident}"') == 1, ident


def test_the_manual_tab_starts_hidden_and_hidden_actually_hides():
    assert re.search(r'<div id="tab-manual"[^>]*\shidden>', UI)
    assert "[hidden] { display: none !important; }" in UI


def test_the_tabs_are_reachable_by_keyboard_and_announced():
    """They are buttons with roles, not divs with click handlers."""
    bar = UI.split('<div class="tabs"')[1].split("</div>")[0]
    assert bar.count("<button") == 2
    assert 'role="tablist"' in UI.split("\n")[
        [i for i, l in enumerate(UI.split("\n")) if 'class="tabs"' in l][0]]
    assert 'aria-selected' in bar and 'aria-controls' in bar
    fn = UI.split("function showTab(which)")[1].split("\n}\n")[0]
    assert "aria-selected" in fn, "the announced state has to follow the visible one"

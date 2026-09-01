"""The blast-radius warning goes out when the plan that raised it goes away.

FM9 parameters live on the channel, not the scene, so changing one moves every
scene sharing that channel. The UI lights those scenes amber rather than
burying the fact in small print under the plan card.

Lighting it was the easy half. The bug this pins is the other half: the
warning belongs to a pending plan, so when the plan is discarded, refused,
applied or replaced by a clarification, the amber has to go out with it.
Clearing the set alone was not enough, because nothing repaints until the next
five-second poll, and in the meantime the UI warned about scenes that nothing
was going to touch.
"""
from pathlib import Path

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


def test_the_warning_is_only_ever_dropped_through_the_helper():
    """One way out, so a new exit path cannot forget to repaint.

    Two mentions are allowed and no more: the declaration, and the assignment
    inside clearAffected() itself. Anything else is a path that empties the set
    while leaving the buttons lit.
    """
    assert UI.count("affectedScenes = new Set()") == 2, (
        "a code path clears the warning without un-painting it; "
        "call clearAffected() instead"
    )


def test_the_helper_removes_the_class_as_well_as_the_state():
    body = UI.split("function clearAffected()")[1].split("\n}")[0]
    assert "affectedScenes = new Set()" in body
    assert "classList.remove('willchange')" in body


def test_every_way_a_plan_can_end_puts_the_warning_out():
    for path in ("plan discarded",          # discard button
                 # The planner asking a question instead of acting. It used to
                 # be logged as "needs clarification"; it is now pushed into
                 # the conversation, where it can actually be answered.
                 "content: plan.clarification",
                 ):
        seg = UI.split(path)[1][:400]
        assert "clearAffected()" in UI.split(path)[0][-400:] or "clearAffected()" in seg, path


# --- AI settings sit behind a header button, not on the front page ---
# Choosing a planner backend is a once-a-month errand. It held a full console
# on the main screen, above the log, competing with the controls you touch
# every session. Moving markup is where element references quietly break, so
# these pin the move rather than trusting a read of the diff.

import re

SCRIPT = UI.split("<script>")[1]


def test_the_settings_panel_is_behind_the_button_not_on_the_page():
    modal = UI.split('<div class="modal" id="aimodal"')[1]
    for control in ("aibackend", "aikey", "aisave", "aiclearkey"):
        assert f'id="{control}"' in modal, f"{control} escaped the modal"
    assert UI.count('data-label="AI SETTINGS"') == 1
    assert 'id="aiopen"' in UI.split("<script>")[0].split('id="aimodal"')[0], \
        "no way to reach the panel from the header"


def test_it_opens_closed():
    assert re.search(r'<div class="modal" id="aimodal" hidden>', UI), \
        "the panel must start hidden or it is not out of the way at all"


def test_every_element_the_script_reaches_for_still_exists():
    """The failure mode of moving markup: a live reference to a dead id.

    Ids the script creates itself are exempt, which is why the check reads
    assignments as well as markup.
    """
    declared = set(re.findall(r'\bid="([^"]+)"', UI))
    created = set(re.findall(r"\.id = '([^']+)'", SCRIPT))
    used = set(re.findall(r"\$\('([^']+)'\)", SCRIPT))
    assert not (used - declared - created)


def test_no_id_is_declared_twice():
    """getElementById would silently pick the first, so a stray duplicate left
    behind by a move would half-work, which is worse than breaking."""
    ids = re.findall(r'\bid="([^"]+)"', UI)
    assert len(ids) == len(set(ids)), \
        [i for i in set(ids) if ids.count(i) > 1]


def test_the_gear_carries_no_label():
    """It briefly showed the backend name, which made a settings gear look
    like it was called AUTO. A label on a control names the control. Which
    model answered belongs on the plan it produced, where it already is."""
    gear = re.search(r'<button class="gear".*?</button>', UI, re.S).group(0)
    assert "<svg" in gear and "</svg>" in gear
    assert not re.search(r">\s*[A-Za-z]", gear.split("<svg")[0].split(">", 1)[1]), \
        "text next to the icon names the control, not the backend"
    assert "ailabel" not in UI


def test_the_gear_is_drawn_not_typed():
    """U+2699 is drawn small inside its own em box, so raising font-size moved
    it barely at all and it stayed a speck beside the LINK pill. A path is
    sized by the numbers we give it."""
    assert "&#9881;" not in UI
    gear = re.search(r'<button class="gear".*?</button>', UI, re.S).group(0)
    size = re.search(r'width="(\d+)"', gear)
    assert size and int(size.group(1)) >= 18, "still too small to hit comfortably"


def test_the_gear_is_last_in_the_header_and_quiet():
    """Out of the way means after the status readout, not interrupting it,
    and without the border that would make it read as a third status pill."""
    status = UI.split('<div class="status">')[1].split("</header>")[0]
    assert status.index('id="aiopen"') > status.index('id="link"')
    style = UI.split("  .gear {")[1].split("}")[0]
    assert "border: none" in style and "background: none" in style


def test_which_backend_is_driving_is_still_reachable_before_a_plan_runs():
    """Quiet is not the same as silent: the tooltip answers it on hover, and
    it reads from the saved settings rather than the dropdown, which can be
    sitting on a selection the user never saved."""
    assert "$('aiopen').title" in SCRIPT
    load = SCRIPT.split("async function loadAiSettings()")[1].split("\n}")[0]
    assert "aiGear(d.settings.backend" in load


def test_a_backend_that_cannot_run_is_flagged_on_the_button():
    """Hiding the panel must not hide a broken planner: ENGAGE would fail with
    the explanation stuck behind a button nothing told you to press."""
    assert "classList.toggle('needs'" in SCRIPT
    assert ".gear.needs" in UI


def test_closing_drops_a_typed_key():
    body = SCRIPT.split("function aiModal(")[1].split("\n}")[0]
    assert "$('aikey').value = ''" in body, \
        "a typed key must not sit in the DOM after the panel closes"


# --- the warning has to be seen, not merely present ---
# It was a thin amber outline, and it was correct: the class landed, the logic
# agreed with the plan card exactly. It failed anyway, because an outline among
# eight boxes, next to an active scene carrying a fill and a glow and a dot, is
# something you find only if you already know to look. This warning exists for
# the case where the small print under the plan card was not read, so it is
# weighted to match the active state rather than to whisper under it.

def test_the_warning_is_as_loud_as_the_active_scene():
    warn = UI.split(".sc.willchange {")[1].split("}")[0]
    for prop in ("background", "box-shadow", "border-color"):
        assert prop in warn, f"the warning has no {prop}, so it is an outline"


def test_it_says_what_it_means():
    """Colour says something is different. It does not say what. The badge
    names it, in the corner where the active scene keeps its dot."""
    badge = UI.split(".sc.willchange::after {")[1].split("}")[0]
    assert "WILL CHANGE" in badge


def test_the_badge_does_not_collide_with_the_active_dot():
    """A scene can be both current and about to change."""
    assert ".sc.on.willchange::after { display: none; }" in UI


def test_the_sentence_agrees_with_itself():
    """"scene 5, which share this block's channel" reads as a typo, on the one
    sentence in the product whose whole job is to be believed."""
    assert "'share' : 'shares'" in SCRIPT or '"share" : "shares"' in SCRIPT


# --- deleting dead CSS must not take live CSS with it ---

def test_every_class_the_page_uses_has_a_rule():
    """The regression this exists for: removing the old flat block list's
    styling took a 7KB run of the stylesheet with it, including every rule for
    the TONE panel. The sliders reverted to browser default blue and the
    health rows lost their layout. Nothing failed, because no test looked at
    the stylesheet, and the tell arrived from Moncy as "the whole look and
    feel of the amp section changed".

    So: every class name the markup or the render functions attach must have
    at least one rule somewhere in the stylesheet.
    """
    style = UI.split("<style>")[1].split("</style>")[0]
    used = set()
    # class="..." in markup and in template literals
    for chunk in re.findall(r'class="([^"$]*)"', UI):
        used.update(c for c in chunk.split() if c)
    # classList.add/remove/toggle('x')
    used.update(re.findall(r"classList\.(?:add|remove|toggle)\('([\w-]+)'", SCRIPT))
    styled = set(re.findall(r'\.([A-Za-z][\w-]*)', style))
    missing = sorted(c for c in used - styled if not c.startswith('_'))
    assert not missing, f"used but unstyled: {missing}"


def test_the_slider_styling_is_present():
    """Named explicitly because its absence is invisible to every other test:
    a range input with no rules still works, it just looks like a web form
    from 2005 in the middle of a panel that does not."""
    style = UI.split("<style>")[1].split("</style>")[0]
    for rule in ("slider-runnable-track", "slider-thumb", ".knob", ".knobs"):
        assert rule in style, rule


# --- what you see without scrolling ---

def test_the_signal_chain_comes_before_the_prompt():
    """It answers "what does my rig look like right now", which is the
    question you arrive with. Fourth panel down it started at 521px, below the
    fold on a laptop, so the rig you came to look at needed a scroll."""
    order = re.findall(r'data-label="([^"]+)"', UI)
    order = [x for x in order if x not in ("PROPOSED CHANGES", "AI SETTINGS")]
    assert order.index("SIGNAL CHAIN") < order.index("COMMAND")
    assert order.index("SCENES") < order.index("SIGNAL CHAIN")
    # undo is reached after a change, not before one
    assert order.index("UNDO / COMPARE") > order.index("AMP &amp; CAB")


def test_the_model_selectors_look_like_selectors():
    """As bare text with a hover border they read as a caption, so nobody
    discovers that the two most interesting facts on the page are also the two
    things easiest to change."""
    # anchored on the base rule: a plain split started matching
    # ".pick .audbtn", a later override that only sets a width
    style = UI.split("<style>")[1].split("</style>")[0]
    rule = re.search(r"^\s*\.audbtn \{([^}]*)\}", style, re.M).group(1)
    assert "border:" in rule and "background:" in rule


def test_the_chevron_is_drawn_not_typed():
    """U+25BE renders small inside its own em box and came out as a speck, the
    same way U+2699 did on the settings gear. A triangle made of borders is
    exactly the size we say it is."""
    # Intent, not pixels. The first version pinned "border-top: 6px solid",
    # so nudging the chevron to 7px reported it missing, and it matched the
    # U+25BE in the comment explaining why the glyph was abandoned.
    markup = UI.split("</style>")[1]
    assert "\u25be" not in markup.lower(), "the glyph is back in the markup"
    # Anchored on the rule itself. A plain substring split started matching
    # ".model.sub .audbtn::after", a later override that only nudges margin,
    # and reported the chevron missing when it was untouched.
    style = UI.split("<style>")[1].split("</style>")[0]
    after = re.search(r"^\s*\.audbtn::after \{([^}]*)\}", style, re.M).group(1)
    assert "border-left" in after and "border-top" in after


def test_the_warning_is_called_a_blast_radius():
    """Moncy named it and the name is good, so it is the name on screen too.
    A warning you can refer to by name is one people repeat to each other."""
    assert "blast radius:" in SCRIPT
    spread = SCRIPT.split("function alsoAffects")[1].split("\n}")[0]
    assert "blast radius" in spread


# --- a result that is about the plan, not about one action ---

def test_a_null_action_does_not_crash_the_transmit():
    """Brian's bug, on an empty preset where add_block legitimately refuses.

    The server appends {"action": null} to say the remaining actions were
    skipped, which is a protective guard: running them would bind modifiers to
    a block that never landed, observed on hardware on 2026-08-20. The UI read
    .kind off that null, threw inside the result loop, and replaced the
    server's useful explanation with "Cannot read properties of null".
    """
    assert "if (!a) return 'plan halted';" in SCRIPT
    body = SCRIPT.split("async function apply()")[1].split("\n}\n")[0]
    assert "res.action && res.action.kind" in body


def test_result_cards_are_not_knocked_out_of_step_by_extra_results():
    """Results do not line up with cards one for one: a failed undo snapshot
    is prepended and a skip note appended, neither of which is a card. Indexed
    naively, every card after an extra result takes the wrong outcome."""
    body = SCRIPT.split("async function apply()")[1].split("\n}\n")[0]
    assert "let card = 0" in body
    assert "cards[card]" in body and "cards[i]" not in body


def test_the_app_carries_the_mark():
    """In the header beside the wordmark, and on the tab. The mark is what you
    recognise among twenty tabs; the wordmark is what you read."""
    assert 'class="brand"' in UI
    assert 'src="/logo.png"' in UI
    assert 'rel="icon"' in UI
    style = UI.split("<style>")[1].split("</style>")[0]
    assert ".brand {" in style


def test_every_dropdown_arrow_is_the_same_drawn_triangle():
    """The third control on this page to hit the same thing. U+25BE is
    rendered small inside its own em box, so the preset caret came out
    noticeably smaller than the amp and cab chevrons beside it whatever font
    size it was given. A glyph is not a shape you can size.
    """
    style = UI.split("<style>")[1].split("</style>")[0]
    caret = re.search(r"^\s*\.pillbtn \.caret \{([^}]*)\}", style, re.M).group(1)
    chevron = re.search(r"^\s*\.audbtn::after \{([^}]*)\}", style, re.M).group(1)
    for rule in (caret, chevron):
        assert "border-left: 6px solid transparent" in rule
        assert "border-top: 7px solid" in rule
    # and no glyph left behind to show through the triangle
    assert "&#9662;" not in UI


def test_hidden_actually_hides():
    """`hidden` carries display:none from the BROWSER's stylesheet, so any
    author rule setting display beats it. Three elements here are laid out
    with display:flex and were visible while hidden: the example chips stayed
    under an open conversation, and the service chips stayed on backends that
    have no endpoint at all. Stated once rather than rediscovered per
    element."""
    assert "[hidden] { display: none !important; }" in UI
    # and it must come before the rules it has to beat
    assert UI.index("[hidden] { display: none !important; }") < UI.index(".egs {")

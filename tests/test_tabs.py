"""The five-stage command rail, which replaced the two tabs.

DESIGN WITH AI / MANUAL implied two separate products and forced users to
remember which side held a control. The rail states the one workflow instead:
REQUEST -> PLAN -> REVIEW -> CONFIRM -> SEND. What stays OUTSIDE the stages
is still the load-bearing decision: the live context, the shelf with Undo,
and the drawers are visible or reachable from every stage.
"""
import re
from pathlib import Path

UI = (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]


def test_the_five_stages_exist_exactly_once_in_order():
    order = [UI.index(f'id="stg-{name}"')
             for name in ("request", "plan", "review", "confirm", "send")]
    assert order == sorted(order)
    for name in ("request", "plan", "review", "confirm", "send"):
        assert UI.count(f'id="stg-{name}"') == 1
        assert UI.count(f'id="pane-{name}"') == 1


def test_stages_are_gated_not_free_navigation():
    """Plan and Review need a plan; Confirm refuses blockers; Send is only
    entered by the armed control, never by clicking the rail cold."""
    gate = SCRIPT.split("function canEnter")[1].split("\n}")[0]
    assert "!!currentPlan" in gate
    assert "hasBlockers()" in gate
    assert "planSending || stageDone.send" in gate


def test_what_you_are_looking_at_is_outside_every_stage():
    """Scenes and the signal path are the subject in EVERY stage. Hiding the
    picture of your own rig during Review would conceal the blast radius."""
    ctx = UI.index('id="context"')
    assert ctx < UI.index('id="workspace"')
    assert UI.index('id="scenes"') < UI.index('id="pane-request"')
    assert UI.index('id="blocks"') < UI.index('id="pane-request"')


def test_undo_is_on_the_shelf_never_behind_a_stage():
    """Undo is the most important recovery action and never depends on
    scroll or stage."""
    shelf = UI.index('id="shelf"')
    assert UI.index('id="undo"') > shelf
    assert UI.index('id="pane-send"') < shelf, "the shelf sits below the stages"


def test_a_pending_plan_is_never_left_behind_navigation():
    """A proposal you cannot see is one you cannot refuse. showPlan enters
    the PLAN stage itself rather than hoping the reader finds it."""
    body = SCRIPT.split("function showPlan")[1].split("\nfunction ")[0]
    assert "setStage('plan')" in body


def test_the_final_send_control_exists_only_in_confirm():
    """One SEND TO FM9 button, inside the Confirm stage, hidden until armed.
    No other control may carry the reserved word SEND toward hardware."""
    markup = UI.split("<script>")[0]
    assert markup.count('id="apply"') == 1
    confirm = markup.split('id="pane-confirm"')[1].split("</section>")[0]
    assert 'id="apply"' in confirm
    assert "SEND TO FM9" in confirm
    assert 'hidden>SEND TO FM9' in confirm.replace("\n", " ") or \
           re.search(r'id="apply"\s+hidden', confirm)


def test_arming_is_acknowledge_then_arm_then_eight_seconds():
    assert "I reviewed the target and affected scenes" in UI
    assert "armLeft = 8" in SCRIPT
    assert "Esc to disarm" in UI
    # Esc genuinely disarms, and target changes disarm from the poll.
    assert "disarmSend(); return;" in SCRIPT
    assert "function stageGuard" in SCRIPT


def test_the_send_stage_never_claims_audible_success():
    assert "EARS: PENDING" in SCRIPT
    assert "PRESET NOT STORED" in SCRIPT


def test_the_request_action_does_not_say_send():
    markup = UI.split("<script>")[0]
    composer = markup.split('id="pane-request"')[1].split("</section>")[0]
    assert 'id="engage">GENERATE PLAN<' in composer
    assert ">SEND<" not in composer


def test_no_keyboard_shortcut_reaches_the_final_send():
    """Cmd/Ctrl+Enter may generate a plan; nothing on the keyboard may
    transmit to hardware."""
    keys = SCRIPT.split("// Cmd/Ctrl+Enter generates a plan")[1] \
                 .split("addEventListener('beforeunload'")[0]
    assert "talk()" in keys
    assert "apply()" not in keys


def test_only_one_utility_drawer_opens_at_a_time():
    body = SCRIPT.split("function openDrawer")[1].split("\nfunction ")[0]
    assert "key !== name" in body, "opening one drawer hides the rest"


def test_the_poll_cannot_wipe_the_acknowledgement():
    """renderGig runs on every five-second poll tick, and an unconditional
    Confirm redraw reset the acknowledgement checkbox faster than a person
    could check it and arm (owner, 2026-09-02)."""
    fn = SCRIPT.split("const plainGig = renderGig;")[1].split("\n}")[0]
    assert "changed = on !== gigOn" in fn
    assert "changed && stage === 'confirm'" in fn

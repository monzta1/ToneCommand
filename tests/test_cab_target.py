"""CabTarget: the minimal resolved cab intent (brief 19.5, 26.5).

Direct, behavioural coverage of the new type: real calls to
`CabTarget.from_plan`, asserted on the real dataclass it returns, never a
source-string check.
"""
from __future__ import annotations

from fm9.cab_target import CabTarget


def test_a_blank_cab_need_is_unreadable():
    t = CabTarget.from_plan({"cab_need": ""}, {"state": "unresolved"})
    assert t.readable is False
    assert t.gear is None


def test_a_null_cab_need_is_unreadable():
    t = CabTarget.from_plan({"cab_need": None}, {"state": "unresolved"})
    assert t.readable is False


def test_gear_words_are_readable_and_stripped():
    t = CabTarget.from_plan({"cab_need": "  4x12 v30 bright lead  "},
                            {"state": "unresolved"})
    assert t.readable is True
    assert t.gear == "4x12 v30 bright lead"


def test_the_players_own_words_are_carried_not_the_models():
    """The request comes from the plan's `request`/`prompt` field, which is
    the player's own words, set by _plan_for BEFORE the selector runs. A
    model's summary must never substitute for it (brief 26.4)."""
    t = CabTarget.from_plan(
        {"cab_need": "darker", "request": "keep the same cab but darker",
         "summary": "keeps the same speaker, similar character"},
        {"state": "unresolved"})
    assert t.request == "keep the same cab but darker"


def test_request_falls_back_to_prompt_then_to_empty():
    t = CabTarget.from_plan({"cab_need": "darker", "prompt": "make it darker"},
                            {"state": "unresolved"})
    assert t.request == "make it darker"
    t2 = CabTarget.from_plan({"cab_need": "darker"}, {"state": "unresolved"})
    assert t2.request == ""


def test_a_gear_anchored_anchor_preserves_its_identity():
    t = CabTarget.from_plan({"cab_need": "darker"},
                            {"state": "gear_anchored", "gear": "4x12 RECTO SM57"})
    assert t.preserve == "4x12 RECTO SM57"


def test_a_measured_anchor_preserves_too():
    """A curve is not the same promise as keeping the cabinet, so a measured
    anchor still offers its gear as a preserve constraint (brief 21.5)."""
    t = CabTarget.from_plan({"cab_need": "darker"},
                            {"state": "measured", "gear": "4x12 Celestion V30"})
    assert t.preserve == "4x12 Celestion V30"


def test_an_unresolved_anchor_never_preserves():
    t = CabTarget.from_plan({"cab_need": "darker"},
                            {"state": "unresolved", "gear": "4x12 RECTO SM57"})
    assert t.preserve is None


def test_a_whole_rig_build_never_preserves_even_when_gear_anchored():
    """Replacing the cab by definition, so there is nothing to keep."""
    t = CabTarget.from_plan({"cab_need": "4x12 v30", "whole_rig": True},
                            {"state": "gear_anchored", "gear": "1x4 Pig 57"})
    assert t.preserve is None


def test_a_measured_anchors_own_name_is_not_gear():
    """A measured anchor with no catalogue gear (a plain label the player
    typed) must not preserve on it. `gear` absent means no preserve, even
    though `name` may be set (brief 26.1)."""
    t = CabTarget.from_plan(
        {"cab_need": "darker"},
        {"state": "measured", "name": "Soldano SLO30 - Emil Rohbe"})
    assert t.preserve is None


def test_preserve_prefers_gear_then_fractal_then_models():
    t = CabTarget.from_plan(
        {"cab_need": "darker"},
        {"state": "gear_anchored", "fractal": "4x12 RECTO SM57",
         "models": "Mesa Rectifier 4x12"})
    assert t.preserve == "4x12 RECTO SM57"
    t2 = CabTarget.from_plan(
        {"cab_need": "darker"},
        {"state": "gear_anchored", "models": "Mesa Rectifier 4x12"})
    assert t2.preserve == "Mesa Rectifier 4x12"

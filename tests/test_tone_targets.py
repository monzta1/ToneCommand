"""Issue #50: why absolute parameter floors were tried, and why they were removed.

v1 turned the rulebook's adjectives into numeric floors, each sitting just above
a value the owner had rejected in one build. Checked against 104 scenes from 13
presets of AustinBuddy's '25 pack, read off the owner's own FM9, those floors
raised 196 FAIL findings against professionally voiced, gig-ready work.

The tests below pin the retraction, so nobody reintroduces the floors without
first beating the evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import server
from fm9 import tone_review
from fm9.tone_review import Scene

FIXTURE = Path(__file__).resolve().parent / "data" / "austinbuddy_sample.json"


def role_of(name: str):
    n = (name or "").lower()
    if any(w in n for w in ("lead", "solo", "burn")):
        return "lead"
    if any(w in n for w in ("clean", "cln", "spank", "chime")):
        return "clean"
    if any(w in n for w in ("rhythm", "rhy", "crunch", "chug", "grind")):
        return "rhythm"
    return None


def professional_presets():
    """Real scenes read off the hardware, grouped by preset."""
    rows = json.loads(FIXTURE.read_text())
    by = {}
    for r in rows:
        by.setdefault(r["preset"], []).append(
            Scene(n=r["scene"], name=r["scene_name"],
                  role=role_of(r["scene_name"]),
                  amp_gain=r["drive"], amp_level=r["amp_level"],
                  fx_mix={k.upper(): r[k] for k in ("reverb", "delay", "chorus")
                          if r.get(k) is not None}))
    return by


# --- the retraction, pinned -------------------------------------------

def test_the_absolute_floors_are_gone():
    """Removed, not tuned. Their reintroduction should break this."""
    pol = tone_review.targets()
    assert pol.get("version", 0) >= 2
    assert "all_roles" not in pol, "the amp-level floor must not come back"
    for spec in (pol.get("roles") or {}).values():
        assert "mix_min" not in spec, "effect-mix floors must not come back"
        assert "amp_level_min" not in spec


def test_the_policy_records_why_it_was_refuted():
    raw = json.loads(tone_review.TARGETS_PATH.read_text())
    text = json.dumps(raw).lower()
    assert "refuted" in text
    assert "196" in text and "104" in text, "keep the measured counts"
    assert "output trim" in text, "keep WHY the parameter cannot work"


@pytest.mark.parametrize("preset", list(professional_presets()))
def test_professional_presets_raise_no_findings_from_the_numeric_policy(preset):
    """The floors used to fail every one of these scenes. Whatever the review
    says about professional work now, it must not come from my policy."""
    scenes = professional_presets()[preset]
    for f in tone_review.review(scenes):
        assert "floor" not in f.message, f"{preset}: {f.message}"
        assert "below the" not in f.message or "rhythm" in f.message, \
            f"{preset}: {f.message}"


def test_the_pack_really_does_sit_below_the_old_floor():
    """Guards the evidence itself: if this ever stops being true, the argument
    for the retraction needs re-examining."""
    scenes = [s for rows in professional_presets().values() for s in rows]
    lows = [s.amp_level for s in scenes if s.amp_level is not None]
    assert lows and max(lows) < -6.0, \
        "every professional scene sat below the old -6 dB floor"


def test_the_pack_reverb_is_far_under_the_old_clean_floor():
    scenes = [s for rows in professional_presets().values() for s in rows]
    revs = [s.fx_mix["REVERB"] for s in scenes if "REVERB" in s.fx_mix]
    assert revs and max(revs) < 25.0, \
        "the old 25% clean reverb floor exceeded the pack's maximum"


# --- what survives, and only as advice ---------------------------------

def test_nothing_from_the_experiment_is_still_wired_up():
    """The relational lead-versus-rhythm idea already existed as rule 10, so
    the numeric-policy attempt contributed no surviving check. Its own
    'advisory' duplicate was removed rather than left to double-report."""
    scenes = [Scene(n=1, name="Rhythm", role="rhythm", amp_gain=6.5),
              Scene(n=2, name="Lead", role="lead", amp_gain=6.6)]
    found = tone_review.review(scenes)
    assert not [f for f in found if "within" in f.message], \
        "the duplicate advisory must not have come back"
    # rule 10 itself is pre-existing and still fires; that is not mine to change
    assert any(f.rule == "10" for f in found)


def test_the_policy_file_says_nothing_reads_it():
    raw = tone_review.TARGETS_PATH.read_text().lower()
    assert "record, not a policy" in raw


def test_a_missing_policy_still_disables_everything_cleanly(monkeypatch):
    monkeypatch.setattr(tone_review, "TARGETS_PATH",
                        tone_review.TARGETS_PATH.parent / "nope.json")
    assert tone_review.targets() == {}
    tone_review.review([Scene(n=1, name="Lead", role="lead", amp_gain=1.0)])


# --- the planner must not be told refuted numbers ----------------------

def test_the_planner_is_no_longer_given_the_floors():
    lines = " ".join(server._tone_target_lines())
    assert "amp level at or above" not in lines
    assert "reverb mix >=" not in lines


# --- depth capture is still useful even without floors -----------------

def test_a_plan_that_sets_a_mix_still_records_its_depth():
    """Worth keeping: a future check that measures AUDIO will want to know what
    the plan asked for, even though the value alone proves nothing."""
    scenes = tone_review.summary_from_plan([
        {"kind": "set_scene", "value": 1},
        {"kind": "set_param", "block": "reverb", "param": "REVERB_MIX",
         "value": 12.0},
    ])
    assert scenes[0].fx_mix["REVERB"] == 12.0


def test_a_scene_with_no_role_is_still_not_judged():
    assert tone_review.review(
        [Scene(4, "Scene 4", None, amp_gain=2.0, amp_level=-8.0)]) == []

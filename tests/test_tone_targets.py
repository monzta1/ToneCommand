"""Issue #50: make the rulebook's adjectives into arithmetic.

config/tone_rules.md says a clean gets a "generous mix" and a lead is "audibly
more saturated". A build satisfied every adjective and still arrived timid,
because 12 percent reverb is as "generous" as 40 percent to anything that
cannot measure. These are the numbers those words mean.
"""
from __future__ import annotations

import json

import pytest

import server
from fm9 import tone_review
from fm9.tone_review import Scene


def sykes_build():
    """The John Sykes build exactly as recorded on hardware in issue #50, which
    the owner judged not release-ready. Every value here is from the issue."""
    return [
        Scene(n=1, name="Clean", role="clean", amp_level=-8.0,
              effects={"DELAY", "REVERB", "CHORUS"},
              fx_mix={"REVERB": 12.0, "DELAY": 18.0, "CHORUS": 22.0}),
        Scene(n=2, name="Rhythm", role="rhythm", amp_gain=7.5, amp_level=-12.0,
              boost_gain=7.5),
        Scene(n=3, name="Lead", role="lead", amp_gain=7.8, amp_level=-10.0,
              boost_gain=6.0, effects={"DELAY", "REVERB"},
              fx_mix={"REVERB": 15.0, "DELAY": 18.0}),
    ]


def messages(scenes):
    return " | ".join(f.message for f in tone_review.review(scenes))


# --- the build that shipped must now be caught -------------------------

def test_the_rejected_build_is_now_refused():
    """It previously passed. Every complaint in the issue is now arithmetic."""
    found = tone_review.review(sykes_build())
    assert any(f.severity == "fail" for f in found)


@pytest.mark.parametrize("complaint,needle", [
    ("quiet clean", "amp level -8"),
    ("cut rhythm", "amp level -12"),
    ("cut lead", "amp level -10"),
    ("timid reverb", "reverb mix 12%"),
    ("timid delay", "delay mix 18%"),
    ("timid chorus", "chorus mix 22%"),
    ("undercooked lead", "not clearly above the rhythm"),
    ("clean boost, not an overdrive", "dialled below the rhythm"),
])
def test_every_complaint_in_the_issue_is_caught(complaint, needle):
    assert needle in messages(sykes_build()), complaint


def test_the_boost_check_is_the_subtle_one():
    """A boost dialled BELOW the rhythm it is meant to push is a clean volume
    push. Engagement checks cannot see this; only comparing the numbers can."""
    scenes = sykes_build()
    assert "clean volume push" in messages(scenes)
    scenes[2].boost_gain = 9.0            # now genuinely pushing the amp
    assert "clean volume push" not in messages(scenes)


# --- a good build must pass --------------------------------------------

def good_build():
    return [
        Scene(n=1, name="Clean", role="clean", amp_level=-2.0,
              effects={"DELAY", "REVERB", "CHORUS"},
              fx_mix={"REVERB": 35.0, "DELAY": 28.0, "CHORUS": 34.0}),
        Scene(n=2, name="Rhythm", role="rhythm", amp_gain=7.5, amp_level=-3.0,
              boost_gain=7.5, fx_mix={"REVERB": 12.0}),
        Scene(n=3, name="Lead", role="lead", amp_gain=9.2, amp_level=-2.0,
              boost_gain=8.5, effects={"DELAY", "REVERB"},
              fx_mix={"REVERB": 28.0, "DELAY": 24.0}),
    ]


def test_a_build_that_meets_the_floors_has_no_failures():
    fails = [f for f in tone_review.review(good_build()) if f.severity == "fail"]
    assert not fails, [f.message for f in fails]


def test_the_rhythm_ceiling_is_a_ceiling_not_a_floor():
    """Rhythm reverb is the one value that must stay LOW."""
    scenes = good_build()
    assert "above the 25% ceiling" not in messages(scenes)
    scenes[1].fx_mix["REVERB"] = 45.0
    assert "above the 25% ceiling" in messages(scenes)


# --- the policy itself --------------------------------------------------

def test_targets_load_and_are_versioned():
    t = tone_review.targets()
    assert t["version"] >= 1 and t["issue"] == 50
    assert set(t["roles"]) >= {"clean", "lead", "rhythm"}


def test_a_missing_policy_disables_the_checks_rather_than_crashing(monkeypatch):
    """A policy file that is absent or corrupt must never take a build down."""
    monkeypatch.setattr(tone_review, "TARGETS_PATH",
                        tone_review.TARGETS_PATH.parent / "nope.json")
    assert tone_review.targets() == {}
    tone_review.review(sykes_build())          # must not raise


def test_a_corrupt_policy_disables_the_checks(monkeypatch, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setattr(tone_review, "TARGETS_PATH", bad)
    assert tone_review.targets() == {}


def test_the_policy_records_where_its_numbers_came_from():
    """These are calibrated to one rejected build, not universal truth, and the
    file has to say so or someone will treat them as physics."""
    raw = json.loads(tone_review.TARGETS_PATH.read_text())
    prov = " ".join(raw["_provenance"]).lower()
    assert "rejected" in prov and "not a number invented here" in prov
    assert "editable" in prov


# --- the planner is told the same numbers -------------------------------

def test_the_planner_is_given_the_floors():
    lines = " ".join(server._tone_target_lines())
    assert "amp level at or above -6" in lines
    assert "reverb mix >= 25%" in lines
    assert "boost must NOT be dialled below" in lines


def test_the_planner_grounding_is_absent_when_the_policy_is(monkeypatch):
    monkeypatch.setattr(tone_review, "targets", lambda: {})
    assert server._tone_target_lines() == []


def test_the_floors_reach_the_actual_param_reference():
    assert "NUMERIC TONE FLOORS" in server.PARAM_REFERENCE


# --- depth is captured from a plan, not just engagement -----------------

def test_a_plan_that_sets_a_mix_records_its_depth():
    scenes = tone_review.summary_from_plan([
        {"kind": "set_scene", "value": 1},
        {"kind": "set_param", "block": "reverb", "param": "REVERB_MIX",
         "value": 12.0},
    ])
    assert scenes[0].fx_mix["REVERB"] == 12.0


def test_a_plan_that_sets_a_boost_records_it():
    scenes = tone_review.summary_from_plan([
        {"kind": "set_scene", "value": 3},
        {"kind": "set_param", "block": "drive", "param": "FUZZ_DRIVE",
         "value": 6.0},
    ])
    assert scenes[0].boost_gain == 6.0

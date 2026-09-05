"""The deterministic pre-ship tone check (fm9/tone_review.py): the enforcement
half of config/tone_rules.md rule 14. It must catch the failures that actually
shipped on 2026-09-04 (cleans cut quiet and dry, leads that do not out-saturate
the rhythm) and stay quiet on a build that is done right.
"""
from fm9 import tone_review as tr
from fm9.tone_review import Scene


def _by_rule(findings):
    return {(f.scene, f.rule) for f in findings}


def test_infer_role_reads_the_scene_name():
    assert tr.infer_role("Sykes Clean") == "clean"
    assert tr.infer_role("Sykes Rhythm") == "rhythm"
    assert tr.infer_role("Sykes Dry Lead") == "lead"
    assert tr.infer_role("Solo") == "lead"
    assert tr.infer_role("Scene 4") is None


def test_it_catches_the_sykes_failure():
    """The exact build that shipped wrong: cleans at -8 with no wets, a lead at
    gain 7.8 barely over a 6.8 rhythm."""
    scenes = [
        Scene(1, "Sykes Clean", "clean", amp_gain=2.8, amp_level=-8, effects={"REVERB"}),
        Scene(3, "Sykes Rhythm", "rhythm", amp_gain=6.8, amp_level=-2),
        Scene(5, "Sykes Dry Lead", "lead", amp_gain=7.8, amp_level=-2),
    ]
    f = tr.review(scenes)
    rules = _by_rule(f)
    assert (1, "8") in rules, "did not flag the dry clean (no delay)"
    assert (1, "8") in rules and any(f_.scene == 1 and "cut quiet" in f_.message for f_ in f), \
        "did not flag the clean cut quiet"
    assert (5, "10") in rules, "did not flag the under-saturated lead"
    assert all(x.severity == "fail" for x in f if x.rule in ("8", "10"))


def test_a_good_build_passes_clean():
    scenes = [
        Scene(1, "Big Clean", "clean", amp_gain=2.5, amp_level=1,
              effects={"CHORUS", "DELAY", "REVERB"}),
        Scene(2, "Rhythm", "rhythm", amp_gain=6.5, amp_level=-2, effects={"REVERB"}),
        Scene(3, "Lead", "lead", amp_gain=8.5, amp_level=0,
              effects={"DELAY", "REVERB"}, boosted=True),
    ]
    assert tr.review(scenes) == []


def test_a_lead_only_a_hair_over_the_rhythm_is_flagged():
    scenes = [
        Scene(1, "Rhythm", "rhythm", amp_gain=7.0, amp_level=-2),
        Scene(2, "Lead", "lead", amp_gain=7.2, amp_level=-2, effects={"DELAY", "REVERB"}),
    ]
    assert (2, "10") in _by_rule(tr.review(scenes))


def test_unknown_role_is_skipped_not_guessed():
    # no role -> no role-specific findings
    assert tr.review([Scene(4, "Scene 4", None, amp_gain=2.0, amp_level=-8)]) == []


def test_summary_from_plan_extracts_scene_state():
    actions = [
        {"kind": "rename_scene", "value": 1, "type_name": "Clean"},
        {"kind": "set_scene", "value": 1},
        {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE", "value": 2.5},
        {"kind": "set_param", "block": "amp", "param": "DISTORT_LEVEL", "value": 1},
        {"kind": "set_bypass", "block": "delay", "bypassed": False},
        {"kind": "set_bypass", "block": "reverb", "bypassed": False},
        {"kind": "rename_scene", "value": 2, "type_name": "Lead"},
        {"kind": "set_scene", "value": 2},
        {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE", "value": 9},
        {"kind": "set_param", "block": "output", "param": "OUTPUT_SCENE2", "value": 3},
    ]
    scenes = {s.n: s for s in tr.summary_from_plan(actions)}
    assert scenes[1].role == "clean" and scenes[1].amp_gain == 2.5 and scenes[1].amp_level == 1
    assert scenes[1].effects == {"DELAY", "REVERB"}
    assert scenes[2].role == "lead" and scenes[2].amp_gain == 9 and scenes[2].scene_level == 3


def test_findings_as_dicts_is_json_shaped():
    f = tr.review([Scene(1, "Clean", "clean", amp_level=-8, effects=set())])
    d = tr.findings_as_dicts(f)
    assert d and all(set(x) == {"scene", "rule", "severity", "message"} for x in d)

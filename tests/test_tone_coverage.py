"""Issue #54: an empty findings list must not pose as a pass.

A plan is a delta, so a parameter it does not set is unknown and its check is
skipped. That made one green result mean three different things: nothing was
wrong, nothing could be checked, or no scene role could be inferred.
"""
from __future__ import annotations

from fm9 import tone_review
from fm9.tone_review import Scene


def test_no_scenes_is_not_applicable():
    c = tone_review.coverage([])
    assert c["status"] == "not_applicable"
    assert c["checks_run"] == 0


def test_a_plan_that_reveals_nothing_is_unknown_not_a_pass():
    """The dangerous case: no findings, because nothing could be looked at."""
    c = tone_review.coverage([Scene(n=1), Scene(n=2)])
    assert c["status"] == "unknown"
    assert c["roles_unknown"] == [1, 2]
    assert "no scene role" in c["why"]


def test_known_roles_and_values_are_verified():
    scenes = [Scene(n=1, name="Rhythm", role="rhythm", amp_gain=6.0,
                    amp_level=-10.0, scene_level=0.0, effects={"DELAY"}),
              Scene(n=2, name="Lead", role="lead", amp_gain=7.5,
                    amp_level=-8.0, scene_level=1.0, effects={"DELAY"})]
    c = tone_review.coverage(scenes)
    assert c["status"] == "verified"
    assert c["scenes_checked"] == [1, 2]
    assert c["checks_run"] == c["checks_possible"]
    assert c["missing"] == {}


def test_partial_knowledge_reports_what_was_missing():
    scenes = [Scene(n=1, role="rhythm", amp_gain=6.0)]
    c = tone_review.coverage(scenes)
    assert c["status"] == "verified", "a role plus a value is a real check"
    assert 1 in c["missing"]["level"], "the absent facts must be named"
    assert 1 in c["missing"]["effects"]
    assert c["checks_run"] < c["checks_possible"]


def test_a_role_with_no_values_still_cannot_check_much():
    c = tone_review.coverage([Scene(n=1, role="lead")])
    assert c["checks_run"] == 1          # role only
    assert set(c["missing"]) >= {"gain", "level", "scene_level", "effects"}


def test_coverage_never_claims_more_scenes_than_it_saw():
    scenes = [Scene(n=3, role="clean", amp_gain=2.0)]
    c = tone_review.coverage(scenes)
    assert c["scenes"] == [3] and c["scenes_checked"] == [3]


def test_the_ui_cannot_render_zero_coverage_as_a_pass():
    """Guard on the copy itself: the branch that used to say 'nothing flagged'
    for any empty list must now be gated on coverage."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    block = ui.split("const bad = d.findings.length;")[1][:900]
    assert "tone_coverage" in block, "the pass message must consult coverage"
    assert "nothing could be checked" in block
    assert "I could run" in block


def test_a_structural_finding_does_not_make_the_values_verified():
    """Issue #51 added rule 15, which reads the channel map rather than any
    parameter value. That is exactly the shape of the #54 regression: a check
    that RAN, on a scene whose tone values are still entirely unknown.

    A clone finding must therefore not let coverage claim the build was
    judged. Both statements have to survive together: 'these two scenes are
    the same sound' and 'nothing was verified about how either one sounds'.
    """
    plan = []
    for n, name in ((4, "Lead"), (8, "Solo")):
        plan += [{"kind": "rename_scene", "value": n, "type_name": name},
                 {"kind": "set_scene", "value": n},
                 {"kind": "set_channel", "block": "amp", "value": 2}]
    scenes = tone_review.summary_from_plan(plan)

    assert [f.rule for f in tone_review.review(scenes)] == ["15"], \
        "the clone itself should still be reported"
    c = tone_review.coverage(scenes)
    assert c["status"] == "unknown"
    assert c["missing"]["gain"] == [4, 8] and c["missing"]["level"] == [4, 8]

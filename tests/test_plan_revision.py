"""Issue #55: Review and Send must refer to the same plan.

Review lets numeric values be edited in place. Those edits mutated the
browser's own action objects after the server had produced plan-time
validation and tone findings, so Confirm could display guidance computed
against a plan that no longer existed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server

ACT = {"kind": "set_param", "block": "cab", "param": "CABINET_LEVEL",
       "value": -3.0}


def action(**over):
    return server.Action(**{**ACT, **over})


def test_the_digest_describes_the_actions_not_the_object():
    a, b = [action()], [action()]
    assert server.plan_digest(a) == server.plan_digest(b)


def test_changing_any_value_changes_the_digest():
    assert server.plan_digest([action()]) != server.plan_digest([action(value=-4.0)])


def test_changing_the_order_changes_the_digest():
    one, two = action(), action(value=-4.0)
    assert server.plan_digest([one, two]) != server.plan_digest([two, one])


# --- the enforcement ----------------------------------------------------

def test_a_send_with_no_digest_is_left_alone():
    """Legacy callers keep working; the guard only bites when a digest is
    supplied, which the UI always does."""
    assert server.check_revision(
        server.ApplyBody(actions=[action()])) is None


def test_the_reviewed_plan_may_send():
    acts = [action()]
    dg = server.register_revision(acts)
    assert server.check_revision(
        server.ApplyBody(actions=acts, plan_digest=dg)) is None


def test_an_edit_after_review_is_refused():
    """The actual bug: the browser changed a number after the review ran."""
    dg = server.register_revision([action()])
    why = server.check_revision(
        server.ApplyBody(actions=[action(value=-99.0)], plan_digest=dg))
    assert why and "not the ones that were reviewed" in why


def test_a_plan_the_server_never_validated_is_refused():
    acts = [action(value=-7.5)]
    why = server.check_revision(
        server.ApplyBody(actions=acts, plan_digest=server.plan_digest(acts)))
    assert why and "never validated" in why


def test_apply_refuses_a_stale_plan_before_touching_hardware(monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False}, raising=False)
    dg = server.register_revision([action()])
    out = server._apply_for(
        server.ApplyBody(actions=[action(value=-99.0)], plan_digest=dg))
    assert out["refused"] == "stale_plan"
    assert len(out["results"]) == 1
    assert out["results"][0]["action"]["kind"] == "revision"


# --- the revise endpoint ------------------------------------------------

def test_revising_mints_a_new_revision_that_can_send():
    c = TestClient(server.app)
    d = c.post("/api/plan/revise", json={"actions": [ACT]}).json()
    assert d["ok"] and d["plan_digest"]
    assert server.check_revision(server.ApplyBody(
        actions=[action()], plan_digest=d["plan_digest"])) is None


def test_revising_returns_fresh_findings_and_coverage():
    d = TestClient(server.app).post(
        "/api/plan/revise", json={"actions": [ACT]}).json()
    assert "tone_review" in d and "tone_coverage" in d
    assert d["tone_coverage"]["status"] in (
        "verified", "unknown", "not_applicable")


def test_an_invalid_edit_is_refused_with_the_row_that_failed():
    c = TestClient(server.app)
    bad = {**ACT, "param": "NO_SUCH_PARAM"}
    r = c.post("/api/plan/revise", json={"actions": [ACT, bad]})
    assert r.status_code == 400
    assert r.json()["errors"][0]["index"] == 1


def test_two_different_edits_produce_two_different_revisions():
    c = TestClient(server.app)
    a = c.post("/api/plan/revise", json={"actions": [ACT]}).json()["plan_digest"]
    b = c.post("/api/plan/revise",
               json={"actions": [{**ACT, "value": -5.0}]}).json()["plan_digest"]
    assert a != b


# --- the UI half --------------------------------------------------------

def _ui():
    from pathlib import Path
    return (__import__("pathlib").Path(server.__file__).parent
            / "ui" / "index.html").read_text()


def test_transmit_names_the_revision_it_believes_it_is_sending():
    assert "plan_digest: currentPlan.plan_digest" in _ui()


def test_an_edit_voids_the_reviewed_revision_and_revalidates():
    ui = _ui()
    assert "function revisePlan()" in ui
    block = ui.split("function revisePlan()")[1][:900]
    assert "currentPlan.plan_digest = null" in block, \
        "the old revision must be void the instant an edit happens"
    assert "/api/plan/revise" in block
    assert "$('toconfirm').disabled = true" in block, \
        "Confirm must not stay armed against evidence that no longer applies"


def test_both_edit_paths_revalidate():
    """Typing a new value and pressing reset both change the plan."""
    ui = _ui()
    assert ui.count("revisePlan();") >= 2

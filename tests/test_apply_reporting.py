"""What the UI is told when an action is refused, and what it does with it.

Two faults found by the owner on v0.3.0 while asking for an amp on an empty
preset. Neither was a transmit failure, and one of them said it was.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


# --- the skipped marker is a contract, and the UI has to implement it ---

def test_a_refused_add_block_still_reports_a_null_action(client):
    """The server appends a marker with action None so later actions are not
    run against a block that never landed. Pinned here as well as in
    test_builder_actions, because the UI reads this shape."""
    body = {"actions": [
        {"kind": "add_block", "block": "amp", "instance": 1},
        {"kind": "add_block", "block": "amp", "instance": 1},
    ]}
    results = client.post("/api/apply", json=body).json()["results"]
    assert any(r["action"] is None for r in results)


def test_the_ui_guards_the_null_action_before_touching_kind():
    """`describe(res.action)` read .kind straight off the marker. The throw
    escaped the results loop, so the remaining results never logged and the
    log said

        transmit failed: Cannot read properties of null (reading 'kind')

    about a transmit that had happened and been reported correctly.

    Asserts a guard exists, not which one. The first version of this test
    demanded the exact line `if (!a) return 'skipped';`, and the independent
    review called that out as pinning tokens rather than behaviour: an equally
    correct guard would fail it. That prediction came true within hours, when
    upstream shipped `if (!a) return 'plan halted';` for the same fault."""
    body = UI.split("function describe(a) {")[1].split("\n}")[0]
    code = [ln.strip() for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("//")]
    assert code, "describe() has no body"
    guard = code[0]
    assert "return" in guard and ("!a" in guard or "a ==" in guard
                                  or "a ===" in guard), (
        f"describe() must handle a null action before touching .kind, got {guard!r}")
    assert ".kind" not in guard


# --- a refusal names the wall it actually hit ---

def test_an_empty_preset_is_not_described_as_having_no_free_cell(client,
                                                                 monkeypatch):
    """An empty FM9 slot has no grid cells at all, not even shunts (finding
    18), so "no free pass-through cell" describes a packed preset and tells
    the owner of a blank one nothing they can act on."""
    monkeypatch.setattr(server._fm9, "read_grid", lambda: [])
    monkeypatch.setattr(server._fm9, "status_dump", lambda: [])
    results = client.post("/api/apply", json={
        "actions": [{"kind": "add_block", "block": "amp", "instance": 1}]}).json()["results"]
    detail = results[0]["detail"]
    assert results[0]["ok"] is False
    assert "this preset is empty" in detail
    # The answer used to be a terminal, which is what issue #36 was about.
    # It is now a button, and the point of the assertion is unchanged: a
    # refusal has to say what the way forward IS, not only that this is not it.
    assert "BUILD A STARTING CHAIN" in detail, "say what the answer actually is"
    assert "no free pass-through cell" not in detail


@pytest.mark.parametrize("pos,phrase", [
    ("pre", "before the amp"),
    ("post", "after the amp"),
    ("any", "anywhere on the grid"),
])
def test_the_position_reads_as_a_phrase_not_an_enum(client, monkeypatch,
                                                    pos, phrase):
    """It rendered as "no free pass-through cell any of the amp".

    Driven through /api/apply, not by calling the helper: a test that only
    exercises the helper stays green if the caller goes back to interpolating
    the raw enum, which is the regression that matters.

    The grid here is packed AND has no amp. A packed grid on its own no longer
    refuses: #32 splices into one, which is the whole point of it. Refusal is
    now the case where a splice is impossible too, and removing the amp is the
    smallest way to reach it, since "before the amp" has no meaning without
    one. That is the path this wording still has to be right on.
    """
    amp = server.reg.effect_id("DISTORT")
    packed = [c for c in (server._fm9.read_grid() or [])
              if not c.is_shunt and c.effect_id != amp]
    monkeypatch.setattr(server._fm9, "read_grid", lambda: packed)
    results = client.post("/api/apply", json={"actions": [
        {"kind": "add_block", "block": "wah", "instance": 1,
         "position": pos}]}).json()["results"]
    detail = results[0]["detail"]
    assert results[0]["ok"] is False
    assert phrase in detail, detail
    assert f"cell {pos} of the amp" not in detail


def test_a_grid_that_did_not_answer_is_not_called_an_empty_preset(client,
                                                                  monkeypatch):
    """Finding 18: an empty slot's grid read SUCCEEDS with zero cells. Folding
    a read that returned nothing at all into "this preset is empty" is a
    confident wrong diagnosis, and it sends the owner off to load a different
    preset over what may be a cable or FM9-Edit holding the port."""
    monkeypatch.setattr(server._fm9, "read_grid", lambda: None)
    results = client.post("/api/apply", json={"actions": [
        {"kind": "add_block", "block": "wah", "instance": 1}]}).json()["results"]
    detail = results[0]["detail"]
    assert results[0]["ok"] is False
    assert "did not answer" in detail
    assert "this preset is empty" not in detail
    assert "build_from_scratch" not in detail, "do not prescribe a remedy here"


def test_a_one_action_plan_is_not_told_its_remaining_actions_were_skipped(
        client, monkeypatch):
    """A false sentence sitting under a true refusal. It was invisible while
    the marker crashed the UI."""
    monkeypatch.setattr(server._fm9, "read_grid", lambda: [])
    monkeypatch.setattr(server._fm9, "status_dump", lambda: [])
    results = client.post("/api/apply", json={"actions": [
        {"kind": "add_block", "block": "wah", "instance": 1}]}).json()["results"]
    assert len(results) == 1, [r["detail"] for r in results]
    assert all("remaining actions skipped" not in r["detail"] for r in results)


def test_a_multi_action_plan_still_says_what_it_skipped(client, monkeypatch):
    """The contract this marker exists for is unchanged, and now it counts."""
    monkeypatch.setattr(server._fm9, "read_grid", lambda: [])
    monkeypatch.setattr(server._fm9, "status_dump", lambda: [])
    results = client.post("/api/apply", json={"actions": [
        {"kind": "add_block", "block": "wah", "instance": 1},
        {"kind": "set_param", "block": "wah", "param": "WAH_LEVEL", "value": 0},
        {"kind": "set_bypass", "block": "wah", "instance": 1, "bypassed": True},
    ]}).json()["results"]
    assert results[-1]["action"] is None
    assert "remaining actions skipped (2)" in results[-1]["detail"]
    assert len(results) == 2, "the later actions must not have run"

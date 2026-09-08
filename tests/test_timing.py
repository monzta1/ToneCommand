"""Where a build's time actually goes (2026-09-07).

The owner asked why a build took over ten minutes, and the honest answer was
that nothing timed any of it: the question could only be argued from settle
constants and a docstring. Now every build reports its own numbers.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server
from fm9.sim import SimFM9


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


ONE = [{"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE",
        "value": 6, "reason": "more gain"}]


def test_a_plan_reports_how_long_it_took(client, monkeypatch):
    monkeypatch.setattr(server.planner, "plan", lambda *a, **kw: {
        "summary": "x", "clarification": None, "actions": ONE})
    d = client.post("/api/plan", json={"prompt": "more gain"}).json()
    assert "plan_s" in d["timing"] and d["timing"]["plan_s"] >= 0


def test_a_send_reports_its_total_and_its_worst_actions(client, signed):
    out = client.post("/api/apply", json=signed(ONE)).json()
    t = out["timing"]
    assert t["send_s"] >= 0 and t["actions"] == 1
    assert t["slowest"] and t["slowest"][0]["kind"] == "set_param"


def test_every_action_carries_its_own_cost(client, signed):
    """A total cannot tell a slow splice from ninety fast parameter writes,
    which is the whole question when a build feels slow."""
    out = client.post("/api/apply", json=signed(ONE)).json()
    rows = [r for r in out["results"] if r.get("action")]
    assert rows and all("seconds" in r for r in rows)


def test_a_refused_action_is_still_timed(client, signed):
    """Otherwise a plan full of refusals would look instant."""
    out = client.post("/api/apply", json=signed([
        {"kind": "set_param", "block": "amp", "param": "NOT_A_PARAM",
         "value": 1, "reason": "x"}])).json()
    rows = [r for r in out["results"] if r.get("action")]
    assert rows and all("seconds" in r for r in rows)


def test_the_reason_field_asks_for_proportionate_length():
    """Measured on a real stored build: reason prose was 38 percent of
    everything the model wrote, mostly paragraphs attached to single EQ
    values. That is time the player spends waiting, so the schema says how
    long a reason should be rather than leaving it to taste."""
    from fm9.planner import PLAN_SCHEMA
    desc = PLAN_SCHEMA["properties"]["actions"]["items"]["properties"]["reason"]["description"]
    assert "8 words" in desc
    assert "amp" in desc and "cab" in desc, "the choices worth a sentence"
    assert "38 percent" in desc, "keep the measurement that motivated it"

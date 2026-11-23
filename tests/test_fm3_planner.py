"""#40: planning for the FM3, within what it takes.

The planner is told the FM3's whole vocabulary (its measured settings on
the FM3's own ranges, block on/off, channel, scene), and every planned
action is checked against those limits before Review: anything else arrives
refused, in words, and never reaches Send."""
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import fm3_map


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setattr(server, "_fm3_knob_backoff", {"skip": 0})
    monkeypatch.setenv("TONECOMMAND_FM3_SIM", "1")
    c = TestClient(server.app)
    assert c.post("/api/device/select", json={"kind": "fm3"}).status_code == 200
    return c


def _plan(client, monkeypatch, actions):
    seen = {}

    def fake(prompt, context, *a, **k):
        seen["context"] = context
        return {"summary": "s", "clarification": None,
                "actions": [dict(a, reason="r") for a in actions]}
    monkeypatch.setattr(server.planner, "plan", fake)
    monkeypatch.setattr(server.planner, "repair_action", lambda *a, **k: None)
    r = client.post("/api/plan", json={"prompt": "more gain"})
    assert r.status_code == 200, r.text
    return r.json(), seen["context"]


def test_the_context_names_every_measured_setting_on_the_fm3s_range(client, monkeypatch):
    _, ctx = _plan(client, monkeypatch, [])
    assert "DEVICE LIMITS (Fractal FM3)" in ctx
    for (fam, pid) in fm3_map.PARAMS:
        assert server.reg.spec(fam, pid, 1).name in ctx
    assert "DELAY_TIME (Time): 0..16000" in ctx
    assert "REVERB_HICUT (High Cut): 200..20000, log taper" in ctx


def test_measured_settings_on_off_channel_and_scene_pass(client, monkeypatch):
    plan, _ = _plan(client, monkeypatch, [
        {"kind": "set_param", "block": "DISTORT", "instance": 1, "param": "DISTORT_DRIVE", "value": 6.5},
        {"kind": "set_param", "block": "DELAY", "instance": 1, "param": "DELAY_TIME", "value": 12000},
        {"kind": "set_bypass", "block": "REVERB", "instance": 1, "bypassed": True},
        {"kind": "set_channel", "block": "DELAY", "instance": 1, "value": 1},
        {"kind": "set_scene", "value": 2},
    ])
    for a in plan["actions"]:
        assert a["validation_errors"] == [], a


@pytest.mark.parametrize("action,needle", [
    ({"kind": "set_type", "block": "DISTORT", "instance": 1, "type_name": "Plexi 100W High"}, "cannot do set_type"),
    ({"kind": "add_block", "block": "CHORUS", "instance": 1, "position": "post"}, "cannot do add_block"),
    ({"kind": "set_cab", "block": "CABINET", "instance": 1, "bank": 0, "value": 1}, "cannot do set_cab"),
    ({"kind": "store", "value": 500}, "cannot do store"),
    ({"kind": "bind_pedal", "block": "DISTORT", "instance": 1, "param": "DISTORT_DRIVE"}, "cannot do bind_pedal"),
    ({"kind": "set_param", "block": "REVERB", "instance": 1, "param": "REVERB_SIZE", "value": 50}, "not one of the FM3 settings"),
    ({"kind": "set_param", "block": "DELAY", "instance": 2, "param": "DELAY_MIX", "value": 20}, "not one of the FM3 settings"),
    ({"kind": "set_param", "block": "DELAY", "instance": 1, "param": "DELAY_TIME", "value": 20000}, "outside the FM3's range"),
    ({"kind": "set_bypass", "block": "OUTPUT", "instance": 1, "bypassed": True}, "silences the rig"),
])
def test_anything_else_arrives_refused_in_words(client, monkeypatch, action, needle):
    plan, _ = _plan(client, monkeypatch, [action])
    errs = plan["actions"][0]["validation_errors"]
    assert errs and needle in errs[0], errs


def test_a_planned_setting_sends_and_reads_back(client, monkeypatch):
    plan, _ = _plan(client, monkeypatch, [
        {"kind": "set_param", "block": "REVERB", "instance": 1, "param": "REVERB_MIX", "value": 35}])
    act = {k: plan["actions"][0][k] for k in ("kind", "block", "instance", "param", "value")}
    r = client.post("/api/apply", json={"actions": [act]}).json()
    res = [x for x in r["results"] if x.get("action")]
    assert res and res[0]["ok"], r
    assert client.get("/api/state").json()["values"]["REVERB_MIX"] == 35.0


def test_the_fm9_is_validated_as_before(monkeypatch):
    """The FM3 limits apply only with the FM3 selected."""
    monkeypatch.setattr(server, "_context", server._default_context)
    errs, _ = server.validate_action(server.Action(kind="set_param", block="REVERB", instance=1,
                                                   param="REVERB_SIZE", value=50))
    assert not any("FM3" in e for e in errs)

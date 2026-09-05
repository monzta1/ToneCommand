"""Bounded repair pass (issue #39): one refused action fed back to the model
once, corrected only if the fix passes the SAME validation, never loosened, and
the substitution surfaced. The recurring failure is an invented parameter name
on a big build (e.g. DISTORT_GAIN), which validation refuses and the transmit
then silently drops.
"""
import sys

sys.argv = ["x"]
import server
from fm9 import planner


# --- planner.repair_action (the model call), backend injected ---

def test_repair_action_returns_the_models_corrected_action():
    def ask(prompt, dev, ref):
        assert "refused" in prompt.lower() and "reason" in prompt.lower()
        return {"actions": [{"kind": "set_param", "block": "amp",
                             "param": "DISTORT_DRIVE", "value": 6}]}
    fixed = planner.repair_action(
        {"kind": "set_param", "block": "amp", "param": "DISTORT_GAIN", "value": 6},
        "unknown parameter 'DISTORT_GAIN'", "ref", ask=ask)
    assert fixed and fixed["param"] == "DISTORT_DRIVE"


def test_repair_action_returns_none_when_the_model_offers_no_fix():
    assert planner.repair_action({"kind": "set_param"}, "bad", "ref",
                                 ask=lambda *a: {"actions": []}) is None


def test_repair_action_swallows_a_backend_failure():
    def boom(*a):
        raise RuntimeError("no backend")
    assert planner.repair_action({"kind": "set_param"}, "bad", "ref", ask=boom) is None


# --- server._repair_refused_actions (the wiring) ---

def _plan(actions):
    return {"actions": actions}


def test_a_refused_param_is_repaired_and_the_swap_is_surfaced(monkeypatch):
    monkeypatch.setattr(server.planner, "repair_action",
                        lambda a, r, ref, ctx="", **k:
                        {"kind": "set_param", "block": "amp",
                         "param": "DISTORT_DRIVE", "value": 6})
    result = _plan([{"kind": "set_param", "block": "amp",
                     "param": "DISTORT_GAIN", "value": 6, "instance": 1}])
    server._repair_refused_actions(result, "")
    a = result["actions"][0]
    assert a["param"] == "DISTORT_DRIVE", "the invented name was not corrected"
    assert a["repaired_from"]["param"] == "DISTORT_GAIN", "the swap is not surfaced"


def test_a_fix_that_still_fails_keeps_the_honest_refusal(monkeypatch):
    # the model returns another invented name -> validation still refuses -> keep
    monkeypatch.setattr(server.planner, "repair_action",
                        lambda *a, **k: {"kind": "set_param", "block": "amp",
                                         "param": "STILL_FAKE", "value": 6})
    result = _plan([{"kind": "set_param", "block": "amp",
                     "param": "DISTORT_GAIN", "value": 6, "instance": 1}])
    server._repair_refused_actions(result, "")
    a = result["actions"][0]
    assert a["param"] == "DISTORT_GAIN" and "repaired_from" not in a, \
        "a fix that still fails must not replace the original"


def test_a_valid_action_is_left_alone(monkeypatch):
    called = {}
    monkeypatch.setattr(server.planner, "repair_action",
                        lambda *a, **k: called.setdefault("ran", True))
    result = _plan([{"kind": "set_param", "block": "amp",
                     "param": "DISTORT_DRIVE", "value": 6, "instance": 1}])
    server._repair_refused_actions(result, "")
    assert "ran" not in called, "repair must not touch a valid action"


def test_structural_kinds_are_not_repaired(monkeypatch):
    called = {}
    monkeypatch.setattr(server.planner, "repair_action",
                        lambda *a, **k: called.setdefault("ran", True))
    result = _plan([{"kind": "add_block", "block": "nonsense", "instance": 1}])
    server._repair_refused_actions(result, "")
    assert "ran" not in called, "add_block placement is out of scope for repair"


def test_repairs_are_capped(monkeypatch):
    n = {"calls": 0}

    def fake(a, r, ref, ctx="", **k):
        n["calls"] += 1
        return {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE",
                "value": 6}
    monkeypatch.setattr(server.planner, "repair_action", fake)
    acts = [{"kind": "set_param", "block": "amp", "param": "FAKE",
             "value": 6, "instance": 1} for _ in range(20)]
    server._repair_refused_actions(_plan(acts), "")
    assert n["calls"] <= server._MAX_REPAIRS

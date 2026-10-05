"""#198: a sentence has to reach the pedal.

The IR-2 adapter shipped able to read and write every parameter, and the
product still could not drive it: `run_action` resolved a block through the
FM9 registry and called `set_param_display`, and the IR-2 has no blocks and
publishes no taper, so all three action kinds raised. The refusals were
right. The loop was the thing that was wrong.
"""
from pathlib import Path

import pytest

from fm9.adapter import NamedParams
from devices.ir2 import planning
from devices.ir2.adapter import IR2Adapter
from devices.ir2.sim import SimIR2

import server
from server import Action, run_action, validate_action


@pytest.fixture
def ir2(monkeypatch):
    ctx = server.DeviceContext("ir2", server.FM9_REGISTRY,
                               IR2Adapter(client=SimIR2()), "BOSS IR-2")
    monkeypatch.setattr(server, "_context", ctx)
    return ctx.adapter


# --- the contract ---------------------------------------------------------

def test_the_ir2_declares_named_parameters(ir2):
    assert ir2.capabilities().has_named_params is True
    assert isinstance(ir2, NamedParams)


def test_the_fm9_does_not_declare_them():
    """The FM9's parameters live at (block, instance, id) and its registry
    publishes a taper, so set_param_display is the honest path there. This
    gate is for devices that have neither."""
    from fm9.device import FM9
    assert FM9.CAPABILITIES.has_named_params is False


def test_the_vocabulary_comes_from_the_device(ir2):
    names = [p["name"] for p in ir2.named_params()]
    assert names == ["BASS", "MIDDLE", "TREBLE", "LEVEL", "GAIN",
                     "AMBIENCE", "AMP"]
    amp = ir2.named_params()[-1]
    assert len(amp["options"]) == 11 and "BROWN" in amp["options"]
    # every voicing names the cab it ships with, verbatim, so it can be
    # matched against a real IR library rather than paraphrased
    assert amp["option_cabs"]["BROWN"].endswith(".wav")


# --- validation, before anything reaches the wire -------------------------

def test_a_named_parameter_is_applied_and_verified(ir2):
    act = Action(kind="set_device_param", param="GAIN", value=96)
    assert validate_action(act) == ([], [])
    assert run_action(ir2, act)["detail"] == "GAIN = 96"
    assert ir2.patch()["GAIN"] == 96


def test_an_enum_is_set_by_name(ir2):
    act = Action(kind="set_device_param", param="AMP", type_name="BROWN")
    assert validate_action(act) == ([], [])
    assert run_action(ir2, act)["after"] == "BROWN"
    assert ir2.patch()["AMP"] == "BROWN"


def test_out_of_range_is_refused_before_the_wire(ir2):
    """The pedal clamps silently, so a clamped write would read back as a
    successful one. The range check has to happen before the send."""
    errs, _ = validate_action(Action(kind="set_device_param", param="GAIN",
                                     value=200))
    assert errs and "0 to 127" in errs[0]
    assert ir2.io.writes == []


def test_a_parameter_the_device_lacks_is_refused_and_names_what_it_has(ir2):
    errs, _ = validate_action(Action(kind="set_device_param",
                                     param="PRESENCE", value=10))
    assert errs and "no parameter 'PRESENCE'" in errs[0] and "GAIN" in errs[0]


def test_an_amp_the_device_lacks_is_refused_and_names_what_it_has(ir2):
    errs, _ = validate_action(Action(kind="set_device_param", param="AMP",
                                     type_name="PLEXI"))
    assert errs and "no setting 'PLEXI'" in errs[0] and "RFIER" in errs[0]


# --- the planner speaks this device's language ----------------------------

def test_the_prompt_never_offers_what_the_pedal_does_not_have():
    s = planning.SYSTEM.lower()
    # Naming what is absent beats staying silent about it: a model told only
    # what exists will still reach for a delay block.
    for absent in ("scene", "block", "grid", "modulation", "drive"):
        assert absent in s, f"the prompt should name {absent!r} as absent"
    assert "no effect blocks" in s and "no scenes" in s
    assert "do not propose any of those" in s


def test_the_schema_admits_one_action_kind_only():
    kinds = planning.SCHEMA["properties"]["actions"]["items"]["properties"]["kind"]["enum"]
    assert kinds == ["set_device_param"]


def test_the_validator_drops_actions_this_device_cannot_take():
    out = planning.validate({"summary": "", "actions": [
        {"kind": "set_device_param", "param": "AMP", "type_name": "BROWN"},
        {"kind": "set_scene", "value": 2},
        {"kind": "set_cab", "block": "cab", "value": 12},
        {"kind": "set_device_param", "param": "GAIN", "value": 100}]})
    assert [a["param"] for a in out["actions"]] == ["AMP", "GAIN"]


def test_a_clarifying_question_means_zero_actions():
    """Same rule as the FM9 validator (#72): a reply carrying both would show
    the question AND offer the actions for confirm and send."""
    out = planning.validate({"clarification": "Which record?", "actions": [
        {"kind": "set_device_param", "param": "GAIN", "value": 100}]})
    assert out["actions"] == []


def test_the_reference_is_read_from_the_device_not_hardcoded(ir2):
    ref = planning.param_reference(ir2)
    for p in ir2.named_params():
        assert p["name"] in ref
    assert "0 to 127" in ref and "RFIER" in ref
    low = ref.lower()
    assert "no blocks" in low and "no scenes" in low


# --- the page ------------------------------------------------------------

def test_the_state_route_answers_for_a_device_with_no_scenes(ir2):
    """It used to 500: `snapshot` reads a preset, eight scenes and a grid,
    and the IR-2 declines all three, so the page read OFFLINE for a pedal
    that was plugged in and answering."""
    from fastapi.testclient import TestClient
    r = TestClient(server.app).get("/api/state")
    assert r.status_code == 200
    d = r.json()
    assert d["connected"] is True
    # NOT "params": that key is the FM9's own block metadata, and the
    # collision made renderParams throw and paint the header OFFLINE.
    assert "params" not in d
    assert [p["name"] for p in d["device_params"]][0] == "BASS"
    assert d["preset"]["name"] == "CLEAN"
    assert "scenes" not in d, "claiming scenes here would be inventing them"


def test_a_whole_plan_lands_on_the_device(ir2):
    """The end goal: ask for a tone, get it."""
    plan = [{"kind": "set_device_param", "param": "AMP", "type_name": "BROWN"},
            {"kind": "set_device_param", "param": "GAIN", "value": 96},
            {"kind": "set_device_param", "param": "BASS", "value": 54},
            {"kind": "set_device_param", "param": "MIDDLE", "value": 78},
            {"kind": "set_device_param", "param": "TREBLE", "value": 80},
            {"kind": "set_device_param", "param": "AMBIENCE", "value": 18}]
    for row in planning.validate({"summary": "", "actions": plan})["actions"]:
        act = Action(**{k: v for k, v in row.items() if k != "reason"})
        assert validate_action(act) == ([], [])
        run_action(ir2, act)
    assert ir2.patch() == {"BASS": 54, "MIDDLE": 78, "TREBLE": 80,
                           "LEVEL": 64, "GAIN": 96, "AMBIENCE": 18,
                           "AMP": "BROWN"}


def test_an_fm9_port_event_does_not_overrule_another_selected_device():
    """The link stream watches the FM9's USB port and nothing else. With an
    IR-2 selected, unplugging an FM9 used to paint the header OFFLINE and dim
    the page over a pedal that was working, until the next poll corrected it.
    An FM9 event may only drive the header when the FM9 is the selected
    device; otherwise it just prompts a fresh read of the device in use."""
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(
        encoding="utf-8")
    handler = ui.split("if (ev !== 'link') continue;")[1].split("} catch")[0]
    assert "d.present || devNamed()" in handler
    # and the FM9's own unplug still goes offline, unchanged
    assert "$('link').className = 'pill off';" in handler
    assert "setRigOff(true);" in handler

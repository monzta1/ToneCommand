"""Tests for the planner-exposed builder actions (#9), on the simulator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import server
from server import Action, validate_action, run_action
from fm9.sim import SimFM9


@pytest.fixture
def fm9():
    dev = SimFM9(server.reg)
    dev.status_dump()
    return dev


def test_add_block_places_on_shunt(fm9):
    res = run_action(fm9, Action(kind="add_block", block="wah", position="pre"))
    assert res["ok"], res["detail"]
    grid = {(c.row + 1, c.col + 1): c for c in fm9.read_grid() or []}
    placed = [k for k, c in grid.items() if c.effect_id == 94]
    assert placed and grid[placed[0]].cable_in_mask != 0


def test_add_block_refuses_duplicate(fm9):
    run_action(fm9, Action(kind="add_block", block="wah"))
    res = run_action(fm9, Action(kind="add_block", block="wah"))
    assert not res["ok"] and "already exists" in res["detail"]


def test_add_block_splices_once_the_free_cells_are_gone(fm9):
    """Issue #10, decided as option 2: exhausting the pass-through cells used
    to mean refusal, which is what real presets hit, because none keep a spare
    before the amp. It now displaces neighbours right instead, and reports what
    it moved."""
    # the sim's default chain has exactly three shunt cells
    for block in ("wah", "phaser", "chorus"):
        run_action(fm9, Action(kind="add_block", block=block))
    res = run_action(fm9, Action(kind="add_block", block="flanger"))
    assert res["ok"], res["detail"]
    assert res.get("spliced") is True
    assert res["moved"], "a splice has to say which blocks it displaced"
    assert res["alive"], "and prove the signal still gets through"


def test_add_block_still_refuses_when_the_row_cannot_shift(fm9):
    """The refusal survives where it is real: with no room to the right, a
    block would fall off the end of the grid."""
    for block in ("wah", "phaser", "chorus"):
        run_action(fm9, Action(kind="add_block", block=block))
    for col in range(12, 15):                     # fill the row to the end
        fm9.place_block(2, col, 100 + col)
    res = run_action(fm9, Action(kind="add_block", block="flanger"))
    assert not res["ok"]
    assert res.get("reason") == "no_room_right", res
    assert "fall off the end of the grid" in res["detail"]
    assert "another preset" in res["detail"], "say what to do instead"


def test_bind_pedal_uses_free_slot_and_curve(fm9):
    res = run_action(fm9, Action(kind="bind_pedal", block="delay",
                                 param="DELAY_MIX", value=20))
    assert res["ok"], res["detail"]
    slot = fm9.sim_core.st.buffer["modifiers"][1]
    assert slot[0] == 11 and slot[8] == 70 and slot[9] == 0
    assert slot[4] > 0 and slot[5] > 0          # curve initialized
    assert abs(slot[1] / 65534 - 0.20) < 0.02   # floor honored


def test_store_action_and_validation():
    ok_errs, ok_warns = validate_action(Action(kind="store", value=140))
    assert not ok_errs and any("OVERWRITE" in w for w in ok_warns)
    bad_errs, _ = validate_action(Action(kind="store", value=509))
    assert bad_errs                              # protected slot refused


def test_store_executes_on_whitelisted_slot(fm9):
    run_action(fm9, Action(kind="rename_preset", type_name="Sim Store Test"))
    res = run_action(fm9, Action(kind="store", value=137))
    assert res["ok"], res["detail"]
    fm9.select_preset(0)
    got = fm9.select_preset(137)
    assert got[1].startswith("FM9AI-")           # prefix auto-applied


def test_rename_prefix_enforced(fm9):
    res = run_action(fm9, Action(kind="rename_preset", type_name="My Tone"))
    assert res["ok"]
    assert fm9.current_preset()[1] == "FM9AI-My Tone"


def test_rename_scene(fm9):
    res = run_action(fm9, Action(kind="rename_scene", value=4, type_name="BRIDGE Big"))
    assert res["ok"]
    assert fm9.scene_name(4)[1] == "BRIDGE Big"


def test_validation_rejects_pedal_on_selector():
    errs, _ = validate_action(Action(kind="bind_pedal", block="amp", param="DISTORT_TYPE"))
    assert errs


def test_validation_rejects_bad_position():
    errs, _ = validate_action(Action(kind="add_block", block="wah", position="sideways"))
    assert errs


def test_apply_skips_rest_after_failed_add_block(monkeypatch):
    """A failed add_block must abort the plan: later actions would target a
    block that never landed (hardware-observed dangling modifier binding)."""
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    client = TestClient(server.app)
    server._fm9.status_dump()
    run_action(server._fm9, Action(kind="add_block", block="wah"))  # occupy
    body = {"actions": [
        {"kind": "add_block", "block": "wah"},                # duplicate: fails
        {"kind": "set_param", "block": "wah", "param": "WAH_LEVEL", "value": 0},
    ]}
    results = client.post("/api/apply", json=body).json()["results"]
    assert results[0]["ok"] is False
    assert results[-1]["action"] is None
    assert "skipped" in results[-1]["detail"]
    assert len(results) == 2                                  # set_param never ran

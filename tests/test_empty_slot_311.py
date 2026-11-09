"""#311: an empty-slot build whose plan voices the starter template without
add_block. Plan time tells the planner the template is already laid
(starter_template.roster_text), so send time must lay it for any block
action, not only for add_block. And a write to a block that is not on the
grid must not be reported as done."""
import pytest
from fastapi.testclient import TestClient

import server
from fm9.signal_path import scene_alive
from fm9.sim import SimFM9


@pytest.fixture
def rig(monkeypatch):
    fm9 = SimFM9(server.reg)
    monkeypatch.setattr(server, "_fm9", fm9)
    return fm9, TestClient(server.app, base_url="http://127.0.0.1")


def _empty_slot(fm9):
    slot = fm9.first_empty_slot(0, 511)
    fm9.select_preset(slot.number)
    assert fm9.read_grid() == []
    return slot.number


def _eids(fm9):
    return {c.effect_id for c in fm9.read_grid() or []}


def test_voicing_only_plan_on_an_empty_slot_lays_the_template_first(rig, signed):
    fm9, client = rig
    _empty_slot(fm9)
    acts = [
        {"kind": "set_bypass", "block": "drive", "instance": 1, "bypassed": False},
        {"kind": "set_bypass", "block": "reverb", "instance": 1, "bypassed": False},
    ]
    results = client.post("/api/apply", json=signed(acts)).json()["results"]
    kinds = [(r["action"] or {}).get("kind") for r in results]
    assert kinds[0] == "build_chain" and results[0]["ok"], results
    assert all(r["ok"] for r in results), [r["detail"] for r in results]
    drive = server.reg.resolve_block("drive", 1)[1]
    reverb = server.reg.resolve_block("reverb", 1)[1]
    assert {drive, reverb} <= _eids(fm9)
    blocks = {b.effect_id: b for b in fm9.status_dump() or []}
    assert not blocks[drive].bypassed and not blocks[reverb].bypassed
    alive, why = scene_alive(fm9.read_grid(), blocks, server.reg)
    assert alive, why


def test_a_rename_only_plan_on_an_empty_slot_lays_nothing(rig, signed):
    fm9, client = rig
    _empty_slot(fm9)
    acts = [{"kind": "rename_preset", "type_name": "Test Tone"}]
    results = client.post("/api/apply", json=signed(acts)).json()["results"]
    assert all((r["action"] or {}).get("kind") != "build_chain" for r in results)
    assert fm9.read_grid() == []


def test_a_write_to_a_block_that_is_not_on_the_grid_fails(rig, signed):
    fm9, client = rig
    fm9.select_preset(0)
    on = _eids(fm9)
    assert on, "the simulator's preset 0 has a grid"
    absent = next(name for name in ("wah", "chorus", "flanger", "phaser", "pitch")
                  if server.reg.resolve_block(name, 1)[1] not in on)
    acts = [{"kind": "set_bypass", "block": absent, "instance": 1, "bypassed": False}]
    results = client.post("/api/apply", json=signed(acts)).json()["results"]
    row = [r for r in results if (r["action"] or {}).get("kind") == "set_bypass"][0]
    assert row["ok"] is False
    assert "not on this preset's grid" in row["detail"]


def test_a_block_added_earlier_in_the_plan_can_be_voiced(rig, signed, monkeypatch):
    fm9, client = rig
    fm9.select_preset(0)
    on = _eids(fm9)
    absent = next(name for name in ("wah", "chorus", "flanger", "phaser", "pitch")
                  if server.reg.resolve_block(name, 1)[1] not in on)
    monkeypatch.setattr(server, "_add_block",
                        lambda dev, a: {"ok": True, "detail": "placed"})
    acts = [{"kind": "add_block", "block": absent, "instance": 1},
            {"kind": "set_bypass", "block": absent, "instance": 1, "bypassed": False}]
    results = client.post("/api/apply", json=signed(acts)).json()["results"]
    row = [r for r in results if (r["action"] or {}).get("kind") == "set_bypass"][0]
    assert "not on this preset's grid" not in row["detail"]

"""Independent in-memory grid fixture; no FM9 simulator or hardware ports."""
from copy import deepcopy
import threading
from types import MethodType
from unittest.mock import Mock

import pytest

from devices.axefx3 import grid, route_guard, protocol
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from fm9 import protocol as shared

ROUTE = ["Input 1", "Wah 1", "Amp 1", "Cab 1", "Delay 1", "Reverb 1", "Output 1"]
ADDS = [{"kind": "add_block", "block": name} for name in ("wah", "amp", "cab", "delay", "reverb")]


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(grid.time, "sleep", lambda _: None)
    dev = Mock()
    dev.reg = Registry("32.06")
    dev._lock = threading.RLock()
    cells = []
    dev.read_grid.side_effect = lambda: deepcopy(cells)
    dev.status_dump.side_effect = lambda: [shared.BlockStatus(c.effect_id, False, 0, 4) for c in cells]
    def write(frame):
        assert protocol.valid_reply(frame[1:-1])
        assert grid.valid_write(frame, dev.reg)
        payload = frame[6:-2]
        if payload[:2] == [0x32, 0]:
            eid = shared.decode14(*payload[2:4])
            col, row = divmod(shared.decode14(*payload[6:8]), 6)
            cells.append(shared.GridCell(row, col, eid, False, 0))
        elif payload[:2] == [0x35, 0]:
            # Independently enumerate candidate human coordinates. The fixture
            # emulates application, not the actual device's cable decoder.
            pos = next((r, c, d) for r in range(2, 6) for c in range(1, 14) for d in range(2, 6)
                       if grid.reframe(shared.build_set_grid_routing(r, c, d)) == frame)
            r, c, d = pos
            cell = next(x for x in cells if (x.row, x.col) == (d - 1, c))
            cell.cable_in_mask = 1 << r
    dev._write.side_effect = write
    for method in ("place_block", "connect_cells", "build_route"):
        setattr(dev, method, MethodType(getattr(AxeFxIII, method), dev))
    return dev, cells


def test_empty_build_and_repeat_reuse_do_not_load_or_store_presets(rig):
    dev, cells = rig
    result = dev.build_route(ROUTE, ADDS)
    assert result.ok
    assert route_guard.serial_route(cells, dev.status_dump(), dev.reg) == [37, 94, 58, 62, 70, 66, 42]
    dev._write.reset_mock()
    assert dev.build_route(ROUTE, ADDS).ok
    dev._write.assert_not_called()
    dev.select_preset.assert_not_called()
    dev.store_preset.assert_not_called()


def test_drop_placement_stops_before_cables_or_later_blocks(rig):
    dev, _ = rig
    dev._write.side_effect = lambda _: None
    assert not dev.build_route(ROUTE, ADDS).ok
    assert all(c.args[0][6] in (0x30, 0x32) for c in dev._write.call_args_list)
    assert len(dev._write.call_args_list) == 2


def test_drop_cable_never_claims_a_complete_route(rig):
    dev, _ = rig
    write = dev._write.side_effect
    dev._write.side_effect = lambda frame: None if frame[6] == 0x35 else write(frame)
    assert not dev.build_route(ROUTE, ADDS).ok


@pytest.mark.parametrize("problem", ["parallel", "broken", "status", "extra", "row"])
def test_invalid_existing_route_is_never_overwritten(rig, problem):
    dev, cells = rig
    assert dev.build_route(ROUTE, ADDS).ok
    dev._write.reset_mock()
    if problem == "parallel": cells[2].cable_in_mask |= 4
    if problem == "broken": cells[2].cable_in_mask = 0
    if problem == "status": dev.status_dump.side_effect = lambda: []
    if problem == "extra": cells.append(shared.GridCell(3, 10, 110, False, 0))
    if problem == "row": cells[2].row = 6
    with pytest.raises(ValueError):
        dev.build_route(ROUTE, ADDS)
    dev._write.assert_not_called()


def test_incomplete_add_contract_is_refused_before_first_write(rig):
    dev, _ = rig
    with pytest.raises(ValueError, match="ADD"):
        dev.build_route(ROUTE, ADDS[:-1])
    dev._write.assert_not_called()


@pytest.mark.parametrize("frame", [shared.build_set_grid_cell(3, 1, 0),
    shared.build_set_grid_cell(3, 1, 182), shared.build_set_grid_cell(1, 1, 58),
    shared.build_set_grid_routing(3, 1, 3, op=shared.ROUTING_DISCONNECT)])
def test_transport_boundary_does_not_enable_clear_feedback_or_disconnect(frame):
    assert not grid.valid_write(grid.reframe(frame), Registry("32.06"))

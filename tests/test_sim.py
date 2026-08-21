"""Regression suite against the virtual FM9.

Every hardware quirk learned on the real unit (fw 11.00) is encoded here.
The simulator is a REGRESSION tool: these tests prove the client library
handles the device's known behaviors, not that the device behaves this way
(that part was proven on hardware first).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from fm9.sim import SimFM9
from fm9 import protocol as p


@pytest.fixture
def fm9():
    dev = SimFM9()
    dev.status_dump()
    return dev


def test_handshake_and_names(fm9):
    num, name = fm9.current_preset()
    assert num == 0 and name.startswith("Sim Preset")
    assert fm9.current_scene() == 1
    s, sname = fm9.scene_name(3)
    assert s == 3


def test_scene_select_roundtrip(fm9):
    assert fm9.set_scene(5) == 5
    assert fm9.current_scene() == 5


def test_bypass_is_per_scene(fm9):
    fm9.set_scene(1)
    fm9.set_bypass(70, True)
    assert fm9.get_bypass(70) is True
    fm9.set_scene(2)
    assert fm9.get_bypass(70) is False       # scene 2 unaffected
    fm9.set_scene(1)
    assert fm9.get_bypass(70) is True


def test_param_set_and_bulk_read(fm9):
    spec = fm9.reg.spec("DISTORT", 11)       # amp gain 0..10
    r = fm9.set_param_display(spec, 6.5)
    assert r.ok, r.detail
    assert fm9.get_param_display(spec) == 6.5


def test_zeroed_get_is_noop(fm9):
    """sub 09 00 with value 0 must NOT change a continuous param."""
    spec = fm9.reg.spec("DISTORT", 11)
    fm9.set_param_display(spec, 4.86)
    fm9._drain()
    fm9._send(p.build_get_param(58, 11))     # the zeroed GET
    assert fm9.get_param_display(spec) == 4.86


def test_amp_type_display_name_does_not_track_the_param(fm9):
    """read_display_name never reflects DISTORT_TYPE, settled or not.

    Checked on an FM9 running firmware 12.00 (2026-08-21). The sub 0x1F
    display-name query returned "59 Bassguy Bright" -- the roster's first entry
    -- while the amp was actually on ordinal 28 (Recto2 Red Modern), and went on
    returning it after a write to ordinal 39 at settles of 0.1s, 0.5s, 1.0s and
    3.0s. It is already wrong BEFORE the write, which no settle can explain.

    The write itself is fine: get_param_wire reads back 39 immediately, with no
    settle at all. Only the name query is broken, and it is worse than an error
    because the name looks plausible -- anything trusting it silently reports
    the wrong amp. server.py avoids it, reading the wire value and mapping it
    through the roster. See also the README note that the same query returns
    "NONE" for modifier source enums.
    """
    spec = fm9.reg.spec("DISTORT", 10)
    before = fm9.read_display_name(58, 10)

    fm9.set_param_ordinal(spec, 39)

    after = fm9.read_display_name(58, 10)
    assert after == before
    assert after != "PVH 6160 Block Lead"


def test_grid_insert_requires_select(fm9):
    """Insert without select lands on the cursor, not the target cell."""
    import time
    fm9._drain()
    fm9._send(p.build_set_grid_cell(4, 10, 94))   # raw insert, no select
    time.sleep(0.1)                                # writes are async on hardware
    cells = {(c.row + 1, c.col + 1): c.effect_id for c in fm9.read_grid() or []}
    assert cells.get((4, 10)) != 94               # did NOT land at target
    assert cells.get((1, 1)) == 94                # landed on the cursor cell
    # recovery mirrors the hardware session: clear the stray, then
    # select-then-insert (place_block does both) lands correctly
    fm9.place_block(1, 1, 0)
    fm9.place_block(4, 10, 94)
    cells = {(c.row + 1, c.col + 1): c.effect_id for c in fm9.read_grid() or []}
    assert cells.get((4, 10)) == 94


def test_move_is_ignored_and_clear_kills_cables(fm9):
    grid = {(c.row + 1, c.col + 1): c for c in fm9.read_grid() or []}
    assert grid[(2, 6)].effect_id == 70           # delay in default chain
    fm9.place_block(2, 9, 70)                     # "move" attempt: ignored
    grid = {(c.row + 1, c.col + 1): c for c in fm9.read_grid() or []}
    assert (2, 9) not in grid or grid[(2, 9)].effect_id != 70
    assert grid[(2, 6)].effect_id == 70
    had_cables = grid[(2, 6)].cable_in_mask != 0
    fm9.place_block(2, 6, 0)                      # clear the cell
    grid = {(c.row + 1, c.col + 1): c for c in fm9.read_grid() or []}
    assert (2, 6) not in grid                     # gone, cables and all
    assert had_cables


def test_cable_draw_roundtrip(fm9):
    fm9.place_block(2, 6, 0)                      # make room downstream
    fm9.place_block(3, 6, 126)                    # mixer on row 3 col 6
    fm9.connect_cells(2, 5, 3)                    # cable r2c5 -> r3c6
    grid = {(c.row + 1, c.col + 1): c for c in fm9.read_grid() or []}
    assert grid[(3, 6)].cable_in_mask & (1 << 2)  # fed from display row 2


def test_fresh_modifier_slot_is_dead_without_curve(fm9):
    """All-zero curve = dead binding; bind_modifier must initialize it."""
    fm9.bind_modifier(1, 70, 0, 11, min_norm=0.0, max_norm=0.5)
    vals = fm9.bulk_read(p.mod_slot_eid(1))
    slot = fm9.sim_core.st.buffer["modifiers"][1]
    assert slot[p.MOD_PID_SOURCE] == 11
    assert slot[p.MOD_PID_TARGET_EFFECT] == 70
    assert slot[4] > 0 and slot[5] > 0            # mid and end initialized
    assert abs(slot[2] / 65534 - 0.5) < 0.02      # max honored


def test_rename_and_store_roundtrip(fm9):
    fm9.rename_preset("FM9AI-Sim Test")
    fm9.rename_scene(2, "CHORUS Big")
    fm9.store_preset(133)                          # whitelisted slot
    fm9.select_preset(134)
    got = fm9.select_preset(133)
    assert got == (133, "FM9AI-Sim Test")
    assert fm9.scene_name(2)[1] == "CHORUS Big"


def test_store_whitelist_refuses_other_slots(fm9):
    with pytest.raises(PermissionError):
        fm9.store_preset(509)


def test_edit_buffer_discard_on_preset_change(fm9):
    fm9.rename_preset("SHOULD VANISH")
    fm9.select_preset(7)                           # away without store
    got = fm9.select_preset(0)
    assert got[1] != "SHOULD VANISH"


def test_tempo_roundtrip_and_store(fm9):
    fm9._drain()
    fm9._send(p.build_set_tempo(86))
    fm9.store_preset(140)
    fm9.select_preset(139)
    fm9.select_preset(140)
    got = fm9._request(p.build_get_tempo(),
                       lambda d: p.decode14(d[5], d[6]) if p.is_fractal(d, p.FN_TEMPO_BPM) and len(d) >= 7 else None)
    assert got == 86


def test_reads_inside_settle_window_see_stale_state(fm9):
    """Hardware writes are async: a read right after a raw write must see
    the OLD value (the 2026-08-20 race class). Settled reads see the new."""
    import time
    import fm9.sim as simmod
    from fm9 import protocol as p2
    spec = fm9.reg.spec("DISTORT", 11)
    fm9.set_param_display(spec, 3.0)          # settled write, known base
    time.sleep(0.1)
    prev = simmod.SETTLE
    simmod.SETTLE = 30.0                      # deterministic: no clock racing
    try:
        fm9._send(p2.build_set_param_continuous(spec.effect_id, spec.param_id, 0.9))
        stale = fm9.get_param_wire(spec, channel=0)
    finally:
        simmod.SETTLE = prev
    fm9.sim_core._snapshot_expire = 0.0       # force the window closed
    fresh = fm9.get_param_wire(spec, channel=0)
    assert stale != fresh                      # unsettled read lied honestly
    assert abs(fresh / 65534 - 0.9) < 0.02


def test_undecoded_territory_is_reported(fm9):
    """The sim must name what hardware never verified instead of passing
    silently: modifier curve writes and unproven cable geometries."""
    fm9.bind_modifier(1, 70, 0, 11, min_norm=0.0, max_norm=0.5)
    fm9.place_block(2, 6, 0)
    fm9.place_block(5, 6, 126)
    fm9.connect_cells(2, 5, 5)                 # 3-row jump: never verified
    rep = "\n".join(sorted(fm9.sim_core.undecoded))
    assert "modifier slot" in rep and "issue #11" in rep
    assert "cable" in rep and "not" in rep

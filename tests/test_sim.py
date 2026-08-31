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


def test_zeroed_get_is_noop(fm9, monkeypatch):
    """sub 09 00 with value 0 must NOT change a param.

    SETTLE is stood down for the duration. Brian's point on #37, and he was
    right: this test passed on a fast machine for a reason that had nothing to
    do with the behaviour it names. The settle window served the read from the
    pre-write snapshot while the live buffer had already been zeroed, so the
    damage was hidden. It failed only on CI, which was slow enough for the
    window to lapse first. With no window there is nowhere for a bad write to
    hide, and if this test ever goes quiet again, that is why.
    """
    import fm9.sim as sim
    monkeypatch.setattr(sim, "SETTLE", 0.0)
    spec = fm9.reg.spec("DISTORT", 11)
    fm9.set_param_display(spec, 4.86)
    fm9._drain()
    fm9._send(p.build_get_param(58, 11))     # the zeroed GET
    assert fm9.get_param_display(spec) == 4.86


def test_a_discrete_zero_is_a_read_for_every_kind_of_param(fm9, monkeypatch):
    """Not only for continuous ones.

    device.set_param_ordinal sends ordinal 0 as a CONTINUOUS 0.0 precisely
    because the discrete path cannot carry it: sub 09 with a zero value is the
    zeroed GET whatever the parameter is. A simulator that lets a discrete
    zero land on an enum is more permissive than the hardware, so code doing
    it would pass here and silently do nothing on the rig.
    """
    import fm9.sim as sim
    monkeypatch.setattr(sim, "SETTLE", 0.0)
    spec = fm9.reg.spec("DISTORT", 10)               # DISTORT_TYPE, an enum
    fm9.set_param_ordinal(spec, 28)
    assert fm9.get_param_wire(spec) == 28
    fm9._drain()
    fm9._send(p.build_set_param_discrete(58, 10, 0))  # a discrete zero
    assert fm9.get_param_wire(spec) == 28, \
        "a discrete zero wrote; on hardware it is a read"
    # and the way that IS supported still works
    fm9.set_param_ordinal(spec, 0)
    assert fm9.get_param_wire(spec) == 0


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


def test_the_zeroed_get_is_a_noop_regardless_of_timing(fm9, monkeypatch):
    """test_zeroed_get_is_noop passed on a fast machine for the wrong reason.

    The simulator models hardware's asynchronous writes: a write snapshots the
    pre-write buffer and reads inside SETTLE are served from it. That window
    was answering the read from the snapshot, so the value looked intact while
    the live buffer had already been zeroed by the very GET being tested. On
    CI, slow enough for the window to lapse first, the read hit the live
    buffer and returned 0.0 - failing on main at v0.3.1 and on every open PR.

    Pinned with the window removed, so the assertion is about the no-op rather
    than about how quickly the test ran.
    """
    import fm9.sim as sim
    monkeypatch.setattr(sim, "SETTLE", 0.0)
    spec = fm9.reg.spec("DISTORT", 11)
    fm9.set_param_display(spec, 4.86)
    fm9._drain()
    fm9._send(p.build_get_param(58, 11))
    assert fm9.get_param_display(spec) == 4.86


def test_a_discrete_write_of_zero_to_an_enum_still_lands(fm9, monkeypatch):
    """The no-op is scoped to continuous parameters, because that is where the
    GET collides. An enum set to ordinal 0 is a real write and must survive."""
    import fm9.sim as sim
    monkeypatch.setattr(sim, "SETTLE", 0.0)
    spec = fm9.reg.spec("DISTORT", 10)         # DISTORT_TYPE, an enum
    assert spec.kind == "enum"
    fm9.set_param_ordinal(spec, 3)
    fm9._drain()
    assert fm9.get_param_wire(spec) == 3
    fm9.set_param_ordinal(spec, 0)
    fm9._drain()
    assert fm9.get_param_wire(spec) == 0, "an enum write of 0 is a real write"


def test_a_snapshot_shares_nothing_with_the_live_buffer():
    """The settle window is modelled by snapshotting the buffer before each
    write, so a snapshot that aliases the live one stops modelling anything:
    the write lands in both and a read inside the window sees the new value.

    `copy.deepcopy` guaranteed this and cost 16 of the 23 seconds of a single
    splice, fifteen million calls deep. `_copy_buffer` knows the shape and
    slices instead. This is the property that made deepcopy worth its price,
    so it is checked directly rather than assumed.
    """
    from fm9.registry import Registry
    from fm9.sim import SimFM9, _copy_buffer
    dev = SimFM9(Registry())
    with dev:
        live = dev.sim_core.st.buffer
        snap = _copy_buffer(live)
        # _Cell has no __eq__, so cells compare by identity and a whole-dict
        # comparison would fail for deepcopy too. Compare what they hold.
        assert snap.keys() == live.keys()
        assert {k: v for k, v in snap.items() if k != "grid"} \
            == {k: v for k, v in live.items() if k != "grid"}
        assert {pos: vars(c) for pos, c in snap["grid"].items()} \
            == {pos: vars(c) for pos, c in live["grid"].items()}

        eid = next(iter(live["params"]))
        live["params"][eid][0][0] = 4321
        assert snap["params"][eid][0][0] != 4321, "parameter lists are shared"

        pos = next(iter(live["grid"]))
        live["grid"][pos].effect_id = 999
        assert snap["grid"][pos].effect_id != 999, "grid cells are shared"

        sc = next(iter(live["scenes"]))
        beid = next(iter(live["scenes"][sc]))
        live["scenes"][sc][beid]["bypassed"] = not live["scenes"][sc][beid]["bypassed"]
        assert snap["scenes"][sc][beid] != live["scenes"][sc][beid], \
            "per-scene block state is shared"

        slot = next(iter(live["modifiers"]))
        live["modifiers"][slot][0] = 77
        assert snap["modifiers"][slot][0] != 77, "modifier slots are shared"

        live["scene_names"][1] = "changed"
        assert snap["scene_names"][1] != "changed", "scene names are shared"


def test_an_unrecognised_key_is_still_copied_deeply():
    """A shape-aware copier is only safe while it knows the shape. Anything
    added to the buffer later must not be aliased in by default."""
    from fm9.sim import _copy_buffer
    live = {"number": 1, "surprise": {"nested": [1, 2, 3]}}
    snap = _copy_buffer(live)
    live["surprise"]["nested"].append(4)
    assert snap["surprise"]["nested"] == [1, 2, 3]

"""Splicing a block into a packed row (issue #10).

Nothing can be inserted between two adjacent blocks by cable alone, because
cables only ever run to the next column. The splice displaces neighbours
right, which is safe because a cleared block keeps its parameters, and
re-cables the span, which is possible because removal and same-row draws are
both decoded. Hardware-verified on fw 12.00; these pin the behaviour.
"""
from fm9.registry import Registry
from fm9.sim import SimFM9

ROW = 2          # the simulator's default preset runs along display row 2
# A block the default preset does NOT already contain. The simulator ignores
# placing an already-placed block at a second cell, exactly as the unit does,
# so splicing one that is already on the grid tests the refusal rather than
# the splice. This was CHORUS until the default preset gained one.
CHORUS, VOLUME = 78, 102

# The hardware needs 0.35s between grid writes and splice_block sleeps it once
# per displaced block, which is twelve seconds a test against a simulator that
# is not going anywhere. This is still comfortably above the simulator's own
# 0.08s settle window, so the read-after-write races these tests would
# otherwise stop catching are still modelled.
SETTLE = 0.12


def dev():
    return SimFM9(Registry())


def families(d, row=ROW):
    reg = d.registry if hasattr(d, "registry") else Registry()
    out = []
    for c in sorted((c for c in (d.read_grid() or []) if c.row == row - 1),
                    key=lambda c: c.col):
        if c.effect_id:
            fam = reg.family_of_effect_id(c.effect_id)
            out.append((c.col + 1, fam[0] if fam else c.effect_id))
    return out


def test_a_block_lands_where_asked_and_neighbours_move_right():
    with dev() as d:
        d.select_preset(0)
        before = dict(families(d))
        was_at_3 = before.get(3)
        r = d.splice_block(ROW, 3, CHORUS, settle=SETTLE)
        assert r["ok"], r["detail"]
        after = dict(families(d))
        assert after[3] == "CHORUS", "the new block takes the requested column"
        assert after[4] == was_at_3, "the displaced block moved one column right"


def test_continuity_is_proven_by_walking_the_path():
    """Not by counting members, and not by counting cells with no input
    cable: a block can be present, un-starved, and stranded off the signal."""
    from fm9.signal_path import scene_alive
    with dev() as d:
        d.select_preset(0)
        r = d.splice_block(ROW, 3, CHORUS, settle=SETTLE)
        assert r["ok"] and r["alive"], r["detail"]
        assert "live signal path confirmed" in r["detail"]
        st = {b.effect_id: b for b in d.status_dump() or []}
        alive, _ = scene_alive(d.read_grid() or [], st, Registry())
        assert alive


def test_a_splice_that_strands_the_signal_is_not_ok():
    """If the redraw failed to reconnect the span, the report must say so
    rather than counting the new block as placed and calling it done."""
    with dev() as d:
        d.select_preset(0)
        d.splice_block(ROW, 3, CHORUS, settle=SETTLE)
        # sever the feed into the spliced block: the path dies downstream
        d.connect_cells(ROW, 2, ROW, disconnect=True)
        st = {b.effect_id: b for b in d.status_dump() or []}
        from fm9.signal_path import scene_alive
        alive, why = scene_alive(d.read_grid() or [], st, Registry())
        assert not alive, "a severed span must not read as a live path"


def test_displaced_blocks_keep_their_parameters():
    """Hardware: all 588 values across four channels were byte-identical."""
    with dev() as d:
        d.select_preset(0)
        amp = 58
        d.status_dump()
        before = d.bulk_read(amp)
        d.splice_block(ROW, 3, CHORUS, settle=SETTLE)
        d.status_dump()
        assert d.bulk_read(amp) == before


def test_it_refuses_when_the_row_has_no_slack():
    """Rather than pushing a block off the end of the grid. The last column
    is the sharpest case: there is nowhere to the right at all."""
    with dev() as d:
        d.select_preset(0)
        d.place_block(ROW, 14, VOLUME)
        assert any(c.col == 13 and c.row == ROW - 1 for c in (d.read_grid() or [])), \
            "the last column must be occupied for this to test what it claims"
        r = d.splice_block(ROW, 14, CHORUS, settle=SETTLE)
        assert r["ok"] is False
        assert "off the end of the grid" in r["detail"]


def test_it_refuses_a_column_that_is_already_free():
    with dev() as d:
        d.select_preset(0)
        cols = [c for c, _ in families(d)]
        free = max(cols) + 2
        r = d.splice_block(ROW, free, CHORUS, settle=SETTLE)
        assert r["ok"] is False
        assert "already free" in r["detail"]


def test_it_refuses_when_the_span_is_fed_from_another_row():
    """Same-row redraw would silently break routing this code does not model."""
    with dev() as d:
        d.select_preset(0)
        d.place_block(ROW + 1, 3, VOLUME)
        d.connect_cells(ROW + 1, 3, ROW)          # cross-row feed into the span
        r = d.splice_block(ROW, 3, CHORUS, settle=SETTLE)
        assert r["ok"] is False
        assert "another row" in r["detail"]


def test_the_report_says_what_it_moved_and_what_it_spent():
    with dev() as d:
        d.select_preset(0)
        r = d.splice_block(ROW, 3, CHORUS, settle=SETTLE)
        assert r["placed_at"] == (ROW, 3)
        assert all(dst == src + 1 for _, src, dst in r["moved"])
        assert isinstance(r["spent_a_shunt"], bool)

"""Block reorder (#49): put effects in the right signal-chain order.

Signal-chain order is not cosmetic: delay belongs before reverb, drive before
the amp. The planner adds blocks and copy/compose lifts them, but neither used
to move a block to the correct position. reorder_block does, on the same-row
contiguous geometry the grid code models, and it proves the path still walks
rather than trusting a member count.

SimFM9 does not model the routing grid at all, so this uses a small in-memory
grid that reproduces the cabling semantics scene_alive actually walks: a
same-row cable from (row, c) to (row, c+1) sets bit (row+1) in the next cell's
input mask, an INPUT block starts the path, and an engaged OUTPUT ends it.
"""
from dataclasses import dataclass

from fm9.device import FM9
from fm9.registry import Registry


@dataclass
class _Cell:
    row: int
    col: int
    effect_id: int | None
    is_shunt: bool
    cable_in_mask: int


@dataclass
class _Blk:
    effect_id: int
    channel: int
    bypassed: bool
    channels_supported: int


class _GridDev:
    """One-row grid with real cabling semantics, enough for reorder + walk."""

    def __init__(self, row_eids, row=0):
        self.reg = Registry()
        self.row = row
        # col -> effect_id (None == pass-through/shunt)
        self.cells = {c: eid for c, eid in enumerate(row_eids)}
        self.mask = {}
        for c in self.cells:
            # every non-first cell is fed same-row from its left neighbour
            self.mask[c] = (1 << (row + 1)) if c > 0 else 0

    # --- grid reads/writes the reorder primitive uses --------------------
    def read_grid(self, timeout=2.0):
        out = []
        for c, eid in self.cells.items():
            out.append(_Cell(self.row, c, eid, eid is None, self.mask.get(c, 0)))
        return out

    def place_block(self, row_1, col_1, eid):
        c = col_1 - 1
        if eid == 0:
            self.cells[c] = None            # clear to a pass-through
        else:
            self.cells[c] = eid
        self.mask[c] = 0                     # clearing/placing drops the cable

    def connect_cells(self, src_row_1, src_col_1, dest_row_1, disconnect=False):
        # connect (src_row, src_col) -> (dest_row, src_col+1), same as hardware
        dest_c = src_col_1                   # 0-based col of the dest cell
        bit = 1 << src_row_1                 # walk tests 1 << (src_row0 + 1)
        if disconnect:
            self.mask[dest_c] = self.mask.get(dest_c, 0) & ~bit
        else:
            self.mask[dest_c] = self.mask.get(dest_c, 0) | bit

    def status_dump(self):
        return [_Blk(eid, 0, False, 1)
                for eid in self.cells.values() if eid is not None]

    def scene_name(self, scene=None):
        return (1, "SCENE 1")

    def set_scene(self, s):
        return s

    # reorder_block calls self.plan_reorder; delegate to the real logic
    def plan_reorder(self, *a, **k):
        return FM9.plan_reorder(self, *a, **k)


# effect ids: 37 INPUT, 58 amp, 62 cab, 70 DELAY, 66 REVERB, 42 OUTPUT
def _wrong_order_rig():
    # reverb BEFORE delay: the exact fault #49 exists to fix
    return _GridDev([37, 58, 62, 66, 70, 42])


def test_plan_reorder_computes_the_new_order_without_touching_the_grid():
    dev = _wrong_order_rig()
    before = dict(dev.cells)
    intent = FM9.plan_reorder(dev, 70, 66, "before")   # delay before reverb
    assert intent["ok"], intent
    assert intent["cur_order"] == [66, 70]
    assert intent["new_order"] == [70, 66]
    assert not intent["noop"]
    assert dev.cells == before, "plan must not mutate the grid"


def test_reorder_puts_delay_before_reverb_and_keeps_the_path_alive():
    dev = _wrong_order_rig()
    res = FM9.reorder_block(dev, 70, 66, "before", settle=0.0)
    assert res["ok"], res
    # the run columns (delay/reverb sat at cols 4,5 one-based) now read delay,reverb
    assert res["new_order"] == [70, 66]
    ids_in_order = [dev.cells[c] for c in sorted(dev.cells)]
    assert ids_in_order == [37, 58, 62, 70, 66, 42]
    assert res["alive"], res["detail"]


def test_reorder_is_a_noop_when_already_correct():
    dev = _GridDev([37, 58, 62, 70, 66, 42])          # already delay->reverb
    res = FM9.reorder_block(dev, 70, 66, "before", settle=0.0)
    assert res["ok"]
    assert res["reordered"] == []
    assert "already in that order" in res["detail"]


def test_reorder_refuses_a_cross_row_move():
    dev = _GridDev([37, 58, 62, 70, 42])
    dev.cells[10] = 66                                 # a reverb "on another row"
    # force it onto a different row by faking its cell row via a second dev read
    # simpler: point plan at a ref not on the moving block's row
    dev2 = _GridDev([37, 58, 62, 70, 42])

    class _TwoRow(_GridDev):
        def read_grid(self, timeout=2.0):
            cells = super().read_grid()
            cells.append(_Cell(2, 3, 66, False, 0))    # reverb on row 2
            return cells

    d = _TwoRow([37, 58, 62, 70, 42])
    intent = FM9.plan_reorder(d, 70, 66, "before")
    assert not intent["ok"] and intent["reason"] == "cross_row"


def test_reorder_refuses_a_gap_in_the_run():
    # a pass-through sits between the two blocks: not re-insertable, so refuse
    dev = _GridDev([37, 58, 62, 66, None, 70, 42])
    intent = FM9.plan_reorder(dev, 70, 66, "before")
    assert not intent["ok"] and intent["reason"] == "run_not_contiguous"


def test_the_reorder_endpoint_exists_and_is_shaped_right():
    import server
    routes = {r.path for r in server.app.routes if getattr(r, "methods", None)}
    assert "/api/reorder" in routes

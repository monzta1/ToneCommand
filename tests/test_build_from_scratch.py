"""Building a chain into an empty slot, and refusing when there is none.

An empty FM9 slot has no grid cells and no Input/Output blocks, so a
from-scratch build places everything and draws every cable. The rule this
suite protects: it lands on a slot the device calls <EMPTY> or it does not
run at all.
"""
import pytest

from fm9.device import NoEmptySlot
from fm9.registry import Registry
from fm9.sim import SimFM9
from tools.build_from_scratch import CHAIN, ROW, main


@pytest.fixture
def sim(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_SIM", "1")


def dev():
    return SimFM9(Registry())


# --- slot selection ---

def test_first_empty_slot_returns_the_lowest_free_one():
    with dev() as d:
        assert d.first_empty_slot().number == 386


def test_first_empty_slot_honours_a_range():
    with dev() as d:
        assert d.first_empty_slot(400, 511).number == 449


def test_no_free_slot_refuses_with_a_message_about_empty_presets():
    """The build must never fall back to overwriting someone's preset."""
    with dev() as d:
        with pytest.raises(NoEmptySlot, match="no empty presets to build on"):
            d.first_empty_slot(0, 10)


def test_the_refusal_says_how_to_find_a_slot():
    with dev() as d:
        with pytest.raises(NoEmptySlot) as err:
            d.first_empty_slot(0, 10)
    assert "find_empty_slots" in str(err.value)


# --- the tool ---

def test_it_picks_an_empty_slot_by_itself(sim, capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "target: slot 387 (wire 386)" in out and "'<EMPTY>'" in out
    assert "live signal path confirmed" in out


def test_it_refuses_when_the_range_holds_no_empty_slot(sim, capsys):
    assert main(["--range", "0", "10"]) == 1
    out = capsys.readouterr().out
    assert "refusing to build" in out
    assert "no empty presets to build on" in out


def test_it_refuses_an_occupied_slot_given_explicitly(sim, capsys):
    assert main(["--slot", "0"]) == 1
    out = capsys.readouterr().out
    assert "refusing to build" in out
    assert "requires a slot the device reports as <EMPTY>" in out


def test_an_explicit_empty_slot_is_honoured(sim, capsys):
    assert main(["--slot", "449"]) == 0
    assert "target: slot 450 (wire 449)" in capsys.readouterr().out


def test_no_force_flag_exists(sim):
    """Overwriting an owned preset should not be one flag away."""
    with pytest.raises(SystemExit):
        main(["--force"])


# --- what the build produces ---

def test_every_block_lands_and_the_chain_is_continuous():
    with dev() as d:
        d.select_preset(386)
        for col, (eid, _) in enumerate(CHAIN, start=1):
            d.place_block(ROW, col, eid)
        for col in range(1, len(CHAIN)):
            d.connect_cells(ROW, col, ROW)
        cells = {c.col + 1: c for c in d.read_grid() or []}
        assert sorted(c.effect_id for c in cells.values()) == \
            sorted(eid for eid, _ in CHAIN)
        assert cells[1].cable_in_mask == 0, "the input feeds nothing upstream"
        for col in range(2, len(CHAIN) + 1):
            assert cells[col].cable_in_mask != 0, f"col {col} has no input cable"


def test_the_build_stores_nothing(sim, capsys, monkeypatch):
    """Watch the instance the tool actually uses: asserting against a fresh
    SimFM9 would pass even if the tool called store_preset."""
    from fm9.device import FM9
    calls = []
    monkeypatch.setattr(FM9, "store_preset",
                        lambda self, slot: calls.append(slot))
    assert main([]) == 0
    assert calls == [], f"the build must not persist anything, stored: {calls}"
    with dev() as d:
        assert d.slot_name(386).name == "<EMPTY>"
    assert "nothing stored" in capsys.readouterr().out


def test_it_refuses_when_the_select_lands_somewhere_else(sim, capsys, monkeypatch):
    """The select decides which preset every later insert edits. If it is
    dropped, the tool would edit the owner's loaded preset and still report
    success, because verification reads back the buffer it just wrote."""
    from fm9.device import FM9
    inserts = []
    monkeypatch.setattr(FM9, "select_preset", lambda self, n: (n + 1, "somewhere else"))
    monkeypatch.setattr(FM9, "place_block",
                        lambda self, r, c, e: inserts.append((r, c, e)))
    assert main([]) == 1
    assert inserts == [], "nothing may be edited once the slot is in doubt"
    assert "refusing to build" in capsys.readouterr().out


def test_a_present_but_stranded_block_is_not_a_live_path():
    """Membership is not a path. A block on the cursor cell at row 1 col 1 is
    present and un-starved while being nowhere near the signal - the class of
    silent preset this project has been bitten by repeatedly."""
    from tools.path_audit import scene_alive
    reg = Registry()
    with dev() as d:
        d.select_preset(386)
        for col, (eid, _) in enumerate(CHAIN, start=1):
            d.place_block(ROW, col, eid)
        for col in range(1, len(CHAIN)):
            d.connect_cells(ROW, col, ROW)
        cells = d.read_grid() or []
        blocks = {b.effect_id: b for b in d.status_dump() or []}
        alive, why = scene_alive(cells, blocks, reg)
        assert alive, f"the built chain should be alive: {why}"

        # now strand the input: present, un-starved, off the path
        d.place_block(ROW, 1, 0)
        d.place_block(1, 1, 37)
        cells = d.read_grid() or []
        blocks = {b.effect_id: b for b in d.status_dump() or []}
        present = {c.effect_id for c in cells}
        assert all(eid in present for eid, _ in CHAIN), \
            "membership alone still looks fine, which is the trap"
        alive, why = scene_alive(cells, blocks, reg)
        assert not alive, "a stranded input must not read as a live path"


def test_the_tool_prints_the_editor_number_too(sim, capsys):
    """The owner reads FM9-Edit, not the wire: a bare wire number is how the
    wrong preset gets cleared."""
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "387 (wire 386)" in out


def test_the_build_leaves_no_undecoded_geometry_on_the_sim():
    """This PR declares row-3 same-row draws hardware-verified (finding 20),
    so the simulator must stop flagging them. Otherwise a sim run of the tool
    reports geometry as unverified that the ledger already records."""
    with dev() as d:
        d.select_preset(386)
        for col, (eid, _) in enumerate(CHAIN, start=1):
            d.place_block(ROW, col, eid)
        for col in range(1, len(CHAIN)):
            d.connect_cells(ROW, col, ROW)
        cable_notes = [u for u in d.sim_core.undecoded if "cable" in u]
        assert cable_notes == [], f"unexpected undecoded report: {cable_notes}"


# --- the refusal path has to actually be reachable (#22 review) ---

def test_a_device_nack_prints_a_refusal_rather_than_a_traceback(sim, capsys,
                                                                monkeypatch):
    """NoEmptySlot and FM9NotFound are both RuntimeError, but _request raises
    the BARE parent on a device NACK. Naming only the children let that escape
    as a traceback where a refusal line belongs."""
    from fm9.device import FM9
    def nack(self, n=None):
        raise RuntimeError("device NACK: rejected (invalid function)")
    monkeypatch.setattr(FM9, "slot_name", nack)
    assert main(["--slot", "386"]) == 1
    out = capsys.readouterr().out
    assert "refusing to build" in out
    assert "device NACK" in out


def test_an_inverted_range_is_refused_not_reported_as_a_full_unit(sim, capsys):
    """--range 449 386 scanned nothing and announced that every slot in
    449-386 holds a preset, which tells the owner their unit is full when it
    may be empty."""
    assert main(["--range", "449", "386"]) == 1
    out = capsys.readouterr().out
    assert "refusing to build" in out
    assert "runs backwards" in out
    assert "holds a preset" not in out


def test_scan_slots_refuses_an_inverted_range_for_every_caller():
    with dev() as d:
        with pytest.raises(ValueError, match="runs backwards"):
            list(d.scan_slots(449, 386))
        with pytest.raises(ValueError, match="runs backwards"):
            d.first_empty_slot(449, 386)

"""Issue #10: a splice must be consented to on its real terms.

The maintainer's condition for wiring this into the planner: the column slide
is reversible by re-selecting the preset, spending a pass-through cell is not,
and one approval covering both with nothing to tell them apart is not informed
consent. So the two are reported and displayed separately.

The FIRST wording of that distinction was wrong, and hardware said so. It
claimed the spent cell "does not come back, even after re-selecting the
preset". Re-selecting reloads from flash, so it does come back, along with
everything else the edit buffer held. What is actually one-way is that
nothing can put the cell back on its own: the only route is to discard the
whole edit, and a store makes the loss permanent. The tests below pin the
corrected claim, since a confirmation that overstates is not better than one
that understates - both teach the reader to stop believing it.
"""
from pathlib import Path

from fm9.registry import Registry
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


def test_the_plan_reports_the_slide_and_the_spend_separately():
    with SimFM9(Registry()) as dev:
        dev.select_preset(0)
        intent = dev.plan_splice(2, 3)
    assert intent["ok"]
    assert intent["moves"], "the slide has to be enumerated, not summarised"
    assert "spends_shunt" in intent, "the one-way step needs its own field"
    assert intent["spends_shunt"] is True     # the sim's col 5 is a shunt


def test_a_free_column_spends_nothing():
    """Sliding into empty space costs nobody anything, and must not claim to."""
    with SimFM9(Registry()) as dev:
        dev.select_preset(0)
        dev.place_block(2, 12, 102)           # occupy past the shunts
        intent = dev.plan_splice(2, 12)
    assert intent["ok"] and intent["spends_shunt"] is False


def test_refusals_name_themselves():
    with SimFM9(Registry()) as dev:
        dev.select_preset(0)
        assert dev.plan_splice(2, 13)["reason"] == "already_free"
        dev.place_block(2, 14, 102)
        assert dev.plan_splice(2, 14)["reason"] == "no_room_right"
        dev.place_block(3, 3, 103)
        dev.connect_cells(3, 3, 2)            # cross-row feed into the span
        assert dev.plan_splice(2, 3)["reason"] == "fed_from_another_row"


def test_the_ui_shows_the_two_consequences_differently():
    assert "spliceNote" in UI
    assert "re-selecting the preset puts them back" in UI
    assert "nothing here puts" in UI
    assert ".splice .oneway" in UI, "the one-way step needs its own styling"
    assert "ONE WAY" in UI


def test_the_one_way_claim_is_the_one_hardware_supports():
    """Verified on fw 12.00, preset wire 1: after the splice the shunt was
    gone from the grid read, and after re-selecting the preset it was back
    along with every other block. So the cell is unrecoverable ON ITS OWN,
    not unrecoverable full stop, and the copy says exactly that."""
    assert "does not come back, even after re-selecting" not in UI
    assert "throws away " in UI and "every other change too" in UI
    assert "Store the preset and it is gone for good" in UI


def test_transmit_asks_before_spending_a_shunt():
    """Distinct from the existing store confirmation, and it must name what
    is reversible so the two are not conflated."""
    assert "spends a pass-through cell" in UI
    assert "Moving the blocks one column" in UI and "is reversible" in UI
    assert "storing the preset makes it permanent" in UI
    assert "splice not confirmed; transmit cancelled" in UI


def test_no_em_dashes_in_the_new_copy():
    assert "—" not in UI

"""Empty preset slots: the <EMPTY> marker, the ghost it leaves, and the
non-destructive by-number name read a from-scratch build needs.

Byte fixtures are verbatim from the reference FM9 (fw 12.00), captured in a
512-slot sweep. Slot 386 is an empty slot whose previous name survives past
the marker; slot 144 is occupied.
"""
import pytest

from fm9 import protocol as p
from fm9.registry import Registry
from fm9.sim import SimFM9

# Raw 32-byte name fields, straight off the wire.
EMPTY_386 = b'<EMPTY>\x00 Phat Time             \x00'
EMPTY_449 = b'<EMPTY>\x00                        \x00'
FULL_144 = b'Jeff Gets Ready FM             \x00'


def name_frame(number: int, field: bytes) -> list[int]:
    """A fn 0x0D response as the device delivers it (F0/F7 stripped)."""
    return p.envelope(p.FN_PATCH_NAME,
                      [*p.encode14(number), *list(field)])[1:-1]


def test_name_field_is_cut_at_the_first_nul_not_right_stripped():
    """The bug the sweep exposed: rstrip leaves the old name glued on."""
    name, ghost = p.decode_name_field(EMPTY_386)
    assert name == "<EMPTY>"
    assert ghost == "Phat Time"
    # what the old right-stripping parser produced, for the record
    assert "".join(chr(c) for c in EMPTY_386).rstrip("\x00 ") \
        == "<EMPTY>\x00 Phat Time"


def test_occupied_name_survives_unchanged():
    name, ghost = p.decode_name_field(FULL_144)
    assert name == "Jeff Gets Ready FM"
    assert ghost == ""


def test_empty_slot_without_a_ghost():
    name, ghost = p.decode_name_field(EMPTY_449)
    assert (name, ghost) == ("<EMPTY>", "")


def test_parse_patch_name_no_longer_leaks_the_ghost():
    assert p.parse_patch_name(name_frame(386, EMPTY_386)) == (386, "<EMPTY>")
    assert p.parse_patch_name(name_frame(144, FULL_144)) \
        == (144, "Jeff Gets Ready FM")


def test_parse_patch_name_full_reports_number_name_ghost_and_emptiness():
    got = p.parse_patch_name_full(name_frame(386, EMPTY_386))
    assert (got.number, got.name, got.ghost) == (386, "<EMPTY>", "Phat Time")
    assert got.empty is True
    occupied = p.parse_patch_name_full(name_frame(144, FULL_144))
    assert occupied.empty is False
    assert occupied.ghost == ""


def test_is_empty_slot_name_only_matches_the_device_marker():
    assert p.is_empty_slot_name("<EMPTY>")
    assert p.is_empty_slot_name("  <EMPTY> ")
    assert not p.is_empty_slot_name("EMPTY")
    assert not p.is_empty_slot_name("<EMPTY> Lead")     # a real, named preset
    assert not p.is_empty_slot_name("New Preset")


# --- device surface, exercised against the simulator ---

def test_slot_name_reads_any_slot_without_selecting_it():
    dev = SimFM9(Registry())
    with dev:
        before = dev.current_preset()
        assert dev.slot_name(386).name == "<EMPTY>"
        assert dev.slot_name(386).ghost == "Phat Time"
        assert dev.slot_name(0).empty is False
        assert dev.current_preset() == before, \
            "reading a slot name must not move the loaded preset"


def test_is_slot_empty_both_ways():
    dev = SimFM9(Registry())
    with dev:
        assert dev.is_slot_empty(387) is True
        assert dev.is_slot_empty(0) is False


def test_require_empty_slot_gates_from_scratch_builds():
    dev = SimFM9(Registry())
    with dev:
        got = dev.require_empty_slot(386)
        assert got.number == 386 and got.empty
        with pytest.raises(ValueError, match="requires a slot"):
            dev.require_empty_slot(0)


def test_scan_slots_finds_the_empty_ones_in_a_range():
    dev = SimFM9(Registry())
    with dev:
        found = list(dev.scan_slots(384, 390))
        assert [s.number for s in found] == list(range(384, 391))
        assert [s.number for s in found if s.empty] == [386, 387]


def test_an_empty_slot_is_empty_by_all_three_signals():
    """Name marker, status dump, and grid must agree - the check the sweep
    ran on hardware, reproduced headless."""
    dev = SimFM9(Registry())
    with dev:
        assert dev.select_preset(386)[1] == "<EMPTY>"
        assert dev.status_dump() == []
        assert dev.read_grid() == []
        assert dev.scene_name(1)[1] == ""       # hardware: all-NUL field
        dev.select_preset(0)
        assert dev.status_dump(), "an occupied slot still reports blocks"


def test_range_collapse_reports_contiguous_free_runs():
    from tools.find_empty_slots import runs
    assert runs([386, 387, 388, 449, 508, 509]) == [(386, 388), (449, 449),
                                                    (508, 509)]
    assert runs([]) == []


# --- preset numbering: wire 0-511 vs FM9-Edit 1-512 ---

def test_editor_numbering_is_one_based():
    """FM9-Edit and the front panel number the same 512 slots from 1."""
    assert p.editor_number(0) == 1
    assert p.editor_number(386) == 387        # the slot this was found on
    assert p.editor_number(511) == p.PRESET_COUNT == 512


def test_slot_label_shows_both_numbers_owners_first():
    """The editor number leads: it is the one on the front panel, in
    FM9-Edit and in the header pill, so every label agrees with them on
    which number comes first (reordered 2026-09-01 after the header said
    159 over a panel saying 158)."""
    assert p.slot_label(386) == "387 (wire 386)"
    got = p.SlotName(386, "<EMPTY>", "Phat Time")
    assert got.editor == 387 and got.label == "387 (wire 386)"


def test_out_of_range_slots_are_refused_not_believed():
    """The unit ANSWERS a query for preset 512 with a blank name, and a blank
    is not the <EMPTY> marker - so an unguarded read calls it OCCUPIED, which
    is the wrong direction for code deciding where to write."""
    dev = SimFM9(Registry())
    with dev:
        for bad in (-1, 512, 9999):
            with pytest.raises(ValueError, match="out of range"):
                dev.slot_name(bad)
        with pytest.raises(ValueError, match="out of range"):
            list(dev.scan_slots(500, 512))


def test_range_refusal_names_both_numbering_schemes():
    dev = SimFM9(Registry())
    with dev:
        with pytest.raises(ValueError) as err:
            dev.slot_name(512)
    assert "0-511" in str(err.value) and "1-512" in str(err.value)


def test_an_occupied_slot_refusal_carries_the_editor_number():
    dev = SimFM9(Registry())
    with dev:
        with pytest.raises(ValueError, match=r"preset 1 \(wire 0\)"):
            dev.require_empty_slot(0)

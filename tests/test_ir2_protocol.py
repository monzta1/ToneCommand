"""The IR-2 codec, pinned against frames actually seen on the wire.

The golden frame is BOSS's own IR-2 IR Loader talking to the pedal, captured
with MIDI Monitor on 2026-09-29. If the codec ever stops reproducing it byte
for byte, the codec is wrong, not the capture.
"""
import pytest

from devices.ir2 import protocol as p

# Captured from the BOSS loader's launch handshake (kb/IR2_PROTOCOL.md)
LOADER_RQ1 = [0xF0, 0x41, 0x10, 0x01, 0x05, 0x09, 0x11,
              0x7F, 0x00, 0x03, 0x01, 0x00, 0x00, 0x00, 0x01, 0x7C, 0xF7]
PEDAL_DT1 = [0xF0, 0x41, 0x10, 0x01, 0x05, 0x09, 0x12,
             0x7F, 0x00, 0x03, 0x01, 0x03, 0x7A, 0xF7]


def test_read_frame_reproduces_the_vendor_loaders_own_request():
    assert p.read_frame(0x7F000301, 1) == LOADER_RQ1


def test_parse_reads_the_pedals_reply():
    assert p.parse(PEDAL_DT1) == (0x7F000301, [0x03])


def test_checksums_match_rolands_rule_on_both_captured_frames():
    assert p.checksum([0x7F, 0x00, 0x03, 0x01, 0x00, 0x00, 0x00, 0x01]) == 0x7C
    assert p.checksum([0x7F, 0x00, 0x03, 0x01, 0x03]) == 0x7A


def test_a_bad_checksum_is_not_parsed_rather_than_raising():
    bad = list(PEDAL_DT1)
    bad[-2] = (bad[-2] + 1) & 0x7F
    assert p.parse(bad) is None


def test_foreign_sysex_is_ignored():
    assert p.parse([0xF0, 0x00, 0x21, 0x1A, 0xF7]) is None          # not Roland
    assert p.parse([0xF0, 0x41, 0x10, 0x99, 0x99, 0x99, 0x12, 0, 0, 0, 0, 1, 2, 0xF7]) is None


# --- invariant 0 is structural, not a habit ------------------------------

@pytest.mark.parametrize("cmd", [0x00, 0x10, 0x13, 0x1F, 0x7F, 0x41])
def test_only_rq1_and_dt1_can_ever_be_built(cmd):
    """Anything that is not a parameter read or write is unsendable by
    construction: `build` refuses before a frame exists, so no firmware or
    bootloader operation has a code path out of this process."""
    with pytest.raises(p.ProtocolError):
        p.build(cmd, p.PATCH, [0])


def test_allowed_set_is_exactly_read_and_write():
    assert p.ALLOWED == {p.RQ1, p.DT1}


def test_a_payload_byte_above_7_bits_is_refused():
    with pytest.raises(p.ProtocolError):
        p.write_frame(p.PATCH, [0x80])


def test_an_address_byte_above_7_bits_is_refused():
    with pytest.raises(p.ProtocolError):
        p.addr_bytes(0x80000000)


# --- the IR slot map ------------------------------------------------------

def test_user_slots_are_numbered_the_way_the_pedal_numbers_them():
    """Eleven, starting at one. The vendor config declares
    `numOfIrData = 11` and its editor addresses them IRDATA(1) to
    IRDATA(11); an earlier version of this module listed twelve starting at
    zero, which presented a staging region as an empty user slot and put
    every real slot's number out by one at the top."""
    assert p.IR_SLOTS == 11 and p.IR_FIRST_SLOT == 1
    assert p.ir_slot_addr(1) == 0x31000000
    assert p.ir_slot_addr(11) == 0x3B000000


def test_there_is_no_slot_zero():
    """0x30000000 accepts a write and reads it back, but nothing in BOSS's
    own software writes there, so asking for it by number is a mistake worth
    naming rather than quietly resolving."""
    with pytest.raises(p.ProtocolError, match="no slot 0"):
        p.ir_slot_addr(0)
    assert p.IRDATA_STAGING == 0x30000000


def test_ir_slot_out_of_range_is_refused():
    with pytest.raises(p.ProtocolError, match="not 12"):
        p.ir_slot_addr(12)


# --- base-128 addressing --------------------------------------------------

def test_addresses_carry_at_128_not_256():
    """Every byte of a Roland address is 7-bit. Plain integer addition looks
    right for small offsets and then produces an illegal address: this was
    found when reading an IR in 240-nibble chunks walked off the end."""
    assert p.addr_offset(0x31300000, 240) == 0x31300170
    with pytest.raises(p.ProtocolError):
        p.addr_bytes(0x31300000 + 240)


def test_the_vendor_map_agrees_with_our_arithmetic():
    """IRDATA DATA entry 3400 sits at 0x00015438 in BOSS's own address map,
    which is 3399 * 8 in base 128 exactly."""
    assert p.addr_offset(0, 3399 * 8) == 0x00015438

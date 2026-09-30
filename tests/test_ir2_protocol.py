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

def test_ir_slot_addresses_step_by_one_high_byte():
    assert p.ir_slot_addr(0) == 0x30000000
    assert p.ir_slot_addr(11) == 0x3B000000


def test_ir_slot_out_of_range_is_refused():
    with pytest.raises(p.ProtocolError):
        p.ir_slot_addr(p.IR_SLOTS)

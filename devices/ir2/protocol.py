"""BOSS IR-2 SysEx codec.

Roland addressed SysEx. Every constant here was proven on the unit
(kb/IR2_PROTOCOL.md) rather than taken from a forum post: the model ID and
the frame shape were read off BOSS's own IR-2 IR Loader traffic with MIDI
Monitor's spy, and both checksums in that exchange were recomputed and
matched before anything was built on them.

    F0 41 <dev> 01 05 09 <cmd> <address x4> <payload> <checksum> F7

`cmd` is RQ1 (0x11, a read, payload is a 4-byte size) or DT1 (0x12, data,
payload is the data). The device answers an RQ1 with a DT1 at the same
address, and also emits DT1 unprompted whenever a knob moves or the
footswitch is pressed, which is what gives this device a real read path.

INVARIANT 0. `build` refuses any command that is not RQ1 or DT1 before a
frame exists, so a firmware or bootloader operation is unsendable by
construction rather than by care. There is no code path here that can emit
one, the same property fm9/device.py's transport whitelist provides.
"""
from __future__ import annotations

ROLAND = 0x41
DEVICE_ID = 0x10
MODEL = (0x01, 0x05, 0x09)

RQ1 = 0x11          # read
DT1 = 0x12          # data (sent by the device; we send it to write)

#: The only commands that may ever leave this process. Anything else raises
#: before a frame is built. Invariant 0, structural.
ALLOWED = frozenset({RQ1, DT1})

# --- address tree (js/config/address_map.js in the BOSS loader, confirmed
# against the unit for SETUP, SYSTEM, PATCH and IRDATA NAME) ---------------
SETUP = 0x00000000
SYSTEM = 0x10000000
PATCH = 0x20000000          # the live/edit patch
PATCH_1 = 0x21000000        # stored memory 1
PATCH_2 = 0x22000000        # stored memory 2
#: NOT a user slot. The vendor config declares `numOfIrData = 11` and its
#: editor addresses them as IRDATA(1) to IRDATA(11); this bare IRDATA region
#: appears in neither list. It accepts a write and reads it back (proven on
#: hardware 2026-09-29) but nothing in BOSS's own software writes here, so
#: neither does this. Named so the address is not mistaken for slot zero,
#: which is what an earlier version of this file called it.
IRDATA_STAGING = 0x30000000

#: The user slots, numbered as the pedal and its editor number them: USER 1
#: through USER 11 at 0x31000000 through 0x3B000000. There is no USER 0.
IR_SLOT_BASE = 0x31000000
IR_SLOTS = 11
IR_FIRST_SLOT = 1
IR_NAME = 0x00000000        # offset within an IRDATA slot, 32 bytes
IR_SIZE = 0x00100000
IR_FILE = 0x00200000
IR_DATA = 0x00300000


class ProtocolError(RuntimeError):
    """One line, written for the person at the rig."""


def checksum(body: list[int]) -> int:
    """Roland's: 128 minus the sum of address and payload, modulo 128."""
    return (128 - (sum(body) % 128)) % 128


def addr_bytes(addr: int) -> list[int]:
    """A 32-bit address as the four 7-bit-safe bytes the device expects.

    Every byte of a Roland address is already below 0x80 in this device's
    map, so this is a plain split and a value that would set the high bit
    is a bug in the caller, not something to mask away quietly.
    """
    out = [(addr >> 24) & 0xFF, (addr >> 16) & 0xFF,
           (addr >> 8) & 0xFF, addr & 0xFF]
    for b in out:
        if b > 0x7F:
            raise ProtocolError(f"address {addr:#010x} has a byte above 0x7F; "
                                "that is not a valid Roland address")
    return out


def addr_offset(addr: int, delta: int) -> int:
    """`addr` advanced by `delta` units, in Roland's base-128 arithmetic.

    Every byte of a Roland address is 7-bit, so the bytes carry at 0x80 and
    not at 0x100. Plain integer addition looks right for small offsets and
    then silently produces an illegal address: 0x31300000 + 240 gives
    0x313000F0, whose low byte is above 0x7F. `addr_bytes` refuses that
    rather than masking it away, which is how this was found.

    Confirmed against the vendor's own map: IRDATA DATA entry 3400 sits at
    0x00015438, which is 3399 * 8 in base 128 exactly.
    """
    n = (((addr >> 24) & 0x7F) << 21 | ((addr >> 16) & 0x7F) << 14
         | ((addr >> 8) & 0x7F) << 7 | (addr & 0x7F)) + int(delta)
    if n < 0:
        raise ProtocolError("address offset goes below zero")
    return (((n >> 21) & 0x7F) << 24 | ((n >> 14) & 0x7F) << 16
            | ((n >> 7) & 0x7F) << 8 | (n & 0x7F))


def build(cmd: int, addr: int, payload: list[int]) -> list[int]:
    """One frame. Refuses any command outside ALLOWED before building."""
    if cmd not in ALLOWED:
        raise ProtocolError(
            f"command {cmd:#04x} is not RQ1 or DT1; refusing to build a frame. "
            "This device's transport carries parameter reads and writes only.")
    for b in payload:
        if not 0 <= b <= 0x7F:
            raise ProtocolError(f"payload byte {b:#04x} is not 7-bit")
    body = addr_bytes(addr) + list(payload)
    return ([0xF0, ROLAND, DEVICE_ID, *MODEL, cmd]
            + body + [checksum(body), 0xF7])


def read_frame(addr: int, size: int) -> list[int]:
    """RQ1. `size` is the byte count, sent as Roland's four-byte size."""
    if size < 1:
        raise ProtocolError("size must be at least 1")
    return build(RQ1, addr, [(size >> 21) & 0x7F, (size >> 14) & 0x7F,
                             (size >> 7) & 0x7F, size & 0x7F])


def write_frame(addr: int, data: list[int]) -> list[int]:
    """DT1."""
    if not data:
        raise ProtocolError("a write needs at least one byte")
    return build(DT1, addr, list(data))


def parse(raw: list[int]) -> tuple[int, list[int]] | None:
    """(address, data) from a DT1 this device sent, or None if the message
    is not one of ours. A bad checksum returns None rather than raising: the
    caller is draining a live MIDI stream, not validating a file."""
    if len(raw) < 13 or raw[0] != 0xF0 or raw[1] != ROLAND:
        return None
    if tuple(raw[3:6]) != MODEL or raw[6] != DT1:
        return None
    body = raw[7:-2]
    if checksum(body) != raw[-2]:
        return None
    addr = (body[0] << 24) | (body[1] << 16) | (body[2] << 8) | body[3]
    return addr, list(body[4:])


def ir_slot_addr(slot: int, offset: int = IR_NAME) -> int:
    """The address of one field inside USER slot `slot`.

    `slot` is the number the pedal and its editor use, 1 to 11, so what a
    caller types matches what the player sees. Slot 0 is refused rather than
    quietly resolving to IRDATA_STAGING, which is not a user slot and which
    an earlier version of this module wrongly presented as one.
    """
    if not IR_FIRST_SLOT <= slot < IR_FIRST_SLOT + IR_SLOTS:
        raise ProtocolError(
            f"the IR-2 has USER slots {IR_FIRST_SLOT} to "
            f"{IR_FIRST_SLOT + IR_SLOTS - 1}, not {slot}"
            + (". There is no slot 0: the region below USER 1 is a staging "
               "area the vendor's own editor never writes to"
               if slot == 0 else ""))
    return IR_SLOT_BASE + ((slot - IR_FIRST_SLOT) << 24) + offset

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
IRDATA = 0x30000000         # IR slot 0; slots 1..11 are +0x01000000 each

IR_SLOTS = 12
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
    """The address of one field inside IR slot `slot` (0 to 11)."""
    if not 0 <= slot < IR_SLOTS:
        raise ProtocolError(f"IR slot {slot} is outside 0..{IR_SLOTS - 1}")
    return IRDATA + (slot << 24) + offset

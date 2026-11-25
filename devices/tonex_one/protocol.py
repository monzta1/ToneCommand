"""The IK Multimedia ToneX One's USB control protocol.

WHERE THIS COMES FROM. The One has no MIDI. It is a USB CDC serial device
(vendor 0x1963, product 0x00D1) speaking HDLC-framed messages, decoded by the
community: vit3k/tonex_controller (MIT, protocol.md) and
Builty/TonexOneController (Apache-2.0, usb_tonex_one.c). Every frame below
was then checked on a real One (fw 1.3.17, 2026-11-25): the footswitch push,
the hello reply, the state reply and all twenty preset summaries, each frame
passing its checksum. See kb/TONEX_ONE_PROTOCOL.md.

FRAMING. 0x7E, payload, CRC-16/X-25 (little-endian), 0x7E; 0x7E and 0x7D
inside are escaped as 0x7D, byte ^ 0x20 (checksum included).

VALUES. Tagged: 0x80 one byte (for values >= 0x80), 0x81/0x82 two bytes
little-endian, 0x88 float32 little-endian, 0xB9/0xBA lists with a count,
0xBC a byte string with a length; any other byte below 0x80 is itself.

THE SEND GATE. `checked_frame` is the only way bytes are produced for the
wire, and it refuses anything that is not one of five shapes: hello, request
state, request a preset's summary, set one preset setting (an allowed index,
a value inside its range) and write the pedal state (the same length as the
state last read, with only the bytes this module knows how to change
differing). There is no firmware, bootloader or file transfer message here,
and none can be built: rule zero, by construction.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass

VENDOR_ID = 0x1963
PRODUCT_ID = 0x00D1

FLAG, ESC = 0x7E, 0x7D

#: Message types, as the header's first value.
T_HELLO = 0x0002            # the pedal's hello reply
T_PRESET = 0x0304           # a preset summary (name, settings, tags)
T_STATE = 0x0306            # the pedal's whole state
T_PARAM = 0x0309            # one setting changed

PRESETS = 20


class ProtocolError(ValueError):
    """A frame that does not decode, or a send the gate refuses."""


# --- checksum and framing ---------------------------------------------------

def crc_x25(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def frame(payload: bytes) -> bytes:
    c = crc_x25(payload)
    out = bytearray([FLAG])
    for b in payload + bytes([c & 0xFF, c >> 8]):
        if b in (FLAG, ESC):
            out += bytes([ESC, b ^ 0x20])
        else:
            out.append(b)
    out.append(FLAG)
    return bytes(out)


def unframe_stream(stream: bytes) -> tuple[list[bytes], bytes]:
    """Split a byte stream into checked payloads. Returns (payloads, the
    unfinished tail to keep for the next read). A frame whose checksum fails
    is dropped: a lost byte must never become a wrong value."""
    payloads: list[bytes] = []
    start = stream.find(bytes([FLAG]))
    if start < 0:
        return payloads, b""
    i = start
    while True:
        end = stream.find(bytes([FLAG]), i + 1)
        if end < 0:
            return payloads, stream[i:]
        raw = stream[i + 1:end]
        if raw:
            body = bytearray()
            j = 0
            while j < len(raw):
                if raw[j] == ESC and j + 1 < len(raw):
                    body.append(raw[j + 1] ^ 0x20)
                    j += 2
                else:
                    body.append(raw[j])
                    j += 1
            if len(body) > 2:
                data, crc = bytes(body[:-2]), body[-2] | body[-1] << 8
                if crc_x25(data) == crc:
                    payloads.append(data)
            i = end
        else:
            i = end


# --- values -----------------------------------------------------------------

class Reader:
    def __init__(self, data: bytes, at: int = 0):
        self.d, self.i = data, at

    def _u8(self) -> int:
        if self.i >= len(self.d):
            raise ProtocolError("message ended inside a value")
        v = self.d[self.i]
        self.i += 1
        return v

    def value(self):
        t = self._u8()
        if t == 0x80:
            return self._u8()
        if t in (0x81, 0x82):
            lo, hi = self._u8(), self._u8()
            return lo | hi << 8
        if t == 0x88:
            if self.i + 4 > len(self.d):
                raise ProtocolError("message ended inside a float")
            v = struct.unpack("<f", self.d[self.i:self.i + 4])[0]
            self.i += 4
            return v
        if t in (0xB9, 0xBA):
            n = self._u8()
            return [self.value() for _ in range(n)]
        if t == 0xBC:
            n = self._u8()
            if self.i + n > len(self.d):
                raise ProtocolError("message ended inside a string")
            v = bytes(self.d[self.i:self.i + n])
            self.i += n
            return v
        if t >= 0x80:
            raise ProtocolError(f"unknown tag {t:#04x}")
        return t


def text(raw: bytes) -> str:
    return raw.split(b"\0")[0].decode("latin-1").strip()


@dataclass
class Message:
    type: int
    size: int
    body_at: int          # where the body starts in the payload
    payload: bytes

    def body(self) -> list:
        r = Reader(self.payload, self.body_at)
        out = []
        while r.i < len(self.payload):
            out.append(r.value())
        return out


def parse(payload: bytes) -> Message:
    if payload[:2] != b"\xb9\x03":
        raise ProtocolError("not a message header")
    r = Reader(payload, 2)
    typ, size, _extra = r.value(), r.value(), r.value()
    if not isinstance(typ, int) or not isinstance(size, int):
        raise ProtocolError("malformed header")
    return Message(typ, size, r.i, payload)


# --- the pedal's state ------------------------------------------------------

#: Offsets in the state body (everything after the header), from Builty's
#: usb_tonex_one.c and checked against this unit's state frames. From the
#: start:
OFF_INPUT_TRIM = 15         # float32, -15..15 dB
OFF_STOMP_MODE = 19         # 0 dual (A/B), 1 stomp
OFF_CAB_BYPASS = 20         # 0 off, 1 on
OFF_TUNING_MODE = 21        # 0 mute, 1 through
#: From the end (distance back from the last byte):
END_BPM = 4                 # float32
END_TEMPO_SOURCE = 6        # 0 global, 1 preset
END_DIRECT_MONITOR = 7
END_TUNING_REF = 9          # uint16 LE, 415..465 Hz
END_CURRENT_SLOT = 11       # 0 A, 1 B, 2 stomp (C)
END_BYPASS = 12             # stomp-mode bypass
END_SLOT_C = 14
END_SLOT_B = 16
END_SLOT_A = 18

SLOTS = ("A", "B", "C")


@dataclass
class State:
    """The state body as the pedal sent it. Writes copy it, change the named
    bytes and send it back whole, which is how the protocol works: there is no
    'set one field' message for these."""
    raw: bytes

    def _end(self, back: int) -> int:
        return len(self.raw) - back

    @property
    def slot_a(self) -> int: return self.raw[self._end(END_SLOT_A)]
    @property
    def slot_b(self) -> int: return self.raw[self._end(END_SLOT_B)]
    @property
    def slot_c(self) -> int: return self.raw[self._end(END_SLOT_C)]
    @property
    def current_slot(self) -> int: return self.raw[self._end(END_CURRENT_SLOT)]
    @property
    def stomp_mode(self) -> bool: return bool(self.raw[OFF_STOMP_MODE])
    @property
    def cab_bypass(self) -> bool: return bool(self.raw[OFF_CAB_BYPASS])
    @property
    def bypassed(self) -> bool: return bool(self.raw[self._end(END_BYPASS)])

    @property
    def input_trim(self) -> float:
        return round(struct.unpack("<f", self.raw[OFF_INPUT_TRIM:OFF_INPUT_TRIM + 4])[0], 2)

    @property
    def tuning_ref(self) -> int:
        at = self._end(END_TUNING_REF)
        return self.raw[at] | self.raw[at + 1] << 8

    def colors(self) -> list[tuple[int, int, int]]:
        """The twenty preset colours the pedal shows, as RGB. An unexpected
        shape gives an empty list: colours are decoration, never a reason
        to refuse a state."""
        try:
            rows = Reader(self.raw, OFF_TUNING_MODE + 1).value()
            out = [tuple(int(c) for c in row[:3]) for row in rows]
            return out if len(out) == PRESETS else []
        except (ProtocolError, TypeError, ValueError, IndexError):
            return []

    @property
    def active_preset(self) -> int:
        return (self.slot_a, self.slot_b, self.slot_c)[min(self.current_slot, 2)]

    def check(self) -> None:
        """Refuse a state whose known fields are not where they should be,
        so a firmware with another layout is read as undecoded rather than
        written to with guessed offsets."""
        if len(self.raw) < 40:
            raise ProtocolError("state message too short")
        if self.raw[OFF_INPUT_TRIM - 1] != 0x88 or self.raw[self._end(END_BPM) - 1] != 0x88:
            raise ProtocolError("state layout not the one this code knows")
        if self.raw[self._end(END_SLOT_A) - 2:self._end(END_SLOT_A)] != b"\xbc\x06":
            raise ProtocolError("state layout not the one this code knows")
        for v in (self.slot_a, self.slot_b, self.slot_c):
            if v >= PRESETS:
                raise ProtocolError("a slot names a preset that does not exist")
        if self.current_slot > 2 or self.raw[OFF_STOMP_MODE] > 1 or self.raw[OFF_CAB_BYPASS] > 1:
            raise ProtocolError("state value outside what this code knows")

    def changed(self, **fields) -> "State":
        """A copy with the named fields changed. Only these fields exist."""
        b = bytearray(self.raw)
        for k, v in fields.items():
            if k in ("slot_a", "slot_b", "slot_c"):
                if not (isinstance(v, int) and 0 <= v < PRESETS):
                    raise ProtocolError(f"{k} must be a preset 0..{PRESETS - 1}")
                b[self._end({"slot_a": END_SLOT_A, "slot_b": END_SLOT_B,
                             "slot_c": END_SLOT_C}[k])] = v
            elif k == "current_slot":
                if v not in (0, 1, 2):
                    raise ProtocolError("current_slot must be 0 (A), 1 (B) or 2 (C)")
                b[self._end(END_CURRENT_SLOT)] = v
            elif k == "stomp_mode":
                b[OFF_STOMP_MODE] = 1 if v else 0
            elif k == "cab_bypass":
                b[OFF_CAB_BYPASS] = 1 if v else 0
            elif k == "bypassed":
                b[self._end(END_BYPASS)] = 1 if v else 0
            elif k == "input_trim":
                v = float(v)
                if not -15.0 <= v <= 15.0:
                    raise ProtocolError("input trim must be -15..15 dB")
                b[OFF_INPUT_TRIM:OFF_INPUT_TRIM + 4] = struct.pack("<f", v)
            else:
                raise ProtocolError(f"no state field {k!r}")
        return State(bytes(b))


def writable_state_bytes(raw: bytes) -> set[int]:
    n = len(raw)
    return ({OFF_STOMP_MODE, OFF_CAB_BYPASS} | set(range(OFF_INPUT_TRIM, OFF_INPUT_TRIM + 4))
            | {n - END_SLOT_A, n - END_SLOT_B, n - END_SLOT_C,
               n - END_CURRENT_SLOT, n - END_BYPASS})


# --- a preset summary -------------------------------------------------------

@dataclass
class Preset:
    index: int
    name: str
    params: list[float]          # the first of the three lists (see kb)
    lists: list[list[float]]
    tags: dict


TAG_NAMES = ("author", "date", "character", "instrument")


def parse_preset(msg: Message) -> Preset:
    body = msg.body()
    try:
        top = body[0]
        index = top[1]
        inner = top[2]
        name = text(inner[0][0])
        lists = [list(x) for x in inner[2] if isinstance(x, list)]
        tags_raw = inner[3] if len(inner) > 3 else []
    except (IndexError, TypeError) as e:
        raise ProtocolError(f"preset summary not in the known shape: {e}")
    if not lists or len(lists[0]) != 109:
        raise ProtocolError("preset summary does not carry 109 settings")
    tags = {}
    for k, row in zip(TAG_NAMES, tags_raw):
        if isinstance(row, list) and row and isinstance(row[0], bytes):
            tags[k] = text(row[0])
    return Preset(index, name, lists[0], lists, tags)


# --- what may be sent -------------------------------------------------------

HELLO = bytes([0xB9, 0x03, 0x00, 0x82, 0x04, 0x00, 0x80, 0x0B, 0x01,
               0xB9, 0x02, 0x02, 0x0B])
REQUEST_STATE = bytes([0xB9, 0x03, 0x00, 0x82, 0x06, 0x00, 0x80, 0x0B, 0x03,
                       0xB9, 0x02, 0x81, 0x06, 0x03, 0x0B])


def request_preset(index: int) -> bytes:
    if not (isinstance(index, int) and 0 <= index < PRESETS):
        raise ProtocolError(f"preset must be 0..{PRESETS - 1}")
    return bytes([0xB9, 0x03, 0x81, 0x00, 0x03, 0x82, 0x06, 0x00, 0x80, 0x0B, 0x03,
                  0xB9, 0x04, 0x0B, 0x01, index, 0x00])


_SET_PARAM_HEAD = bytes([0xB9, 0x03, 0x81, 0x09, 0x03, 0x82, 0x0A, 0x00, 0x80, 0x0B, 0x03])


def set_param(index: int, value: float) -> bytes:
    return _SET_PARAM_HEAD + bytes([0xB9, 0x04, 0x02, 0x00, index, 0x88]) + struct.pack("<f", float(value))


def write_state(state: State) -> bytes:
    n = len(state.raw)
    return bytes([0xB9, 0x03, 0x81, 0x06, 0x03, 0x82, n & 0xFF, n >> 8, 0x80, 0x0B, 0x03]) + state.raw


class SendGate:
    """The only producer of wire bytes. `last_state` is the state the pedal
    last reported; a state write must match it outside the known fields."""

    def __init__(self, writable_params):
        self.writable = writable_params        # index -> (lo, hi)
        self.last_state: State | None = None

    def checked_frame(self, payload: bytes) -> bytes:
        if payload == HELLO or payload == REQUEST_STATE:
            return frame(payload)
        if payload[:15] == request_preset(0)[:15] and len(payload) == 17 \
                and payload[15] < PRESETS and payload[16] == 0:
            return frame(payload)
        if payload[:len(_SET_PARAM_HEAD)] == _SET_PARAM_HEAD and len(payload) == 21 \
                and payload[11:15] == bytes([0xB9, 0x04, 0x02, 0x00]) and payload[16] == 0x88:
            idx = payload[15]
            value = struct.unpack("<f", payload[17:21])[0]
            rng = self.writable.get(idx)
            if rng is None:
                raise ProtocolError(f"setting {idx} is not one ToneCommand may write")
            if not (math.isfinite(value) and rng[0] - 1e-6 <= value <= rng[1] + 1e-6):
                raise ProtocolError(f"setting {idx}: {value} is outside {rng[0]}..{rng[1]}")
            if len(rng) > 2 and rng[2] and value != int(value):
                raise ProtocolError(f"setting {idx} takes a whole number, got {value}")
            return frame(payload)
        if payload[:5] == bytes([0xB9, 0x03, 0x81, 0x06, 0x03]) and self.last_state is not None:
            raw = payload[11:]
            old = self.last_state.raw
            n = len(old)
            if payload[5:11] != bytes([0x82, n & 0xFF, n >> 8, 0x80, 0x0B, 0x03]) or len(raw) != n:
                raise ProtocolError("a state write must keep the state's length")
            allowed = writable_state_bytes(old)
            moved = [i for i in range(n) if raw[i] != old[i] and i not in allowed]
            if moved:
                raise ProtocolError(f"a state write may not change bytes {moved[:6]}")
            new = State(raw)
            new.check()
            if not (math.isfinite(new.input_trim) and -15.0 <= new.input_trim <= 15.0):
                raise ProtocolError("input trim must be -15..15 dB")
            if raw[n - END_BYPASS] > 1:
                raise ProtocolError("bypass must be 0 or 1")
            return frame(payload)
        raise ProtocolError("not a message ToneCommand sends to the ToneX One")

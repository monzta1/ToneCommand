"""An in-memory ToneX One, so the suite runs with no pedal on the desk.

It is seeded from a real capture of one (tests/fixtures/tonex_one/), so its
twenty presets, their settings and its state are what a real unit sent. It
answers the same frames the pedal does, applies a setting change to the
preset now playing and a state write whole, and, like the pedal, ignores a
frame it does not understand rather than answering it.
"""
from __future__ import annotations

import struct
from pathlib import Path

from . import protocol as p

FIXTURE = (Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "tonex_one"
           / "read_all_2026-11-25.bin")


class SimLink:
    def __init__(self, capture: Path = FIXTURE):
        payloads, _ = p.unframe_stream(capture.read_bytes())
        self.hello_reply: bytes | None = None
        self.state_payload: bytes | None = None
        self.presets: dict[int, bytearray] = {}
        for pl in payloads:
            m = p.parse(pl)
            if m.type == p.T_HELLO:
                self.hello_reply = pl
            elif m.type == p.T_STATE:
                self.state_payload = pl
            elif m.type == p.T_PRESET:
                self.presets[p.parse_preset(m).index] = bytearray(pl)
        self._out = b""
        self.received: list[bytes] = []
        self.closed = False

    # the pedal's side -----------------------------------------------------

    def _state(self) -> p.State:
        m = p.parse(self.state_payload)
        return p.State(self.state_payload[m.body_at:])

    def _answer(self, payload: bytes) -> None:
        self.received.append(payload)
        if payload == p.HELLO:
            self._out += p.frame(self.hello_reply)
        elif payload == p.REQUEST_STATE:
            self._out += p.frame(self.state_payload)
        elif payload[:15] == p.request_preset(0)[:15] and len(payload) == 17:
            pl = self.presets.get(payload[15])
            if pl is not None:
                self._out += p.frame(bytes(pl))
        elif payload[:5] == bytes([0xB9, 0x03, 0x81, 0x09, 0x03]):
            idx = payload[15]
            value = payload[17:21]
            self._set_param(self._state().active_preset, idx, value)
        elif payload[:5] == bytes([0xB9, 0x03, 0x81, 0x06, 0x03]):
            m = p.parse(self.state_payload)
            self.state_payload = self.state_payload[:m.body_at] + payload[11:]

    def _set_param(self, preset: int, idx: int, value4: bytes) -> None:
        """Write the float into the first settings list of the preset's
        summary: the list of three opens with ba 03, the first of 109 floats
        with ba 6d, and each setting is 0x88 plus four bytes."""
        pl = self.presets[preset]
        at = bytes(pl).find(b"\xba\x03\xba\x6d")
        if at < 0:
            return
        pos = at + 4 + idx * 5
        if pl[pos] == 0x88:
            pl[pos + 1:pos + 5] = value4

    # the link's side ------------------------------------------------------

    def write(self, data: bytes) -> None:
        payloads, _ = p.unframe_stream(data)
        for pl in payloads:
            self._answer(pl)

    def read(self) -> bytes:
        out, self._out = self._out, b""
        return out

    def footswitch(self) -> None:
        """What a press does on a pedal in dual mode: flip A and B, push the
        state, then the newly active preset."""
        st = self._state()
        new = st.changed(current_slot=0 if st.current_slot else 1)
        m = p.parse(self.state_payload)
        self.state_payload = self.state_payload[:m.body_at] + new.raw
        self._out += p.frame(self.state_payload)
        self._out += p.frame(bytes(self.presets[new.active_preset]))

    def value(self, preset: int, idx: int) -> float:
        pl = bytes(self.presets[preset])
        at = pl.find(b"\xba\x03\xba\x6d") + 4 + idx * 5
        return struct.unpack("<f", pl[at + 1:at + 5])[0]

    def close(self) -> None:
        self.closed = True

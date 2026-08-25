#!/usr/bin/env python3
"""Decode a ToneX serial control frame.

The pedal emits one of these on every preset change over its CDC serial
port (/dev/cu.usbmodem* on macOS). It is the device's own report of what it
just loaded, which makes it a real read-back path: the FM9 ladder's first
rung is available on this device after all, just not over MIDI.

Frame grammar, decoded from 128 captured frames (every addressable program):

    0x7e                  leads the frame
    0xbc <len> <ascii>    string, zero-padded to <len>
    0x88 <4 bytes>        little-endian IEEE-754 float
    anything else         single structural byte, not yet decoded

Every frame carries exactly 14 strings and 329 floats, in a stable order, so
both can be addressed by ordinal. The string slots that are populated:

    0   preset name          126 distinct across the 128 factory programs
    2   a date, "2026-04-20" on this unit, identical in every frame
    3   category             CLEAN, DRIVE or HI-GAIN
    4-7 "None"               unassigned effect slots on factory presets

WHAT THIS FRAME DOES NOT CONTAIN, and it matters: the amp identity. Programs
2 and 5 ("5150 Aggression (Advanced)" and "MES LS I Lead AT TDR CAB EL34")
have byte-identical float arrays. On this pedal the tone lives in the
capture, and the float block describes the control and effect state wrapped
around it. Do not read a parameter map out of these floats and call it a
tone description; the preset name is currently the only handle on identity.

Undecoded territory, reported rather than papered over: the structural bytes,
the trailing region (token counts vary 417-420 across frames, always after
the float block), and the leading region of the two frames for programs
125 and 126, which differ from the other 126 near token 19.
"""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

FRAME_LEAD = 0x7E
TAG_STR = 0xBC
TAG_F32 = 0x88

NAME_SLOT, DATE_SLOT, CATEGORY_SLOT = 0, 2, 3


@dataclass
class Frame:
    strings: list[str] = field(default_factory=list)
    floats: list[float] = field(default_factory=list)
    structural: int = 0

    @property
    def name(self) -> str:
        return self.strings[NAME_SLOT] if len(self.strings) > NAME_SLOT else ""

    @property
    def category(self) -> str:
        return self.strings[CATEGORY_SLOT] if len(self.strings) > CATEGORY_SLOT else ""

    @property
    def date(self) -> str:
        return self.strings[DATE_SLOT] if len(self.strings) > DATE_SLOT else ""

    def summary(self) -> dict:
        return {"name": self.name, "category": self.category, "date": self.date,
                "strings": len(self.strings), "floats": len(self.floats)}


def decode(raw: bytes) -> Frame:
    """Walk the frame as tags. Unknown bytes are counted, never guessed at."""
    f = Frame()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == TAG_F32 and i + 5 <= len(raw):
            f.floats.append(struct.unpack("<f", raw[i + 1:i + 5])[0])
            i += 5
        elif b == TAG_STR and i + 1 < len(raw):
            ln = raw[i + 1]
            f.strings.append(raw[i + 2:i + 2 + ln].split(b"\x00")[0]
                             .decode("ascii", "replace"))
            i += 2 + ln
        else:
            f.structural += 1
            i += 1
    return f


def diff(a: Frame, b: Frame) -> list[tuple[int, float, float]]:
    """Float slots where two frames disagree. Empty means identical control
    state, which happens between completely different amps on this device."""
    return [(i, x, y) for i, (x, y) in enumerate(zip(a.floats, b.floats))
            if round(x, 5) != round(y, 5)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("frames", nargs="+", type=Path, help="captured .bin frames")
    ap.add_argument("--diff", action="store_true",
                    help="compare the first two frames slot by slot")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    decoded = [(p, decode(p.read_bytes())) for p in args.frames]

    if args.json:
        print(json.dumps({p.name: f.summary() for p, f in decoded}, indent=2))
        return

    for p, f in decoded:
        print(f"{p.name}: {f.name!r}  [{f.category}]  "
              f"{len(f.floats)} floats, {f.structural} undecoded bytes")

    if args.diff and len(decoded) >= 2:
        (pa, a), (pb, b) = decoded[0], decoded[1]
        d = diff(a, b)
        print(f"\n{pa.name} vs {pb.name}: {len(d)} float slot(s) differ")
        for i, x, y in d[:40]:
            print(f"  slot {i:3d}: {x:>12.4f}  ->  {y:>12.4f}")
        if not d:
            print("  identical control state (the tone is in the capture, "
                  "not in these floats)")


if __name__ == "__main__":
    main()

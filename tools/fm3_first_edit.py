#!/usr/bin/env python3
"""The first FM3 edit (#40): one block bypass changed, read back, put back.

    python tools/fm3_first_edit.py                 # picks reverb, delay, chorus...
    python tools/fm3_first_edit.py --block delay   # or names the block
    TONECOMMAND_FM3_SIM=1 python tools/fm3_first_edit.py   # on the simulator

ToneCommand keeps the FM3 read-only until each kind of change is proven on a
real unit by a write and a read-back. This is the first of those proofs, and
the smallest: Fractal's documented bypass command (the same one a foot
controller uses), sent to one block of the preset that is loaded, in the
edit buffer only.

What it does, in order:
1. reads the loaded preset and its blocks, the way the app does;
2. flips one block's bypass and reads the state back twice (the bypass query
   and the status dump);
3. flips it back and reads it again;
4. reloads the preset, which discards the edit buffer, so the unit is left
   exactly as it was. Nothing is ever stored.

The FM3's output stays read-only throughout, except for the one bypass frame
for the one chosen block, and only while it is being sent. Stop ToneCommand
before running this: on Windows only one program can hold a MIDI port.

At the end it prints a result block to paste back, and saves the same text
to fm3_first_edit_result.txt in the current folder.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mido  # noqa: E402

from fm9 import protocol as p  # noqa: E402
from fm9.device import FM9, ReadOnly, ReadOnlyOut  # noqa: E402
from fm9.registry import Registry  # noqa: E402

#: The only blocks this may flip (registry family names), best first: easy
#: to hear and harmless to bypass for a moment. FUZZ is the drive block. The
#: amp (DISTORT), cab, input, output, volume and anything else are never
#: flipped, even when named: bypassing them can silence the rig, and proving
#: the command does not need that.
PREFERRED = ("REVERB", "DELAY", "CHORUS", "FLANGER", "PHASER", "FUZZ",
             "MULTITAP", "TREMOLO", "PLEX", "PITCH", "FILTER", "COMP")
SETTLE = 0.3


class OneBypassOut:
    """The FM3's read-only output, with exactly one more form let through:
    the documented bypass write (fn 0x0A, value 0 or 1) for one effect id.
    Everything else still goes to ReadOnlyOut, which refuses any write."""

    def __init__(self, read_only: ReadOnlyOut, effect_id: int):
        self.read_only = read_only
        self.effect_id = effect_id

    def allows(self, frame: list[int]) -> bool:
        if len(frame) != 11 or frame[0] != 0xF0 or frame[-1] != 0xF7:
            return False
        if tuple(frame[1:4]) != p.MFR or frame[4] not in (p.MODEL_FM9, p.MODEL_FM3):
            return False
        if p.checksum(frame[1:-2]) != frame[-2] or frame[5] != p.FN_BYPASS:
            return False
        lo, hi, value = frame[6:9]
        return p.decode14(lo, hi) == self.effect_id and value in (0, 1)

    def send(self, msg):
        if msg.type == "sysex":
            frame = [0xF0, *msg.data, 0xF7]
            if self.allows(frame):
                frame = p.readdress(frame, self.read_only.model)
                self.read_only.port.send(mido.Message("sysex", data=frame[1:-1]))
                return
        self.read_only.send(msg)

    def __getattr__(self, name):
        return getattr(self.read_only, name)


@contextlib.contextmanager
def one_bypass_open(dev, effect_id: int):
    """Let the one bypass frame through for the length of the block, then
    put the plain read-only output back, whatever happened inside."""
    read_only = dev.outp
    if not isinstance(read_only, ReadOnlyOut):
        raise RuntimeError("expected the FM3's read-only output")
    dev.outp = OneBypassOut(read_only, effect_id)
    try:
        yield
    finally:
        dev.outp = read_only


def open_fm3(reg: Registry):
    if os.environ.get("TONECOMMAND_FM3_SIM") == "1":
        from fm9.sim import SimFM3
        return SimFM3(reg)
    from fm9.device import FM3
    return FM3(reg)


def name_of(reg: Registry, effect_id: int) -> str:
    fam = reg.family_of_effect_id(effect_id)
    return f"{fam[0]} {fam[1]}" if fam else f"effect {effect_id}"


def choose(reg: Registry, blocks, wanted: str | None):
    by_id = {b.effect_id: b for b in blocks}
    if wanted:
        try:
            eid = reg.resolve_block(wanted, 1)[1]
        except Exception as e:      # noqa: BLE001  a bad name is the player's to fix
            raise SystemExit(f"Unknown block {wanted!r}: {e}")
        if eid not in by_id:
            raise SystemExit(f"{wanted!r} is not in the loaded preset. Its blocks: "
                             + ", ".join(name_of(reg, b.effect_id) for b in blocks))
        fam = (reg.family_of_effect_id(eid) or ("",))[0]
        if fam not in PREFERRED:
            raise SystemExit(f"{wanted!r} is not used for this test; pick an effect "
                             "such as reverb, delay or chorus.")
        return by_id[eid]
    for fam in PREFERRED:
        for b in blocks:
            f = reg.family_of_effect_id(b.effect_id)
            if f and f[0] == fam:
                return b
    return None


def run(dev, reg: Registry, wanted: str | None = None) -> list[str]:
    """The whole test; returns the result lines. Never stores."""
    out: list[str] = ["FM3 first edit (#40)"]
    preset = dev.current_preset()
    if preset is None:
        raise SystemExit("The FM3 did not answer. Is ToneCommand stopped, and the "
                         "interface connected?")
    number, pname = preset
    out.append(f"preset: {p.slot_label(number)} {pname!r}")
    fw = None
    with contextlib.suppress(Exception):
        fw = dev.firmware()
    out.append(f"firmware: {fw if fw else 'not read'}")
    blocks = dev.status_dump() or []
    out.append("blocks: " + ", ".join(
        f"{name_of(reg, b.effect_id)}{' (bypassed)' if b.bypassed else ''}"
        for b in blocks))
    target = choose(reg, blocks, wanted)
    if target is None:
        raise SystemExit("This preset has no reverb, delay, chorus or drive to test "
                         "with. Load a preset that has one and run this again.")
    eid, label = target.effect_id, name_of(reg, target.effect_id)
    before = dev.get_bypass(eid)
    out.append(f"block: {label} (effect id {eid}), bypassed before: {before}")
    if before is None:
        raise SystemExit(f"The FM3 did not answer the bypass query for {label}.")

    def step(want: bool, name: str) -> bool:
        with one_bypass_open(dev, eid):
            echo = FM9.set_bypass(dev, eid, want)
        time.sleep(SETTLE)
        query = dev.get_bypass(eid)
        dump = next((b.bypassed for b in dev.status_dump() or []
                     if b.effect_id == eid), None)
        ok = query == want and dump == want
        out.append(f"{name}: sent bypassed={want}; echo {echo}, query {query}, "
                   f"status dump {dump} -> {'PASS' if ok else 'FAIL'}")
        return ok

    flipped = step(not before, "flip")
    restored = step(before, "restore")
    reloaded = dev.select_preset(number)
    out.append(f"reload (discards the edit buffer): "
               f"{p.slot_label(reloaded[0]) if reloaded else 'no answer'}")
    still = dev.get_bypass(eid)
    out.append(f"after reload, {label} bypassed: {still} "
               f"({'as before' if still == before else 'NOT as before'})")
    verdict = "PASS" if flipped and restored and still == before else "FAIL"
    out.append(f"result: {verdict}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--block", help="block to flip, e.g. reverb or delay")
    args = ap.parse_args(argv)
    reg = Registry()
    try:
        dev = open_fm3(reg)
    except Exception as e:          # noqa: BLE001  told to the player, in words
        print(f"Could not open the FM3: {e}")
        return 1
    try:
        lines = run(dev, reg, args.block)
    except ReadOnly as e:
        lines = ["FM3 first edit (#40)", f"refused before the wire: {e}", "result: FAIL"]
    finally:
        with contextlib.suppress(Exception):
            dev.close()
    text = "\n".join(lines)
    print("\n----- copy from here -----")
    print(text)
    print("----- to here -----")
    with contextlib.suppress(OSError):
        Path("fm3_first_edit_result.txt").write_text(text + "\n", encoding="utf-8")
        print("Also saved to fm3_first_edit_result.txt")
    return 0 if lines[-1] == "result: PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

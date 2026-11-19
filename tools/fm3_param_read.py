#!/usr/bin/env python3
"""Read an FM3's block settings the FM9's way, to compare with its screen (#40).

    python tools/fm3_param_read.py                  # amp, reverb, delay, chorus
    TONECOMMAND_FM3_SIM=1 python tools/fm3_param_read.py   # on the simulator

ToneCommand cannot change an FM3's settings (gain, mix, time...) until it
knows the FM3 lays them out the way the FM9 does. This test only READS:
for each block it asks for the whole block's values with the FM9's block
read (fn 0x1F, a request the FM9 answers with values and nothing else),
decodes them with the FM9's map, and prints what it found: the amp model,
Gain, Bass, Mid, Treble and so on. You compare those with the FM3's own
screen. Where they match, the FM9's map holds for that block on the FM3.

Nothing is sent but that read, one block at a time, and only during this
test; the app's FM3 still refuses it. As a check, the preset and every
block's on/off and channel are read before and after and must be the same.
Nothing is stored or reloaded, so your unsaved edits stay as they are.
Stop ToneCommand before running this: on Windows only one program can hold
a MIDI port.

At the end it prints a result block to paste back, and saves the same text
to fm3_param_read_result.txt in the current folder.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mido  # noqa: E402

from fm9 import protocol as p  # noqa: E402
from fm9.device import FM9, ReadOnly, ReadOnlyOut  # noqa: E402
from fm9.registry import Registry  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
from fm3_first_edit import name_of, open_fm3  # noqa: E402

#: Blocks read, in order, and the parameter ids the app shows for each.
#: The same ids as server.INTEREST (a test keeps them in step).
READ = {
    "DISTORT": [11, 12, 13, 14, 15, 26, 30, 1],
    "REVERB": [0, 1, 11],
    "DELAY": [0, 1, 12, 32],
    "CHORUS": [2, 4, 10, 11],
}
#: Where the type (amp model, reverb type) sits, and which roster names it.
#: The same as server.TYPE_PARAMS for these blocks.
TYPES = {"DISTORT": (10, "amp_roster"), "REVERB": (10, "reverb_roster")}
#: How a unit reads on the unit's screen; the rest print as bare numbers.
UNITS = {"db": " dB", "percent": "%", "bipolar_percent": "%", "ms": " ms",
         "seconds": " s", "hz": " Hz", "semitones": " st", "degrees": " deg"}


class OneReadOut:
    """The FM3's read-only output with one more form let through: the
    block read (fn 0x1F) for one effect id. Everything else still goes to
    ReadOnlyOut, which refuses any write."""

    def __init__(self, read_only: ReadOnlyOut, effect_id: int):
        self.read_only = read_only
        self.effect_id = effect_id

    def allows(self, frame: list[int]) -> bool:
        if len(frame) != 10 or frame[0] != 0xF0 or frame[-1] != 0xF7:
            return False
        if tuple(frame[1:4]) != p.MFR or frame[4] not in (p.MODEL_FM9, p.MODEL_FM3):
            return False
        if p.checksum(frame[1:-2]) != frame[-2] or frame[5] != p.FN_BULK_READ:
            return False
        return p.decode14(frame[6], frame[7]) == self.effect_id

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
def one_read_open(dev, effect_id: int):
    read_only = dev.outp
    if not isinstance(read_only, ReadOnlyOut):
        raise RuntimeError("expected the FM3's read-only output")
    dev.outp = OneReadOut(read_only, effect_id)
    try:
        yield
    finally:
        dev.outp = read_only


def _state(dev):
    """What must not change: the preset and every block's on/off and channel."""
    preset = dev.current_preset()
    blocks = sorted((b.effect_id, b.bypassed, b.channel) for b in dev.status_dump() or [])
    return preset, blocks


def read_block(dev, reg: Registry, block) -> list[str]:
    fam = (reg.family_of_effect_id(block.effect_id) or ("", 1))
    fname, inst = fam[0], fam[1]
    with one_read_open(dev, block.effect_id):
        vals = FM9.bulk_read(dev, block.effect_id)
    chans = max(1, block.channels_supported)
    head = (f"{name_of(reg, block.effect_id)} (effect id {block.effect_id}), "
            f"channel {'ABCD'[block.channel]} of {chans}")
    if not vals:
        return [f"{head}: no answer to the block read"]
    stride = len(vals) // chans if chans > 1 else len(vals)
    base = min(block.channel, chans - 1) * stride
    out = [f"{head}: {len(vals)} values ({stride} per channel)"]
    if fname in TYPES:
        pid, roster_attr = TYPES[fname]
        if base + pid < len(vals):
            wire = vals[base + pid]
            label = (getattr(reg, roster_attr) or {}).get(str(wire), "not in the FM9 list")
            out.append(f"  type: {label} (ordinal {wire})")
    for pid in READ.get(fname, []):
        idx = base + pid
        if idx >= len(vals):
            out.append(f"  param {pid}: past the end of the reply")
            continue
        s = reg.spec(fname, pid, inst)
        label = s.label or s.name.split("_", 1)[-1]
        if s.dmin is None:
            out.append(f"  {label}: raw {vals[idx]}")
            continue
        shown = round(p.normalized_to_display(vals[idx] / 65534, s.dmin, s.dmax, s.scale), 2)
        out.append(f"  {label}: {shown}{UNITS.get(s.unit or '', '')}")
    return out


def run(dev, reg: Registry) -> list[str]:
    out = ["FM3 settings read (#40)"]
    before = _state(dev)
    if before[0] is None:
        raise SystemExit("The FM3 did not answer. Is ToneCommand stopped, and the "
                         "interface connected?")
    number, pname = before[0]
    out.append(f"preset: {p.slot_label(number)} {pname!r}")
    fw = None
    with contextlib.suppress(Exception):
        fw = dev.firmware()
    out.append(f"firmware: {fw if fw else 'not read'}")
    blocks = dev.status_dump() or []
    chosen = []
    for fname in READ:
        for b in blocks:
            f = reg.family_of_effect_id(b.effect_id)
            if f and f[0] == fname and f[1] == 1:
                chosen.append(b)
    if not chosen:
        raise SystemExit("This preset has no amp, reverb, delay or chorus. Load a "
                         "preset that has an amp and run this again.")
    for b in chosen:
        out.extend(read_block(dev, reg, b))
    after = _state(dev)
    same = after == before
    out.append(f"unit unchanged (preset, on/off, channels): {'yes' if same else 'NO'}")
    out.append(f"result: {'READ' if same else 'CHANGED'}")
    return out


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args(argv)
    reg = Registry()
    try:
        dev = open_fm3(reg)
    except Exception as e:          # noqa: BLE001  told to the player, in words
        print(f"Could not open the FM3: {e}")
        return 1
    try:
        lines = run(dev, reg)
    except ReadOnly as e:
        lines = ["FM3 settings read (#40)", f"refused before the wire: {e}",
                 "result: FAIL"]
    finally:
        with contextlib.suppress(Exception):
            dev.close()
    text = "\n".join(lines)
    print("\n----- copy from here -----")
    print(text)
    print("----- to here -----")
    print("Now compare each value above with the same knob on the FM3's screen.")
    with contextlib.suppress(OSError):
        Path("fm3_param_read_result.txt").write_text(text + "\n", encoding="utf-8")
        print("Also saved to fm3_param_read_result.txt")
    return 0 if lines[-1] == "result: READ" else 2


if __name__ == "__main__":
    sys.exit(main())

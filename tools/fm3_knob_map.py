#!/usr/bin/env python3
"""Map an FM3 block's settings one knob at a time (#40).

    python tools/fm3_knob_map.py              # the amp (DISTORT 1)
    python tools/fm3_knob_map.py reverb       # or delay, chorus, ...
    TONECOMMAND_FM3_SIM=1 python tools/fm3_knob_map.py   # on the simulator

The FM3 answers the FM9's block read, but it lays a block's values out in
its own order (fm3_param_read, 2026-11-21: the amp's model and Gain sit
four places earlier than on the FM9, the reverb's type and Time ten
places earlier, the delay's Mix in the same place). This finds each
setting's place directly: the tool reads the block, you turn ONE knob on
the FM3 itself, press Enter, and it reads again and shows which value
moved. You type the knob's name and what the screen shows, and the next
round starts.

ToneCommand sends only the block read (fn 0x1F) for that one block; every
change is made by you, on the unit. Nothing is stored: reselect the preset
on the FM3 afterwards to drop your knob turns. Stop ToneCommand before
running this: on Windows only one program can hold a MIDI port.

At the end it prints a result block to paste back and saves the same text
to fm3_knob_map_result.txt in the current folder.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from fm9 import protocol as p  # noqa: E402
from fm9.device import ReadOnly  # noqa: E402
from fm9.registry import Registry  # noqa: E402
from fm3_first_edit import name_of, open_fm3  # noqa: E402
from fm3_param_read import capture_read, one_read_open  # noqa: E402

#: Rounds at most, so a forgotten window does not read forever.
MAX_ROUNDS = 40


def read_words(dev, effect_id: int) -> tuple[list[int], int]:
    """The block's values and the total its chunks declare."""
    with one_read_open(dev, effect_id):
        vals, burst, _heard = capture_read(dev, effect_id)
    total = sum(c[0] for c in burst["chunks"]) if burst else len(vals)
    return vals, total


def find_block(dev, reg: Registry, family: str):
    blocks = dev.status_dump() or []
    for b in blocks:
        f = reg.family_of_effect_id(b.effect_id)
        if f and f[0] == family and f[1] == 1:
            return b
    raise SystemExit(f"This preset has no {family} 1. Its blocks: "
                     + ", ".join(name_of(reg, b.effect_id) for b in blocks))


def diff(before: list[int], after: list[int], stride: int) -> list[str]:
    out = []
    for i in range(min(len(before), len(after))):
        if before[i] != after[i]:
            ch = "ABCD"[i // stride] if stride and i // stride < 4 else "?"
            word = i % stride if stride else i
            out.append(f"word {word} (channel {ch}): {before[i]} -> {after[i]}")
    return out


def run(dev, reg: Registry, family: str, ask=input, say=print) -> list[str]:
    block = find_block(dev, reg, family)
    eid = block.effect_id
    chans = max(1, block.channels_supported)
    preset = dev.current_preset()
    out = ["FM3 knob map (#40)",
           f"preset: {p.slot_label(preset[0])} {preset[1]!r}" if preset else "preset: not read",
           f"block: {name_of(reg, eid)} (effect id {eid}), on channel "
           f"{'ABCD'[block.channel]} of {chans}"]
    before, total = read_words(dev, eid)
    if not before:
        raise SystemExit("The FM3 sent no values for this block. Is the "
                         "interface connected?")
    stride = total // chans if chans > 1 else total
    out.append(f"values: {len(before)} of {total} ({stride} per channel)")
    say(f"\nRead {name_of(reg, eid)}. Open that block on the FM3's screen.")
    for n in range(1, MAX_ROUNDS + 1):
        say(f"\nRound {n}: turn ONE knob on the FM3 (or change one setting),")
        answer = ask("then press Enter here. Type q and Enter to finish: ").strip()
        if answer.lower() == "q":
            break
        after, _ = read_words(dev, eid)
        moved = diff(before, after, stride)
        if not moved:
            say("Nothing changed in the values. Try that knob again, a bit further.")
            out.append(f"round {n}: no change")
            continue
        for line in moved[:8]:
            say("  " + line)
        knob = ask("Which knob was it? (name as on the screen): ").strip()
        shown = ask("What does the screen show for it now?: ").strip()
        out.append(f"round {n}: {knob or '?'} = {shown or '?'}")
        out.extend("  " + line for line in moved[:8])
        if len(moved) > 8:
            out.append(f"  ... and {len(moved) - 8} more")
        before = after
    out.append("result: MAPPED")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("block", nargs="?", default="amp",
                    help="amp (default), reverb, delay, chorus, ...")
    args = ap.parse_args(argv)
    reg = Registry()
    try:
        family = reg.resolve_block(args.block, 1)[0]
    except Exception as e:          # noqa: BLE001  a bad name is the player's to fix
        print(f"Unknown block {args.block!r}: {e}")
        return 1
    try:
        dev = open_fm3(reg)
    except Exception as e:          # noqa: BLE001  told to the player, in words
        print(f"Could not open the FM3: {e}")
        return 1
    try:
        lines = run(dev, reg, family)
    except ReadOnly as e:
        lines = ["FM3 knob map (#40)", f"refused before the wire: {e}", "result: FAIL"]
    except (KeyboardInterrupt, EOFError):
        lines = ["FM3 knob map (#40)", "stopped before the end", "result: STOPPED"]
    finally:
        with contextlib.suppress(Exception):
            dev.close()
    text = "\n".join(lines)
    print("\n----- copy from here -----")
    print(text)
    print("----- to here -----")
    print("Reselect the preset on the FM3 to drop your knob turns.")
    with contextlib.suppress(OSError):
        Path("fm3_knob_map_result.txt").write_text(text + "\n", encoding="utf-8")
        print("Also saved to fm3_knob_map_result.txt")
    return 0 if lines[-1] == "result: MAPPED" else 2


if __name__ == "__main__":
    sys.exit(main())

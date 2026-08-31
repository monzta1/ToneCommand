#!/usr/bin/env python3
"""Build a working chain into an empty preset slot, from nothing.

    python tools/build_from_scratch.py                 # pick a free slot
    python tools/build_from_scratch.py --slot 386       # a specific free one
                                                       # (WIRE number; FM9-Edit calls it 387)
    python tools/build_from_scratch.py --range 386 444  # search only this band
    TONECOMMAND_SIM=1 python tools/build_from_scratch.py

An empty FM9 slot is emptier than it looks: no grid cells at all, and no
Input or Output blocks either. There is nothing to splice into, so this
places the whole chain and draws every cable itself.

ALWAYS lands on a slot the device itself reports as <EMPTY>, and refuses
outright when there is no free slot to build on. It will not pick a
preset someone owns, and it takes no --force.

EDIT BUFFER ONLY. Nothing is stored, so the slot's stored name stays
<EMPTY> and re-selecting any preset discards the build. Storing is a
separate, whitelisted operation on purpose.

The blocks arrive at factory defaults and will sound plain until voiced.
Audible is the claim being made here, not good: verify with your ears,
which outrank every read path this tool has (docs/PROTOCOL.md, finding 13).
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fm9.registry import Registry  # noqa: E402
from fm9.scratch_build import CHAIN, ROW, SETTLE, build  # noqa: E402,F401


def describe(cells, reg) -> list[str]:
    """Render a grid already read. Re-reading here would cost a round trip and,
    on a timed-out second read, print an empty grid under a success line."""
    lines = []
    for c in sorted(cells, key=lambda c: (c.col, c.row)):
        fam = reg.family_of_effect_id(c.effect_id or 0)
        name = "SHUNT" if c.is_shunt else (fam[0] if fam else f"eid{c.effect_id}")
        lines.append(f"  row {c.row + 1} col {c.col + 1}: {name:9s} "
                     f"in_mask={c.cable_in_mask:#06b}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slot", type=int, default=None,
                    help="build here (WIRE number 0-511, which FM9-Edit shows "
                         "as 1-512); must be empty, or the run refuses")
    ap.add_argument("--range", type=int, nargs=2, metavar=("START", "END"),
                    default=[0, 511],
                    help="wire slots to search (default 0 511)")
    args = ap.parse_args(argv)

    reg = Registry()
    if os.environ.get("TONECOMMAND_SIM") == "1":
        from fm9.sim import SimFM9
        dev = SimFM9(reg)
    else:
        from fm9.device import FM9
        dev = FM9(reg)

    with dev:
        res = build(dev, reg, slot=args.slot, search=tuple(args.range))
        for line in res["steps"]:
            print(f"  {line}" if not line.startswith("target") else line)
        if res.get("cells"):
            print("\ngrid:")
            for c in sorted(res["cells"], key=lambda c: (c["col"], c["row"])):
                fam = reg.family_of_effect_id(c["effect_id"] or 0)
                name = ("SHUNT" if c["shunt"]
                        else (fam[0] if fam else f"eid{c['effect_id']}"))
                print(f"  row {c['row']} col {c['col']}: {name:9s} "
                      f"in_mask={c['in_mask']:#06b}")
        print()
        if res["bypassed"]:
            print(f"NOTE: bypassed blocks: {', '.join(res['bypassed'])}")
        if res["undecoded"]:
            print("simulated but NOT hardware-verified:")
            for note in res["undecoded"]:
                print(f"  !! {note}")
        print(res["detail"])
        if res["ok"]:
            print("PLAY IT. Audible is the claim; your ears outrank every "
                  "read path here.")
        return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

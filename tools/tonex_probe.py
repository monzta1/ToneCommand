#!/usr/bin/env python3
"""ToneX Phase 1 feasibility probe: does this pedal answer anything?

The one question that decides the adapter design. The KB says ToneX has no
official read-back over MIDI, so an adapter would have to either track state
locally (and label it unverified) or wait on the RE'd USB editor protocol.
Before accepting that, ask the hardware directly: listen for anything it
emits, then send the most benign message MIDI has and watch for a reply.

SAFETY, and this is not optional. Outbound traffic is limited to Program
Change and Control Change, which are structurally incapable of touching
firmware, bootloader or flash. SysEx is absent from the allowlist because on
an undecoded device that is exactly where brick risk lives.

The pedal's serial control port is READ ONLY here and should stay that way
until it is decoded. Firmware and bootloader traffic travels over precisely
that kind of channel, so this tool never opens it for writing.

Enforcement is fm9.safety.SendGuard, the shared gate, not a local check.
That is the point: a second device inherits invariant 0 rather than
reimplementing it.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import mido

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fm9.safety import message_type_guard        # noqa: E402

PORT = "ToneX"

# PC selects a preset and CC moves a published parameter; neither can write
# firmware. Widening this needs a hardware-verified decode and a documented
# recovery path (power cycle plus preset reselect).
GUARD = message_type_guard(
    PORT, ("program_change", "control_change"),
    note="The serial control port is read-only until it is decoded.")


def _guard(msg: mido.Message) -> mido.Message:
    GUARD.check(msg.type)
    return msg


def listen(inp, seconds: float, label: str) -> list:
    """Collect every inbound message for a fixed window."""
    got, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        for msg in inp.iter_pending():
            got.append((round(time.monotonic() - (end - seconds), 3), msg))
        time.sleep(0.005)
    print(f"  [{label}] {len(got)} message(s) inbound")
    for at, msg in got:
        print(f"    +{at:6.3f}s  {msg}")
    return got


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passive", type=float, default=15.0,
                    help="seconds to listen before sending anything")
    ap.add_argument("--programs", type=int, default=4,
                    help="how many program numbers to try")
    ap.add_argument("--settle", type=float, default=1.0,
                    help="seconds to listen after each send")
    ap.add_argument("--no-send", action="store_true",
                    help="listen only, put nothing on the wire")
    args = ap.parse_args()

    ins = [n for n in mido.get_input_names() if PORT.lower() in n.lower()]
    outs = [n for n in mido.get_output_names() if PORT.lower() in n.lower()]
    print(f"input ports : {ins}")
    print(f"output ports: {outs}")
    if not ins or not outs:
        raise SystemExit(f"{PORT} not found on the MIDI bus")

    with mido.open_input(ins[0]) as inp, mido.open_output(outs[0]) as outp:
        print(f"\n== passive: listening {args.passive}s, sending nothing ==")
        print("   (step on a footswitch or turn a knob now if you can)")
        passive = listen(inp, args.passive, "passive")

        if args.no_send:
            print("\n--no-send: stopping before any outbound message.")
            return

        print(f"\n== active: program change, listening {args.settle}s after each ==")
        replies = {}
        for program in range(args.programs):
            outp.send(_guard(mido.Message("program_change", program=program)))
            print(f"  -> program_change program={program}")
            replies[program] = listen(inp, args.settle, f"after PC {program}")

        answered = sum(1 for v in replies.values() if v)
        print("\n== verdict ==")
        print(f"spontaneous inbound while idle : {len(passive)}")
        print(f"program changes that drew a reply: {answered}/{args.programs}")
        if answered:
            print("A REPLY EXISTS. There may be a read-back path after all;")
            print("decode it before designing the adapter around blind writes.")
        else:
            print("Silent, as the KB predicted: no MIDI read-back path.")
            print("The adapter must declare no read path rather than infer one.")


if __name__ == "__main__":
    main()

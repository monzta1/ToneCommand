#!/usr/bin/env python3
"""Issue #43: find the wire addressing for user cab Bank 2 and above.

READ ONLY. Every message this sends is SysEx function 0x19, the user-cab read
REQUEST. It never sends 0x7A/0x7B/0x7C (the install frames), never stores, and
never selects a preset. The transport's own cab_guard is left in place, so a
write frame could not leave this process even by mistake.

    python tools/probe_cab_banks.py --populated 27          # bank 2, slot 27
    python tools/probe_cab_banks.py --populated 27 --full   # wider sweep

WHY A PROBE AND NOT A FIX. `FM9._cab_addr_candidates` yields exactly two
encodings:

    (number - 1,                 0x10 + (bank - 1))   -> bank 2: idx 26, tag 0x11
    ((bank - 1) * 512 + number - 1, 0x10)             -> bank 2: idx 538, tag 0x10

Neither answered a read on FM9 firmware 12.x, so `install_user_cab_at` refuses
rather than writing blind, and any pack that files its cabs above Bank 1
installs silent. The correct encoding is unknown, and the never-write-blind
rule means it has to be DISCOVERED by reading, not guessed at by writing.

HOW IT TELLS A HIT FROM A MISS. An empty user-cab slot still ANSWERS, with an
all-0x7F body. So there are three outcomes, not two:

    no answer      the address is not valid on this device
    answered 7F    valid address, empty slot
    answered data  valid address, and something is stored there

That third case is the one that identifies Bank 2, which is why the sweep
needs a slot you have deliberately populated.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fm9.registry import Registry  # noqa: E402

#: Bank 1 is the only addressing verified on hardware, so it is the control.
KNOWN_TAG = 0x10


def fingerprint(got) -> tuple:
    """(kind, bytes_seen, first_16) for a read result.

    `kind` is 'empty' when the body is entirely 0x7F, which is how the device
    reports a valid but unused slot.
    """
    if got is None:
        return ("no answer", 0, ())
    head, chunks = got
    body = list(head or ())
    for c in chunks:
        body += list(c)
    if not body:
        return ("answered, empty body", 0, ())
    kind = "EMPTY slot" if all(b == 0x7F for b in body) else "HAS DATA"
    return (kind, len(body), tuple(body[:16]))


def read(dev, idx: int, tag: int, timeout: float):
    try:
        return dev.read_user_cab_addr(idx, tag, timeout=timeout)
    except Exception as exc:                      # noqa: BLE001
        print(f"    ! {type(exc).__name__}: {exc}")
        return None


def show(label: str, fp: tuple) -> None:
    kind, n, first = fp
    head = " ".join(f"{b:02X}" for b in first)
    print(f"  {label:34} {kind:22} {n:6} bytes  {head}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--populated", type=int, required=True,
                    help="a user-cab NUMBER you know holds an IR (1-based, "
                         "as FM9-Edit shows it)")
    ap.add_argument("--bank", type=int, default=2,
                    help="which bank that populated slot is in (default 2)")
    ap.add_argument("--control", type=int, default=1,
                    help="a Bank 1 number to use as the positive control")
    ap.add_argument("--timeout", type=float, default=1.0,
                    help="per-read timeout; a miss costs this much")
    ap.add_argument("--full", action="store_true",
                    help="also sweep the flat index space at the known tag")
    a = ap.parse_args()

    from fm9.device import FM9
    dev = FM9(Registry())
    n0 = a.populated - 1              # 0-based, as the wire wants
    findings = []

    with dev:
        # --- 0. positive control ----------------------------------------
        # If Bank 1 does not answer, nothing below means anything: the fault
        # would be the connection, not the addressing.
        print(f"\n0. CONTROL, bank 1 number {a.control} (the verified path)")
        ctrl = fingerprint(read(dev, a.control - 1, KNOWN_TAG, 4.0))
        show(f"idx={a.control - 1} tag=0x{KNOWN_TAG:02X}", ctrl)
        if ctrl[0] == "no answer":
            print("\n  The known-good address did not answer. Stopping: the "
                  "problem is the link, not the bank encoding.")
            return 1
        print("  control answered, so the harness and the link are good.\n")

        # Bank 1 at the SAME number, to compare content against later. If the
        # two banks hold different IRs, this is what proves a hit is really
        # bank 2 and not bank 1 answering under another name.
        same_n = fingerprint(read(dev, n0, KNOWN_TAG, 4.0))
        print(f"   bank 1 number {a.populated} (for content comparison)")
        show(f"idx={n0} tag=0x{KNOWN_TAG:02X}", same_n)

        # --- 1. the two encodings the code already tries ------------------
        print(f"\n1. THE TWO CANDIDATES ALREADY IN _cab_addr_candidates")
        for idx, tag, why in (
                (n0, KNOWN_TAG + (a.bank - 1), "tag carries the bank"),
                ((a.bank - 1) * 512 + n0, KNOWN_TAG, "flat index, 512 per bank")):
            fp = fingerprint(read(dev, idx, tag, a.timeout))
            show(f"idx={idx} tag=0x{tag:02X}  ({why})", fp)
            if fp[0] == "HAS DATA":
                findings.append((idx, tag, fp, why))

        # --- 2. tag sweeps ------------------------------------------------
        # Two places the bank could ride, so sweep the tag at both: at the
        # bare number (bank in the tag) and at the flat index (bank in the
        # index, but under a tag other than 0x10).
        flat = (a.bank - 1) * 512 + n0
        for base, label in ((n0, "bare number"), (flat, "flat index")):
            print(f"\n2. TAG SWEEP at idx={base} ({label}), tag 0x00-0x7F")
            for tag in range(0x80):
                if tag == KNOWN_TAG and base == n0:
                    continue                      # that is the bank 1 control
                fp = fingerprint(read(dev, base, tag, a.timeout))
                if fp[0] != "no answer":
                    show(f"idx={base} tag=0x{tag:02X}", fp)
                    if fp[0] == "HAS DATA" and fp != same_n:
                        findings.append((base, tag, fp, f"tag sweep, {label}"))
            print("  (only answering addresses are listed)")

        # --- 3. flat index sweep at the known tag -------------------------
        # If instead the bank rides in the index, the bank size is what is
        # wrong, not the scheme. Bank sizes worth testing are the ones that
        # put number N of bank 2 at a round offset.
        print(f"\n3. FLAT INDEX at tag=0x{KNOWN_TAG:02X}, common bank sizes")
        for size in (64, 100, 128, 200, 256, 512, 1000, 1024):
            idx = (a.bank - 1) * size + n0
            fp = fingerprint(read(dev, idx, KNOWN_TAG, a.timeout))
            show(f"idx={idx} (bank size {size})", fp)
            if fp[0] == "HAS DATA" and fp != same_n:
                findings.append((idx, KNOWN_TAG, fp, f"bank size {size}"))

        if a.full:
            print(f"\n4. FULL SWEEP idx 0-1200 at tag=0x{KNOWN_TAG:02X} "
                  "(answering, non-empty only)")
            for idx in range(0, 1201):
                fp = fingerprint(read(dev, idx, KNOWN_TAG, 0.4))
                if fp[0] == "HAS DATA":
                    show(f"idx={idx}", fp)

    # --- what it found ---------------------------------------------------
    print("\n" + "=" * 68)
    if not findings:
        print("No address outside Bank 1 returned stored data.")
        print("That is a real result, not a failure: it says the bank is not")
        print("reachable by any of these schemes, and #43 needs the next")
        print("idea rather than another guess.")
        return 2
    print(f"{len(findings)} candidate address(es) returned STORED DATA:")
    for idx, tag, fp, why in findings:
        print(f"  idx={idx} tag=0x{tag:02X}  ({why})  first bytes "
              + " ".join(f"{b:02X}" for b in fp[2]))
    print("\nNext: confirm by reading a DIFFERENT populated bank-2 slot at the")
    print("same scheme. One hit could be coincidence; two is an encoding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

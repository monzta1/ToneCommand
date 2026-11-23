#!/usr/bin/env python3
"""Check every FM3 setting ToneCommand can change, on a real FM3 (#40).

    python tools/fm3_settings_check.py
    TONECOMMAND_FM3_SIM=1 python tools/fm3_settings_check.py   # on the simulator

This drives the app's own FM3 code (the device handle and fm9/fm3_map.py,
nothing opened just for the test) through each of the 19 measured settings
of the amp, reverb and delay in the loaded preset: it reads the setting,
moves it a small step (5% of its range, toward the middle), reads it back,
and puts the old value back. At the end it reloads the preset, which
discards the edit buffer, so the unit is left as it was. Nothing is stored.

Turn your monitors down a little first: Level and Master move too, by a
small step and only for a moment. Stop ToneCommand before running this: on
Windows only one program can hold a MIDI port.

At the end it prints a result block to paste back, and saves the same text
to fm3_settings_check_result.txt in the current folder.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from fm9 import fm3_map  # noqa: E402
from fm9 import protocol as p  # noqa: E402
from fm9.device import ReadOnly  # noqa: E402
from fm9.registry import Registry  # noqa: E402
from fm3_first_edit import open_fm3  # noqa: E402

FAMILY = {"DISTORT": "amp", "REVERB": "reverb", "DELAY": "delay"}
STEP = 0.05


def _target(before: float, m: fm3_map.Fm3Param) -> float:
    """A small step toward the middle of the range, on the setting's scale."""
    n = p.display_to_normalized(before, m.dmin, m.dmax, m.scale)
    n = n + STEP if n < 0.5 else n - STEP
    return round(p.normalized_to_display(n, m.dmin, m.dmax, m.scale), 2)


def run(dev, reg: Registry, say=print) -> list[str]:
    out = ["FM3 settings check (#40)"]
    preset = dev.current_preset()
    if preset is None:
        raise SystemExit("The FM3 did not answer. Is ToneCommand stopped, and the "
                         "interface connected?")
    number, name = preset
    out.append(f"preset: {p.slot_label(number)} {name!r}")
    present = {b.effect_id for b in dev.status_dump() or []}
    passed = failed = skipped = 0
    for (family, pid), m in fm3_map.PARAMS.items():
        what = f"{FAMILY[family]} {m.label}"
        if fm3_map.EFFECT_IDS[family] not in present:
            out.append(f"{what}: skipped, no {FAMILY[family]} 1 in this preset")
            skipped += 1
            continue
        spec = reg.spec(family, pid, 1)
        before = dev.get_param_display(spec)
        if not isinstance(before, (int, float)):
            out.append(f"{what}: FAIL, could not read it")
            failed += 1
            continue
        target = _target(before, m)
        say(f"{what}: {before} -> {target}")
        r = dev.set_param_display(spec, target)
        if p.display_to_normalized(before, m.dmin, m.dmax, m.scale) == 0.0:
            # a write of exactly 0 is a read on the FM9; the reload restores it
            back, note = None, "restore by reload"
        else:
            back = dev.set_param_display(spec, before)
            note = f"restored {back.display_after}" if back.ok else f"restore FAILED ({back.detail})"
        ok = r.ok and (back is None or back.ok)
        passed, failed = passed + ok, failed + (not ok)
        out.append(f"{what}: {before} -> {target}, read back {r.display_after}; "
                   f"{note} -> {'PASS' if ok else 'FAIL'}")
    reloaded = dev.select_preset(number)
    out.append("reload (discards the edit buffer): "
               f"{p.slot_label(reloaded[0]) if reloaded else 'no answer'}")
    out.append(f"settings: {passed} passed, {failed} failed, {skipped} skipped")
    out.append(f"result: {'PASS' if passed and not failed else 'FAIL'}")
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
        lines = ["FM3 settings check (#40)", f"refused before the wire: {e}", "result: FAIL"]
    except (KeyboardInterrupt, EOFError):
        lines = ["FM3 settings check (#40)",
                 "stopped before the end; reselect the preset on the FM3", "result: STOPPED"]
    finally:
        with contextlib.suppress(Exception):
            dev.close()
    text = "\n".join(lines)
    print("\n----- copy from here -----")
    print(text)
    print("----- to here -----")
    with contextlib.suppress(OSError):
        Path("fm3_settings_check_result.txt").write_text(text + "\n", encoding="utf-8")
        print("Also saved to fm3_settings_check_result.txt")
    return 0 if lines[-1] == "result: PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

"""The #172 hardware pass: the same reads and writes through whichever MIDI
backend is active, recorded so two backends can be compared byte for byte.

    python tools/transport_pass.py run --preset FILE.syx --cab FILE.syx \
        --cab-slot 522 --out record.json
    python tools/transport_pass.py compare a.json b.json

Run it once on Python 3.12 (python-rtmidi through mido) and once on Python
3.14 (supriya-midi), with nothing else holding the FM9's port, then compare.

What it touches, inside the hardware rules (kb/HARDWARE_RULES.md):
- reads: the status dump, the CABINET block, the two routing globals, the
  edit buffer before and after;
- the EDIT BUFFER: the given preset file is loaded into it and never
  stored, and the preset that was loaded at the start is re-selected at the
  end, which discards the load;
- one user-cab slot, which must be inside TONECOMMAND_CAB_SLOTS: the given
  cab file is installed there and the slot's name is read back.
Nothing is stored and fn 0x19 is never sent.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: The acceptance policy for comparing two passes. These differ between two
#: runs without any fault, and are listed as expected, never hidden:
#: run metadata, and the cab slot's name BEFORE the install (the first run's
#: install is what the second run finds there). Everything else must match.
EXPECTED = {"/backend", "/python", "/started_at", "/seconds", "/cab/name_before"}


def _status(fm9) -> list[list]:
    return [[b.effect_id, bool(b.bypassed), int(b.channel), int(b.channels_supported)]
            for b in (fm9.status_dump() or [])]


class PassError(RuntimeError):
    pass


def problems(rec: dict) -> list[str]:
    """Why a record cannot count as a successful pass. A pass whose reads
    came back empty, whose cab install was not verified by the unit, or which
    did not end on the preset it started on proves nothing, however well two
    such records match."""
    out = []
    if not rec.get("status"):
        out.append("the status dump came back empty")
    if not rec.get("cabinet_bulk"):
        out.append("the CABINET bulk read came back empty")
    routing = rec.get("routing") or {}
    if set(routing) != {"72", "73"} or any(v.get("ordinal") is None for v in routing.values()):
        out.append("the routing globals were not both read")
    for key in ("capture_before", "capture_after_load"):
        cap = rec.get(key) or {}
        blocks = cap.get("blocks") or []
        if not blocks:
            out.append(f"{key}: no blocks were read")
        elif any(not b.get("values") for b in blocks):
            out.append(f"{key}: {sum(1 for b in blocks if not b.get('values'))} block(s) read no values")
    if (rec.get("capture_after_load") or {}).get("preset_name") == (rec.get("capture_before") or {}).get("preset_name") \
            and rec.get("capture_before"):
        out.append("the edit buffer still shows the starting preset's name after the load")
    cab = rec.get("cab") or {}
    if not cab.get("verified"):
        out.append(f"the cab install was not verified by the unit (read back {cab.get('name_after')!r})")
    if rec.get("cab_name_read_again") != cab.get("name_after"):
        out.append("the cab slot's name read twice gave two answers")
    if not rec.get("start_preset") or rec.get("end_preset") != rec.get("start_preset"):
        out.append(f"the pass did not end on the preset it started on "
                   f"({rec.get('start_preset')} -> {rec.get('end_preset')})")
    if rec.get("error"):
        out.append(f"the pass stopped: {rec['error']}")
    return out


def run(fm9, reg, preset_file: Path, cab_file: Path, cab_slot: int) -> dict:
    """One pass on an open device. Refuses a cab slot outside the whitelist,
    or a unit whose loaded preset cannot be read, before anything is sent.
    Whatever happens after the first write, the starting preset is
    re-selected and read back."""
    from fm9 import editbuffer, midi_transport, presetfile, routing
    from fm9.device import get_cab_slots

    if cab_slot not in get_cab_slots():
        raise PermissionError(f"user cab slot {cab_slot} is not in TONECOMMAND_CAB_SLOTS; "
                              "the pass writes only to a slot you have designated")
    t0 = time.time()
    try:
        backend = midi_transport.backend()
    except Exception as exc:                     # the simulator needs no binding
        backend = f"none ({exc})"
    rec: dict = {"backend": backend, "python": platform.python_version(),
                 "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    start = fm9.current_preset()
    if not start:
        raise PassError("the loaded preset could not be read, so it could not be put back; "
                        "nothing was sent")
    rec["start_preset"] = list(start)
    rec["status"] = _status(fm9)
    _fam, cab_eid = reg.resolve_block("cab", 1)
    rec["cabinet_bulk"] = fm9.bulk_read(cab_eid)
    rec["routing"] = {str(k): v for k, v in routing.read_routing(fm9).items()}
    rec["capture_before"] = editbuffer.capture(fm9, reg)
    raw = preset_file.read_bytes()
    rec["preset_file"] = {"name": presetfile.parse(raw).name,
                          "frames": len(presetfile.for_edit_buffer(presetfile.parse(raw)))}
    try:
        fm9.load_preset_buffer(raw)
        time.sleep(0.5)
        rec["capture_after_load"] = editbuffer.capture(fm9, reg)
        cab = fm9.install_user_cab_slot(cab_file.read_bytes(), cab_slot, cab_file.name)
        rec["cab"] = {"slot": cab.slot, "verified": cab.verified, "name_before": cab.name_before,
                      "name_after": cab.name_after}
        rec["cab_name_read_again"] = fm9.read_user_cab_name(cab_slot)
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        # Put the starting preset back whatever happened, and read it back:
        # a read that settles and retries, not one that passes on timing.
        end = None
        for _ in range(3):
            fm9.select_preset(start[0])          # discards the edit-buffer load
            time.sleep(0.5)
            end = fm9.current_preset()
            if end and end[0] == start[0]:
                break
        rec["end_preset"] = list(end) if end else None
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def diff(a, b, path: str = "") -> list[str]:
    """Every key path whose value differs, VOLATILE keys skipped."""
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'b' if k not in a else 'a'}")
            else:
                out += diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


def compare(a: dict, b: dict) -> tuple[list[str], list[str], list[str]]:
    """(unexpected differences, expected differences, problems). Both
    records must be complete; an expected difference is listed, not hidden."""
    found = diff(a, b)
    expected = [d for d in found if d.split(":")[0] in EXPECTED]
    unexpected = [d for d in found if d.split(":")[0] not in EXPECTED]
    bad = [f"a: {x}" for x in problems(a)] + [f"b: {x}" for x in problems(b)]
    return unexpected, expected, bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--preset", type=Path, required=True)
    r.add_argument("--cab", type=Path, required=True)
    r.add_argument("--cab-slot", type=int, required=True)
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "compare":
        a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (args.a, args.b))
        unexpected, expected, bad = compare(a, b)
        ok = not unexpected and not bad
        print(f"{a.get('backend')} on {a.get('python')} vs {b.get('backend')} on {b.get('python')}: "
              + ("PASS" if ok else "FAIL"))
        for title, lines in (("incomplete", bad), ("unexpected", unexpected), ("expected", expected)):
            for line in lines:
                print(f"  {title}: {line}")
        return 0 if ok else 1
    from fm9.device import FM9
    from fm9.registry import Registry
    reg = Registry()
    fm9 = FM9(reg)
    try:
        rec = run(fm9, reg, args.preset, args.cab, args.cab_slot)
    finally:
        fm9.close()
    args.out.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    bad = problems(rec)
    cab = rec.get("cab") or {}
    print(f"{rec['backend']} on Python {rec['python']}: {len(rec.get('status') or [])} blocks, "
          f"cab {cab.get('name_after')!r} {'verified' if cab.get('verified') else 'NOT verified'}, "
          f"back on preset {rec.get('end_preset')}, {rec.get('seconds')} s: "
          + ("complete" if not bad else "INCOMPLETE"))
    for line in bad:
        print("  " + line)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())

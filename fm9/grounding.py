"""The grounding sidecar envelope (#17, ARCHITECTURE.md step 3).

A grounding sidecar maps a device's own roster entries to the real-world gear
they model: `amp_models.json` says FM9 "Euro Blue" is a Bogner Ecstasy blue
channel, and so on for drives, cabs and effect types. The planner reads these
so it can reason in the names players use rather than Fractal's.

They are the highest-risk files in the repo, which is why they get a spec at
all. Every fact in them is copied from somewhere, none of it is measured here,
and a wrong entry does not crash: it teaches the planner a confident falsehood
that reaches the player as advice. So the envelope is not bookkeeping, it is
the part that makes a sidecar reviewable.

WHAT WAS ALREADY TRUE. All four existing sidecars already carry the same seven
envelope fields with real citations. This module does not invent a shape; it
writes down the one that four files converged on and makes it enforceable, so
the fifth (a second device's) has something to conform to instead of being
compared to whichever existing file the author happened to open.

WHAT IT DELIBERATELY DOES NOT DO. It does not check that the FACTS are right.
Nothing local can: that is what `source` is for, and why `warning` exists to
carry each file's specific caveat. It checks that a sidecar says where it came
from and what it is keyed by, which is the precondition for a human to check
the facts at all.

Drift guards are separate and live in registry.py, because they compare a
sidecar against the catalog roster it was built from, which is per-family.
Not every sidecar can have one: `effect_type_models.json` is keyed by display
name and the catalog carries no ordinal roster for delay, chorus, multitap or
pitch types, so there is nothing to drift against until #5 maps them on
hardware. That absence is correct, and `REQUIRES_DRIFT_GUARD` records which
families can be guarded rather than leaving it to be rediscovered.
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config"

#: Every sidecar carries these. Each exists because a reviewer needs it to
#: judge whether an entry is trustworthy without opening the generator.
ENVELOPE = {
    "schema_version": "int, bumped when the payload shape changes",
    "device": "which device's roster this maps, e.g. FM9",
    "source": "where the facts came from, specific enough to check",
    "generated_by": "the script that wrote it, so it can be regenerated",
    "keyed_by": "what the payload keys ARE (ordinal? display name?), because "
                "the two drift differently and are easy to confuse",
    "content": "what one record holds",
    "warning": "this file's specific caveat, in its own words",
}

#: Families whose sidecar CAN be checked against a catalog roster. The others
#: are not unguarded by oversight: there is no roster to compare them to.
REQUIRES_DRIFT_GUARD = frozenset({"amp_models", "drive_models", "cab_models"})


def sidecars() -> list[Path]:
    return sorted(CONFIG.glob("*_models.json"))


def validate(path: Path) -> list[str]:
    """Problems with one sidecar's envelope. Empty means it conforms."""
    problems: list[str] = []
    try:
        blob = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        return [f"unreadable: {exc}"]
    if not isinstance(blob, dict):
        return ["top level is not an object"]

    for field in ENVELOPE:
        val = blob.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            problems.append(f"missing {field!r}: {ENVELOPE[field]}")
    if not isinstance(blob.get("schema_version", 0), int):
        problems.append("schema_version must be an int")

    # A citation that says nothing is worse than none, because it looks like
    # provenance. Any real source names a document, a page or a capture date.
    src = str(blob.get("source") or "")
    if src and len(src) < 12:
        problems.append(f"source {src!r} is too vague to check a fact against")

    # The payload is whatever is left. A sidecar with only an envelope is a
    # header, not grounding.
    payload = {k: v for k, v in blob.items() if k not in ENVELOPE}
    if not payload:
        problems.append("no payload: the envelope describes nothing")
    elif not any(isinstance(v, dict) and v for v in payload.values()):
        problems.append("payload holds no records")
    return problems

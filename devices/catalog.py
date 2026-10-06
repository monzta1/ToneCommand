"""DPDP, the Dynamic Processor Discovery Protocol (#208, phase 1 #209): what
ToneCommand knows about a device before it has, or even could have, any code
for it. DPDP finds the device; it then hands off to DDCP, the Dynamic Device
Control Protocol, which is the adapter contract in fm9/adapter.py that every
device's code implements.

Data, not code. `catalog.json` says, per device, how to recognise it from
the MIDI port list, which adapter drives it (or that none does yet) and the
issue tracking that adapter. Recognition is a pure function over port NAMES:
it opens nothing and sends nothing, so a device ToneCommand cannot drive is
named to the player without a single byte reaching it.

A pattern marked `verified` was seen on real hardware (the FM9's
'FM9 MIDI In 0' from #193, the IR-2's 'IR-2' on the bench). The rest are
inferred from Fractal's naming and say "looks like" when they match.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

ISSUES_URL = "https://github.com/monzta1/ToneCommand/issues/"
FIELDS = ("kind", "label", "ports", "adapter", "issue", "verified")


class CatalogError(ValueError):
    pass


def _check(entry: dict) -> dict:
    missing = [f for f in FIELDS if f not in entry]
    if missing:
        raise CatalogError(f"catalog entry {entry.get('kind')!r} lacks {missing}")
    if entry["adapter"] is None and not isinstance(entry["issue"], int):
        raise CatalogError(f"{entry['kind']!r} has no adapter and no issue to point at")
    return dict(entry, patterns=[re.compile(p, re.I) for p in entry["ports"]])


@lru_cache(maxsize=1)
def load() -> tuple[dict, ...]:
    """Every catalog entry, validated, in file order."""
    raw = json.loads(resources.files("devices").joinpath("catalog.json")
                     .read_text(encoding="utf-8"))
    entries = tuple(_check(e) for e in raw["devices"])
    kinds = [e["kind"] for e in entries]
    if len(kinds) != len(set(kinds)):
        raise CatalogError(f"duplicate kinds in the catalog: {kinds}")
    return entries


def public(entry: dict) -> dict:
    """What the page is told about one entry."""
    return {"kind": entry["kind"], "label": entry["label"],
            "supported": entry["adapter"] is not None,
            "verified": bool(entry["verified"]),
            "issue": entry["issue"],
            "issue_url": f"{ISSUES_URL}{entry['issue']}" if entry["issue"] else None,
            # #212: supported for reading only (the FM3 through the FM9 module).
            "read_only": bool(entry.get("read_only"))}


def recognise(port_names) -> list[dict]:
    """The catalog entries whose patterns match a port in `port_names`, in
    catalog order, one per kind (an FM9 exposes several ports). Pure: names
    in, entries out."""
    names = [str(n) for n in port_names or ()]
    return [public(e) for e in load()
            if any(p.search(n) for p in e["patterns"] for n in names)]

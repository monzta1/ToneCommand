"""Names for the player's OWN user-cab slots.

Factory cabs live in a catalogue, so ToneCommand can name them. USER-bank cabs
are whatever the player installed, so no catalogue can ever list them: the name
lookup missed and the UI printed a bare ordinal, showing "26" where it should
say "Soldano SLO30". This is the small map that gives those slots names.

Two ways it gets filled:
  - automatically when ToneCommand installs an IR, since it knows the filename
  - by hand for cabs installed with another tool, such as Fractal's Cab-Lab

The FM9 itself does know the name, but it is packed among the IR data in the
cab dump and fm9/cabfile.py does not decode it, so this map is the honest way
to carry the label rather than pretending to read it off the device.

Shape on disk, bank then ordinal, both as strings because JSON keys are:

    {"2": {"26": "Soldano SLO30 - Emil Rohbe"}}

Never raises. A missing, unreadable or malformed file simply means no names,
and the caller falls back to the ordinal exactly as before.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_cache: dict = {}
_stamp: tuple | None = None


def path() -> Path:
    env = (os.environ.get("TONECOMMAND_USER_CABS") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "user_cabs.json"


def all_names() -> dict:
    """The whole map, re-read when the file changes. {bank: {ordinal: name}}."""
    global _cache, _stamp
    p = path()
    try:
        st = p.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        _cache, _stamp = {}, None
        return {}
    if stamp != _stamp:
        try:
            got = json.loads(p.read_text())
            _cache = got if isinstance(got, dict) else {}
        except (ValueError, OSError):
            _cache = {}
        _stamp = stamp
    return _cache


def record(bank: int | str, ordinal: int | str):
    """The raw entry for a slot: a legacy display string, a dict, or None.

    Two shapes live here. A bare string is a LABEL, written by hand or by an
    older install, and it identifies nothing. A dict carries provenance that
    ToneCommand recorded when it installed the file, which is what may serve
    as a measured anchor (brief 26.1).
    """
    return (all_names().get(str(bank)) or {}).get(str(ordinal))


def name(bank: int | str, ordinal: int | str) -> str | None:
    """The player's name for a slot, or None when they have not named it."""
    got = all_names().get(str(bank), {})
    if not isinstance(got, dict):
        return None
    val = got.get(str(ordinal))
    # Two shapes: a legacy display string, or a provenance dict whose label
    # is one field of it. Both name the slot in the UI; only the dict can
    # anchor a measurement (see record()).
    if isinstance(val, dict):
        val = val.get("label")
    return val.strip() or None if isinstance(val, str) else None


def set_name(bank: int | str, ordinal: int | str, label: str) -> dict:
    """Name a slot, or clear it with an empty label. Returns the whole map."""
    global _stamp
    data = dict(all_names())
    b = str(bank)
    slots = dict(data.get(b) or {})
    label = (label or "").strip()
    if label:
        slots[str(ordinal)] = label[:64]
    else:
        slots.pop(str(ordinal), None)
    if slots:
        data[b] = slots
    else:
        data.pop(b, None)
    path().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    _stamp = None                      # force a re-read on the next lookup
    return data

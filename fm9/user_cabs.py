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
import time
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


def _write(data: dict) -> dict:
    global _stamp
    path().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    _stamp = None                      # force a re-read on the next lookup
    return data


def set_name(bank: int | str, ordinal: int | str, label: str) -> dict:
    """Name a slot, or clear it with an empty label. Returns the whole map.

    RENAMING NEVER DISCARDS A LINK. This used to overwrite the whole entry
    with a bare string, so typing a nicer name into a linked slot silently
    threw the provenance away and the slot stopped being a measured anchor,
    with nothing said. A name is a label; the link is a fact about a file.
    Clearing the name still clears the whole entry, because that is what the
    player asked for.

    An INSTALL is not a rename and must not come through here: what the slot
    holds has changed, so the old link is now a lie. Use relabel_installed().
    """
    data = dict(all_names())
    b = str(bank)
    slots = dict(data.get(b) or {})
    key = str(ordinal)
    label = (label or "").strip()
    if label:
        existing = slots.get(key)
        if isinstance(existing, dict):
            slots[key] = dict(existing, label=label[:64])
        else:
            slots[key] = label[:64]
    else:
        slots.pop(key, None)
    if slots:
        data[b] = slots
    else:
        data.pop(b, None)
    return _write(data)


def relabel_installed(bank: int | str, ordinal: int | str, label: str) -> dict:
    """Name a slot that has just had something WRITTEN INTO IT, dropping any
    link it carried. Returns the whole map.

    The distinction matters because set_name merges into an existing entry to
    protect a link across a rename, and the install path is a set_name call.
    So installing a different IR into a linked slot kept the old `source` and
    `digest`: the file on disk was untouched, the digest still matched,
    IRCommand still held its curve, and the slot went on serving as a
    `measured` anchor for a capture it no longer contained. Every "x dB from
    current" after that was measured against something the player could not
    hear. Protecting the link across a rename created this; the two writes
    have to be different calls because they mean different things.
    """
    data = dict(all_names())
    b = str(bank)
    slots = dict(data.get(b) or {})
    label = (label or "").strip()[:64]
    if label:
        slots[str(ordinal)] = label
    else:
        slots.pop(str(ordinal), None)
    if slots:
        data[b] = slots
    else:
        data.pop(b, None)
    return _write(data)


def set_link(bank: int | str, ordinal: int | str, source: str,
             digest: str, label: str = "") -> dict:
    """Record WHICH FILE a user-cab slot holds. Returns the whole map.

    This is the only writer of the provenance shape, and until it existed the
    `measured` anchor state was unreachable by any route the product offers:
    every install path wrote a bare display string, so a slot could be named
    and never linked. Verified by test and never once by use.

    What a link asserts, exactly, so nothing downstream over-reads it:

      - the player says this slot holds this file
      - the file is one IRCommand has measured, checked when the link is made
      - `digest` is the file's bytes at link time, so a later change is caught

    What it does NOT assert: that the FM9 slot really contains that capture.
    Nothing can read the IR back off the device and compare it, so the device
    side is the player's word. That is enough to rank against, which is all
    the anchor is for, and it is not enough to call the slot verified.

    Clearing the source reverts the slot to a plain name.
    """
    data = dict(all_names())
    b = str(bank)
    slots = dict(data.get(b) or {})
    key = str(ordinal)
    existing = slots.get(key)
    kept = (existing.get("label") if isinstance(existing, dict)
            else existing if isinstance(existing, str) else None)
    label = (label or kept or "").strip()[:64]
    source = (source or "").strip()
    if not source:
        slots[key] = label or None
        if not label:
            slots.pop(key, None)
    else:
        slots[key] = {"label": label, "source": source, "digest": digest,
                      "linked": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if slots:
        data[b] = slots
    else:
        data.pop(b, None)
    return _write(data)

"""Fetch presets from Gift of Tone by asking for them in words. Issue #42.

"Get me the Periphery tones from Gift of Tone" should not require knowing
that Fractal hosts a zip at a particular URL. This module turns that
sentence into files: it reads the official Gift of Tone page, matches the
artist deterministically (the catalog is regular; no model call, nothing
to hallucinate), downloads the bundle, and hands every FM9 preset inside
to the same validating parser the file-drop path uses.

Nothing here touches hardware. The output is parsed PresetFiles for the
install cache; every flash write still goes through /api/install with the
whitelist, the gig lock, the confirmation and the read-back verification.

Sources are fetched as the user, for the user, one bundle per ask: this
is a hand reaching for a published free download, not a crawler.
"""
from __future__ import annotations

import io
import re
import urllib.request
import zipfile

from . import cabfile, presetfile

GOT_URL = "https://www.fractalaudio.com/gift-of-tone/"

_ZIP_RE = re.compile(
    r'href="(https://www\.fractalaudio\.com/downloads/[^"]+\.zip)"')
_NAME_RE = re.compile(r"FAS-gift(\d\d)-[0-9]+[a-z0-9]*-(.+)\.zip$")

#: Words in an ask that say WHAT DOING, not WHO: stripped before matching.
_STOPWORDS = frozenset(
    "get me the a an tones tone preset presets from gift of got download "
    "grab install fetch load and please for my fm9 find go it straight "
    "some can you please pull bring".split())

#: Bundles can be tens of MB of extras; refuse anything absurd.
MAX_DOWNLOAD = 64 * 1024 * 1024


class AcquireError(ValueError):
    """Written for the person who asked, not for a log."""


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ToneCommand"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise AcquireError("that download is larger than anything a preset "
                           "bundle should be; refusing it")
    return data


def catalog(fetch=None) -> list[dict]:
    """Every gift on the official page: artist, year, url. Newest first.

    `fetch` resolves at call time so tests can replace _download; a default
    bound at def time hit the real network from CI once.
    """
    fetch = fetch or _download
    try:
        html = fetch(GOT_URL).decode("utf-8", "replace")
    except AcquireError:
        raise
    except Exception as exc:
        raise AcquireError(
            f"could not reach the Gift of Tone page: {exc}") from exc
    seen, out = set(), []
    for url in _ZIP_RE.findall(html):
        if url in seen:
            continue
        seen.add(url)
        m = _NAME_RE.search(url)
        if not m:
            continue
        artist = m.group(2).replace("_", " ").replace("-", " ").strip()
        out.append({"artist": artist, "year": 2000 + int(m.group(1)),
                    "url": url})
    if not out:
        raise AcquireError("the Gift of Tone page answered but no bundles "
                           "were found on it; its layout may have changed")
    out.sort(key=lambda e: -e["year"])
    return out


def find(query: str, entries: list[dict]) -> dict | None:
    """The best-matching gift for a plain-words ask, or None.

    Deterministic: every non-stopword in the ask must appear in the artist
    name (so "periphery" finds Periphery and "steve vai" finds Steve Vai,
    but "periphery" never falls back to somebody else). Ties go newest.
    """
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower())
             if w not in _STOPWORDS]
    if not words:
        return None
    for e in entries:                      # already newest-first
        artist = e["artist"].lower()
        if all(w in artist for w in words):
            return e
    return None


def fetch_presets(url: str, fetch=None) -> tuple[list[dict], list[str]]:
    """Back-compat face of fetch_bundle: presets and skip notes only."""
    presets, _cabs, skipped = fetch_bundle(url, fetch)
    return presets, skipped


def fetch_bundle(url: str, fetch=None
                 ) -> tuple[list[dict], list[dict], list[str]]:
    """Download a bundle; validate every FM9 preset AND user-cab IR inside.

    Returns (presets, cabs, skipped). Presets as {name, file, raw, chunks};
    cabs as {label, file, raw, chunks, default_slot} where default_slot is
    the artist's own U{n} filing when the filename states one - the slot
    their presets reference, which is the step players get wrong by hand.
    Skips carry honest notes so "found 3 of 9 files" never reads as loss.
    """
    fetch = fetch or _download
    data = fetch(url)
    candidates: list[tuple[str, bytes]] = []
    if data[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise AcquireError(f"the download is not a readable zip: {exc}")
        fasbundles = []
        for info in zf.infolist():
            base = info.filename.rsplit("/", 1)[-1]
            if base.startswith("._"):
                continue                    # AppleDouble junk
            if base.lower().endswith(".fasbundle"):
                fasbundles.append(base)     # noted below, never silent
                continue
            if not base.lower().endswith(".syx"):
                continue                    # readmes and extras
            candidates.append((base, zf.read(info)))
    elif data[:1] == b"\xf0":
        candidates.append((url.rsplit("/", 1)[-1], data))
    else:
        raise AcquireError("the download is neither a zip nor a .syx; "
                           "nothing here to install")
    presets, cabs, skipped = [], [], []
    for base in (fasbundles if data[:2] == b"PK" else []):
        skipped.append(f"{base}: FM9-Edit bundle format (.fasBundle), not "
                       "yet supported here; import it with FM9-Edit")
    for base, raw in candidates:
        try:
            pf = presetfile.parse(raw)
            presets.append({"name": pf.name, "file": base, "raw": raw,
                            "chunks": pf.chunks})
            continue
        except presetfile.PresetFileError as exc:
            preset_why = str(exc)   # `as` names unbind after the block
        try:
            cf = cabfile.parse(raw, base)
            cabs.append({"label": cf.label, "file": base, "raw": raw,
                         "chunks": cf.chunks,
                         "default_slot": cabfile.default_slot(base)})
            continue
        except cabfile.CabFileError:
            pass
        skipped.append(f"{base}: {preset_why}")
    if not presets and not cabs:
        raise AcquireError(
            "the bundle held no FM9 presets or cabs. "
            + ("; ".join(skipped[:4]) if skipped else "it was empty"))
    return presets, cabs, skipped


# --- local library: presets already on this machine ----------------------
#
# "find the luke tone and load it" should not require knowing the file is a
# purchased zip in Downloads. This scans local folders for FM9 preset files
# and bundles, matches by name the same deterministic way the Gift of Tone
# catalog does, and hands the winner to the same parser + install path.

import os
import zipfile as _zipfile
from pathlib import Path as _Path

#: The one folder the owner keeps offline tones in, set in Settings. Stored
#: like the store whitelist: a JSON file, overridable by env for operators.
def tone_dir_path() -> _Path:
    return _Path(__file__).resolve().parent.parent / "tone_dir.json"


def get_tone_dir() -> str:
    import json as _json
    raw = os.environ.get("TONECOMMAND_TONE_DIR", "").strip()
    if raw:
        return raw
    f = tone_dir_path()
    if f.exists():
        try:
            got = _json.loads(f.read_text())
            if isinstance(got, dict) and isinstance(got.get("dir"), str):
                return got["dir"]
        except (ValueError, OSError):
            pass
    return ""


def set_tone_dir(path: str) -> str:
    import json as _json
    path = str(path or "").strip()
    if path and not _Path(path).expanduser().is_dir():
        raise AcquireError(f"no folder at {path}")
    tone_dir_path().write_text(_json.dumps({"dir": path}) + "\n")
    return path


def local_dirs() -> list:
    """The configured tone folder, if it exists. Only that one is combed,
    never the whole disk (owner's rule: comb that location only)."""
    d = get_tone_dir()
    if not d:
        return []
    p = _Path(d).expanduser()
    return [p] if p.is_dir() else []


def _fm9_from_zip_bytes(data: bytes) -> list:
    """Every FM9 preset/bundle inside a zip, as (label, raw, kind)."""
    out = []
    try:
        zf = _zipfile.ZipFile(io.BytesIO(data))
    except _zipfile.BadZipFile:
        return out
    for info in zf.infolist():
        base = info.filename.rsplit("/", 1)[-1]
        if base.startswith("._") or "/FM3" in info.filename \
                or "Axe-Fx" in info.filename or "FM3 (" in info.filename:
            continue                     # skip other-device folders and junk
        low = base.lower()
        if low.endswith(".fasbundle"):
            out.append((base, zf.read(info), "bundle"))
        elif low.endswith(".syx"):
            out.append((base, zf.read(info), "syx"))
    return out


def search_local(query: str) -> list:
    """FM9 presets on this machine matching `query`, newest file first.

    Returns dicts {label, raw, kind, source}. A .zip is opened and its FM9
    presets/bundles are pulled out; loose .syx and .fasBundle files match
    directly. Matching is the same all-words-must-appear rule as the Gift
    of Tone catalog, against the file name.
    """
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower())
             if w not in _STOPWORDS]
    if not words:
        return []

    def matches(name: str) -> bool:
        # Substring, or a filename token sharing a 3+ char prefix, so a
        # nickname finds the full name: "luke" -> "Lukather", "petty" ->
        # "Tom Petty". Every query word must connect to something.
        tokens = re.findall(r"[a-z0-9]+", name.lower())
        for w in words:
            if w in name.lower():
                continue
            pre = w[:3]
            if len(w) >= 3 and any(tok.startswith(pre) for tok in tokens):
                continue
            return False
        return True

    hits = []
    for d in local_dirs():
        for f in sorted(d.iterdir(), key=lambda x: -x.stat().st_mtime
                        if x.is_file() else 0):
            if not f.is_file():
                continue
            if not matches(f.name):
                continue
            low = f.name.lower()
            try:
                if low.endswith(".zip"):
                    for label, raw, kind in _fm9_from_zip_bytes(f.read_bytes()):
                        hits.append({"label": label, "raw": raw, "kind": kind,
                                     "source": f.name})
                elif low.endswith((".syx", ".fasbundle")):
                    kind = "bundle" if low.endswith(".fasbundle") else "syx"
                    hits.append({"label": f.name, "raw": f.read_bytes(),
                                 "kind": kind, "source": f.name})
            except OSError:
                continue
    return hits


def parse_local(hits: list) -> tuple:
    """Turn local search hits into (presets, cabs, skipped) like fetch_bundle."""
    from . import bundlefile
    presets, cabs, skipped = [], [], []
    for h in hits:
        try:
            if h["kind"] == "bundle":
                bf = bundlefile.parse(h["raw"])
                presets.append({"name": bf.preset.name, "file": h["label"],
                                "raw": bf.preset_raw,
                                "chunks": bf.preset.chunks})
                for cb in bf.cabs:
                    cabs.append({"label": cb.name, "file": cb.file,
                                 "raw": cb.raw, "chunks": cb.cab.chunks,
                                 "bank": cb.bank, "number": cb.number,
                                 "default_slot": None})
            else:
                pf = presetfile.parse(h["raw"])
                presets.append({"name": pf.name, "file": h["label"],
                                "raw": h["raw"], "chunks": pf.chunks})
        except (presetfile.PresetFileError, Exception) as exc:
            skipped.append(f"{h['label']}: {exc}")
    if not presets and not cabs:
        raise AcquireError("found files but none were FM9 presets: "
                           + ("; ".join(skipped[:3]) if skipped else ""))
    return presets, cabs, skipped

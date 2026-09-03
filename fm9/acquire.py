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

from . import presetfile

GOT_URL = "https://www.fractalaudio.com/gift-of-tone/"

_ZIP_RE = re.compile(
    r'href="(https://www\.fractalaudio\.com/downloads/[^"]+\.zip)"')
_NAME_RE = re.compile(r"FAS-gift(\d\d)-[0-9]+[a-z0-9]*-(.+)\.zip$")

#: Words in an ask that say WHAT DOING, not WHO: stripped before matching.
_STOPWORDS = frozenset(
    "get me the a an tones tone preset presets from gift of got download "
    "grab install fetch load and please for my fm9".split())

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
    """Download a bundle and validate every FM9 preset inside.

    Returns (presets, skipped): presets as {name, file, raw, chunks}; and
    honest notes for everything in the bundle that was not an FM9 preset,
    so "it found 3 of 9 files" never reads as silent loss.
    """
    fetch = fetch or _download
    data = fetch(url)
    candidates: list[tuple[str, bytes]] = []
    if data[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise AcquireError(f"the download is not a readable zip: {exc}")
        for info in zf.infolist():
            base = info.filename.rsplit("/", 1)[-1]
            if not base.lower().endswith(".syx") or base.startswith("._"):
                continue                    # extras and AppleDouble junk
            candidates.append((base, zf.read(info)))
    elif data[:1] == b"\xf0":
        candidates.append((url.rsplit("/", 1)[-1], data))
    else:
        raise AcquireError("the download is neither a zip nor a .syx; "
                           "nothing here to install")
    presets, skipped = [], []
    for base, raw in candidates:
        try:
            pf = presetfile.parse(raw)
        except presetfile.PresetFileError as exc:
            skipped.append(f"{base}: {exc}")
            continue
        presets.append({"name": pf.name, "file": base, "raw": raw,
                        "chunks": pf.chunks})
    if not presets:
        raise AcquireError(
            "the bundle held no FM9 presets. "
            + ("; ".join(skipped[:4]) if skipped else "it was empty"))
    return presets, skipped

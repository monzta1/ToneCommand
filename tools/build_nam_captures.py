#!/usr/bin/env python3
"""Generate config/nam_capture_models.json from TONE3000's own API (#18).

Harvests FACTS ONLY about real NAM Architecture 2 (A2) captures: the id,
title, the capture author's own stated gear identity (`makes`), the creator's
username and whether TONE3000 has verified them, usage signals, licence and
the citable URL. Nothing here is inferred or guessed; a term that returns no
A2 captures contributes nothing, and a capture's `gear_claimed` is always the
author's own words, never a corrected or invented one.

TONE3000 exposes no per-capture accuracy/error metric (checked directly:
`/tones/{id}` and `/tones/{id}/models` carry no such field; only the
aggregate A2 launch announcement publishes one, across 39 captures as a
whole, not per capture). That is recorded in this file's own `warning`
rather than papered over with an invented number.

Usage:
    python tools/build_nam_captures.py [--terms mesa,marshall,...] [--per-term N]

Auth: the TONE3000 Secret Key (t3k_cs_...) as a Bearer credential, read from
env TONE3000_SECRET_KEY or a `TONE3000_SECRET_KEY=` line in the repo's
gitignored .env, the same convention TONECOMMAND_STORE_SLOTS already uses
(fm9/device.py). The key is never printed and never written to this output.

This is a small, honest seed, not the ~30k-entry harvest issue #18 eventually
wants: re-run this script (or widen SEARCH_TERMS) any time to grow it, always
against the live API, never by hand-editing the JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "config" / "nam_capture_models.json"
ENV_FILE = ROOT / ".env"

API = "https://www.tone3000.com/api/v1"

#: Well-known real amps, chosen so a small seed still covers gear players
#: actually search for. Not exhaustive; growing this list is how the seed
#: grows, never by inventing a record outside the API's own response.
SEARCH_TERMS = [
    "mesa boogie mark v", "marshall plexi", "fender twin reverb",
    "vox ac30", "soldano slo", "friedman be-100", "5150",
]

#: This seed stays small and reviewable; widen with --per-term for a bigger
#: pull, always against the live API.
DEFAULT_PER_TERM = 3


def _key() -> str:
    key = os.environ.get("TONE3000_SECRET_KEY", "").strip()
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.strip().startswith("TONE3000_SECRET_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    if not key:
        raise SystemExit(
            "No TONE3000 key. Set TONE3000_SECRET_KEY in the environment or "
            f"in {ENV_FILE} (gitignored).")
    if not key.startswith("t3k_cs_"):
        raise SystemExit(
            "That is not a TONE3000 SECRET key. The publishable key "
            "(t3k_pub_...) is rejected by the API; use the t3k_cs_ one.")
    return key


def api_search(query: str, page_size: int) -> list[dict]:
    url = (f"{API}/tones/search?" +
           urllib.parse.urlencode({"query": query, "page_size": page_size,
                                    "architectures": "a2"}))
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {_key()}",
        "Accept": "application/json",
        "User-Agent": "ToneCommand-local/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")).get("data", [])
    except urllib.error.HTTPError as e:
        raise SystemExit(f"TONE3000 HTTP {e.code} on search {query!r}: "
                          f"{e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"TONE3000 unreachable: {e}")


def provenance_tier(raw: dict) -> str:
    """Weakest-signal-last, exactly as issue #18 asks: an author's own claim
    is the floor, and TONE3000 marking that author verified is the one thing
    that can raise it. Usage counts are a tiebreaker recorded on the record,
    never folded into the tier itself.
    """
    if (raw.get("user") or {}).get("is_verified"):
        return "author_stated_verified_creator"
    return "author_stated"


def shape_record(raw: dict) -> dict:
    """The facts worth keeping from one raw API tone, and nothing else."""
    user = raw.get("user") or {}
    return {
        "title": raw["title"],
        "gear_claimed": [m["name"] for m in (raw.get("makes") or [])],
        "creator": user.get("username", "unknown"),
        "creator_verified": bool(user.get("is_verified")),
        "provenance_tier": provenance_tier(raw),
        "a2_models_count": raw.get("a2_models_count", 0),
        "downloads_count": raw.get("downloads_count", 0),
        "favorites_count": raw.get("favorites_count", 0),
        "license": raw.get("license"),
        "url": raw["url"],
    }


def build(terms: list[str], per_term: int) -> dict:
    captures: dict[str, dict] = {}
    for term in terms:
        for raw in api_search(term, per_term):
            if raw.get("a2_models_count", 0) <= 0:
                continue  # not an A2 capture; this sidecar is A2-only
            captures[str(raw["id"])] = shape_record(raw)
    return {
        "schema_version": 1,
        "device": "none (TONE3000 capture catalog, not a Fractal device roster)",
        "source": (f"TONE3000 API {API}/tones/search, live GET, "
                   f"harvested {datetime.now(timezone.utc).date().isoformat()}"),
        "generated_by": "tools/build_nam_captures.py",
        "keyed_by": "TONE3000 tone id (capture id) as returned by the API, string-keyed",
        "content": ("facts-only record of a real TONE3000 A2 capture: the "
                    "author's own stated gear identity, creator identity and "
                    "verification, usage signals, licence and citation URL"),
        "warning": ("gear_claimed is the capture author's own free-text label, "
                    "not independently verified by ToneCommand. TONE3000 exposes "
                    "no per-capture accuracy/error metric, so provenance here "
                    "rests on author-stated identity, creator verification and "
                    "usage signals only. Ranking captures against each other by "
                    "that evidence is deferred; this sidecar only records "
                    "citable facts for a recipe author to reference directly."),
        "captures": captures,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--terms", default=",".join(SEARCH_TERMS))
    p.add_argument("--per-term", type=int, default=DEFAULT_PER_TERM)
    args = p.parse_args(argv)
    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    blob = build(terms, args.per_term)
    OUT_PATH.write_text(json.dumps(blob, indent=1, sort_keys=True) + "\n")
    print(f"wrote {len(blob['captures'])} real A2 captures to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

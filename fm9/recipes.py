"""Finding and using other people's tones, without needing a GitHub account.

Sharing was wired to open a prefilled GitHub ISSUE, which was wrong three ways
at once: an issue is not a container for a recipe, the tracker would silt up
with them, and it asks a guitarist to learn a developer's tool before they can
give anything back.

The two halves of this are not equally hard, and conflating them was the
mistake:

CONSUMING is the ninety-five percent case and it needs no account at all.
Recipes live in the repository's recipes/ folder, which is public, so the app
reads them straight out of it and browses them in place. Nobody signs in,
nobody clicks through a web UI, nobody learns what a pull request is.

CONTRIBUTING genuinely needs somewhere to put the file. Without paying for
hosting there are exactly two honest paths, and the app offers both rather
than pretending one fits everyone:

    save it and send it     the file lands in your own recipes/ folder and you
                            pass it on however you already talk to people
    open a file PR          for anyone who does use GitHub, prefilled, landing
                            in recipes/ where it belongs and not in the tracker

A hosted endpoint would remove the last of that friction. It would also cost
money every month and need moderating, so it is a decision to take
deliberately rather than a thing to drift into.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

#: Where the shared ones live. Public, so reading needs no credentials.
REPO = os.environ.get("TONECOMMAND_RECIPE_REPO", "monzta1/ToneCommand")
BRANCH = os.environ.get("TONECOMMAND_RECIPE_BRANCH", "main")
_INDEX_TTL = 600.0          # ten minutes; this is a catalogue, not a feed

_cache: dict = {"at": 0.0, "items": None}


def local_dir() -> Path:
    override = os.environ.get("TONECOMMAND_RECIPES_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "recipes"


def _safe_name(name: str) -> str:
    """A filename that cannot walk out of the directory or collide with git."""
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or "").strip().lower()).strip("-")
    return (slug or "untitled")[:64]


def read_local() -> list[dict]:
    out = []
    d = local_dir()
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        if f.name == "index.json":
            continue
        try:
            r = json.loads(f.read_text())
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        r["_source"] = "local"
        r["_file"] = f.name
        out.append(r)
    return out


def fetch_shared(timeout: float = 6.0) -> tuple[list[dict], str | None]:
    """Everything in the repository's recipes/ folder.

    Unauthenticated: the contents API is open for public repositories, and
    reading a shared tone should never ask anyone to sign in to anything.
    Returns (recipes, why_not) so a failure is reported rather than shown as
    an empty catalogue, which would read as "nobody has shared anything".
    """
    now = time.time()
    if _cache["items"] is not None and now - _cache["at"] < _INDEX_TTL:
        return _cache["items"], None
    url = f"https://api.github.com/repos/{REPO}/contents/recipes?ref={BRANCH}"
    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ToneCommand",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            listing = json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            json.JSONDecodeError, ValueError) as e:
        return [], f"could not reach the shared recipes: {e}"

    out = []
    for entry in listing:
        if not entry.get("name", "").endswith(".json"):
            continue
        if entry["name"] == "index.json":
            continue
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(entry["download_url"], headers={
                        "User-Agent": "ToneCommand"}), timeout=timeout) as r:
                rec = json.load(r)
        except Exception:
            continue
        rec["_source"] = "shared"
        rec["_file"] = entry["name"]
        out.append(rec)
    _cache["items"], _cache["at"] = out, now
    return out, None


def save_local(recipe: dict) -> Path:
    """Keep a recipe of your own where the browser can find it."""
    d = local_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{_safe_name(recipe.get('name') or recipe.get('title'))}.json"
    p.write_text(json.dumps(recipe, indent=1))
    return p


def steps_of(recipe: dict) -> list[dict]:
    """The actions, under either of the two names the format has used.

    docs/RECIPES.md writes them as `actions`; the exporter wrote `steps`.
    Reading both is one line and saves every recipe written either way.
    """
    return list(recipe.get("actions") or recipe.get("steps") or [])


def pr_url(recipe: dict) -> str:
    """A prefilled NEW FILE in recipes/, not a new issue.

    GitHub's new-file page takes the path and the content in the query, and
    offers "Propose new file", which forks and opens the pull request without
    the contributor touching git. Two clicks, and it lands where recipes live.
    """
    from urllib.parse import quote
    name = _safe_name(recipe.get("name") or recipe.get("title"))
    body = json.dumps({k: v for k, v in recipe.items()
                       if not k.startswith("_")}, indent=1)
    return (f"https://github.com/{REPO}/new/{BRANCH}"
            f"?filename=recipes/{name}.json&value={quote(body)}")


def firmware_note(tested: str, rig: str) -> str:
    """What to say when a recipe was made on different firmware.

    Names, not ordinals, are what make a recipe portable: a step says
    `type_name: "Brit 800 2204 High"` and resolves through THIS rig's roster,
    so a model that moved position between releases still lands correctly, and
    one that does not exist here is refused rather than silently becoming its
    neighbour.

    That covers the structural risk and not the audible one. Fractal revises
    model voicings between firmware versions, so the same name can be a
    slightly different amp on a different release. No amount of validation can
    see that, and the recipe's own `tested_firmware` is the only signal there
    is. It was being recorded and never shown to anybody.
    """
    tested = (tested or "").strip()
    rig = (rig or "").strip()
    if not tested or not rig or tested == rig:
        return ""
    return (f"made on firmware {tested}, and this rig is on {rig}. Model names "
            f"resolve against your own rosters, so nothing will load the wrong "
            f"block, but Fractal revises voicings between releases and the "
            f"same model can sound different. Trust your ears over the recipe.")

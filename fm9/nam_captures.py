"""The nam_captures grounding sidecar and the recipe tone_target it grounds.

Issue #18, items 1 and 2. A recipe may cite a TONE3000 NAM Architecture 2
(A2) capture as "the sound this build approximates": on an A2-capable device
the capture IS the tone, on the FM9 the recipe's own steps are the grounded
approximation. That citation is only honest if the cited capture is a real,
recorded fact rather than a name someone typed. config/nam_capture_models.json
is the record of which captures are real, harvested from TONE3000's own API
by tools/build_nam_captures.py; this module is the one place that reads it
and the one place that decides whether a citation is grounded.

TONE3000 exposes no per-capture accuracy/error metric (checked directly
against their API; only the aggregate A2 announcement publishes one, across
39 captures as a whole). So a record's provenance rests on three real
signals, weakest last: the capture author's own stated gear identity
(`gear_claimed`), whether TONE3000 has verified that author
(`creator_verified`), and usage (`downloads_count`/`favorites_count`) as a
tiebreaker only. Ranking captures against each other by that evidence is
explicitly deferred; this module only checks that a cited id is one of the
real ones on file.
"""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "nam_capture_models.json"

#: The only source this pass understands. Naming any other invents an
#: integration nothing has built (no-speculative-adapters, ARCHITECTURE.md).
SUPPORTED_SOURCE = "TONE3000"

#: A public recipe field; keep the sub-shape as tight as the top-level one.
TONE_TARGET_KEYS = frozenset({"source", "capture_id", "note"})

#: TONE3000 ids are small integers today; this is a sanity ceiling against a
#: typo or a hostile value, not a claim about their real range.
MAX_CAPTURE_ID = 10_000_000


def load() -> dict[str, dict]:
    """The sidecar's capture records, keyed by TONE3000 tone id as a string."""
    blob = json.loads(CONFIG_PATH.read_text())
    return blob.get("captures", {})


def lookup(capture_id: int) -> dict | None:
    return load().get(str(capture_id))


def validate_tone_target(tone_target: dict) -> str | None:
    """None if `tone_target` is well-formed and cites a real, on-file capture.
    Otherwise the reason, meant to be read by whoever wrote the recipe.
    """
    if not isinstance(tone_target, dict):
        return "tone_target must be an object"
    unknown = set(tone_target) - TONE_TARGET_KEYS
    if unknown:
        return f"tone_target has unknown field(s): {sorted(unknown)}"
    if tone_target.get("source") != SUPPORTED_SOURCE:
        return (f"tone_target.source must be {SUPPORTED_SOURCE!r} "
                f"(got {tone_target.get('source')!r})")
    capture_id = tone_target.get("capture_id")
    if not isinstance(capture_id, int) or isinstance(capture_id, bool) \
            or capture_id <= 0 or capture_id > MAX_CAPTURE_ID:
        return f"tone_target.capture_id must be a positive integer (got {capture_id!r})"
    if lookup(capture_id) is None:
        return (f"tone_target cites TONE3000 capture {capture_id}, which is not in "
                f"{CONFIG_PATH.name}; the AI never invents a citation, so this "
                "recipe cannot be replayed until that capture is harvested for real")
    return None


def describe(capture_id: int) -> str:
    """One line for a human: what the citation actually names, for
    replay_recipe.py to print before anything reaches a device."""
    rec = lookup(capture_id)
    if rec is None:
        return f"TONE3000 capture {capture_id} (ungrounded)"
    gear = ", ".join(rec.get("gear_claimed") or []) or "unspecified gear"
    return f"{rec['title']} ({gear}, by {rec['creator']}) -- {rec['url']}"

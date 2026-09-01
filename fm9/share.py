"""Sharing that cannot lose a recipe, whatever the network is doing.

The requirement came first and the design fell out of it: nothing a person
writes may be lost because a service was unreachable. So the order of
operations is never negotiable.

    1. write the recipe into recipes/          <- durable, local, done
    2. append an outbox entry                  <- durable, local, done
    3. try to send it                          <- may fail, and that is fine

By the time any network call happens the work is already safe on disk and
visible in the app's own browser. A submission that fails is not an error
condition, it is simply an entry that has not been accepted yet, and it stays
in the outbox until a server says it has it. Nothing is ever removed on a
timeout, a 500, or a hopeful guess.

That inverts the usual shape, where a POST is the event and local state is a
cache of it. Here the local file IS the event. The service is a place copies
go, and it can be down for a week without anyone losing a tone.

WHAT GETS COUNTED
-----------------
Transmits, not downloads. The app knows when a recipe actually reached
hardware, which is a far better signal than a fetch, and it is much harder to
inflate by refreshing a page. Uses are queued in the same outbox and flushed
the same way, so a gig with the laptop offline still counts once it is back.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

#: Where copies go. Empty means sharing is local only, which is a perfectly
#: good state and the one a fresh checkout starts in.
def endpoint() -> str:
    """The service URL, from the environment or from `.env`.

    The `.env` fallback is not a convenience. Every other setting in this
    project lives there, the service README says to set this one the same way,
    and reading only `os.environ` meant following those instructions left the
    feature silently dark: recipes queue in the outbox forever and the app
    reports no endpoint, with nothing anywhere saying why. A configuration
    that fails closed AND says nothing is the worst of both.
    """
    raw = os.environ.get("TONECOMMAND_SHARE_URL", "").strip()
    if not raw:
        raw = _from_env_file("TONECOMMAND_SHARE_URL")
    return raw.rstrip("/")


def _env_path() -> Path:
    """The .env this reads. Indirected for the same reason planner._env_path
    is: without it a test that unsets the variable still picks up whatever the
    developer has configured on their own machine, and the suite starts
    depending on the box it runs on. Caught immediately, by a test that
    asserted sharing was local-only and found a live endpoint."""
    return Path(__file__).resolve().parent.parent / ".env"


def _from_env_file(key: str) -> str:
    """One line out of `.env`, quotes and trailing comment removed.

    Deliberately small rather than a dotenv dependency: this project has no
    runtime dependencies it does not need, and the file is ours.
    """
    env_file = _env_path()
    if not env_file.exists():
        return ""
    try:
        lines = env_file.read_text().splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if not line.startswith(f"{key}="):
            continue
        val = line.split("=", 1)[1].strip()
        if val[:1] in ('"', "'"):
            close = val.find(val[0], 1)
            if close != -1:
                return val[1:close]
        if " #" in val:
            val = val.split(" #", 1)[0].strip()
        return val
    return ""


def outbox_path() -> Path:
    override = os.environ.get("TONECOMMAND_OUTBOX", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "outbox.json"


def _read() -> dict:
    p = outbox_path()
    if not p.exists():
        return {"entries": []}
    try:
        got = json.loads(p.read_text())
        return got if isinstance(got, dict) and "entries" in got else {"entries": []}
    except (json.JSONDecodeError, ValueError, OSError):
        # A corrupt outbox must not take the recipes with it. The files in
        # recipes/ are the work; this is only the record of what has been sent.
        return {"entries": []}


def _write(data: dict) -> None:
    p = outbox_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(p)          # atomic: a crash mid-write cannot truncate it


def queue(kind: str, payload: dict) -> dict:
    """Record something to send. Called AFTER the work is already on disk."""
    data = _read()
    entry = {
        "id": uuid.uuid4().hex,
        "kind": kind,                  # "recipe" or "use"
        "payload": payload,
        "queued": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "attempts": 0,
        "last_error": None,
        "accepted": False,
    }
    data["entries"].append(entry)
    _write(data)
    return entry


def pending() -> list[dict]:
    return [e for e in _read()["entries"] if not e.get("accepted")]


def history() -> list[dict]:
    return _read()["entries"]


def forget_accepted(keep: int = 200) -> None:
    """Trim the tail of things a server has confirmed. Pending is never cut."""
    data = _read()
    done = [e for e in data["entries"] if e.get("accepted")]
    live = [e for e in data["entries"] if not e.get("accepted")]
    data["entries"] = live + done[-keep:]
    _write(data)


def sync(timeout: float = 6.0) -> dict:
    """Try to hand over everything waiting. Safe to call as often as you like.

    An entry is marked accepted only on an explicit 2xx. Anything else, of any
    kind, leaves it queued: a recipe that might not have arrived is worth
    sending twice, and losing one is not worth avoiding a duplicate.
    """
    url = endpoint()
    waiting = pending()
    if not url:
        return {"endpoint": None, "pending": len(waiting), "sent": 0,
                "why": "no sharing service configured; recipes stay local"}
    sent, failed, why = 0, 0, None
    data = _read()
    by_id = {e["id"]: e for e in data["entries"]}
    for e in waiting:
        route = "/submit" if e["kind"] == "recipe" else "/used"
        body = json.dumps(e["payload"]).encode()
        req = urllib.request.Request(
            url + route, data=body,
            headers={"Content-Type": "application/json",
                     "User-Agent": "ToneCommand"})
        live = by_id[e["id"]]
        live["attempts"] = live.get("attempts", 0) + 1
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if 200 <= r.status < 300:
                    live["accepted"] = True
                    live["last_error"] = None
                    sent += 1
                    continue
                live["last_error"] = f"HTTP {r.status}"
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as ex:
            live["last_error"] = str(ex)
        failed += 1
        why = why or live["last_error"]
    _write(data)
    return {"endpoint": url, "pending": len(pending()), "sent": sent,
            "failed": failed, "why": why}


def fetch_stats(timeout: float = 4.0) -> tuple[dict, str | None]:
    """How often each recipe has actually been played. Optional, by design.

    The browser must render perfectly without this. A ranking is a nicety; a
    catalogue that will not load because a counter is down is a broken tool.
    """
    url = endpoint()
    if not url:
        return {}, None
    try:
        req = urllib.request.Request(url + "/stats",
                                     headers={"User-Agent": "ToneCommand"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            got = json.load(r)
        return (got.get("stats") or {}), None
    except Exception as e:
        return {}, str(e)

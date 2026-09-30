"""Test runs the admin page shows: what kinds exist, how to start one, and
what is happening right now.

WHY THIS IS A MODULE AND NOT SERVER CODE. Starting a subprocess from an HTTP
route is the sort of thing that deserves to be read on its own. Everything
that decides WHAT may run lives here, in one table, and the route does
nothing but look a name up in it. There is no path by which a caller's
string reaches a shell: `KINDS` holds fixed argument lists, the route can
only name a key, and every launch is `subprocess.Popen` with a list and no
shell.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / ".testruns"
KEEP = 25                      # runs retained on disk


@dataclass(frozen=True)
class Kind:
    key: str
    label: str
    blurb: str
    args: tuple = ()
    #: minutes, from observed runs. Shown so a reader knows what they are in
    #: for before they press the button, not used for anything else.
    typical_minutes: float = 0.0
    coverage: bool = False
    #: Spread across cores with pytest-xdist. Worth it only for the long
    #: runs: on 35 tests the workers cost more to start than they save, and
    #: CI has run the full suite this way for months (4m 54s against 15m 32s
    #: serial, measured 2026-09-29).
    parallel: bool = False


#: The only things that may be started. A caller names a key; nothing else
#: reaches the command line.
KINDS: dict[str, Kind] = {
    "sanity": Kind(
        "sanity", "Sanity",
        "The three files CLAUDE.md requires before every commit.",
        ("tests/test_device_handle.py", "tests/test_capability_gates.py",
         "tests/test_ui_warning.py"),
        typical_minutes=1.0, parallel=True),
    "regression": Kind(
        "regression", "Full regression", "Every test in the suite.",
        (), typical_minutes=5.0, parallel=True),
    "coverage": Kind(
        "coverage", "Coverage",
        "The full suite with line coverage over fm9, devices and server.",
        ("--cov=fm9", "--cov=devices", "--cov=server",
         "--cov-report=json:coverage.json", "--cov-report=term:skip-covered"),
        typical_minutes=8.0, coverage=True, parallel=True),
    "devices": Kind(
        "devices", "Devices",
        "Every device adapter: FM9, HeadRush, ToneX and the BOSS IR-2.",
        ("tests/test_ir2_adapter.py", "tests/test_ir2_protocol.py",
         "tests/test_tonex_adapter.py", "tests/test_device_picker.py",
         "tests/test_device_handle.py"),
        typical_minutes=1.5, parallel=True),
    "ui": Kind(
        "ui", "Interface",
        "The page parses, the warnings render, the picker behaves.",
        ("tests/test_ui_syntax.py", "tests/test_ui_warning.py",
         "tests/test_device_picker.py"),
        typical_minutes=1.0),
}


class RunRefused(RuntimeError):
    """One line, written for the person reading the page."""


def _own_run_id() -> str | None:
    """The run this process is part of, if any.

    A test run exports TONECOMMAND_RUN_ID, and everything it spawns inherits
    it, so a request arriving from inside a suite carries it. The server
    started from a terminal does not. This is what lets a run refuse to act
    on itself.
    """
    return os.environ.get("TONECOMMAND_RUN_ID") or None


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def runs() -> list[dict]:
    """Every run on disk, newest first. A run whose process died without
    finishing is reported as stalled rather than left looking live: a
    progress bar frozen at 40 percent with no explanation is worse than
    saying so."""
    if not RUNS_DIR.is_dir():
        return []
    out = []
    for f in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        rec = _read(f)
        if not rec:
            continue
        if rec.get("state") in ("running", "collecting"):
            pid = rec.get("pid")
            if pid and not _alive(int(pid)):
                rec["state"] = "stalled"
                rec["stalled_reason"] = (
                    "the run's process is gone and it never reported an "
                    "ending; what you see is where it stopped")
        out.append(rec)
    return out[:KEEP]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True             # someone else's process, but it exists
    except OSError:
        return False
    return True


def current() -> dict | None:
    for rec in runs():
        if rec.get("state") in ("running", "collecting"):
            return rec
    return None


def start(kind_key: str, extra_env: dict | None = None) -> dict:
    """Launch one run in the background and return its first state."""
    kind = KINDS.get(kind_key)
    if kind is None:
        raise RunRefused(f"there is no test run called {kind_key!r}; "
                         f"there is {', '.join(sorted(KINDS))}")
    own = _own_run_id()
    if own:
        raise RunRefused(
            f"this request came from inside test run {own}, which would be "
            "starting a suite from within a suite. Refused.")
    live = current()
    if live is not None:
        raise RunRefused(
            f"{KINDS.get(live.get('kind'), kind).label} is already running "
            f"({live.get('percent', 0)} percent done). Two suites at once "
            "make each other slower and make timing-sensitive tests lie; "
            "wait for it or stop it first.")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{kind_key}"
    env = dict(os.environ)
    env.update({"TONECOMMAND_RUN_ID": run_id, "TONECOMMAND_RUN_KIND": kind_key,
                "TONECOMMAND_SIM": "1", "PYTHONUNBUFFERED": "1"})
    env.update(extra_env or {})
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "tools.pytest_progress",
           *(("-n", "auto") if kind.parallel else ()), *kind.args]
    log = RUNS_DIR / f"{run_id}.log"
    with open(log, "w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=fh,
                                stderr=subprocess.STDOUT)
    # The plugin owns the file from here. This seeds it so the page has
    # something the instant the button is pressed, and records the pid so a
    # dead run can be told from a slow one.
    seed = {"id": run_id, "kind": kind_key, "state": "collecting",
            "started": time.time(), "finished": None, "total": 0, "done": 0,
            "passed": 0, "failed": 0, "skipped": 0, "percent": 0.0,
            "elapsed": 0.0, "eta": None, "current": None, "failures": [],
            "exit_status": None, "coverage": None, "pid": proc.pid}
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(seed), encoding="utf-8")
    return seed


def stop() -> dict:
    """Stop the live run. SIGTERM, never SIGKILL: pytest gets to write its
    own ending, and the plugin's last state stays on disk so the page shows
    where it stopped rather than going blank."""
    live = current()
    if live is None:
        raise RunRefused("nothing is running")
    # A run must not be able to stop itself. The capability-gate suite drives
    # every route, this one included, so without this a regression started
    # from the console killed itself partway through and reported "stopped on
    # request" with nobody having asked. Observed 2026-09-29 at 199 of 2534.
    own = _own_run_id()
    if own and own == live.get("id"):
        raise RunRefused(
            f"run {own} is the one making this request; a suite cannot stop "
            "itself. Refused, and nothing was signalled.")
    pid = live.get("pid")
    if not pid:
        raise RunRefused("that run did not record a process id, so it cannot "
                         "be stopped from here")
    try:
        os.kill(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass                      # already gone; the state below still holds
    except OSError as e:
        raise RunRefused(f"could not stop it: {e}")
    path = RUNS_DIR / f"{live['id']}.json"
    rec = _read(path) or live
    rec["state"] = "stopped"
    rec["finished"] = time.time()
    rec["current"] = None
    rec["stalled_reason"] = "stopped on request"
    try:
        path.write_text(json.dumps(rec), encoding="utf-8")
    except OSError:
        pass
    return rec


def prune(keep: int = KEEP) -> int:
    """Drop the oldest runs. Returns how many were removed."""
    if not RUNS_DIR.is_dir():
        return 0
    files = sorted(RUNS_DIR.glob("*.json"), reverse=True)
    removed = 0
    for f in files[keep:]:
        for path in (f, f.with_suffix(".log")):
            try:
                path.unlink()
                removed += 1 if path is f else 0
            except OSError:
                pass
    return removed


def kinds() -> list[dict]:
    return [{"key": k.key, "label": k.label, "blurb": k.blurb,
             "typical_minutes": k.typical_minutes, "coverage": k.coverage,
             "parallel": k.parallel}
            for k in KINDS.values()]


# --- continuous integration ------------------------------------------------
#
# Read through the `gh` CLI, which is already authenticated on a maintainer's
# machine and absent on everyone else's. Absent is not an error: the console
# says so in one line rather than showing an empty table that looks like a
# green board.

_CI_CACHE: dict = {"at": 0.0, "value": None}
CI_TTL = 60.0             # the page polls every second while a run is live


def ci_status(ttl: float = CI_TTL) -> dict:
    now = time.time()
    if _CI_CACHE["value"] is not None and now - _CI_CACHE["at"] < ttl:
        return _CI_CACHE["value"]
    value = _ci_fetch()
    _CI_CACHE.update({"at": now, "value": value})
    return value


def _ci_fetch() -> dict:
    import shutil
    gh = shutil.which("gh")
    if gh is None:
        return {"available": False,
                "reason": "the GitHub CLI is not installed here, so CI status "
                          "cannot be read. Everything else on this page is local."}
    try:
        proc = subprocess.run(
            [gh, "run", "list", "--limit", "8", "--json",
             "displayTitle,workflowName,headBranch,conclusion,status,createdAt,url"],
            cwd=ROOT, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return {"available": False, "reason": f"could not run the GitHub CLI: {e}"}
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return {"available": False,
                "reason": detail[-1][:200] if detail else
                          "the GitHub CLI refused; is it signed in?"}
    try:
        rows = json.loads(proc.stdout or "[]")
    except ValueError:
        return {"available": False, "reason": "the GitHub CLI returned "
                                              "something that was not JSON"}
    out = []
    for r in rows:
        out.append({
            "name": r.get("workflowName") or r.get("displayTitle") or "workflow",
            "branch": r.get("headBranch"),
            "conclusion": r.get("conclusion") or None,
            "status": r.get("status"),
            "at": _iso_to_epoch(r.get("createdAt")),
            "url": r.get("url"),
        })
    return {"available": True, "runs": out}


def _iso_to_epoch(s: str | None) -> float | None:
    if not s:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def latest_coverage(recs: list[dict] | None = None) -> dict | None:
    """The most recent run that actually measured coverage. A number from
    three days ago is still a fact, as long as the page says when."""
    for rec in (recs if recs is not None else runs()):
        cov = rec.get("coverage")
        if cov:
            out = dict(cov)
            out["at"] = rec.get("finished") or rec.get("started")
            out["from_kind"] = KINDS[rec["kind"]].label if rec.get("kind") in KINDS \
                else rec.get("kind")
            return out
    return None

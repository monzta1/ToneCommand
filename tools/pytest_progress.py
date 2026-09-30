"""A pytest plugin that publishes live progress as JSON.

WHY. Watching a suite meant watching dots in a terminal, which tells you
nothing useful while it runs: not how far along it is, not what is failing,
not how long is left. This writes a small JSON file after every test, so
something else can render it while the run is still going.

It is deliberately dumb. It holds no lock, keeps nothing in memory but
counters, and writes atomically (temp file then `os.replace`), so a reader
either sees the previous state or the next one and never a half-written
file. A crashed run leaves its last written state behind, which is the
useful thing to look at rather than a gap.

Used as `-p tools.pytest_progress` with TONECOMMAND_RUN_ID and
TONECOMMAND_RUN_KIND in the environment. Without TONECOMMAND_RUN_ID it does
nothing at all, so it is inert for anyone running pytest normally.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent.parent / ".testruns"

#: Lines pytest adds that are advice to the reader, not the defect.
NOISE = frozenset({"Use -v to get more diff", "Use -v to get the full diff",
                   "assert False", "Full diff:"})


def _now() -> float:
    return time.time()


class ProgressPlugin:
    def __init__(self, run_id: str, kind: str, path: Path):
        self.path = path
        self.state = {
            "id": run_id,
            "kind": kind,
            # Carried on every write, not just the seed. Without it the file
            # the plugin writes has no process to check and a killed run
            # reads as live forever.
            "pid": os.getpid(),
            "state": "collecting",
            "started": _now(),
            "finished": None,
            "total": 0,
            "done": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "current": None,
            "failures": [],
            "exit_status": None,
            "coverage": None,
        }
        self._flush()

    # --- lifecycle ------------------------------------------------------

    def pytest_collection_finish(self, session):
        # Serial runs only. Under -n auto the controller collects nothing of
        # its own and this fires with an empty list, which is why the total
        # also comes from the xdist hook below. Without that, every parallel
        # run showed 0 percent forever: the counter moved and the bar did not.
        if session.items:
            self.state["total"] = len(session.items)
        self.state["state"] = "running"
        self._flush()

    def pytest_xdist_node_collection_finished(self, node, ids):
        """Every worker collects the same full set, so the first one to
        report gives the total. Later workers must not add to it."""
        if ids and not self.state["total"]:
            self.state["total"] = len(ids)
            self.state["state"] = "running"
            self._flush()

    def pytest_runtest_logstart(self, nodeid, location):
        self.state["current"] = nodeid
        self._flush()

    def pytest_runtest_logreport(self, report):
        # A test is counted once. 'call' is the real outcome; a setup or
        # teardown that fails never reaches 'call', so those count too or a
        # broken fixture would silently shrink the total.
        if report.when == "call":
            if report.passed:
                self.state["passed"] += 1
            elif report.failed:
                self.state["failed"] += 1
                self._record_failure(report)
            elif report.skipped:
                self.state["skipped"] += 1
        elif report.when in ("setup", "teardown") and report.failed:
            self.state["failed"] += 1
            self._record_failure(report)
        elif report.when == "setup" and report.skipped:
            self.state["skipped"] += 1
        else:
            return
        self.state["done"] = (self.state["passed"] + self.state["failed"]
                              + self.state["skipped"])
        self._flush()

    def pytest_sessionfinish(self, session, exitstatus):
        self.state["finished"] = _now()
        self.state["exit_status"] = int(exitstatus)
        self.state["current"] = None
        if self.state["state"] != "error":
            self.state["state"] = "passed" if int(exitstatus) == 0 else "failed"
        self._read_coverage()
        self._flush()

    # --- helpers --------------------------------------------------------

    def _record_failure(self, report):
        if len(self.state["failures"]) >= 50:
            return                      # a wall of failures helps nobody
        text = str(getattr(report, "longreprtext", "") or report.longrepr or "")
        # The FIRST "E " line is the assertion; the last ones are pytest's own
        # advice ("Use -v to get more diff"), which told a reader nothing and
        # was what this showed until someone looked at the rendered page.
        line = ""
        for candidate in text.strip().splitlines():
            stripped = candidate.strip()
            if stripped.startswith("E ") and stripped[2:].strip() not in NOISE:
                line = stripped[2:].strip()
                break
        self.state["failures"].append({
            "nodeid": report.nodeid,
            "when": report.when,
            "message": line[:300] or text.strip().splitlines()[-1][:300] if text.strip() else "",
        })

    def _read_coverage(self):
        """coverage.json if the run was asked for one. Absent is not an
        error: most runs are not coverage runs."""
        f = RUNS_DIR.parent / "coverage.json"
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        totals = data.get("totals") or {}
        pct = totals.get("percent_covered")
        if pct is None:
            return
        self.state["coverage"] = {
            "percent": round(float(pct), 2),
            "covered": totals.get("covered_lines"),
            "missing": totals.get("missing_lines"),
            "files": len(data.get("files") or {}),
        }

    def _flush(self):
        self.state["elapsed"] = round(
            (self.state["finished"] or _now()) - self.state["started"], 2)
        done, total = self.state["done"], self.state["total"]
        self.state["percent"] = round(100.0 * done / total, 1) if total else 0.0
        # Remaining time from the rate so far. Honest about being an estimate
        # and absent until there is enough to estimate from.
        if done >= 5 and total and self.state["elapsed"] > 0 and done < total:
            rate = done / self.state["elapsed"]
            self.state["eta"] = round((total - done) / rate, 1) if rate else None
        else:
            self.state["eta"] = None
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.state), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass          # never fail a test run over its own telemetry


def pytest_configure(config):
    run_id = os.environ.get("TONECOMMAND_RUN_ID")
    if not run_id:
        return                       # inert for an ordinary pytest run
    # Under -n auto this hook runs in every worker as well as the controller.
    # Workers must not register: they would all write the same file, each
    # with its own slice of the tests, and the page would show whichever
    # wrote last. The controller receives every worker's reports, so it alone
    # has the whole picture.
    if hasattr(config, "workerinput"):
        return
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    kind = os.environ.get("TONECOMMAND_RUN_KIND", "custom")
    plugin = ProgressPlugin(run_id, kind, RUNS_DIR / f"{run_id}.json")
    config.pluginmanager.register(plugin, "tonecommand_progress")

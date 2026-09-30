"""The test console: what may be started, and what must never be.

The two guards here were both earned. A regression run started from the
console killed itself at 199 of 2534 tests, because the capability-gate
suite drives every registered route and one of them is "stop the running
suite". The run found itself and sent itself SIGTERM. The log showed the
xdist workers losing their controller mid-run, and the page reported
"stopped on request" with nobody having asked.
"""
import json
import os

import pytest

from fm9 import test_runs as tr


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "RUNS_DIR", tmp_path)
    monkeypatch.delenv("TONECOMMAND_RUN_ID", raising=False)
    return tmp_path


def _write(dirpath, run_id, **over):
    rec = {"id": run_id, "kind": "regression", "state": "running",
           "started": 1.0, "finished": None, "total": 10, "done": 1,
           "passed": 1, "failed": 0, "skipped": 0, "percent": 10.0,
           "pid": os.getpid(), "failures": []}
    rec.update(over)
    (dirpath / f"{run_id}.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


# --- what may be started --------------------------------------------------

def test_only_named_kinds_can_be_started(runs_dir):
    """A caller names a key. Nothing a caller types reaches a command line."""
    for bad in ("rm -rf /", "", "tests/; echo hi", "regression; id"):
        with pytest.raises(tr.RunRefused, match="no test run called"):
            tr.start(bad)


def test_every_kind_carries_a_fixed_argument_list():
    for kind in tr.KINDS.values():
        assert isinstance(kind.args, tuple)
        assert all(isinstance(a, str) for a in kind.args)


def test_a_second_run_is_refused_while_one_is_live(runs_dir):
    _write(runs_dir, "20260101-000000-regression")
    with pytest.raises(tr.RunRefused, match="already running"):
        tr.start("sanity")


# --- the guards a real failure taught us ----------------------------------

def test_a_suite_cannot_start_another_suite(runs_dir, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_RUN_ID", "20260101-000000-regression")
    with pytest.raises(tr.RunRefused, match="from inside test run"):
        tr.start("sanity")


def test_a_suite_cannot_stop_itself(runs_dir, monkeypatch):
    """The exact defect: the capability-gate table drives POST
    /api/tests/stop, so a run started from the console reached this and
    killed itself at 199 of 2534."""
    run_id = "20260101-000000-regression"
    _write(runs_dir, run_id)
    monkeypatch.setenv("TONECOMMAND_RUN_ID", run_id)
    with pytest.raises(tr.RunRefused, match="cannot stop itself"):
        tr.stop()
    # and nothing was signalled: the record is untouched
    rec = json.loads((runs_dir / f"{run_id}.json").read_text(encoding="utf-8"))
    assert rec["state"] == "running"


def test_a_suite_may_still_stop_a_different_run(runs_dir, monkeypatch):
    """The guard is about identity, not about being inside a run at all.

    The run has to look alive for there to be anything to stop, and the
    signal is intercepted: a test that really sent SIGTERM would be sending
    it to whatever now owns that pid.
    """
    _write(runs_dir, "20260101-000000-regression", pid=424242)
    monkeypatch.setattr(tr, "_alive", lambda pid: True)
    signalled = []
    monkeypatch.setattr(tr.os, "kill", lambda pid, sig: signalled.append((pid, sig)))
    monkeypatch.setenv("TONECOMMAND_RUN_ID", "some-other-run")
    rec = tr.stop()
    assert rec["state"] == "stopped"
    assert signalled == [(424242, tr.signal.SIGTERM)], "SIGTERM, never SIGKILL"


def test_stopping_nothing_says_so(runs_dir):
    with pytest.raises(tr.RunRefused, match="nothing is running"):
        tr.stop()


# --- honesty about a run that died ----------------------------------------

def test_a_run_whose_process_is_gone_reads_as_stalled_not_live(runs_dir):
    """A progress bar frozen at 40 percent with no explanation is worse than
    saying the process went away."""
    _write(runs_dir, "20260101-000000-regression", pid=10**9)
    rec = tr.runs()[0]
    assert rec["state"] == "stalled"
    assert "process is gone" in rec["stalled_reason"]
    assert tr.current() is None


def test_the_pid_survives_every_write_or_a_dead_run_looks_live():
    """The plugin overwrites the seed record, so it has to carry the pid
    itself; without it the stall check has nothing to check."""
    src = (tr.ROOT / "tools" / "pytest_progress.py").read_text(encoding="utf-8")
    assert '"pid": os.getpid(),' in src


def test_workers_do_not_register_the_plugin():
    """Under -n auto this hook runs in every worker; all of them writing the
    same file made the page show whichever wrote last."""
    src = (tr.ROOT / "tools" / "pytest_progress.py").read_text(encoding="utf-8")
    assert 'hasattr(config, "workerinput")' in src


def test_the_long_kinds_run_in_parallel_and_the_short_ones_do_not():
    assert tr.KINDS["regression"].parallel and tr.KINDS["coverage"].parallel
    assert not tr.KINDS["ui"].parallel

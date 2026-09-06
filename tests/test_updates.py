"""Version awareness and the guarded one-click updater.

The app should always be able to say what it is running and whether GitHub is
ahead, and the updater must never touch a checkout it cannot update safely
(dirty tree, wrong branch) or run during a gig.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import updates


def test_current_version_is_reported():
    v = updates.current_version()
    assert v and isinstance(v, str)


@pytest.mark.parametrize("latest,current,newer", [
    ("1.2.0", "1.1.0", True),
    ("1.1.0", "1.1.0", False),
    ("1.9.0", "1.10.0", False),   # numeric, not string, comparison
    ("v2.0.0", "1.1.0", True),    # a leading v never breaks it
    ("1.1.0", "unknown", False),  # unknown never claims stale
    ("", "1.1.0", False),
])
def test_is_newer_is_semver_aware(latest, current, newer):
    assert updates.is_newer(latest, current) is newer


def test_offline_check_returns_none_not_an_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)
    updates._cache["data"] = None
    updates._cache["at"] = 0
    assert updates.latest_release(Path("."), force=True) is None


def test_the_version_endpoint_reports_current_and_capability(monkeypatch):
    monkeypatch.setattr(updates, "latest_release", lambda *a, **k: None)
    d = TestClient(server.app).get("/api/version").json()
    assert d["current"] == updates.current_version()
    assert "update_available" in d and "can_update" in d
    assert d["commands"] and d["commands_windows"]


def test_update_is_blocked_during_a_gig(monkeypatch):
    monkeypatch.setitem(server._gig_mode, "on", True)
    r = TestClient(server.app).post("/api/update")
    assert r.status_code == 423
    monkeypatch.setitem(server._gig_mode, "on", False)


def test_update_refuses_a_dirty_or_wrong_branch_checkout(monkeypatch):
    # never pull over local work
    monkeypatch.setattr(updates, "repo_state",
                        lambda root: {"git": True, "branch": "main", "clean": False})
    ok, why = updates.can_auto_update(Path("."))
    assert ok is False and "local changes" in why
    # never run git pull when it cannot
    called = {"pull": False}
    monkeypatch.setattr(updates.subprocess, "run",
                        lambda *a, **k: called.__setitem__("pull", True))
    res = updates.run_update(Path("."))
    assert res["ok"] is False and called["pull"] is False

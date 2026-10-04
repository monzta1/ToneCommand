"""Epic H (#106): #107 local secret-scrubbed logging, #108 voluntary share.
"""
from __future__ import annotations

import inspect
import json
import time

from fm9 import diagnostics as diag


# --- #107: scrubbing -------------------------------------------------------

def test_scrub_redacts_known_secret_patterns():
    assert diag.REDACTED in diag.scrub_text("key is sk-ant-api03-abcDEF12345xyz")
    assert diag.REDACTED in diag.scrub_text("token sk-abcdefghijklmnopqrstuvwx")
    assert diag.REDACTED in diag.scrub_text("Authorization: Bearer abc123.def456")
    scrubbed = diag.scrub_text("ANTHROPIC_API_KEY=sk-ant-verysecretvalue123")
    assert "sk-ant-verysecretvalue123" not in scrubbed
    assert "ANTHROPIC_API_KEY" in scrubbed, "the key NAME is fine to keep, only the value is secret"


def test_scrub_leaves_ordinary_text_alone():
    text = "the lead scene gain 7.8 was below the rhythm's 6.8"
    assert diag.scrub_text(text) == text


def test_scrub_recurses_through_dicts_and_lists():
    obj = {"msg": "using PLANNER_API_KEY=sk-abcdefghijklmnopqrstuvwx now",
           "nested": {"a": ["fine", "Bearer supersecrettoken123"]}}
    out = diag.scrub(obj)
    assert diag.REDACTED in out["msg"]
    assert diag.REDACTED in out["nested"]["a"][1]
    assert out["nested"]["a"][0] == "fine"


# --- #107: local structured log, scoped and expiring -----------------------

def test_local_log_is_structured_scrubbed_and_expires(tmp_path):
    path = tmp_path / "diag.jsonl"
    diag.log_error("planner", "backend failed with sk-ant-api03-realsecret999",
                    path=path, backend="cli")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["scope"] == "planner"
    assert "realsecret999" not in entry["message"]
    assert entry["context"]["backend"] == "cli"
    assert "ts" in entry

    # an old entry is pruned on the next write
    old = {"ts": time.time() - (diag.RETENTION_DAYS + 1) * 86400,
           "scope": "old", "message": "stale", "context": {}}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(old) + "\n")
    diag.log_error("planner", "a second, fresher error", path=path)
    remaining = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert all(e["scope"] != "old" for e in remaining), "expired entry must be pruned"
    assert any(e["message"] == "a second, fresher error" for e in remaining)


def test_prune_expired_is_safe_on_a_missing_file(tmp_path):
    assert diag.prune_expired(path=tmp_path / "nope.jsonl") == 0


def test_read_recent_filters_by_scope_and_orders_newest_first(tmp_path):
    path = tmp_path / "diag.jsonl"
    diag.log_error("planner", "first", path=path)
    diag.log_error("server", "second", path=path)
    diag.log_error("planner", "third", path=path)
    recent = diag.read_recent(scope="planner", path=path)
    assert [e["message"] for e in recent] == ["third", "first"]


def test_diagnostics_module_makes_no_network_calls():
    """Issue #107's AC: nothing is uploaded to any server by default. The
    whole module must be structurally incapable of a network call, not just
    unconfigured to make one."""
    src = inspect.getsource(diag)
    for forbidden in ("requests", "httpx", "urllib.request", "socket",
                       "http.client", "aiohttp", "fetch("):
        assert forbidden not in src, forbidden


# --- #108: voluntary share package ------------------------------------------

def test_share_package_is_scrubbed_and_never_sent_automatically(tmp_path):
    path = tmp_path / "diag.jsonl"
    diag.log_error("planner", "leaked sk-ant-api03-shouldnotship1234", path=path)
    pkg = diag.package_for_sharing(path=path)
    assert "shouldnotship1234" not in pkg["body"]
    assert "shouldnotship1234" not in pkg["title"]
    assert pkg["url"].startswith("https://github.com/monzta1/ToneCommand/issues/new")
    assert pkg["entry_count"] == 1

    # package_for_sharing must not itself perform any network I/O - it
    # returns text and a URL for the player to open, nothing more.
    src = inspect.getsource(diag.package_for_sharing)
    for forbidden in ("requests", "httpx", "urlopen", "socket", ".post(", "urlretrieve"):
        assert forbidden not in src, forbidden


def test_share_package_with_no_entries_is_still_reviewable(tmp_path):
    pkg = diag.package_for_sharing(path=tmp_path / "empty.jsonl")
    assert pkg["entry_count"] == 0
    assert "no local diagnostics" in pkg["body"].lower()


def test_share_package_can_be_scoped_to_one_subsystem(tmp_path):
    path = tmp_path / "diag.jsonl"
    diag.log_error("planner", "planner issue", path=path)
    diag.log_error("server", "server issue", path=path)
    pkg = diag.package_for_sharing(scope="planner", path=path)
    assert pkg["entry_count"] == 1
    assert "planner issue" in pkg["body"]
    assert "server issue" not in pkg["body"]


# --- #107: the logger is actually wired into real error paths --------------
# A working scrub/log/share mechanism nobody's code calls is not "errors are
# logged locally" - it is unused infrastructure. These prove server.py's two
# planner-failure paths (the ordinary and streaming/describe entry points)
# actually call it, not just that the module works in isolation.

def test_a_planner_failure_in_plan_for_is_logged(monkeypatch):
    import server

    def _boom(*a, **kw):
        raise RuntimeError("simulated planner crash")
    monkeypatch.setattr(server.planner, "plan", _boom)

    calls = []
    monkeypatch.setattr(server.diagnostics, "log_error",
                        lambda scope, msg, **kw: calls.append((scope, msg)))

    out = server._plan_for(server.PromptBody(prompt="build me a rig"))
    assert "error" in out and "simulated planner crash" in out["error"]
    assert calls and calls[0][0] == "planner"
    assert "simulated planner crash" in calls[0][1]


def test_a_planner_failure_in_describe_build_for_is_logged(monkeypatch):
    import server

    def _boom(*a, **kw):
        raise RuntimeError("simulated describe crash")
    monkeypatch.setattr(server.planner, "plan", _boom)

    calls = []
    monkeypatch.setattr(server.diagnostics, "log_error",
                        lambda scope, msg, **kw: calls.append((scope, msg)))

    out = server._describe_build_for(server.BuildBody(spec={"style": "modern metal"}))
    assert "error" in out
    assert calls and calls[0][0] == "planner"
    assert "simulated describe crash" in calls[0][1]


# --- #108: the share package route and the two-click UI -------------------
# Sharing is the player's action. The route returns text and a URL and makes
# no request of any kind; the settings drawer shows the whole scrubbed body
# before a second, separate button (the only opener) is even on screen.

import re
import socket
import urllib.request
import webbrowser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    import server
    from fm9.sim import SimFM9
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


def _no_network(monkeypatch):
    calls = []

    def _refuse(name):
        def _f(*a, **kw):
            calls.append(name)
            raise AssertionError(f"{name} must not be called by the share route")
        return _f
    monkeypatch.setattr(urllib.request, "urlopen", _refuse("urlopen"))
    monkeypatch.setattr(webbrowser, "open", _refuse("webbrowser.open"))
    monkeypatch.setattr(socket, "create_connection", _refuse("create_connection"))
    return calls


def _route_log_at(monkeypatch, tmp_path):
    """Point the route's packager at a temp log, never the developer's real
    ~/.tonecommand file. The real function still runs; only its path moves."""
    import server
    log = tmp_path / "diag.jsonl"
    real = diag.package_for_sharing
    monkeypatch.setattr(server.diagnostics, "package_for_sharing",
                        lambda scope=None, limit=10, path=None, note="":
                            real(scope=scope, limit=limit, path=log, note=note))
    return log


def test_share_package_route_returns_scrubbed_package_without_any_network(
        client, monkeypatch, tmp_path):
    log = _route_log_at(monkeypatch, tmp_path)
    fake_key = "sk-ant-" + "A1b2C3d4E5" * 4
    assert len(fake_key) == len("sk-ant-") + 40
    diag.log_error("planner", f"auth failed with key {fake_key}", path=log)
    calls = _no_network(monkeypatch)

    r = client.get("/api/diagnostics/share-package")
    assert r.status_code == 200
    d = r.json()
    assert set(d) == {"title", "body", "url", "entries"}
    assert d["entries"] == 1
    assert "auth failed with key" in d["body"]
    assert fake_key not in d["body"]
    assert fake_key not in d["url"]
    assert diag.REDACTED in d["body"]
    assert d["url"].startswith(f"https://github.com/{diag.REPO}/issues/new?")
    assert calls == []


def test_share_package_route_respects_scope(client, monkeypatch, tmp_path):
    log = _route_log_at(monkeypatch, tmp_path)
    diag.log_error("planner", "planner issue", path=log)
    diag.log_error("server", "server issue", path=log)
    calls = _no_network(monkeypatch)
    d = client.get("/api/diagnostics/share-package?scope=planner").json()
    assert d["entries"] == 1
    assert "planner issue" in d["body"]
    assert "server issue" not in d["body"]
    assert calls == []


def _js_function_body(src: str, name: str) -> str:
    """The text between the braces of `function NAME(` (async or not),
    found by counting braces so nested blocks stay inside."""
    m = re.search(r"(?:async\s+)?function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", src)
    assert m, f"function {name} not found in the inline script"
    i = m.end()
    depth = 1
    while depth:
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return src[m.end():i - 1]


def _inline_script() -> str:
    return "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                               UI, flags=re.S))


def test_settings_drawer_has_the_share_action_elements():
    drawer = UI[UI.index('id="drawer-settings"'):UI.index('id="audpop"')]
    for el in ("shareerrreview", "shareerrpreview", "shareerrtitle",
               "shareerrbody", "shareerrcount", "shareerropen"):
        assert f'id="{el}"' in drawer, el
    # the opener lives inside the preview block, which starts hidden, so it
    # is not on screen until the review step has rendered
    preview = drawer[drawer.index('id="shareerrpreview"'):]
    assert preview.startswith('id="shareerrpreview" hidden')
    assert 'id="shareerropen"' in preview


def test_first_click_only_fetches_and_never_opens():
    body = _js_function_body(_inline_script(), "reviewShareError")
    assert "fetch(" in body
    assert "/api/diagnostics/share-package" in body
    assert "window.open" not in body
    assert "location.href" not in body


def test_second_click_is_the_only_opener_of_the_package_url():
    js = _inline_script()
    body = _js_function_body(js, "openShareError")
    assert "window.open(shareErrPkg.url, '_blank', 'noopener')" in body
    assert "fetch(" not in body
    assert js.count("window.open(shareErrPkg.url") == 1
    assert "$('shareerrreview').onclick = reviewShareError;" in js
    assert "$('shareerropen').onclick = openShareError;" in js

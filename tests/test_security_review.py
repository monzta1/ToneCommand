"""Fixes from an independent security review of 1.6.7 (#340).

Each test pins one finding so it cannot quietly come back.
"""
import os

import pytest

from fm9 import ai_settings, planner


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_AI_SETTINGS", str(tmp_path / "ai_settings.json"))
    before = {n: os.environ.get(n) for n in ai_settings._MANAGED}
    for n in ai_settings._MANAGED:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(ai_settings, "_APPLIED", {})
    yield tmp_path
    for n, v in before.items():
        if v is None:
            os.environ.pop(n, None)
        else:
            os.environ[n] = v


# --- 3. a key goes only to the service it was set up for -------------------

A = "https://api.openai.com/v1"
B = "http://other.example/v1"


def test_a_hand_set_key_is_not_offered_to_another_address(store, monkeypatch):
    monkeypatch.setenv("PLANNER_BASE_URL", A)
    monkeypatch.setenv("PLANNER_API_KEY", "sk-hand")
    assert ai_settings.key_for_url(A) == "sk-hand"
    assert ai_settings.key_for_url(B) == ""
    ai_settings.save({"backend": "openai", "baseUrl": B})
    assert ai_settings.load().key_for("openai") == ""
    # What the planner itself would send: a present blank, not the hand key.
    assert planner._env("PLANNER_BASE_URL") == B
    assert planner._env("PLANNER_API_KEY") == ""


def test_a_key_in_dotenv_is_not_offered_to_another_address(store, tmp_path):
    (tmp_path / ".env").write_text(f"PLANNER_BASE_URL={A}\nPLANNER_API_KEY=sk-file\n",
                                   encoding="utf-8")
    assert ai_settings.key_for_url(A) == "sk-file"
    assert ai_settings.key_for_url(B) == ""
    ai_settings.save({"backend": "openai", "baseUrl": B})
    assert planner._env("PLANNER_API_KEY") == ""


def test_the_hand_set_key_still_works_at_its_own_address(store, monkeypatch):
    monkeypatch.setenv("PLANNER_BASE_URL", A)
    monkeypatch.setenv("PLANNER_API_KEY", "sk-hand")
    ai_settings.save({"backend": "openai", "baseUrl": B})
    ai_settings.save({"backend": "openai", "baseUrl": A})
    assert planner._env("PLANNER_BASE_URL") == A
    assert planner._env("PLANNER_API_KEY") == "sk-hand"


def test_a_key_injected_for_one_service_is_not_read_back_as_the_users(store):
    ai_settings.save({"backend": "openai", "baseUrl": B, "apiKey": "sk-b"})
    assert os.environ["PLANNER_API_KEY"] == "sk-b"
    assert ai_settings.key_for_url(A) == ""
    assert ai_settings.key_for_url(B) == "sk-b"


# --- 2. the connector's password is random, kept private, never sent out ---

def test_the_proxy_password_is_random_and_owner_only(store, monkeypatch):
    import stat
    import sys
    key = ai_settings.cliproxy_key()
    assert key != ai_settings._legacy_cliproxy_key()
    assert len(key) == 32 and ai_settings.cliproxy_key() == key
    if sys.platform != "win32":
        mode = stat.S_IMODE(ai_settings.cliproxy_key_path().stat().st_mode)
        assert mode & 0o077 == 0


def test_two_installs_get_different_passwords(store, tmp_path, monkeypatch):
    first = ai_settings.cliproxy_key()
    monkeypatch.setenv("TONECOMMAND_CLIPROXY_KEY_FILE", str(tmp_path / "other" / "k.txt"))
    assert ai_settings.cliproxy_key() != first


def test_an_install_on_the_old_password_is_moved_off_it(store, tmp_path, monkeypatch):
    import json
    cfg = tmp_path / "cliproxyapi.conf"
    monkeypatch.setattr(ai_settings, "cliproxy_config_path", lambda: str(cfg))
    monkeypatch.setattr(ai_settings, "_brew", lambda: "")
    legacy = ai_settings._legacy_cliproxy_key()
    cfg.write_text(f'api-keys:\n  - "{legacy}"\n', encoding="utf-8")
    slot = "openai@" + ai_settings.CLIPROXY_DEFAULT_URL.rstrip("/")
    ai_settings.settings_path().write_text(json.dumps(
        {"backend": "openai", "keys": {slot: legacy}}), encoding="utf-8")
    assert ai_settings.migrate_cliproxy_key()
    new = ai_settings.cliproxy_key()
    assert legacy not in cfg.read_text(encoding="utf-8")
    assert new in cfg.read_text(encoding="utf-8")
    stored = json.loads(ai_settings.settings_path().read_text(encoding="utf-8"))
    assert stored["keys"][slot] == new and stored["backend"] == "openai"
    assert ai_settings.migrate_cliproxy_key() == ""          # done once


def test_the_setup_api_does_not_return_the_password(store, monkeypatch):
    from fastapi.testclient import TestClient
    import server
    monkeypatch.setattr(ai_settings, "setup_step_state", lambda i: (True, i))
    body = TestClient(server.app).get("/api/ai-settings/setup").text
    assert ai_settings.cliproxy_key() not in body


# --- 5. request and capture-drop limits, checked before decoding -----------

def _client():
    from fastapi.testclient import TestClient
    import server
    return server, TestClient(server.app)


def test_a_body_over_the_cap_is_refused_unread(monkeypatch):
    server, c = _client()
    monkeypatch.setattr(server, "MAX_BODY_BYTES", 1000)
    r = c.post("/api/captures/intake", content=b"x" * 2000,
               headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_a_chunked_body_over_the_cap_is_refused(monkeypatch):
    server, c = _client()
    monkeypatch.setattr(server, "MAX_BODY_BYTES", 1000)

    def chunks():
        for _ in range(5):
            yield b'{"pad": "' + b"x" * 400 + b'"}'
    reached = []
    monkeypatch.setattr(server.nam_intake, "intake", lambda *a: reached.append(1))
    r = c.post("/api/captures/intake", content=chunks(),
               headers={"content-type": "application/json"})
    # Reading stops at the cap. FastAPI reports a body it could not finish
    # reading as 400, so either refusal is right; the route never runs.
    assert r.status_code in (400, 413) and reached == []


def test_too_many_capture_files_are_refused_before_decoding(monkeypatch):
    import base64
    server, c = _client()
    calls = []
    monkeypatch.setattr(base64, "b64decode", lambda *a, **k: calls.append(1) or b"")
    files = [{"name": f"{i}.nam", "data": "AA=="} for i in range(server.INTAKE_MAX_FILES + 1)]
    r = c.post("/api/captures/intake", json={"files": files})
    assert r.status_code == 413 and calls == []


def test_an_oversized_capture_is_refused_before_decoding(monkeypatch):
    import base64
    server, c = _client()
    monkeypatch.setattr(server, "INTAKE_MAX_FILE_BYTES", 300)
    calls = []
    monkeypatch.setattr(base64, "b64decode", lambda *a, **k: calls.append(1) or b"")
    r = c.post("/api/captures/intake", json={"files": [{"name": "big.nam", "data": "A" * 800}]})
    assert r.status_code == 413 and calls == []


def test_a_normal_drop_still_goes_through(monkeypatch):
    server, c = _client()
    r = c.post("/api/captures/intake", json={"files": [{"name": "x.nam", "data": "e30="}]})
    assert r.status_code == 200


# --- 4. updates install the latest release tag, never unreleased main ------

def _git(cwd, *args):
    import subprocess
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def released(tmp_path):
    """A GitHub-looking origin with v1.0.1 released and one commit after it."""
    import shutil
    if not shutil.which("git"):
        pytest.skip("git not installed")
    origin, work = tmp_path / "origin.git", tmp_path / "seed"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    for k, v in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false"),
                 ("tag.gpgsign", "false")):
        _git(work, "config", k, v)
    (work / "f").write_text("1", encoding="utf-8")
    _git(work, "add", "f"); _git(work, "commit", "-qm", "one")
    _git(work, "tag", "-a", "v1.0.0", "-m", "1.0.0")
    (work / "f").write_text("2", encoding="utf-8")
    _git(work, "commit", "-qam", "two")
    _git(work, "tag", "-a", "v1.0.1", "-m", "1.0.1")
    (work / "f").write_text("3", encoding="utf-8")
    _git(work, "commit", "-qam", "unreleased")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "main", "--tags")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "reset", "-q", "--hard", "v1.0.0")
    gh = "https://github.com/example/tc.git"
    _git(clone, "remote", "set-url", "origin", gh)
    _git(clone, "config", f"url.{origin}.insteadOf", gh)
    return work, clone


def test_an_update_stops_at_the_release_not_at_main(released, monkeypatch):
    from fm9 import updates
    work, clone = released
    monkeypatch.setattr(updates, "latest_release", lambda root, **k: {"version": "1.0.1"})
    assert updates._move_to_release(clone) == ""
    assert (clone / "f").read_text(encoding="utf-8") == "2"
    assert _git(clone, "rev-parse", "HEAD") == _git(work, "rev-parse", "v1.0.1^{commit}")


def test_a_lightweight_tag_is_not_installed(released, monkeypatch):
    from fm9 import updates
    work, clone = released
    _git(work, "tag", "v1.0.2", "HEAD")
    _git(work, "push", "-q", "origin", "v1.0.2")
    monkeypatch.setattr(updates, "latest_release", lambda root, **k: {"version": "1.0.2"})
    assert "annotated" in updates._move_to_release(clone)
    assert (clone / "f").read_text(encoding="utf-8") == "1"


def test_a_tag_off_main_is_not_installed(released, monkeypatch):
    from fm9 import updates
    work, clone = released
    _git(work, "checkout", "-q", "-b", "side", "v1.0.0")
    (work / "f").write_text("side", encoding="utf-8")
    _git(work, "commit", "-qam", "side")
    _git(work, "tag", "-a", "v9.9.9", "-m", "x")
    _git(work, "push", "-q", "origin", "v9.9.9")
    monkeypatch.setattr(updates, "latest_release", lambda root, **k: {"version": "9.9.9"})
    assert "main branch" in updates._move_to_release(clone)
    assert (clone / "f").read_text(encoding="utf-8") == "1"


def test_a_checkout_not_from_github_is_not_updated(released, monkeypatch):
    from fm9 import updates
    _, clone = released
    _git(clone, "remote", "set-url", "origin", "https://example.com/x/tc.git")
    monkeypatch.setattr(updates, "latest_release", lambda root, **k: {"version": "1.0.1"})
    assert "GitHub" in updates._move_to_release(clone)


# --- 1. a change needs this install's access key ---------------------------

@pytest.fixture
def keyed(monkeypatch):
    from fastapi.testclient import TestClient
    import server
    from fm9 import access
    monkeypatch.setattr(server, "_REQUIRE_ACCESS_KEY", True)
    return server, access, TestClient(server.app)


def test_a_change_without_the_key_is_refused(keyed):
    server, access, c = keyed
    for path in ("/api/apply", "/api/update", "/api/ai-settings/setup/run",
                 "/api/ai-settings", "/api/captures/intake"):
        r = c.post(path, json={})
        assert r.status_code == 401 and r.json()["needsKey"] is True, path


def test_a_wrong_key_is_refused(keyed):
    server, access, c = keyed
    r = c.post("/api/update", headers={"x-tonecommand-key": "x" * 43})
    assert r.status_code == 401
    c.cookies.set(access.COOKIE, "y" * 43)
    assert c.post("/api/update").status_code == 401


def test_reading_needs_no_key(keyed):
    server, access, c = keyed
    assert c.get("/api/version").status_code == 200
    assert c.get("/api/access").json()["granted"] is False


def test_the_opening_link_sets_the_cookie_and_leaves_the_address(keyed, monkeypatch):
    server, access, c = keyed
    r = c.get("/?key=" + access.key(), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert c.get("/api/access").json()["granted"] is True
    # A granted browser gets past the key check to the route itself.
    monkeypatch.setattr(server, "_gig_mode", {"on": True})
    assert c.post("/api/update").status_code == 423


def test_a_wrong_link_sets_no_cookie(keyed):
    server, access, c = keyed
    r = c.get("/?key=" + "z" * 43, follow_redirects=False)
    assert r.status_code == 303 and "set-cookie" not in r.headers
    assert c.get("/api/access").json()["granted"] is False


def test_a_script_may_send_the_key_as_a_header(keyed, monkeypatch):
    server, access, c = keyed
    monkeypatch.setattr(server, "_gig_mode", {"on": True})
    r = c.post("/api/update", headers={"x-tonecommand-key": access.key()})
    assert r.status_code == 423


def test_the_access_key_is_random_and_owner_only(keyed):
    import stat
    import sys
    server, access, c = keyed
    k = access.key()
    assert len(k) == 43 and access.key() == k
    if sys.platform != "win32":
        assert stat.S_IMODE(access.key_path().stat().st_mode) & 0o077 == 0


# --- found in review of the fixes above ------------------------------------

def test_another_apps_odd_cookie_does_not_hide_the_key(keyed, monkeypatch):
    server, access, c = keyed
    monkeypatch.setattr(server, "_gig_mode", {"on": True})
    for junk in ('x[y]=1', 'foo=bar baz', 'a="b c'):
        r = c.post("/api/update",
                   headers={"cookie": f"{junk}; {access.COOKIE}={access.key()}"})
        assert r.status_code == 423, junk


def test_the_request_log_never_carries_the_key():
    import logging
    from fm9 import access
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                            '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:5", "GET", "/?key=SECRETSECRET&x=1", "1.1", 303), None)
    access.ScrubKeyFilter().filter(rec)
    assert "SECRETSECRET" not in rec.getMessage() and "key=<hidden>" in rec.getMessage()


def test_a_key_file_that_cannot_be_written_falls_back_to_the_user_folder(tmp_path, monkeypatch):
    import sys
    from fm9 import access
    if sys.platform == "win32":
        pytest.skip("POSIX permissions")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        monkeypatch.setenv("TONECOMMAND_ACCESS_KEY_FILE", str(locked / "access_key.txt"))
        k = access.key()
        assert (access.user_dir() / "access_key.txt").read_text(encoding="utf-8").strip() == k
        assert access.key() == k
    finally:
        locked.chmod(0o700)


def test_the_connector_works_after_the_manual_setup_line(store):
    """The shown line writes the password into the connector's config only;
    ToneCommand still sends it to the connector's own address, and nowhere else."""
    k = ai_settings.cliproxy_key()                 # what the shown line reads
    assert ai_settings.key_for_url(ai_settings.CLIPROXY_DEFAULT_URL) == k
    assert ai_settings.key_for_url(B) == ""


def test_no_connector_password_is_made_up_for_someone_who_never_set_it_up(store):
    assert ai_settings.key_for_url(ai_settings.CLIPROXY_DEFAULT_URL) == ""
    assert not ai_settings.cliproxy_key_path().exists()


def test_a_checkout_ahead_of_the_release_is_not_reported_as_updated(released, monkeypatch):
    from fm9 import updates
    work, clone = released
    _git(clone, "merge", "-q", "--ff-only", "origin/main")       # unreleased work
    monkeypatch.setattr(updates, "latest_release", lambda root, **k: {"version": "1.0.1"})
    assert "ahead of the latest release" in updates._move_to_release(clone)
    assert (clone / "f").read_text(encoding="utf-8") == "3"


def test_already_on_the_release_is_not_an_update(released, monkeypatch):
    from fm9 import updates
    work, clone = released
    _git(clone, "merge", "-q", "--ff-only", "v1.0.1")
    monkeypatch.setattr(updates, "latest_release", lambda root, **k: {"version": "1.0.1"})
    assert "already on v1.0.1" in updates._move_to_release(clone)

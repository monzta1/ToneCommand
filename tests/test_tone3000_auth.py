"""Issue #88 (D2): TONE3000 sign-in the way their API documents it. PKCE,
the urls, the token calls on a fake http, the token file, the routes,
and the fetch path preferring the token. No network: http is a fake and
the default http is never reached.
"""
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import owner_only, recipe_capture as rc, tone3000_auth as A

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


class FakeHttp:
    def __init__(self, status=200, body=None, refresh_body=None):
        self.calls, self.status = [], status
        self.body = body if body is not None else {"access_token": "at-1", "refresh_token": "rt-1",
                                                   "token_type": "bearer", "expires_in": 3600, "scope": "read"}
        self.refresh_body = refresh_body or {"access_token": "at-2", "refresh_token": "rt-2",
                                             "token_type": "bearer", "expires_in": 3600}

    def __call__(self, method, url, data=None, headers=None):
        self.calls.append((method, url, dict(data or {}), dict(headers or {})))
        if self.status != 200:
            return self.status, b'{"error":"invalid_grant"}'
        body = self.refresh_body if (data or {}).get("grant_type") == "refresh_token" else self.body
        return 200, json.dumps(body).encode()


@pytest.fixture(autouse=True)
def tokens_path(monkeypatch, tmp_path):
    monkeypatch.setenv("TONECOMMAND_TONE3000_TOKENS", str(tmp_path / "t3k.json"))
    monkeypatch.setenv("TONE3000_PUBLISHABLE_KEY", "t3k_pub_test")
    monkeypatch.delenv("TONE3000_SECRET_KEY", raising=False)
    monkeypatch.setattr(A, "_ENV_FILE", tmp_path / "no.env")
    monkeypatch.setattr(rc, "_ENV_FILE", tmp_path / "no.env")
    server._t3k_pending.clear()
    yield tmp_path / "t3k.json"


# --- REQ-001: pkce, url, exchange, refresh, store ------------------------------------------------

def test_pkce_pair_is_s256_and_url_safe():
    v, c = A.pkce()
    assert 43 <= len(v) <= 128 and re.fullmatch(r"[A-Za-z0-9_-]+", v)
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    assert A.pkce()[0] != v and len(A.new_state()) >= 32


def test_authorize_url_carries_the_documented_parameters():
    u = A.authorize_url("t3k_pub_x", "http://127.0.0.1:8909/api/tone3000/callback", "st", "ch")
    p = urlparse(u); q = parse_qs(p.query)
    assert p.scheme == "https" and p.netloc == "www.tone3000.com" and p.path == "/api/v1/oauth/authorize"
    assert q == {"client_id": ["t3k_pub_x"], "redirect_uri": ["http://127.0.0.1:8909/api/tone3000/callback"],
                 "response_type": ["code"], "code_challenge": ["ch"], "code_challenge_method": ["S256"], "state": ["st"]}
    q2 = parse_qs(urlparse(A.authorize_url("k", "r", "s", "c", prompt="load_tone", tone_id=57410)).query)
    assert q2["prompt"] == ["load_tone"] and q2["tone_id"] == ["57410"]
    with pytest.raises(A.AuthError, match="needs a tone_id"):
        A.authorize_url("k", "r", "s", "c", prompt="load_tone")
    with pytest.raises(A.AuthError, match="not one TONE3000 documents"):
        A.authorize_url("k", "r", "s", "c", prompt="browse")


def test_exchange_posts_the_form_and_stores_tokens_at_0600(tokens_path):
    http = FakeHttp()
    t = A.exchange("code-1", "verif", "http://127.0.0.1:8909/api/tone3000/callback", "t3k_pub_x", http, now=1000.0)
    m, url, data, _ = http.calls[0]
    assert (m, url) == ("POST", "https://www.tone3000.com/api/v1/oauth/token")
    assert data == {"grant_type": "authorization_code", "code": "code-1", "code_verifier": "verif",
                    "redirect_uri": "http://127.0.0.1:8909/api/tone3000/callback", "client_id": "t3k_pub_x"}
    assert t["access_token"] == "at-1" and t["refresh_token"] == "rt-1" and t["expires_at"] == 4600.0
    store = A.TokenStore()
    store.save(t)
    assert owner_only.is_private(tokens_path)
    assert store.load()["access_token"] == "at-1"
    assert store.status() == {"signed_in": True, "expires_at": 4600.0, "client_id_set": True}
    store.clear()
    assert store.load() is None and store.status()["signed_in"] is False
    with pytest.raises(A.AuthError, match="refused the sign-in code"):
        A.exchange("bad", "v", "r", "c", FakeHttp(status=400))
    with pytest.raises(A.AuthError, match="not a token"):
        A.exchange("c", "v", "r", "c", lambda *a: (200, b"<html>"))


def test_refresh_and_access_token_refreshes_a_minute_ahead(tokens_path):
    http = FakeHttp()
    store = A.TokenStore()
    assert A.access_token(store, http, now=0.0) is None                      # not signed in
    store.save(A.exchange("c", "v", "r", "t3k_pub_x", http, now=1000.0))
    assert A.access_token(store, http, now=2000.0) == "at-1" and len(http.calls) == 1
    assert A.access_token(store, http, now=4600.0 - 59) == "at-2"            # inside the minute: refreshed
    m, url, data, _ = http.calls[-1]
    assert data == {"grant_type": "refresh_token", "refresh_token": "rt-1", "client_id": "t3k_pub_test"}
    assert store.load()["refresh_token"] == "rt-2" and store.load()["expires_at"] == 4600.0 - 59 + 3600
    # a refused refresh means sign in again: None, and the old file stays for the message
    bad = FakeHttp(status=401)
    assert A.access_token(store, bad, now=10_000.0) is None
    r = A.refresh("rt-x", "c", FakeHttp(refresh_body={"access_token": "at-3", "expires_in": 10}), now=5.0)
    assert r["refresh_token"] == "rt-x"                                        # kept when TONE3000 sends none


def test_default_http_never_leaves_tone3000_and_no_token_is_logged():
    assert A.default_http("GET", "https://example.com/x") == (0, b"")
    asrc = (ROOT / "fm9" / "tone3000_auth.py").read_text(encoding="utf-8")
    assert "log." not in asrc and "print(" not in asrc                      # the module never logs
    ssrc = (ROOT / "server.py").read_text(encoding="utf-8")
    t3k = ssrc.split("TONE3000 sign-in (#88)", 1)[1].split('@app.get("/api/share/status")', 1)[0]
    assert "log.info(\"TONE3000: signed in\")" in t3k and "access_token" not in t3k


# --- REQ-002: routes ---------------------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(server.app)


def test_route_login_refuses_without_a_key_and_builds_the_url_with_one(client, monkeypatch):
    monkeypatch.delenv("TONE3000_PUBLISHABLE_KEY")
    r = client.get("/api/tone3000/login")
    assert r.status_code == 409 and "TONE3000_PUBLISHABLE_KEY" in r.json()["error"]
    monkeypatch.setenv("TONE3000_PUBLISHABLE_KEY", "t3k_pub_test")
    r = client.get("/api/tone3000/login")
    assert r.status_code == 200, r.text
    q = parse_qs(urlparse(r.json()["url"]).query)
    assert q["client_id"] == ["t3k_pub_test"] and q["redirect_uri"] == [server.TONE3000_REDIRECT]
    assert server._t3k_pending["state"] == q["state"][0] and "verifier" in server._t3k_pending
    assert client.get("/api/tone3000/login?prompt=browse").status_code == 400
    assert client.get("/api/tone3000/load").status_code == 400
    r = client.get("/api/tone3000/load?tone_id=57410")
    q = parse_qs(urlparse(r.json()["url"]).query)
    assert q["prompt"] == ["load_tone"] and q["tone_id"] == ["57410"]


def test_route_callback_verifies_state_exchanges_and_redirects(client, monkeypatch, tokens_path):
    http = FakeHttp()
    monkeypatch.setattr(A, "default_http", http)
    client.get("/api/tone3000/login")
    state = server._t3k_pending["state"]
    # wrong state: nothing stored
    r = client.get("/api/tone3000/callback?code=c&state=nope", follow_redirects=False)
    assert r.status_code == 400 and not tokens_path.exists() and http.calls == []
    # an error from TONE3000: nothing stored, pending cleared, back to the app
    client.get("/api/tone3000/login"); state = server._t3k_pending["state"]
    r = client.get(f"/api/tone3000/callback?error=access_denied&state={state}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/?tone3000=refused:access_denied"
    assert not tokens_path.exists() and server._t3k_pending == {}
    # the right state: exchanged with the verifier, stored 0600, redirected
    client.get("/api/tone3000/login"); state = server._t3k_pending["state"]; verifier = server._t3k_pending["verifier"]
    r = client.get(f"/api/tone3000/callback?code=code-9&state={state}&tone_id=57410", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/?tone3000=signed-in&tone_id=57410"
    assert http.calls[-1][2]["code"] == "code-9" and http.calls[-1][2]["code_verifier"] == verifier
    assert owner_only.is_private(tokens_path) and server._t3k_pending == {}
    st = client.get("/api/tone3000/status").json()
    assert st["signed_in"] is True and st["last_tone_id"] == 57410 and "token" not in json.dumps(st).replace("expires", "")
    assert "at-1" not in r.text and "at-1" not in json.dumps(st)
    r = client.post("/api/tone3000/logout")
    assert r.json() == {"signed_in": False} and not tokens_path.exists()
    # a callback with no pending login
    assert client.get("/api/tone3000/callback?code=c&state=x").status_code == 400
    # atomic: two threads consuming the same pending login, exactly one gets it
    import threading
    client.get("/api/tone3000/login")
    got = []
    def take():
        got.append(bool(server._t3k_consume_pending()))
    ts = [threading.Thread(target=take) for _ in range(8)]
    for th in ts: th.start()
    for th in ts: th.join()
    assert got.count(True) == 1 and server._t3k_pending == {}
    # single use: a mismatch consumes the pending login, so a replay with the right state is refused
    client.get("/api/tone3000/login"); state = server._t3k_pending["state"]
    assert client.get("/api/tone3000/callback?code=c&state=nope").status_code == 400
    assert server._t3k_pending == {}
    assert client.get(f"/api/tone3000/callback?code=c&state={state}").status_code == 400
    assert not tokens_path.exists()
    # expiry: a login older than the TTL is refused even with the right state
    client.get("/api/tone3000/login"); state = server._t3k_pending["state"]
    server._t3k_pending["started_at"] -= server.TONE3000_LOGIN_TTL_S + 1
    r = client.get(f"/api/tone3000/callback?code=c&state={state}")
    assert r.status_code == 400 and "ten minutes" in r.json()["error"] and not tokens_path.exists()


# --- REQ-003: the fetch runs under the token; the replacement; the page; the docs ------------------------

def test_fetch_prefers_the_token_over_the_secret_key(monkeypatch, tokens_path):
    assert rc.key_from_env() is None
    monkeypatch.setenv("TONE3000_SECRET_KEY", "t3k_cs_old")
    assert rc.key_from_env() == "t3k_cs_old"
    A.TokenStore().save({"version": 1, "access_token": "at-9", "refresh_token": "rt-9",
                         "expires_at": 4e9, "scope": None, "obtained_at": 0})
    assert rc.key_from_env() == "at-9"
    # signed in but expired and the refresh refused: None, NEVER the secret key
    A.TokenStore().save({"version": 1, "access_token": "at-old", "refresh_token": "rt-old",
                         "expires_at": 1.0, "scope": None, "obtained_at": 0})
    monkeypatch.setattr(A, "default_http", FakeHttp(status=401))
    assert rc.key_from_env() is None


def test_entitlement_not_yours_carries_the_replacement_url():
    from tests.test_recipe_capture import _field, _fetch
    out = rc.resolve(_field(), set(), fetch=_fetch(record_status=403), key="at-9")
    assert out["status"] == "not_yours" and out["replacement_url"] == "/api/tone3000/load?tone_id=57410"
    out = rc.resolve(_field(), set(), fetch=_fetch(), key=None)
    assert out["status"] == "not_yours" and "sign in to TONE3000 in Settings" in out["line"]
    ok = rc.resolve(_field(), set(), fetch=_fetch(), key="at-9")
    assert ok["status"] == "available" and ok["replacement_url"].endswith("57410")


def test_ui_and_docs_say_sign_in_and_the_redirect_uri():
    assert 'id="t3ksignin"' in UI and 'id="t3ksignout"' in UI and "fetch('/api/tone3000/status')" in UI
    assert "d.capture.replacement_url" in UI
    setup = (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
    assert "TONE3000_PUBLISHABLE_KEY" in setup and "http://127.0.0.1:8909/api/tone3000/callback" in setup
    assert "#88" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 1.5.0", 1)[0]

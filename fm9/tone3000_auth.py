"""TONE3000 sign-in from the app, the way their API documents it (issue
#88, D2): OAuth 2.0 with PKCE.

    GET  https://www.tone3000.com/api/v1/oauth/authorize
         client_id (the publishable key), redirect_uri, response_type=code,
         code_challenge (base64url SHA-256 of the verifier),
         code_challenge_method=S256, state; optional prompt=load_tone with
         tone_id (TONE3000 verifies the account's access to that tone and
         lets the player browse a replacement when it is unavailable) or
         prompt=select_tone.
    POST https://www.tone3000.com/api/v1/oauth/token   (form-encoded)
         grant_type=authorization_code, code, code_verifier, redirect_uri,
         client_id  ->  access_token, refresh_token, token_type, expires_in,
         scope; grant_type=refresh_token, refresh_token, client_id for a new
         pair.

Read from their docs page 2026-09-20. What this module holds: the PKCE
pair, the urls, the two token calls, a token file kept at mode 0600, and
an access token that refreshes itself a minute before it expires. What it
never does: log a token, put one in a response, or reach any host but
www.tone3000.com. HTTP is injected so tests never touch the network.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from fm9 import owner_only

HOST = "https://www.tone3000.com"
AUTHORIZE_URL = HOST + "/api/v1/oauth/authorize"
TOKEN_URL = HOST + "/api/v1/oauth/token"
PROMPTS = (None, "load_tone", "select_tone")
REFRESH_AHEAD_S = 60.0
_ENV_KEY = "TONE3000_PUBLISHABLE_KEY"
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

Http = Callable[[str, str, dict | None, dict | None], tuple[int, bytes]]


class AuthError(RuntimeError):
    """One line, written for the person at the app."""


# --- the publishable key -----------------------------------------------------------

def client_id() -> str | None:
    key = os.environ.get(_ENV_KEY, "").strip()
    if not key and _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(_ENV_KEY + "="):
                key = line.split("=", 1)[1].strip()
                break
    return key or None


# --- PKCE and the authorize url -------------------------------------------------------

def pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge): 64 url-safe bytes, S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def new_state() -> str:
    return secrets.token_urlsafe(32)


def authorize_url(client: str, redirect_uri: str, state: str, challenge: str,
                  prompt: str | None = None, tone_id: int | None = None) -> str:
    if prompt not in PROMPTS:
        raise AuthError(f"prompt {prompt!r} is not one TONE3000 documents")
    if prompt == "load_tone" and not tone_id:
        raise AuthError("load_tone needs a tone_id")
    q = {"client_id": client, "redirect_uri": redirect_uri, "response_type": "code",
         "code_challenge": challenge, "code_challenge_method": "S256", "state": state}
    if prompt:
        q["prompt"] = prompt
    if tone_id:
        q["tone_id"] = str(int(tone_id))
    return AUTHORIZE_URL + "?" + urlencode(q)


# --- the token calls ---------------------------------------------------------------------

def default_http(method: str, url: str, data: dict | None = None,
                 headers: dict | None = None, timeout: float = 20.0) -> tuple[int, bytes]:
    """(status, body). www.tone3000.com only; anything else is (0, b'')."""
    import urllib.error
    import urllib.request
    if not url.startswith(HOST + "/"):
        return 0, b""
    body = urlencode(data).encode() if data is not None else None
    hdrs = {"User-Agent": "ToneCommand (TONE3000 sign-in)"}
    if body is not None:
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.status), r.read(1 << 20)
    except urllib.error.HTTPError as e:
        return int(e.code), e.read(1 << 16) if hasattr(e, "read") else b""
    except (urllib.error.URLError, OSError, ValueError):
        return 0, b""


def _tokens_from(body: bytes, now: float) -> dict:
    try:
        doc = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise AuthError("TONE3000 answered something that is not a token")
    access = doc.get("access_token")
    if not isinstance(access, str) or not access:
        raise AuthError("TONE3000 answered no access token")
    try:
        expires_in = float(doc.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0.0
    return {"version": 1, "access_token": access,
            "refresh_token": str(doc.get("refresh_token") or ""),
            "expires_at": now + expires_in, "scope": doc.get("scope"), "obtained_at": now}


def exchange(code: str, verifier: str, redirect_uri: str, client: str, http: Http,
             now: float | None = None) -> dict:
    """The authorization code for a token pair."""
    status, body = http("POST", TOKEN_URL, {"grant_type": "authorization_code", "code": code,
                                            "code_verifier": verifier, "redirect_uri": redirect_uri,
                                            "client_id": client}, None)
    if status != 200:
        raise AuthError(f"TONE3000 refused the sign-in code (HTTP {status})")
    return _tokens_from(body, time.time() if now is None else now)


def refresh(refresh_token: str, client: str, http: Http, now: float | None = None) -> dict:
    status, body = http("POST", TOKEN_URL, {"grant_type": "refresh_token",
                                            "refresh_token": refresh_token, "client_id": client}, None)
    if status != 200:
        raise AuthError(f"TONE3000 refused the refresh (HTTP {status}); sign in again")
    out = _tokens_from(body, time.time() if now is None else now)
    if not out["refresh_token"]:
        out["refresh_token"] = refresh_token
    return out


# --- the token file ----------------------------------------------------------------------------

class TokenStore:
    def __init__(self, path: Path | None = None):
        override = os.environ.get("TONECOMMAND_TONE3000_TOKENS", "").strip()
        self.path = path or (Path(override) if override else
                             Path.home() / ".tonecommand" / "tone3000_tokens.json")

    def load(self) -> dict | None:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(doc, dict) or not doc.get("access_token"):
            return None
        return doc

    def save(self, tokens: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # #186: owner-only on every OS (an ACL on Windows), and the token is
        # only written once the file is shown to be private.
        owner_only.write_private(self.path, json.dumps(tokens, indent=1))

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def status(self, now: float | None = None) -> dict:
        """What the app may show: signed in or not, and when it expires.
        Never a token."""
        t = self.load()
        return {"signed_in": bool(t), "expires_at": (t or {}).get("expires_at"),
                "client_id_set": bool(client_id())}


def access_token(store: TokenStore | None = None, http: Http | None = None,
                 now: float | None = None) -> str | None:
    """The bearer token for a TONE3000 request, refreshed when it is within
    REFRESH_AHEAD_S of expiring; None when not signed in or when the
    refresh fails (the app then says sign in again)."""
    store = store or TokenStore()
    t = store.load()
    if not t:
        return None
    now = time.time() if now is None else now
    if now < float(t.get("expires_at") or 0) - REFRESH_AHEAD_S:
        return t["access_token"]
    client = client_id()
    if not t.get("refresh_token") or not client:
        return None
    try:
        fresh = refresh(t["refresh_token"], client, http or default_http, now)
    except AuthError:
        return None
    store.save(fresh)
    return fresh["access_token"]

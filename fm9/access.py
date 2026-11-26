"""Who may change things through ToneCommand's local server (#340).

The server listens on 127.0.0.1 only and refuses other sites' pages (the
Host/Origin check in server.py). That still leaves anything else on the
computer able to send it a request: another user account on a shared Mac,
or a program that can reach the port. So every request that changes
something (writes to the unit, updates, setup steps, settings) must also
carry this install's access key.

The key is random, made once per install, and kept in a file only this
user account can read. The browser gets it once, through the link
ToneCommand opens (or prints) when it starts: /?key=... sets a cookie the
browser then sends by itself, and the page redirects to the plain address
so the key does not stay in the address bar or history. Bookmarks keep
working afterwards. A script sends the key in the X-ToneCommand-Key header.

The boundary, stated plainly: a program running as you can read the key
file, as it can read everything else of yours. This keeps out other
accounts and anything that cannot read your files; it is not a sandbox
against your own software. SECURITY.md says the same.
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
from pathlib import Path

from . import owner_only

COOKIE = "tonecommand_key"
HEADER = "x-tonecommand-key"
_SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")


def user_dir() -> Path:
    """The fallback home for secrets when the install folder cannot be
    written (an app bundle in /Applications, a read-only checkout)."""
    return Path.home() / ".tonecommand"


def secret_file(primary: Path, make) -> tuple[Path, str]:
    """Read a one-line secret from `primary` or user_dir(), or create it at
    `primary`; only when that place cannot be written, under user_dir(). `make()` returns a new value.
    Raises OSError only when neither place can be written."""
    def read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    fallback = user_dir() / primary.name
    for path in (primary, fallback):          # an existing secret always wins
        got = read(path)
        if got:
            return path, got
    value = make()
    try:
        primary.parent.mkdir(parents=True, exist_ok=True)
        owner_only.write_private(primary, value + "\n")
        return primary, value
    except OSError:
        pass
    fallback.parent.mkdir(parents=True, exist_ok=True)
    owner_only.write_private(fallback, value + "\n")
    return fallback, value


def key_path() -> Path:
    """Beside the AI settings file, so one override moves both for tests."""
    override = os.environ.get("TONECOMMAND_ACCESS_KEY_FILE", "").strip()
    if override:
        return Path(override)
    from . import ai_settings
    return ai_settings.settings_path().parent / "access_key.txt"


def key() -> str:
    """This install's access key, made on first use."""
    _, got = secret_file(key_path(), lambda: secrets.token_urlsafe(32))
    if not _SHAPE.fullmatch(got):
        raise OSError("the access key file does not hold a key")
    return got


def matches(candidate: str | None) -> bool:
    """Constant-time comparison, so timing says nothing about the key. A key
    that cannot be read matches nothing, so a change is refused, not a 500."""
    if not candidate:
        return False
    try:
        real = key()
    except OSError:
        return False
    return hmac.compare_digest(candidate.encode("utf-8", "replace"), real.encode("utf-8"))


class ScrubKeyFilter:
    """Takes the key out of a logged request line (uvicorn.access)."""
    _KEY = re.compile(r"([?&]key=)[^&\s\"]*")

    def filter(self, record) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._KEY.sub(r"\1<hidden>", a) if isinstance(a, str) else a
                                for a in record.args)
        if isinstance(record.msg, str):
            record.msg = self._KEY.sub(r"\1<hidden>", record.msg)
        return True


def link(port: int) -> str:
    """The address that hands this browser the key."""
    return f"http://127.0.0.1:{port}/?key={key()}"

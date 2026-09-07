"""Optional bridge to IRCommand, the local IR database and matcher.

Config-gated and OFF by default. TONECOMMAND_IR_SERVICE holds the IRCommand
service URL (for example http://127.0.0.1:8770). Unset or empty means the IR
feature is off and ToneCommand behaves exactly as before: factory cabs, no IR
step, no network call. This mirrors the store and cab whitelists, which are
also empty-default-disabled.

It is never a hard dependency. If the service is unset, down, or errors, every
call here returns None or "off" and the caller simply skips the IR step. The
matcher lives in a separate local project (~/Projects/ir-command); ToneCommand
only ever asks it for a cab and receives a name, path, tags and score.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "ir_service.json"


def env_url() -> str:
    return (os.environ.get("TONECOMMAND_IR_SERVICE") or "").strip().rstrip("/")


def get_url() -> str:
    """The IRCommand service URL. The env var wins (an operator pin), else the
    URL saved from Settings, else empty (feature off). Same precedence as the
    store whitelist and tone folder."""
    if env_url():
        return env_url()
    f = _config_path()
    if f.exists():
        try:
            got = json.loads(f.read_text())
            if isinstance(got, dict) and isinstance(got.get("url"), str):
                return got["url"].strip().rstrip("/")
        except (ValueError, OSError):
            pass
    return ""


def set_url(url: str) -> str:
    """Save the service URL from Settings. Empty turns the feature off."""
    url = (url or "").strip().rstrip("/")
    _config_path().write_text(json.dumps({"url": url}) + "\n")
    return url


def base_url() -> str:
    return get_url()


def enabled() -> bool:
    return bool(base_url())


def _get(path: str, timeout: int = 3):
    """GET a JSON endpoint on the IR service, or None on anything going wrong.
    Never raises, so a missing or broken service can never break a build."""
    url = base_url()
    if not url:
        return None
    try:
        with urllib.request.urlopen(url + path, timeout=timeout) as r:
            return json.loads(r.read(300_000).decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def status() -> dict:
    """Whether the IR feature is on, and if so whether the service answers.
    Always reports the saved url and whether the environment pins it, so
    Settings can show the field and lock it when an operator pinned it."""
    url = base_url()
    pinned = bool(env_url())
    if not url:
        return {"enabled": False, "url": "", "pinned": False}
    h = _get("/health")
    return {"enabled": True, "url": url, "pinned": pinned,
            "reachable": bool(h and h.get("ok")),
            "cabs": (h or {}).get("cabs")}


def library_root() -> Path:
    """Root directory the audition endpoint may read IR files from."""
    env = (os.environ.get("TONECOMMAND_IR_LIBRARY") or "").strip()
    return (Path(env) if env else Path.home() / "Documents" / "IR-Library").expanduser()


def safe_ir_path(path: str):
    """Resolve a requested IR path, or None if it is not a real WAV inside the
    IR library.

    This is a security boundary, not a convenience check: the audition endpoint
    reads a file off disk and streams it back, so without this the endpoint
    would be an arbitrary-file-read. Symlinks are resolved before the
    containment test so a link inside the library cannot point out of it.
    """
    if not path:
        return None
    try:
        p = Path(path).expanduser().resolve(strict=True)
        root = library_root().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not p.is_file() or p.suffix.lower() != ".wav":
        return None
    return p if root in p.parents else None


def recommend(need: str, target: str = "fm9", k: int = 3):
    """Best-matching IRs for a need, or None when off / unreachable / empty.
    Each result carries at least name, path, tags and score."""
    if not enabled() or not (need or "").strip():
        return None
    d = _get(f"/ir/recommend?need={quote(need)}&target={quote(target)}&k={int(k)}")
    if not d or "results" not in d:
        return None
    return d["results"]

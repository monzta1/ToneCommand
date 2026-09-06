"""Version awareness and one-click self-update.

ToneCommand is installed as an editable git checkout (pip install -e .), so an
update is a `git pull` plus a reinstall, not a package download. This module
tells the app which version it is running, whether GitHub has a newer release,
and (only on request, never on its own) pulls and reinstalls it.

Design rules that matter for a live hardware tool:
- The update CHECK is network, cached, and fails silently offline like the rest
  of the app. It never blocks a build.
- The update APPLY is guarded: only a clean working tree on the main branch is
  touched, never mid-gig, and it never restarts the process behind your back.
  It pulls, reinstalls, and asks you to restart, so a running FM9 session is
  never yanked out from under you.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
DEFAULT_REPO = "monzta1/ToneCommand"
CACHE_TTL = 6 * 3600  # re-ask GitHub at most every six hours

_cache: dict = {"at": 0.0, "data": None}


def current_version() -> str:
    """The running version, from installed package metadata.

    TONECOMMAND_VERSION_OVERRIDE wins when set, so the update flow can be tested
    on demand: launch with it set to an older version and the app will see the
    real latest release as an available update, banner and all.
    """
    import os
    override = os.environ.get("TONECOMMAND_VERSION_OVERRIDE", "").strip()
    if override:
        return override
    try:
        from importlib.metadata import version
        return version("tonecommand")
    except Exception:
        return "unknown"


def _parse(v: str) -> tuple:
    """A comparable tuple from a version string: 'v1.2.0' -> (1, 2, 0). Any
    pre-release or build suffix is dropped for the comparison, and a malformed
    version sorts low so it never claims to be newer than a real one."""
    nums = re.findall(r"\d+", (v or "").split("+")[0].split("-")[0])
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


def is_newer(latest: str, current: str) -> bool:
    if not latest or current == "unknown":
        return False
    return _parse(latest) > _parse(current)


def repo_slug(root: Path) -> str:
    """owner/name from the git remote, so a fork checks its own releases."""
    try:
        url = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        m = re.search(r"github\.com[/:]([^/]+/[^/.]+)", url)
        if m:
            return m.group(1)
    except Exception:
        pass
    return DEFAULT_REPO


def latest_release(root: Path, timeout: int = 4, force: bool = False) -> dict | None:
    """The newest published release from GitHub, cached. Returns
    {version, url} or None when offline or on any error (never raises)."""
    now = time.time()
    if not force and _cache["data"] is not None and now - _cache["at"] < CACHE_TTL:
        return _cache["data"]
    slug = repo_slug(root)
    req = urllib.request.Request(
        GITHUB_API.format(repo=slug),
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "ToneCommand-update-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read(200_000).decode("utf-8", "replace"))
        tag = (body.get("tag_name") or "").lstrip("v")
        data = ({"version": tag,
                 "url": body.get("html_url")
                     or f"https://github.com/{slug}/releases/latest"}
                if tag else None)
    except (urllib.error.URLError, OSError, ValueError):
        data = None
    _cache["at"] = now
    _cache["data"] = data
    return data


def is_git_checkout(root: Path) -> bool:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5).stdout.strip() == "true"
    except Exception:
        return False


def repo_state(root: Path) -> dict:
    """Branch and whether the working tree is clean, so the app can say why an
    update is or is not safe to apply automatically."""
    if not is_git_checkout(root):
        return {"git": False, "branch": None, "clean": False}

    def g(*args):
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=8)
    branch = g("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    dirty = g("status", "--porcelain").stdout.strip()
    return {"git": True, "branch": branch, "clean": not dirty}


def upgrade_commands(os_name: str = "") -> list[str]:
    """The manual upgrade, copy-paste ready, for the notify banner."""
    if os_name.lower().startswith("win"):
        return ["git pull", ".venv\\Scripts\\pip install -e .",
                ".venv\\Scripts\\tonecommand"]
    return ["git pull", ".venv/bin/pip install -e .", ".venv/bin/tonecommand"]


def can_auto_update(root: Path) -> tuple[bool, str]:
    """Whether the one-click updater may touch this checkout, and why not."""
    st = repo_state(root)
    if not st["git"]:
        return False, "not a git checkout, so update it the way you installed it"
    if st["branch"] not in ("main", "master"):
        return False, f"on branch {st['branch']}, not main; pull it yourself to be safe"
    if not st["clean"]:
        return False, "you have local changes; commit or stash them first"
    return True, ""


def run_update(root: Path) -> dict:
    """Pull and reinstall, in place. Guarded by can_auto_update. Never restarts
    the process: returns restart_required so the app can ask instead of yanking
    a live session. Never raises."""
    ok, why = can_auto_update(root)
    if not ok:
        return {"ok": False, "detail": why, "restart_required": False}
    try:
        pull = subprocess.run(["git", "-C", str(root), "pull", "--ff-only"],
                              capture_output=True, text=True, timeout=120)
        if pull.returncode != 0:
            return {"ok": False, "restart_required": False,
                    "detail": f"git pull failed: "
                              f"{(pull.stderr or pull.stdout).strip()[:200]}"}
        inst = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."],
                              cwd=str(root), capture_output=True, text=True,
                              timeout=600)
        if inst.returncode != 0:
            return {"ok": False, "restart_required": False,
                    "detail": f"reinstall failed: {(inst.stderr or '').strip()[:200]}"}
        return {"ok": True, "restart_required": True,
                "detail": "Updated. Restart ToneCommand to finish."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "restart_required": False,
                "detail": "the update took too long; run git pull yourself"}

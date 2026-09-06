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


def _git(root: Path, *args, timeout: int = 30):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, timeout=timeout)


def _revert(root: Path, commit: str) -> None:
    """Put the checkout back exactly where it was, so a failed update leaves the
    working version intact on disk rather than a half-applied one."""
    if not commit:
        return
    try:
        _git(root, "reset", "--hard", commit)
    except Exception:
        pass


def run_update(root: Path) -> dict:
    """Pull, reinstall, and PROVE the new code loads before the app will restart
    into it. Guarded by can_auto_update. Never restarts the process itself.
    Never raises.

    The safety guarantee for the player: any failure anywhere (pull, reinstall,
    or the new code not importing) reverts the checkout to the version that was
    already running and reports it. A broken release can never take the app
    down, because the working server is never stopped for code that has not been
    shown to start.
    """
    ok, why = can_auto_update(root)
    if not ok:
        return {"ok": False, "detail": why, "restart_required": False}
    old = ""
    try:
        old = _git(root, "rev-parse", "HEAD", timeout=8).stdout.strip()
        pull = _git(root, "pull", "--ff-only", timeout=120)
        if pull.returncode != 0:
            return {"ok": False, "restart_required": False,
                    "detail": f"git pull failed, nothing changed: "
                              f"{(pull.stderr or pull.stdout).strip()[:200]}"}
        inst = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."],
                              cwd=str(root), capture_output=True, text=True,
                              timeout=600)
        if inst.returncode != 0:
            _revert(root, old)
            return {"ok": False, "restart_required": False,
                    "detail": "reinstall failed, so the update was reverted and "
                              "nothing changed. Your current version keeps running."}
        # The new code must import and build the app, or the app never restarts
        # into it. This is the guarantee that a bad release cannot brick the
        # update: the running server keeps serving, and the checkout is reverted.
        smoke = subprocess.run(
            [sys.executable, "-c", "import server; assert server.app is not None"],
            cwd=str(root), capture_output=True, text=True, timeout=90)
        if smoke.returncode != 0:
            _revert(root, old)
            return {"ok": False, "restart_required": False,
                    "detail": "the new version did not load, so the update was "
                              "reverted and nothing changed. Your current version "
                              "keeps running."}
        return {"ok": True, "restart_required": True,
                "detail": "Updated. Restarting ToneCommand..."}
    except subprocess.TimeoutExpired:
        _revert(root, old)
        return {"ok": False, "restart_required": False,
                "detail": "the update took too long and was reverted; nothing "
                          "changed. Try again, or run git pull yourself."}
    except Exception as exc:
        _revert(root, old)
        return {"ok": False, "restart_required": False,
                "detail": f"the update could not complete and was reverted "
                          f"({str(exc)[:120]}). Nothing changed."}


def restart_process(root: Path, close_hook=None) -> None:
    """Relaunch the server in place so new code loads, with nothing for the
    player to do.

    The safe sequence, in order:
    1. Spawn a DETACHED relauncher that waits for this server's port to free,
       then starts a fresh one. It outlives this process on purpose.
    2. Run close_hook to release the FM9's CoreMIDI port cleanly, so the restart
       never leaves a poisoned port behind (the one hard rule for this tool).
    3. SIGTERM ourselves for uvicorn's graceful shutdown. Never a hard kill,
       and never os.execv, which would inherit the listening socket and fail to
       rebind. The detached relauncher binds the freed port and reconnects.
    """
    import os
    import signal
    py = sys.executable
    relaunch = (
        "import time, socket, subprocess\n"
        "root = " + repr(str(root)) + "\n"
        "py = " + repr(py) + "\n"
        "def bound():\n"
        "    s = socket.socket()\n"
        "    try:\n"
        "        s.connect(('127.0.0.1', 8909)); s.close(); return True\n"
        "    except OSError:\n"
        "        return False\n"
        "for _ in range(240):\n"          # wait up to 2 minutes for the port
        "    if not bound(): break\n"
        "    time.sleep(0.5)\n"
        "subprocess.Popen([py, '-c', 'from server import main; main()'], cwd=root)\n"
    )
    try:
        subprocess.Popen([py, "-c", relaunch], cwd=str(root),
                         start_new_session=True)
    except Exception:
        return  # could not spawn the relauncher; leave the server running
    try:
        if close_hook:
            close_hook()
    except Exception:
        pass
    os.kill(os.getpid(), signal.SIGTERM)

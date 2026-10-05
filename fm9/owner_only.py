"""Files only their owner can read, on every OS (#186).

The AI settings file holds a key and the TONE3000 token file holds a token.
On macOS and Linux owner-only means mode 0o600. Windows ignores POSIX modes
(the file lands readable by every local account), so there it means an
access control list: inherited entries removed, one grant of full control to
the current user, every other account removed. Set with icacls, which ships
with Windows, so there is no new dependency.

A secret is never written into a file that is not already private:
write_private creates an empty file, locks it down and checks it, and only
then writes. Anything failing before that point leaves no secret anywhere.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WINDOWS = sys.platform == "win32"


class NotPrivate(OSError):
    """The file could not be made, or shown to be, owner-only."""


def _run(args: list[str]) -> str:
    out = subprocess.run(args, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise NotPrivate(f"{args[0]} failed: {(out.stderr or out.stdout).strip()}")
    return out.stdout


def current_sid() -> str:
    """The current user's SID, from `whoami /user /fo csv /nh`, whose one
    line reads "machine\\user","S-1-5-21-..."."""
    line = _run(["whoami", "/user", "/fo", "csv", "/nh"]).strip().splitlines()[-1]
    return line.rsplit(",", 1)[-1].strip().strip('"')


def parse_grantees(icacls_output: str, path: str) -> list[str]:
    """The accounts in `icacls <path> /q` output. The first line carries the
    path, then one "ACCOUNT:(rights)" entry per line."""
    out = []
    for line in icacls_output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("successfully processed"):
            continue
        if line.lower().startswith(path.lower()):
            line = line[len(path):].strip()
        if ":(" in line:
            out.append(line.split(":(", 1)[0].strip())
    return out


def grantees(path: Path) -> list[str]:
    return parse_grantees(_run(["icacls", str(path), "/q"]), str(path))


def is_me(grantee: str, sid: str, user: str | None = None) -> bool:
    """Whether an icacls account entry names the current user: by SID, by
    bare name or as MACHINE\\name."""
    g = grantee.lstrip("*").lower()
    user = (user if user is not None else os.environ.get("USERNAME", "")).lower()
    return g == sid.lower() or (bool(user) and (g == user or g.endswith("\\" + user)))


def tighten(path: Path) -> None:
    """Make an existing file owner-only, whatever it was before. On Windows
    /grant:r replaces only the current user's own entry, so every other
    explicit grant is removed by name afterwards."""
    path = Path(path)
    if WINDOWS:
        me = current_sid()
        _run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{me}:F"])
        for who in grantees(path):
            if not is_me(who, me):
                _run(["icacls", str(path), "/remove:g", who])
    else:
        os.chmod(path, 0o600)


def is_private(path: Path) -> bool:
    """True when only the owner can read `path`."""
    path = Path(path)
    if WINDOWS:
        who = grantees(path)
        return len(who) == 1 and is_me(who[0], current_sid())
    return (path.stat().st_mode & 0o777) == 0o600


def write_private(path: Path, text: str) -> None:
    """Write a secret that nobody else can read, or write nothing.

    An EMPTY temp file with a name no other writer can have (created
    exclusively, 0o600 on POSIX) is made beside `path`, tightened and
    checked; the secret then goes in through the SAME open descriptor, so
    nothing between the check and the write can swap the file underneath,
    and the file is moved into place (a same-volume move keeps its ACL).
    Two saves at once each have their own temp file. A failure before the
    write leaves no secret bytes anywhere; any failure removes the temp file
    and raises."""
    path = Path(path)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        try:
            tighten(tmp)
            if not is_private(tmp):
                raise NotPrivate(f"{tmp} is still readable by another account")
            data = text.encode("utf-8")
            while data:
                data = data[os.write(fd, data):]
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise

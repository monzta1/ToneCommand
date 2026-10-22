"""Read-only release hygiene check. Never imports the app, AI or MIDI.

Scan the index with --staged before committing, or the committed tree with
--ref HEAD before publishing. Only filenames and rule names are reported;
suspected credential values are never printed. This is a tripwire, not a
replacement for GitHub secret scanning or a manual license/security review.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRS = {"kb", "backups", "designs", ".venv", ".testruns"}
PRIVATE_NAMES = {"ai_settings.json", "device_settings.json", "store_slots.json",
                 "outbox.json", "tone_dir.json", "tone3000_tokens.json",
                 "tone3000-account.dat", "amp_models.full.json", "cab_models.full.json"}
PRIVATE_SUFFIXES = {".syx", ".blk", ".fasbundle", ".nam", ".pem", ".key"}
SECRET_PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    "provider-key": re.compile(r"\bsk-(?:proj-|ant-api)[A-Za-z0-9_-]{40,}\b"),
    "literal-account-token": re.compile(
        r'''["'](?:access_token|refresh_token|client_secret)["']\s*:\s*["']([A-Za-z0-9_.-]{32,})["']'''),
}


def private_path(path: str) -> bool:
    parts = path.replace("\\", "/").lower().split("/")
    return (bool(set(parts) & PRIVATE_DIRS) or parts[:2] == ["devices", "learned"]
            or parts[-1] in PRIVATE_NAMES
            or parts[-1] == ".env" or parts[-1].startswith(".env.")
            or Path(parts[-1]).suffix in PRIVATE_SUFFIXES)


def inspect_blob(path: str, content: bytes) -> list[str]:
    failures = ["private-artifact"] if private_path(path) else []
    text = content.decode("utf-8", errors="replace")
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            failures.append(name)
    return failures


def _git(root: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return proc.stdout


def audit(root: Path = ROOT, *, staged: bool = False, ref: str = "HEAD") -> list[dict]:
    if staged:
        entries = _git(root, "ls-files", "--stage", "-z").split(b"\0")
        files = []
        for entry in filter(None, entries):
            meta, name = entry.split(b"\t", 1)
            mode, oid, stage = meta.split()
            files.append((name.decode("utf-8"), oid.decode(), mode.decode(), stage.decode()))
    else:
        entries = _git(root, "ls-tree", "-r", "-z", ref).split(b"\0")
        files = []
        for entry in filter(None, entries):
            meta, name = entry.split(b"\t", 1)
            mode, kind, oid = meta.split()
            files.append((name.decode("utf-8"), oid.decode(), mode.decode(), "0"))
    failures = []
    for path, oid, mode, stage in files:
        if stage != "0":
            failures.append({"path": path, "rules": ["unresolved-index"]})
            continue
        if mode == "160000":
            failures.append({"path": path, "rules": ["unaudited-submodule"]})
            continue
        issues = inspect_blob(path, _git(root, "cat-file", "blob", oid))
        if issues:
            failures.append({"path": path, "rules": issues})
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true")
    group.add_argument("--ref", default="HEAD")
    args = parser.parse_args(argv)
    for failure in (failures := audit(staged=args.staged, ref=args.ref)):
        print(f"BLOCKED {failure['path']}: {', '.join(failure['rules'])}")
    print("Release tripwire: " + ("FAILED" if failures else "PASS (manual review still required)"))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())

"""Report upstream drift without changing code, branches, settings or hardware.

Default is offline. --fetch only refreshes the expected upstream/main Git ref.
An audited commit is NOT an integrated or hardware-verified version.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode:
        raise ValueError(f"Git operation failed: {args[0]} (exit {proc.returncode})")
    return proc.stdout.strip()


def classify(path: str, rules: list[dict]) -> tuple[str, str]:
    for rule in rules:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in rule["paths"]):
            return rule["name"], rule["policy"]
    return "unclassified", "manual-review"


def report(root: Path = ROOT, *, fetch: bool = False, target: str = "upstream/main") -> dict:
    manifest = json.loads((root / "config/axefx3_upstream.json").read_text(encoding="utf-8"))
    if fetch:
        # No arbitrary remote, token-bearing URL, reset, checkout or merge.
        if git(root, "remote", "get-url", "upstream") != manifest["upstream_url"]:
            raise ValueError("Refused fetch: upstream URL differs from the maintenance manifest")
        git(root, "fetch", "--no-tags", "upstream", manifest["upstream_branch"])
    # Resolve user input as a revision, never as an option or a filename.
    sha = git(root, "rev-parse", "--verify", "--end-of-options", target + "^{commit}")
    audited = manifest["audited_commit"]
    foundation = manifest["integration_foundation"]
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (sha, audited, foundation)):
        raise ValueError("Maintenance manifest must use full commit hashes")
    toml = git(root, "show", f"{sha}:pyproject.toml")
    version = re.search(r'^version\s*=\s*"([^"]+)"', toml, re.M)
    # Compare from the known integration foundation, not from an old fork's
    # HEAD: otherwise equivalent custom ports are mistaken for missing features.
    paths = git(root, "diff", "--name-only", foundation, sha).splitlines()
    local = set(git(root, "diff", "--name-only", foundation, "HEAD").splitlines())
    work = set(git(root, "diff", "--name-only", "HEAD").splitlines())
    incoming = []
    for path in paths:
        name, policy = classify(path, manifest["rules"])
        incoming.append({"path": path, "group": name, "policy": policy,
                         "overlaps_local": path in local or path in work})
    return {
        "target_commit": sha, "target_version": version.group(1) if version else "unknown",
        "audited_commit": audited, "new_since_audit": sha != audited,
        "integration_foundation": foundation,
        "foundation_in_head": git(root,"rev-list","--count",f"HEAD..{foundation}") == '0',
        "integration_status": manifest["integration_status"],
        "new_commit_count": int(git(root, "rev-list", "--count", f"{audited}..{sha}")),
        "tracked_worktree_dirty": bool(git(root, "status", "--porcelain", "--untracked-files=no")),
        "incoming": incoming,
        "notice": "Comparison only. No merge, deployment, AI request or hardware verification.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--target", default="upstream/main")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = report(fetch=args.fetch, target=args.target)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"Cannot inspect upstream: {exc}")
        return 2
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Upstream {data['target_version']} at {data['target_commit'][:12]}")
        print(f"New since audit: {data['new_commit_count']} commits; {data['integration_status']}")
        if not data['foundation_in_head']:
            print('WARNING: declared integration foundation is not an ancestor of this checkout HEAD.')
        groups = {}
        for entry in data["incoming"]:
            key = (entry["group"], entry["policy"])
            groups.setdefault(key, []).append(entry)
        for (group, policy), entries in sorted(groups.items()):
            overlap = sum(entry["overlaps_local"] for entry in entries)
            print(f"  {group}: {len(entries)} files, {overlap} local overlaps; {policy}")
        print(data["notice"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

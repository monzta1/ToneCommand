"""Epic H (#106): local, secret-scrubbed error logging (#107) and a
voluntary "share this error" package (#108).

Two small pieces of operational hygiene, nothing more:

1. Errors get logged locally so failures can be learned from. Structured,
   scoped, and pruned to a retention window, so the file does not grow
   forever and does not become an undeclared record of everything a player
   ever did. Nothing here reaches a network - this module makes no HTTP
   request of any kind - so nothing is uploaded anywhere by default.
2. If a player wants to help fix a specific bug, they can package that same
   scoped, scrubbed log into a pre-filled GitHub issue and review it before
   anything is sent. Sharing is their action, never this module's: the
   packaging function returns text and a URL, it does not open a browser,
   make a request, or otherwise transmit anything on its own.

WHAT GETS SCRUBBED. Anything shaped like a credential: an Anthropic key
(sk-ant-...), a generic long API-key-looking token, an Authorization/Bearer
header value, and a KEY=VALUE line for any *_API_KEY/*_TOKEN/*_SECRET name -
the same env vars fm9/planner.py and fm9/ai_settings.py already read
(ANTHROPIC_API_KEY, PLANNER_API_KEY, XAI_API_KEY, GROK_API_KEY, ...).
Scrubbing runs on write, so a secret that never should have been in a log
message is never persisted to begin with, not filtered out later on read.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

#: Where entries live. Overridable (tests use a tmp_path), local to the
#: machine, never a server. `~` so it survives outside any one repo clone.
DEFAULT_LOG_PATH = Path.home() / ".tonecommand" / "diagnostics.jsonl"

#: How long a scrubbed entry is worth keeping around to learn from before it
#: is just accumulated noise. Matches this project's own log-retention
#: convention elsewhere (14 days).
RETENTION_DAYS = 14

REPO = "monzta1/ToneCommand"

_SECRET_PATTERNS = [
    # Anthropic API keys: sk-ant-<...>
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    # generic long API-key-shaped tokens (OpenAI-style and similar)
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    # an Authorization/Bearer header value
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-.=]{8,}"),
    # KEY=VALUE / "key": "VALUE" for anything credential-shaped by name
    re.compile(r'(?i)\b([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|AUTH_TOKEN))'
               r'(["\']?\s*[:=]\s*["\']?)([^\s"\',}]{4,})'),
]

#: Patterns that mask the whole match rather than keeping a key name.
#: Google's keys are `AIza` plus 35 characters and carry no `sk-` prefix and
#: no `API_KEY=` around them when they appear inside a URL or an error, so
#: none of the four above caught them. The report that prompted all of this
#: came from a Gemini user, which is as direct a warning as these things get.
#: GitHub's tokens are here for the same reason: the publisher PAT would
#: otherwise travel in a log line.
_SECRET_PATTERNS += [
    re.compile(r"\bAIza[A-Za-z0-9_\-]{30,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
]

REDACTED = "[REDACTED]"

#: Built once, at import, from this machine's own home directory.
_HOME_PATTERN = re.compile(re.escape(str(Path.home())))


def scrub_text(text: str) -> str:
    """Mask anything credential-shaped in a string. Never raises: diagnostics
    must never be the reason a real error is lost."""
    if not isinstance(text, str):
        return text
    out = text
    for pat in _SECRET_PATTERNS[:3]:
        out = pat.sub(REDACTED, out)
    # the KEY=VALUE pattern keeps the key name, redacts only the value
    out = _SECRET_PATTERNS[3].sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
    for pat in _SECRET_PATTERNS[4:]:
        out = pat.sub(REDACTED, out)
    # A home directory is not a credential, but it is a real name and a real
    # username on a public issue. The path shape is what diagnoses a problem,
    # not whose machine it is.
    out = _HOME_PATTERN.sub("~", out)
    return out


def scrub(obj):
    """Recursively scrub a string, dict, or list. Anything else (numbers,
    bools, None) is returned as-is; there is nothing secret-shaped in them."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub(v) for v in obj]
    return obj


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a corrupt line is skipped, not fatal
    return out


def prune_expired(path: Path = DEFAULT_LOG_PATH, now: float | None = None,
                   retention_days: int = RETENTION_DAYS) -> int:
    """Drop entries older than the retention window. Returns how many were
    removed. Safe to call on an empty or missing file."""
    now = time.time() if now is None else now
    cutoff = now - retention_days * 86400
    entries = _load(path)
    kept = [e for e in entries if e.get("ts", 0) >= cutoff]
    removed = len(entries) - len(kept)
    if removed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(e) + "\n" for e in kept), encoding="utf-8")
    return removed


def log_error(scope: str, message: str, path: Path = DEFAULT_LOG_PATH,
              **context) -> dict:
    """Append one scrubbed, structured entry. `scope` names the subsystem
    (e.g. "planner", "server") so entries are filterable later; `context`
    is free-form extra detail (e.g. backend name, action kind) and is
    scrubbed exactly like `message`.

    Never raises: a failure to log a diagnostic must not become a second,
    unrelated error on top of the first one.
    """
    entry = {
        "ts": time.time(),
        "scope": scrub_text(str(scope)),
        "message": scrub_text(str(message)),
        "context": scrub(dict(context)),
    }
    try:
        prune_expired(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    return entry


def read_recent(scope: str | None = None, limit: int = 20,
                 path: Path = DEFAULT_LOG_PATH) -> list[dict]:
    """The most recent entries, newest first, optionally filtered by scope.
    Read-only; does not prune (log_error already prunes on write)."""
    entries = _load(path)
    if scope is not None:
        entries = [e for e in entries if e.get("scope") == scope]
    return list(reversed(entries))[:limit]


def environment() -> list[str]:
    """The four questions a maintainer always has to ask, answered up front.

    Every line here is free to collect and is the difference between a report
    that can be acted on and one that starts a correspondence. The planner's
    model NAME is included and its key never is: the name is the diagnosis,
    the key is a credential, and conflating them is how a secret ends up on a
    public issue.

    Nothing in here raises. A report from a half-broken install is the one
    that matters most, so every lookup falls back to saying it could not be
    read rather than taking the report down with it.
    """
    import platform
    import sys as _sys
    lines = []

    def safe(label, fn):
        try:
            value = fn()
        except Exception:      # noqa: BLE001  a report must survive a broken install
            value = "could not be read"
        lines.append(f"{label}: {value}")

    safe("ToneCommand", _version_line)
    safe("OS", lambda: f"{platform.system()} {platform.release()} "
                       f"({platform.machine()})")
    safe("Python", lambda: _sys.version.split()[0])
    safe("Install", _install_kind)
    safe("Planner", _planner_line)
    safe("Device", _device_line)
    # #212: what is on the MIDI bus, by name. An FM3 owner's report said
    # only "Device: fm9", which could not tell a missing device from one
    # named differently than expected. Names only: nothing is opened.
    safe("MIDI in", lambda: _names(_midi().port_names()))
    safe("MIDI out", lambda: _names(_midi().output_names()))
    safe("Detected", _detected_line)
    return lines


def _midi():
    from fm9 import midi_transport
    return midi_transport


def _names(names) -> str:
    return ", ".join(repr(str(n)) for n in names) if names else "none"


def _detected_line() -> str:
    import server
    found = server.detected_devices()
    if not found:
        return "nothing recognised"
    return ", ".join(d["label"] + ("" if d.get("supported") else " (not supported yet)")
                     + (" (read-only)" if d.get("read_only") else "") for d in found)


def _version_line() -> str:
    # #212: the version the update banner uses, which reads pyproject.toml in
    # a checkout. Installed metadata only moves when `pip install -e .` is
    # re-run, so after a git pull it named an older release.
    from fm9 import updates
    try:
        v = updates.current_version()
    except Exception:          # noqa: BLE001  not installed as a distribution
        v = "unknown"
    import subprocess
    root = Path(__file__).resolve().parent.parent
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=5
                             ).stdout.strip()
    except Exception:          # noqa: BLE001  a wheel install has no git
        sha = ""
    return f"{v}" + (f" ({sha})" if sha else "")


def _install_kind() -> str:
    """#177: an editable install and a wheel behave differently, because
    config/, ui/ and recipes/ are repo-root data the wheel does not carry."""
    root = Path(__file__).resolve().parent.parent
    return "editable (repo)" if (root / "pyproject.toml").is_file() else "wheel"


def _planner_line() -> str:
    """Backend and model NAME. Never the key."""
    from fm9 import ai_settings, planner
    cfg = ai_settings.load()
    backend = cfg.backend or "auto"
    model = cfg.model_for(cfg.backend or None) or "auto"
    # Which backends the planner would actually try, in order. "configured"
    # and "reachable" are different answers and the second is the useful one.
    try:
        order = ", ".join(planner.candidates())
    except Exception:          # noqa: BLE001  the list is a courtesy
        order = "could not be read"
    return f"{backend}, model {model}; would try: {order}"


def _device_line() -> str:
    import server
    ctx = server.device_context()
    # #212: whether a handle to the device is open right now. The old check
    # called a function that does not exist, so this part never printed.
    if ctx.kind == "fm9":
        connected = getattr(server, "_fm9", None) is not None
    else:
        connected = ctx.adapter is not None
    fw = ""
    try:
        fw = ctx.adapter.firmware_label() if ctx.adapter else ""
    except Exception:          # noqa: BLE001  a device that declines is fine
        fw = ""
    label = server.DEVICE_KINDS.get(ctx.kind, ctx.kind)
    return f"{label} ({ctx.kind})" + (f", firmware {fw}" if fw else "") + \
           (", handle open" if connected else ", not connected")


def package_for_sharing(scope: str | None = None, limit: int = 10,
                         path: Path = DEFAULT_LOG_PATH,
                         note: str = "") -> dict:
    """Issue #108: build a pre-filled GitHub issue the player can REVIEW,
    never send. Every field here is already-scrubbed log content plus a
    defensive re-scrub, since a shared report is the one that leaves the
    machine and deserves the extra pass. This function performs no request
    of any kind; sending only happens if the player opens `url` themselves.
    """
    entries = read_recent(scope=scope, limit=limit, path=path)
    body_lines = []
    if (note or "").strip():
        # The player's own words first. A maintainer reads this before the
        # machine detail, and it is the only part the machine cannot supply.
        body_lines += ["**What happened**", "", (note or "").strip(), ""]
    body_lines += ["**Environment**", ""]
    body_lines += [f"- {line}" for line in environment()]
    body_lines += ["", "**Recent diagnostics**", ""]
    if not entries:
        body_lines.append("(no local diagnostics entries to include)")
    for e in entries:
        body_lines.append(f"- [{e.get('scope')}] {e.get('message')}")
        ctx = e.get("context") or {}
        if ctx:
            body_lines.append(f"  context: {json.dumps(ctx, sort_keys=True)}")
    body = scrub_text("\n".join(body_lines))
    # The player's own first line makes a better title than a count of log
    # entries ever did: an issue list full of "Diagnostics report (all, 10
    # entries)" is unreadable.
    first = (note or "").strip().splitlines()[0] if (note or "").strip() else ""
    title = scrub_text(f"Problem report: {first[:72]}" if first
                       else f"Problem report ({scope or 'all'}, "
                            f"{len(entries)} diagnostics)")
    from urllib.parse import quote
    url = (f"https://github.com/{REPO}/issues/new"
           f"?title={quote(title)}&body={quote(body)}")
    return {"title": title, "body": body, "url": url, "entry_count": len(entries)}

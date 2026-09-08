"""Optional bridge to IRCommand, the local IR database and matcher.

TONECOMMAND_IR_SERVICE pins the IRCommand service URL (for example
http://127.0.0.1:8770), and Settings can save one. When NEITHER is set, a
local service that is simply running is found automatically.

That default changed on 2026-09-07. It used to be off unless configured, on
the same empty-default-disabled pattern as the store and cab whitelists. The
difference is that those whitelists gate WRITES to hardware, where silence is
the safe answer, and this only gates whether the planner is told which cabs
the player owns. Nobody had configured it, so a Steve Vai build asked nothing
about the cab and said nothing about how one was chosen, with 7,655 analysed
IRs sitting on the machine unused. Requiring someone to paste a port number
into Settings to avoid that is the exposed machinery this product hides.

Discovery is loopback-only by construction rather than by check: the
candidates are literal 127.0.0.1 addresses. It never overrides a deliberate
choice, an empty URL saved from Settings still means OFF, and a miss is
silent, so a build never waits on it.

It is never a hard dependency. If the service is unset, down, or errors, every
call here returns None or "off" and the caller simply skips the IR step. The
matcher lives in a separate local project (~/Projects/ir-command); ToneCommand
only ever asks it for a cab and receives a name, path, tags and score.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse


class UnsafeServiceURL(ValueError):
    """Written for the person who typed the address into Settings."""


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "ir_service.json"


def allow_remote() -> bool:
    """Escape hatch for someone deliberately running IRCommand on another box."""
    return (os.environ.get("TONECOMMAND_IR_ALLOW_REMOTE") or "").strip() not in \
        ("", "0", "false", "no")


def check_url(url: str) -> str:
    """Return the URL if it is safe to have this server fetch, else raise.

    This is a security boundary, not tidiness. The server fetches whatever this
    points at, from inside the user's network, and `server.ir_context()` feeds
    the response into the planner's prompt. An arbitrary host would therefore
    get both a server-side request forgery primitive and a way to put text in
    front of the model. IRCommand is a local tool, so loopback is the whole
    supported surface.
    """
    if not url:
        return ""
    # urlparse itself raises on a malformed IPv6 bracket ("http://[bad/"), and
    # so does .hostname. Callers only catch UnsafeServiceURL, so a raw
    # ValueError escaping here turned a bad address into a 500 instead of a
    # refusal. Everything below must fail as UnsafeServiceURL and nothing else.
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").strip("[]")
    except ValueError as e:
        raise UnsafeServiceURL(f"that is not a usable address: {e}") from None
    if parsed.scheme not in ("http", "https"):
        raise UnsafeServiceURL(
            f"the IR service address must start with http://, got {url!r}")
    if not host:
        raise UnsafeServiceURL(f"no host in {url!r}")
    if allow_remote():
        return url
    if host in ("localhost", "localhost.localdomain"):
        return url
    try:
        if ipaddress.ip_address(host).is_loopback:
            return url
    except ValueError:
        pass
    raise UnsafeServiceURL(
        f"the IR service must be on this machine, not {host!r}. IRCommand runs "
        "locally, so use 127.0.0.1. Set TONECOMMAND_IR_ALLOW_REMOTE=1 only if "
        "you deliberately run it on another machine you trust.")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """A redirect is a second address this never validated, so it is refused
    rather than followed off-host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, f"refusing redirect to {newurl}", headers, fp)


_opener = urllib.request.build_opener(_NoRedirects)


def env_url() -> str:
    return (os.environ.get("TONECOMMAND_IR_SERVICE") or "").strip().rstrip("/")


#: Where IRCommand serves by default. Probed when nothing is configured, so
#: the player never has to know a port number exists.
DEFAULT_PORTS = (8770,)
_found: dict = {"url": None, "at": 0.0}
FIND_EVERY = 30.0


def discover() -> str:
    """The local IRCommand service, if one is simply running.

    Nothing was configured by default, so the bridge was off, so the planner
    was never told the player owns an IR library and never mentioned a cab.
    That is a real build reported on 2026-09-07: a Steve Vai preset where no
    question was asked about the cab and nothing was said about how one was
    chosen. Requiring someone to paste `http://127.0.0.1:8770` into Settings
    to avoid that is exactly the exposed machinery this product hides.

    Loopback only, by construction rather than by check: the candidates are
    literal 127.0.0.1 addresses, so discovery cannot reach anything else. The
    result is cached briefly, and a miss is silent, so a build never waits on
    this more than once every FIND_EVERY seconds.
    """
    now = time.monotonic()
    if _found["url"] is not None and now - _found["at"] < FIND_EVERY:
        return _found["url"]
    _found["at"] = now
    for port in DEFAULT_PORTS:
        url = f"http://127.0.0.1:{port}"
        try:
            with _opener.open(url + "/health", timeout=0.4) as r:
                got = json.loads(r.read(10_000).decode("utf-8", "replace"))
            if got.get("ok") and got.get("cabs"):
                _found["url"] = url
                return url
        except Exception:      # noqa: BLE001  not running is the normal case
            continue
    _found["url"] = ""
    return ""


def get_url() -> str:
    """The IRCommand service URL. The env var wins (an operator pin), else the
    URL saved from Settings, else a local service that is simply running, else
    empty. Same precedence as the store whitelist and tone folder, with
    discovery last so it can never override a deliberate choice.

    An empty string saved from Settings is a deliberate OFF and is respected:
    discovery only runs when nothing has been configured at all.
    """
    if env_url():
        return env_url()
    f = _config_path()
    if f.exists():
        try:
            got = json.loads(f.read_text())
            if isinstance(got, dict) and isinstance(got.get("url"), str):
                return got["url"].strip().rstrip("/")   # "" means OFF on purpose
        except (ValueError, OSError):
            pass
    return discover()


def set_url(url: str) -> str:
    """Save the service URL from Settings. Empty turns the feature off.
    Refuses an address this server should not be fetching."""
    url = check_url((url or "").strip().rstrip("/"))
    _config_path().write_text(json.dumps({"url": url}) + "\n")
    return url


def base_url() -> str:
    """The service URL, re-validated at use.

    Checked here as well as at save time because the config file and the
    environment variable can both be edited outside the UI, and an operator pin
    is not automatically a safe address.
    """
    try:
        return check_url(get_url())
    except UnsafeServiceURL:
        return ""


def enabled() -> bool:
    return bool(base_url())


def _get(path: str, timeout: int = 3):
    """GET a JSON endpoint on the IR service, or None on anything going wrong.
    Never raises, so a missing or broken service can never break a build."""
    url = base_url()
    if not url:
        return None
    try:
        with _opener.open(url + path, timeout=timeout) as r:
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


def recommend(need: str, target: str = "fm9", k: int = 3,
              reference: str = None, preserve: str = None):
    """Best-matching IRs for a need, or None when off / unreachable / empty.

    Each result carries at least name, path, tags and score. When IRCommand has
    been analysed it also carries `match` (absolute quality, unlike `score`
    which is only relative to this result set) and `measured` band values.

    `reference` is the path of the cab the player is on now. With it, "darker"
    means darker THAN THAT rather than darker in the abstract, which is what
    people actually mean. Only available when the current cab is a file we own:
    a factory cab has no IR file, so there is nothing to measure it against.
    """
    if not enabled() or not (need or "").strip():
        return None
    q = f"/ir/recommend?need={quote(need)}&target={quote(target)}&k={int(k)}"
    if reference:
        q += f"&reference={quote(reference)}"
    if preserve:
        q += f"&preserve={quote(preserve)}"
    d = _get(q)
    if not d or "results" not in d:
        return None
    return d["results"]


def linked_source(bank, ordinal):
    """The exact source file a USER cab slot was installed from, or None.

    IDENTITY, NOT A SEARCH. This used to search the library for the slot's
    display label and take the first row containing all its distinctive words.
    That is ranking, and ranking cannot establish identity: two captures from
    the same product, speaker, mic and pack share every token, so the search
    could return a plausible and WRONG reference, which is more dangerous than
    no reference at all. Every relative claim would then be measured against a
    cab the player has never heard, undetectably (brief 26.1).

    A slot is `measured` only when ToneCommand itself recorded where the file
    came from at install time. `user_cabs.json` may hold either shape:

        "26": "Soldano SLO30 - Emil Rohbe"          legacy, a DISPLAY LABEL
        "26": {"label": "...", "source": "/abs/path/x.wav", "digest": "..."}

    A bare string is a label and nothing more. It names the slot in the UI and
    never becomes an anchor. A cab installed by any other tool stays unresolved
    until the player links it deliberately; a name search may offer relink
    CHOICES, but it may not establish the anchor by itself.
    """
    from fm9 import user_cabs
    rec = user_cabs.record(bank, ordinal) if hasattr(user_cabs, "record") else None
    if not isinstance(rec, dict):
        return None                     # legacy label only: displayable, unresolved
    src = (rec.get("source") or "").strip()
    if not src:
        return None
    p = Path(src)
    if not p.is_file():
        return None                     # the file moved or went away

    # EXISTENCE IS NOT IDENTITY. Until 2026-09-08 this returned here, so a
    # record naming any readable file on the machine, with any digest or
    # none, made the loaded cab `measured` and licensed numeric "x dB from
    # current" claims against it. Proven with
    # {"source": "/etc/hosts", "digest": "definitely-wrong"}, which came back
    # measured. Two things have to hold, and neither is about the name.
    #
    # 1. The bytes are still the bytes that were linked. A digest recorded at
    #    link time and never checked records nothing; a re-exported or
    #    replaced file keeps the path and changes the sound.
    if digest_of(p) != (rec.get("digest") or ""):
        return None
    # 2. IRCommand holds a measured curve for this exact path. That is the
    #    entire content of the word `measured`, and it is the only place that
    #    can answer it, so a service that is off or down means unresolved
    #    rather than assumed. Erring toward gear_anchored costs a numeric
    #    delta; erring toward measured quotes a distance from a curve nobody
    #    has.
    known = _get(f"/ir/measured?path={quote(src)}", timeout=2)
    if not (known or {}).get("measured"):
        return None
    return {"path": src, "digest": rec.get("digest"),
            "analysis": rec.get("analysis")}


def digest_of(path) -> str:
    """sha256 of a file's bytes, or "" if it cannot be read.

    The one definition, so the link side and the check side cannot drift into
    hashing different things. Streamed: an IR is small but a mis-set source
    path may not be.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def intent(text: str) -> dict:
    """What IRCommand's PARSER makes of a request, before any ranking.

    ToneCommand needs exactly one thing from it: whether the player asked to
    KEEP what they have. That decision used to be made from a second copy of
    the cue list, written out in server.py alongside a comment saying the
    matcher was authoritative. It was not; it was duplicated, and a cue added
    on one side would silently stop working on the other.

    Returns {} when the service is off, down or slow, and the caller treats
    that as "not asked for": applying a hard preserve constraint on a guess
    would exclude every candidate that is not the cab already loaded.
    """
    text = (text or "").strip()
    if not enabled() or not text:
        return {}
    return _get(f"/ir/intent?q={quote(text)}", timeout=2) or {}


def gaps_online(need: str, target: str = "fm9", k: int = 3):
    """Captures on TONE3000 for a need the OWNED library cannot answer.

    IRCommand decides whether to look outward at all: it only searches when
    the request parsed into real gear terms AND the best owned match is still
    weak, because a low score on an artist name means the request was not
    understood rather than that the shelf is empty.

    Returns [] rather than None when there is simply nothing to add, so a
    caller can treat it as "checked, no gap" instead of "did not check".
    """
    if not enabled() or not (need or "").strip():
        return []
    # 3 seconds, not 8. This runs BEFORE the planner starts, so every second
    # here is a second added to a build, and a cab the player does not own yet
    # is the most optional thing in the request. Measured: 0.88s when it fires
    # and 0.03s when it does not. A miss is silent, so a slow or dead TONE3000
    # costs three seconds once rather than holding up the build.
    d = _get(f"/ir/recommend?need={quote(need)}&target={quote(target)}"
             f"&k={int(k)}", timeout=3)
    return (d or {}).get("online") or []


def blend_partners(path: str, k: int = 5):
    """IRs that combine well with this one, and the alignment each needs.

    Blending is the real answer to a single-mic capture that lacks presence,
    and whether a blend works is decided by a sub-millisecond time alignment
    that nothing else computes. Returns None when off, unreachable, or when
    the library has not been analysed.
    """
    if not enabled() or not path:
        return None
    d = _get(f"/ir/blend?path={quote(path)}&k={int(k)}", timeout=30)
    if not d or "results" not in d:
        return None
    return d["results"]

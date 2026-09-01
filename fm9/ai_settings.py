"""Which planner backend to use, chosen in the UI rather than in a file.

Selecting a backend used to mean editing .env and restarting the server, and
knowing which one answered meant reading a log. This holds the choice instead.

Deliberately does NOT change how the planner decides anything. The planner
already reads its configuration from the environment and from .env
(planner._env), so applying a saved choice means writing those same variables
into this process, and the planner behaves exactly as it does when configured
by hand. Precedence therefore falls out for free, highest first:

    the settings file  >  the environment (including .env)  >  built-in default

Two rules make that precedence real rather than nominal. This module only
removes a variable it put there itself, and it only persists what the user
typed into the panel. Anything else and the file quietly absorbs the
environment it was supposed to sit above.

Each backend reads DIFFERENT variables, and two of them read none at all, so
settings are stored per backend and the UI is told which fields a backend
actually uses. Offering a box that silently does nothing is the same sin as
offering a backend that silently falls through to another one:

    cli     CLAUDE_CLI_MODEL.
    api     ANTHROPIC_API_KEY, CLAUDE_API_MODEL.
    grok    GROK_CLI_MODEL.
    openai  PLANNER_BASE_URL, PLANNER_MODEL, PLANNER_API_KEY (key optional).

API keys never travel outward: `public()` reports whether one exists and
never what it is.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import planner

#: CLIProxyAPI's default, prefilled for the OpenAI-compatible choice.
CLIPROXY_DEFAULT_URL = planner.CLIPROXY_DEFAULT_URL
LOCAL_LLM_DEFAULT_URL = "http://127.0.0.1:1234/v1"      # LM Studio

#: Named services behind the "OpenAI-compatible endpoint" choice.
#:
#: That name is accurate and useless: it describes a protocol, and somebody
#: who wants to use ChatGPT does not know that ChatGPT speaks it, let alone
#: that the answer to type is "https://api.openai.com/v1". An empty box with
#: no clue in it is a dead end for everyone except the person who wrote it.
#: So the services are NAMED, and picking one fills the box in.
#:
#: No model ids here on purpose: the panel lists the real ones from the
#: endpoint's own /models once a URL is set, and a hardcoded id is wrong the
#: day the provider retires it.
ENDPOINT_PRESETS = [
    {
        "name": "ChatGPT",
        "url": "https://api.openai.com/v1",
        "key": "required",
        "help": "Needs a paid OpenAI API key from platform.openai.com. That "
                "is a separate account from ChatGPT Plus, and it bills per "
                "request on top of any subscription you already pay for.",
    },
    {
        "name": "A subscription you already pay for",
        "url": CLIPROXY_DEFAULT_URL,
        "key": "no",
        "help": "Run CLIProxyAPI and log it into ChatGPT/Codex, Gemini, Grok "
                "or Kimi. It signs in the normal way and costs nothing extra "
                "per request. Start it before you send a prompt.",
    },
    {
        "name": "A model on this laptop",
        "url": LOCAL_LLM_DEFAULT_URL,
        "key": "no",
        "help": "LM Studio's default address. Free and offline, but small "
                "local models get the plan format wrong more often.",
    },
    {
        "name": "OpenRouter",
        "url": "https://openrouter.ai/api/v1",
        "key": "required",
        "help": "One key, many providers, billed per request.",
    },
]

BACKEND_LABELS = {
    "": "auto (let the planner choose)",
    "cli": "Claude Code CLI",
    "api": "Claude API",
    "grok": "Grok CLI",
    "openai": "ChatGPT, or another service you choose",
}

#: The same names with the explanation trimmed off, for places with no room to
#: explain: a header button, a status line. The full label reads like a
#: sentence because a dropdown has space for one; a pill does not, and
#: truncating the long form with an ellipsis produces "auto (let the plan...",
#: which is worse than either. Kept here rather than in the browser so a
#: backend is still named in exactly one place.
BACKEND_SHORT = {
    "": "auto",
    "cli": "Claude CLI",
    "api": "Claude API",
    "grok": "Grok",
    "openai": "custom endpoint",
}

#: Which controls each backend genuinely honours, and the variable behind each.
BACKEND_FIELDS = {
    # Auto reads the same three as openai: a configured router is the first
    # candidate the planner tries (#21), so a base URL still matters here.
    "": {"baseUrl": "PLANNER_BASE_URL", "model": "PLANNER_MODEL",
         "key": "PLANNER_API_KEY"},
    "cli": {"baseUrl": None, "model": "CLAUDE_CLI_MODEL", "key": None},
    "api": {"baseUrl": None, "model": "CLAUDE_API_MODEL",
            "key": "ANTHROPIC_API_KEY"},
    "grok": {"baseUrl": None, "model": "GROK_CLI_MODEL", "key": None},
    "openai": {"baseUrl": "PLANNER_BASE_URL", "model": "PLANNER_MODEL",
               "key": "PLANNER_API_KEY"},
}

#: Model boxes can always be left blank: every backend has a default. Keys do
#: not reduce to a per-backend flag, because the Claude API cannot run without
#: one while an OAuth router wants none, so the panel states the whole rule in
#: the field itself.
MODEL_ALWAYS_OPTIONAL = True

#: Said out loud in the UI, because "no model box" invites the question.
BACKEND_NOTES = {
    "": "A configured endpoint is tried first, then the Claude CLI, then the "
        "Claude API. Leave the endpoint blank to use the CLI.",
    "cli": "Runs on your Claude subscription. Model optional; blank uses "
           "the planner default.",
    "api": "Runs on your Anthropic account, billed per request. Model "
           "optional; blank uses the planner default.",
    "grok": "Runs on your Grok subscription. Model optional; blank uses the "
            "CLI's own default.",
    "openai": "Pick a service above to fill in the address, or type your "
              "own. Any OpenAI-compatible server works. A key is often "
              "not needed.",
}

_MANAGED = ("PLANNER_BACKEND", "PLANNER_BASE_URL", "PLANNER_MODEL",
            "PLANNER_API_KEY", "GROK_CLI_MODEL", "ANTHROPIC_API_KEY",
            "CLAUDE_CLI_MODEL", "CLAUDE_API_MODEL")


def settings_path() -> Path:
    """Where the choice is stored. Gitignored; overridable for tests."""
    override = os.environ.get("TONECOMMAND_AI_SETTINGS", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "ai_settings.json"


@dataclass
class AiSettings:
    backend: str = ""          # "" means "let the planner decide as it always has"
    base_url: str = ""
    models: dict = field(default_factory=dict)   # backend -> model
    keys: dict = field(default_factory=dict)     # backend -> key
    #: Whether `backend` is a CHOICE or merely the absence of one. Auto is a
    #: choice, and an empty string cannot carry that on its own: without this
    #: flag, picking Auto was indistinguishable from never having opened the
    #: panel, so a PLANNER_BACKEND pin in .env could not be cleared from here.
    backend_explicit: bool = False

    def model_for(self, backend: str | None = None) -> str:
        want = self.backend if backend is None else backend
        return self.models.get(want or "openai", "")

    def key_for(self, backend: str | None = None) -> str:
        want = self.backend if backend is None else backend
        return self.keys.get(want or "openai", "")

    def public(self) -> dict:
        """What the browser may see. Keys never leave this process."""
        return {"backend": self.backend, "baseUrl": self.base_url,
                "model": self.model_for(), "hasKey": bool(self.key_for())}


def _from_env() -> AiSettings:
    """Seed from however the user has configured things by hand."""
    return AiSettings(
        backend=planner._env("PLANNER_BACKEND").lower(),
        base_url=planner._env("PLANNER_BASE_URL"),
        models={k: v for k, v in
                (("openai", planner._env("PLANNER_MODEL")),
                 ("grok", planner._env("GROK_CLI_MODEL")),
                 ("cli", planner._env("CLAUDE_CLI_MODEL")),
                 ("api", planner._env("CLAUDE_API_MODEL"))) if v},
        keys={k: v for k, v in
              (("openai", planner._env("PLANNER_API_KEY")),
               ("api", planner._env("ANTHROPIC_API_KEY"))) if v},
    )


def _from_file() -> AiSettings:
    """Only what is actually stored, with nothing underneath it.

    Anything written BACK to the file has to be seeded from here rather than
    from the merged view. Seeding a save from load() copies the user's shell
    and .env values into the file, and since the file outranks both, a later
    edit of .env silently stops taking effect - which for an API key is a
    genuinely horrible thing to debug.
    """
    settings = AiSettings()
    path = settings_path()
    if not path.exists():
        return settings
    try:
        stored = json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return settings                   # a corrupt file must not brick startup
    if not isinstance(stored, dict):
        return settings
    if isinstance(stored.get("backend"), str):
        settings.backend = stored["backend"].lower()
        settings.backend_explicit = True
    if isinstance(stored.get("baseUrl"), str):
        settings.base_url = stored["baseUrl"]
    for attr in ("models", "keys"):
        blob = stored.get(attr)
        if isinstance(blob, dict):
            setattr(settings, attr, {k: v for k, v in blob.items()
                                     if isinstance(v, str) and v})
    return settings


def load() -> AiSettings:
    """The stored choice, falling back to the environment then the default."""
    settings = _from_env()
    stored = _from_file()
    if stored.backend_explicit:
        settings.backend = stored.backend        # including "" for Auto
        settings.backend_explicit = True
    if stored.base_url:
        settings.base_url = stored.base_url
    for attr in ("models", "keys"):
        merged = dict(getattr(settings, attr))
        merged.update(getattr(stored, attr))
        setattr(settings, attr, merged)
    return settings


def _write_private(path: Path, text: str) -> None:
    """Write a file only its owner can read.

    This file holds an API key. `Path.write_text` creates with the process
    umask, commonly 0644, so on a shared machine every other local account
    could read it. Unlike `.env`, which the user creates and chmods
    themselves, this one is created by the app, so the mode is ours to get
    right. An existing world-readable file is tightened on the next save
    rather than left as found. (Patch from @Triumph1701 on #25.)
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode())
    finally:
        os.close(fd)
    os.chmod(path, 0o600)          # a pre-existing file keeps its old mode


def save(patch: dict) -> AiSettings:
    """Apply a POST body and persist it.

    A blank or absent key KEEPS whatever is stored for that backend; removing
    one takes an explicit clearKey. Anything else and a user who edits the base
    URL loses their key without being told. Values are stored per backend, so
    an OpenAI router key can never quietly become an Anthropic one.

    Only what the panel sent is persisted. The file is seeded from the file,
    never from load(), because load() has the shell and .env merged into it
    and the file outranks both: seeding from the merged view copied an
    exported ANTHROPIC_API_KEY into ai_settings.json on a save that had
    nothing to do with keys, and then pinned it there.
    """
    stored = _from_file()
    backend = str(patch.get("backend", stored.backend) or "").lower()
    # Sending the field at all is a choice, Auto included.
    explicit = "backend" in patch or stored.backend_explicit
    if backend and backend not in planner.BACKENDS:
        raise ValueError(f"unknown backend {backend!r}; "
                         f"expected one of {', '.join(planner.BACKENDS)}")
    fields = BACKEND_FIELDS.get(backend, {})
    slot = backend or "openai"          # auto shares openai's variables
    models, keys = dict(stored.models), dict(stored.keys)

    if fields.get("model"):
        if "model" in patch:
            new_model = str(patch.get("model") or "")
            models[slot] = new_model
            if not new_model:
                models.pop(slot, None)
    if fields.get("key"):
        if patch.get("clearKey"):
            keys.pop(slot, None)
        elif str(patch.get("apiKey") or ""):
            keys[slot] = str(patch["apiKey"])

    base_url = (str(patch.get("baseUrl", stored.base_url) or "")
                if fields.get("baseUrl") else stored.base_url)
    updated = AiSettings(backend=backend, base_url=base_url,
                         models=models, keys=keys, backend_explicit=explicit)
    _check_runnable(backend, updated)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_private(path, json.dumps(
        {"backend": updated.backend, "baseUrl": updated.base_url,
         "models": updated.models, "keys": updated.keys}, indent=2) + "\n")
    apply_to_env(updated)
    return updated


def missing_setup(backend: str, settings: AiSettings | None = None) -> str:
    """What a backend still needs before it can run, in the user's words.

    Only about things the panel itself can fix. Whether a binary is on the
    machine is not in here; that is a fact about the host.
    """
    settings = load() if settings is None else settings
    if backend == "api" and not settings.key_for("api"):
        return "an Anthropic API key, in the key box"
    if backend == "openai" and not settings.base_url:
        return "an address"
    return ""


def _check_runnable(backend: str, updated: AiSettings) -> None:
    """Refuse a pinned backend that cannot answer, at the moment it is chosen.

    A pinned backend disables fallthrough by design (#21), so saving one that
    is not configured buys a failed prompt later instead of a sentence now.
    Checked against what will be in effect: the environment underneath, the
    about-to-be-written file on top. Not against load(), whose file layer is
    the one being replaced - a key just cleared would still be counted.
    """
    if not backend:
        return
    env = _from_env()
    merged = AiSettings(
        backend=backend, base_url=updated.base_url or env.base_url,
        models=updated.models,
        keys={**env.keys, **updated.keys})
    problem = missing_setup(backend, merged)
    if problem:
        raise ValueError(f"{BACKEND_LABELS[backend]} needs {problem}")


#: What this module has written into os.environ, and what stood there before
#: each write. Releasing a variable restores the user's own value instead of
#: deleting it, which is the difference between outranking and erasing.
_APPLIED: dict[str, tuple[str, str | None]] = {}


def _inject(name: str, value: str) -> None:
    prior = _APPLIED[name][1] if name in _APPLIED else os.environ.get(name)
    _APPLIED[name] = (value, prior)
    os.environ[name] = value


def _release(name: str) -> None:
    """Undo our own write, if it is still ours to undo."""
    written, prior = _APPLIED.pop(name, (None, None))
    if written is None or os.environ.get(name) != written:
        return                  # never ours, or changed by someone else since
    if prior is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = prior


def apply_to_env(settings: AiSettings | None = None) -> AiSettings:
    """Push the choice onto the planner's existing configuration surface.

    This is what makes a UI change take effect on the next prompt with no
    restart, without the planner needing to know this module exists. Only the
    variables the chosen backend reads are set.

    The rest are RELEASED, not cleared: only what this module wrote is
    removed, and what it displaced is put back. Clearing them took away
    configuration the user had set by hand, including the key the subprocess
    allowlist deliberately passes through.
    """
    settings = load() if settings is None else settings
    wanted = {}
    if settings.backend:
        wanted["PLANNER_BACKEND"] = settings.backend
    elif settings.backend_explicit:
        # Auto, chosen on purpose. Releasing the variable would re-expose a
        # pin in .env, and planner._env reads a PRESENT blank as deliberately
        # blank, so this is what "no pin" looks like on that channel.
        wanted["PLANNER_BACKEND"] = ""
    fields = BACKEND_FIELDS.get(settings.backend, {})
    if fields.get("baseUrl") and settings.base_url:
        wanted[fields["baseUrl"]] = settings.base_url
    if fields.get("model") and settings.model_for():
        wanted[fields["model"]] = settings.model_for()
    if fields.get("key") and settings.key_for():
        wanted[fields["key"]] = settings.key_for()
    for name in _MANAGED:
        if name in wanted:
            _inject(name, wanted[name])
        else:
            _release(name)
    return settings


#: Aliases the Claude CLI documents for --model. Suggestions, not a whitelist:
#: full ids like claude-fable-5 are accepted too, so the box stays free text.
CLAUDE_CLI_ALIASES = ("sonnet", "opus", "haiku", "fable")


def list_models(backend: str) -> dict:
    """Model ids to offer for a backend, and where they came from.

    Suggestions only. Every model box stays typeable, because a list that
    cannot be overridden is worse than no list the moment it goes stale.
    """
    backend = (backend or "openai").lower()
    if backend == "grok":
        found, why = _grok_models()
    elif backend == "openai":
        found, why = _endpoint_models()
    elif backend == "cli":
        found, why = list(CLAUDE_CLI_ALIASES), "aliases the claude CLI documents"
    elif backend == "api":
        found, why = _anthropic_models()
    else:
        found, why = [], ""
    return {"backend": backend, "models": found, "source": why}


def _anthropic_models() -> tuple[list[str], str]:
    """Ask Anthropic, rather than shipping a list of ids that will age.

    That backend needs a key to run at all, so when one is configured there
    is nothing to save by guessing. With no key, offer the planner default
    and say that is what it is.
    """
    key = load().key_for("api") or planner._env("ANTHROPIC_API_KEY")
    if not key:
        return [planner.MODEL], "the planner default; add a key to list models"
    try:
        import anthropic
        # Bounded like the other two listers (20s for grok, 10s here). The
        # SDK's default is generous and it retries on top of it, so a hung
        # network otherwise pins a threadpool worker and the panel looks
        # frozen rather than slow.
        client = anthropic.Anthropic(api_key=key, timeout=10.0, max_retries=1)
        listing = client.models.list(limit=20)
        found = [m.id for m in listing.data if getattr(m, "id", None)]
    except Exception as exc:                    # offline, bad key, old SDK
        return ([planner.MODEL],
                f"could not list models ({type(exc).__name__}); showing the default")
    return (found, "the Anthropic models API") if found else (
        [planner.MODEL], "the API listed nothing; showing the default")


def _grok_models() -> tuple[list[str], str]:
    """Ask the grok CLI. It has a `models` subcommand for exactly this."""
    import subprocess
    binary = planner.find_grok_cli()
    if not binary:
        return [], "the grok binary is not on this machine"
    try:
        proc = subprocess.run([binary, "models"], capture_output=True,
                              text=True, timeout=20, cwd="/tmp",
                              env=planner.cli_env(planner.GROK_ENV_KEYS))
    except (subprocess.TimeoutExpired, OSError) as exc:
        return [], f"grok models failed: {exc}"
    found = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(("*", "-")):
            name = stripped.lstrip("*- ").split(" ")[0].strip()
            if name:
                found.append(name)
    return found, "grok models" if found else (
        [], "grok models listed nothing")[1]


def _endpoint_models() -> tuple[list[str], str]:
    """Ask the configured endpoint. /models is part of the OpenAI shape."""
    import json as _json
    import urllib.error
    import urllib.request
    base = load().base_url or planner._openai_base_url()
    if not base:
        return [], "set a base URL first"
    req = urllib.request.Request(f"{base.rstrip('/')}/models", method="GET")
    key = load().key_for("openai")
    if key:
        req.add_header("authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, ValueError,
            _json.JSONDecodeError) as exc:
        return [], f"could not reach {base}: {exc}"
    entries = data.get("data") if isinstance(data, dict) else None
    found = [e["id"] for e in entries or []
             if isinstance(e, dict) and isinstance(e.get("id"), str)]
    return found, f"{base}/models" if found else "the endpoint listed no models"


def panel_state() -> dict:
    """What the panel shows: stored values in the boxes, the environment's as
    placeholders, and the effective backend selected.

    The key box already had this shape: empty, with `hasKey` reporting that
    one exists. The base URL and model boxes need it for the same reason, so
    that saving cannot pin a value the user never typed.
    """
    effective, stored, env = load(), _from_file(), _from_env()
    return {"backend": effective.backend,
            "baseUrl": stored.base_url,
            "baseUrlFallback": env.base_url,
            "hasKey": bool(effective.key_for())}


def available_backends() -> list[dict]:
    """Which backends this host can run, which controls each one honours, and
    why an unusable one is unusable.

    A dead option that silently falls through to something else is worse than
    no option, and so is a control that silently does nothing.
    """
    settings = load()
    stored, env = _from_file(), _from_env()
    # Disabled means "you cannot fix this from this panel". A missing binary
    # is a fact about the host. A missing key or base URL is a box on this
    # very form, and disabling the option that reveals the box is a closed
    # loop: you need the key to pick Claude API, and you need Claude API
    # picked to enter the key (@Triumph1701 on #25). Those are selectable and
    # say what they still need; save() refuses if it is still missing.
    usable = {
        "openai": True,
        "cli": planner.find_claude_cli() is not None,
        "grok": planner.find_grok_cli() is not None,
        "api": True,
    }
    reasons = {
        "cli": "the claude binary is not on this machine",
        "grok": "the grok binary is not on this machine",
    }
    out = []
    # "" (auto) is listed first and is always available: it is the behaviour a
    # fresh install has. It carries fields because a configured endpoint is the
    # planner's first candidate even with nothing pinned.
    for name in ("",) + tuple(planner.BACKENDS):
        fields = BACKEND_FIELDS[name]
        out.append({
            "backend": name, "label": BACKEND_LABELS[name],
            "short": BACKEND_SHORT[name],
            "available": usable.get(name, True),
            "why": "" if usable.get(name, True) else reasons[name],
            "note": BACKEND_NOTES[name],
            "needs": missing_setup(name, settings),
            "needsBaseUrl": bool(fields["baseUrl"]),
            "needsModel": bool(fields["model"]),
            "needsKey": bool(fields["key"]),
            "modelOptional": MODEL_ALWAYS_OPTIONAL,
            # Stored value in the box, environment value as a placeholder:
            # prefilling from the merged view and then saving the box pins
            # what .env provided.
            "model": stored.models.get(name or "openai", ""),
            "modelFallback": env.models.get(name or "openai", ""),
            "hasKey": bool(settings.keys.get(name or "openai")),
        })
    return out

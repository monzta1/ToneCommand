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
import re
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
        "help": "Needs a paid ChatGPT developer key, from OpenAI (the company "
                "behind ChatGPT) at platform.openai.com. That is a separate "
                "account from ChatGPT Plus, and it bills per request on top "
                "of any subscription you already pay for.",
    },
    {
        "name": "A subscription you already pay for",
        "url": CLIPROXY_DEFAULT_URL,
        "key": "no",
        "help": "Use the ChatGPT subscription you already have, at no extra "
                "cost per request. It needs a small free helper program "
                "installed once, which takes about five minutes: click SHOW "
                "ME HOW and it walks you through it a step at a time. The "
                "same setup also covers Gemini, Grok and Kimi.",
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

#: A walkthrough for a service that needs software installed first.
#:
#: "Run CLIProxyAPI" is a fine instruction for somebody who has heard of
#: CLIProxyAPI. Nobody has. A guitarist who wants to use the ChatGPT
#: subscription they already pay for should never have to learn the name of
#: the thing in the middle, so the panel walks them through it one step at a
#: time and CHECKS each step before offering the next.
#:
#: The app never runs these itself. It shows the command, the person runs it,
#: and the app verifies the result: installing software on someone's machine
#: from a web request is not a thing this program should do, and being shown
#: the command is also how they learn what happened.
#:
#: Commands verified against homebrew-core's cliproxyapi formula and the
#: project's own flag definitions in cmd/server/main.go.
SETUP_GUIDE = {
    "url": CLIPROXY_DEFAULT_URL,
    "title": "Use the ChatGPT subscription you already pay for",
    "intro": "This connects ToneCommand to the ChatGPT account you already "
             "have, so there is nothing extra to pay per request. It needs a "
             "small free program in the middle, which you install once. "
             "Three steps, about five minutes. Open the Terminal app and "
             "keep it beside this window.",
    "steps": [
        {
            "id": "brew",
            "title": "Check you have Homebrew",
            "say": "Homebrew is the standard way to install developer tools "
                   "on a Mac. You may already have it. Paste this and press "
                   "return: if it prints a version number you are done with "
                   "this step.",
            "run": "brew --version",
            "fix": "If it says command not found, install Homebrew first by "
                   "pasting the line at https://brew.sh and following its "
                   "prompts, then check again.",
        },
        {
            "id": "installed",
            "title": "Install the connector",
            "say": "This is the free program that lets ToneCommand talk to "
                   "your ChatGPT account. It is called CLIProxyAPI. You will "
                   "not have to think about it again after today.",
            "run": "brew install cliproxyapi",
            "fix": "This downloads a few files and can take a minute or two. "
                   "Wait for your prompt to come back before checking.",
        },
        {
            "id": "signed_in",
            "title": "Sign in to ChatGPT",
            "say": "This opens your web browser and asks you to sign in to "
                   "ChatGPT, the same way any app does. Sign in, approve it, "
                   "and come back here. It is a one time thing.",
            "run": "cliproxyapi --codex-login",
            "fix": "If no browser opened, the terminal will have printed a "
                   "link. Copy that link into your browser instead.",
        },
        {
            "id": "listening",
            "title": "Set its password and start it",
            "say": "The connector ships with placeholder passwords and "
                   "refuses to answer anything until a real one is set, which "
                   "is a sensible thing for it to do. This sets one, then "
                   "starts it now and again whenever you log in. ToneCommand "
                   "fills the password in for you, so you never need to see "
                   "it or type it anywhere.",
            "run": "",       # built per machine: see setup_guide_state
            "fix": "Give it a few seconds to come up, then check again. If it "
                   "says permission denied, put sudo in front of the sed part "
                   "only.",
        },
    ],
}


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
    "openai": "ChatGPT or other",
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
              "own. Anything that speaks the ChatGPT API works, which most "
              "services do. A key is often not needed.",
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


def list_models(backend: str, base_url: str = "") -> dict:
    """Model ids to offer for a backend, and where they came from.

    Suggestions only. Every model box stays typeable, because a list that
    cannot be overridden is worse than no list the moment it goes stale.
    """
    backend = (backend or "openai").lower()
    if backend == "grok":
        found, why = _grok_models()
    elif backend == "openai":
        found, why = _endpoint_models(base_url)
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


#: Ids a /models listing returns that cannot write a tone plan. ChatGPT's
#: listing is the whole catalogue, so without this the model box offers
#: image, speech and embedding models beside the ones that can actually
#: answer, and the first entry alphabetically is usually one of them.
NOT_A_PLANNER = ("embedding", "whisper", "tts", "dall-e", "moderation",
                 "audio", "image", "realtime", "transcribe", "search",
                 "sora", "clip", "rerank", "guard", "codex-mini")

#: Older completion-only families. They answer, so nothing filters them out
#: by shape, and they cannot follow the plan schema. Named rather than
#: pattern-matched, because there is no pattern: they are just old.
LEGACY_COMPLETION = ("babbage", "davinci", "curie", "ada-", "text-ada",
                     "instruct")

#: A dated snapshot: gpt-5-2026-04-11 beside gpt-5. Both work; the undated
#: one is the alias that keeps working after the snapshot is retired.
_DATED = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{4})$")


def usable_models(ids: list[str]) -> list[str]:
    """The listing, minus what cannot write a tone plan, best guess first.

    Ordering matters because the panel FILLS the box with the first entry
    rather than only offering a list, and a /models listing arrives in no
    particular order. Suggestions still, and the box stays typeable: a filter
    that hides a working model is a nuisance, while offering
    `text-embedding-3-small` as a planner is a wrong answer dressed as a
    choice.
    """
    keep = [m for m in ids
            if not any(bad in m.lower() for bad in NOT_A_PLANNER)
            and not any(old in m.lower() for old in LEGACY_COMPLETION)]
    # Undated aliases first, then newest-looking name first.
    #
    # The endpoint's own order is not stable: the same connector returned
    # gpt-5.5 first on one call and gpt-5.4 first on the next. Since the panel
    # FILLS the box with the first entry, "first" was decided by luck. Reverse
    # alphabetical is not cleverness about which model is better, a thing this
    # cannot know; it is a rule that puts 5.6 above 5.4 and, more importantly,
    # gives the same answer every time. The full list is on screen either way.
    dated = [m for m in keep if _DATED.search(m)]
    plain = [m for m in keep if not _DATED.search(m)]
    return sorted(plain, reverse=True) + sorted(dated, reverse=True)


def endpoint_reachable(base_url: str) -> str:
    """"" if something answers at `base_url`, else why it does not.

    Presence is not reachability. Saving only checked that an ADDRESS was
    filled in, so choosing the subscription route without the router running
    saved cleanly and then failed at the next prompt, which is the exact
    trade _check_runnable exists to prevent: a sentence now instead of a
    failed prompt later.

    A warning, never a refusal. Configuring the panel before starting the
    router is a perfectly reasonable order to do things in.
    """
    import urllib.error
    import urllib.request
    if not base_url:
        return ""
    req = urllib.request.Request(f"{base_url.rstrip('/')}/models", method="GET")
    key = load().key_for("openai")
    if key:
        req.add_header("authorization", f"Bearer {key}")
    try:
        urllib.request.urlopen(req, timeout=3)
        return ""
    except urllib.error.HTTPError:
        # It answered. 401 without a key is a running service, not a broken
        # one, and refusing to distinguish those would cry wolf on every
        # correctly configured hosted endpoint.
        return ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return (f"Saved, but nothing is answering at {base_url} "
                f"({getattr(exc, 'reason', exc)}). Start the service, then "
                f"send a prompt.")


def _endpoint_models(base_url: str = "") -> tuple[list[str], str]:
    """Ask the endpoint. /models is part of the shape every one of these speaks.

    `base_url` overrides the saved setting so the panel can list models for a
    service the moment it is picked, rather than only after a save. Picking
    ChatGPT and being shown an empty model box is the same dead end the
    address box used to be.
    """
    import json as _json
    import urllib.error
    import urllib.request
    base = base_url or load().base_url or planner._openai_base_url()
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
    found = usable_models([e["id"] for e in entries or []
                           if isinstance(e, dict) and isinstance(e.get("id"), str)])
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


def setup_step_state(step_id: str) -> tuple[bool, str]:
    """Has this setup step actually been done? Checked, never assumed.

    A wizard that advances because somebody clicked Next teaches nothing and
    fails at the end with no clue which step went wrong. Every step here is
    verifiable from outside, so it is verified.
    """
    import glob
    import os
    import shutil
    if step_id == "brew":
        found = shutil.which("brew")
        return bool(found), (f"Homebrew is installed at {found}." if found else
                             "Homebrew is not installed yet.")
    if step_id == "installed":
        found = shutil.which("cliproxyapi")
        if not found:
            # brew does not put every formula on PATH for a GUI-launched
            # process, so look where the formula actually installs it before
            # telling somebody their working install is missing.
            for guess in ("/opt/homebrew/opt/cliproxyapi/bin/cliproxyapi",
                          "/usr/local/opt/cliproxyapi/bin/cliproxyapi"):
                if os.path.exists(guess):
                    found = guess
                    break
        return bool(found), (f"The connector is installed at {found}."
                             if found else "The connector is not installed yet.")
    if step_id == "signed_in":
        home = os.path.expanduser("~/.cli-proxy-api")
        files = glob.glob(os.path.join(home, "*.json"))
        return bool(files), (
            f"Signed in: {len(files)} account file(s) in {home}." if files else
            "No signed-in account found yet.")
    if step_id == "listening":
        # Not "is a port open" but "does it list a model, to us, with our
        # password". Everything short of that fails later at the only moment
        # it costs anything, which is mid-prompt.
        return cliproxy_probe()
    return False, f"unknown step {step_id!r}"


def setup_guide_state() -> dict:
    """The guide, with each step marked done or not, and what is next."""
    steps = []
    for step in SETUP_GUIDE["steps"]:
        done, detail = setup_step_state(step["id"])
        steps.append({**step, "done": done, "detail": detail})
    nxt = next((s["id"] for s in steps if not s["done"]), "")
    # Built here rather than in the table: the config path and the password
    # are both properties of this machine.
    for s in steps:
        if s["id"] == "listening":
            s["run"] = cliproxy_setup_command()
        # Which steps the app can do on the person's behalf. The browser asks
        # rather than assuming, so a machine without Homebrew gets the manual
        # command opened up instead of a button that would only fail.
        s["canRun"] = s["id"] in RUNNABLE and bool(_brew())
    return {**SETUP_GUIDE, "steps": steps, "next": nxt,
            "complete": not nxt,
            # So the browser can fill it in and nobody has to see it.
            "key": cliproxy_key(), "keyFor": CLIPROXY_DEFAULT_URL}


def cliproxy_config_path() -> str:
    """Where homebrew puts the connector's config, or "" if it is not there."""
    import os
    for guess in ("/opt/homebrew/etc/cliproxyapi.conf",
                  "/usr/local/etc/cliproxyapi.conf"):
        if os.path.exists(guess):
            return guess
    return ""


def cliproxy_key() -> str:
    """A stable local password for the connector, derived rather than stored.

    It has to be the same value every time: the setup command bakes it into a
    config file, and ToneCommand sends it on every request afterwards. A fresh
    random one per page load would leave those two disagreeing with no sign of
    why. Derived from the machine, so it is not a shared secret from a repo
    either, and never written down by us.

    Local only. It authenticates a browser on this laptop to a proxy on this
    laptop; it is not a credential for any upstream service.
    """
    import hashlib
    import os
    seed = f"tonecommand-cliproxy{cliproxy_config_path()}{os.getuid()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


def cliproxy_setup_command() -> str:
    """The one line that replaces the template passwords and restarts it."""
    cfg = cliproxy_config_path()
    if not cfg:
        return "brew services start cliproxyapi"
    key = cliproxy_key()
    return (f"sed -i '' 's/\"your-api-key-1\"/\"{key}\"/; "
            f"/\"your-api-key-2\"/d; /\"your-api-key-3\"/d' {cfg} "
            f"&& brew services restart cliproxyapi")


def cliproxy_probe() -> tuple[bool, str]:
    """Is the connector actually usable, and if not, which step is to blame?

    Worth its own function because the failures look alike from a distance and
    point at completely different steps. Saying "the sign-in did not finish"
    to somebody whose sign-in plainly succeeded sends them to redo the one
    part that was working.
    """
    import json as _json
    import urllib.error
    import urllib.request
    url = CLIPROXY_DEFAULT_URL.rstrip("/") + "/models"
    req = urllib.request.Request(url, method="GET")
    req.add_header("authorization", f"Bearer {cliproxy_key()}")
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = _json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        if "unsafe_example_api_key" in body or "template values" in body:
            return False, ("It is running and signed in, but still has its "
                           "placeholder passwords. Run the line above.")
        if exc.code in (401, 403):
            return False, ("It is running but rejected our password. Run the "
                           "line above again, then check.")
        return False, f"It answered {exc.code}. {body[:120]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"Not running yet ({getattr(exc, 'reason', exc)})."
    models = usable_models([e["id"] for e in (data.get("data") or [])
                            if isinstance(e, dict) and isinstance(e.get("id"), str)])
    if not models:
        return False, ("It is running and answering, but offering no models, "
                       "which means the sign-in did not finish.")
    return True, f"Running and offering {len(models)} model(s)."


# --- doing it, rather than describing it ----------------------------------
#
# Copy-pasting four commands into a terminal is a wall, and most people who
# meet it simply leave. Only ONE of these steps genuinely needs a human, and
# that is signing in to their own ChatGPT account in a browser. The rest is
# ours to do.
#
# The rules this runs under, because a local page executing shell commands
# deserves stated ones:
#
# - Nothing runs without an explicit click. There is no run-on-load path.
# - Every command is a fixed argument list, never a string through a shell,
#   and never built from anything the browser sent. `step` SELECTS from a
#   table; it never becomes part of a command.
# - The config edit is done here in Python rather than by shelling out to
#   sed, so there is no quoting to get wrong on somebody else's machine, and
#   a config that no longer holds the placeholders is left alone rather than
#   silently mangled.
# - Checking stays separate from doing: setup_step_state() still only looks.

#: Steps this may perform. Anything else is refused rather than attempted.
RUNNABLE = ("installed", "signed_in", "listening")

#: The one long-lived child process: the OAuth sign-in, which blocks until
#: the person has finished in their browser.
_LOGIN: dict = {}


def _brew() -> str:
    import shutil
    return shutil.which("brew") or ""


def _cliproxy_bin() -> str:
    """The connector's binary, on PATH or where the formula puts it."""
    import os
    import shutil
    found = shutil.which("cliproxyapi")
    if found:
        return found
    for guess in ("/opt/homebrew/opt/cliproxyapi/bin/cliproxyapi",
                  "/usr/local/opt/cliproxyapi/bin/cliproxyapi"):
        if os.path.exists(guess):
            return guess
    return ""


def _write_api_key(path: str, key: str) -> str:
    """Replace the template api-keys with `key`, in place. "" on success."""
    import pathlib as _pl
    try:
        text = _pl.Path(path).read_text()
    except OSError as exc:
        return f"could not read {path}: {exc}"
    if key in text:
        return ""                                   # already done, not an error
    out, replaced = [], False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped in ('- "your-api-key-1"', "- 'your-api-key-1'"):
            out.append(line.replace("your-api-key-1", key))
            replaced = True
        elif stripped in ('- "your-api-key-2"', '- "your-api-key-3"',
                          "- 'your-api-key-2'", "- 'your-api-key-3'"):
            continue                                # drop the spare templates
        else:
            out.append(line)
    if not replaced:
        return ("the config no longer has the placeholder passwords in it, so "
                "it was left alone. Set api-keys by hand, then check again.")
    try:
        _pl.Path(path).write_text("".join(out))
    except OSError as exc:
        return f"could not write {path}: {exc}"
    return ""


def run_setup_step(step_id: str) -> dict:
    """Perform one setup step. Only ever reached from an explicit click."""
    import subprocess
    if step_id not in RUNNABLE:
        return {"ok": False, "output": "",
                "detail": f"{step_id!r} is not something this can run for you."}
    brew = _brew()
    if not brew:
        return {"ok": False, "output": "",
                "detail": "Homebrew is not installed, so nothing can be "
                          "installed for you. Get it from https://brew.sh, "
                          "then come back."}

    if step_id == "installed":
        if _cliproxy_bin():
            return {"ok": True, "detail": "Already installed.", "output": ""}
        proc = subprocess.run([brew, "install", "cliproxyapi"],
                              capture_output=True, text=True, timeout=900)
        tail = (proc.stdout + proc.stderr)[-1500:]
        ok = proc.returncode == 0 and bool(_cliproxy_bin())
        return {"ok": ok, "output": tail,
                "detail": "Installed." if ok else
                          "The install did not finish. Its output is below."}

    if step_id == "signed_in":
        if setup_step_state("signed_in")[0]:
            return {"ok": True, "detail": "Already signed in.", "output": ""}
        binary = _cliproxy_bin()
        if not binary:
            return {"ok": False, "output": "",
                    "detail": "Install the connector first."}
        running = _LOGIN.get("proc")
        if running is not None and running.poll() is None:
            return {"ok": False, "output": "",
                    "detail": "A sign-in is already waiting in your browser. "
                              "Finish it there, then press CHECK."}
        # Deliberately not waited on. It opens a browser and blocks until the
        # person signs in, which is theirs to do at their own pace; holding
        # the request open would just time out. CHECK is what notices.
        _LOGIN["proc"] = subprocess.Popen(
            [binary, "--codex-login"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return {"ok": False, "output": "",
                "detail": "Your browser should have opened. Sign in to "
                          "ChatGPT, approve it, then press CHECK."}

    # listening: give it a real password, then start it
    cfg = cliproxy_config_path()
    if not cfg:
        return {"ok": False, "output": "",
                "detail": "Could not find the connector's config file. "
                          "Install it first."}
    problem = _write_api_key(cfg, cliproxy_key())
    if problem:
        return {"ok": False, "detail": problem, "output": ""}
    proc = subprocess.run([brew, "services", "restart", "cliproxyapi"],
                          capture_output=True, text=True, timeout=180)
    tail = (proc.stdout + proc.stderr)[-1500:]
    if proc.returncode != 0:
        return {"ok": False, "output": tail,
                "detail": "Could not start it. Its output is below."}
    # It needs a moment to bind the port, and reporting failure before it has
    # had one would be a lie with a retry button next to it.
    import time
    why = "starting"
    for _ in range(12):
        time.sleep(1)
        ok, why = cliproxy_probe()
        if ok:
            return {"ok": True, "detail": why, "output": tail}
    return {"ok": False, "output": tail, "detail": why}

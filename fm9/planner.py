"""Natural-language layer: prompt -> concrete FM9 parameter plan.

Backend order, when nothing is pinned:
1. An OpenAI-compatible HTTP endpoint, when PLANNER_BASE_URL is set. A
   configured router wins over a `claude` binary that merely happens to be on
   PATH: setting a base URL is deliberate, and a router that gets silently
   shadowed is undebuggable.
2. Claude Code CLI in headless mode (uses the existing Claude subscription,
   no API key needed) when the `claude` binary is available.
3. Claude API with structured outputs, if ANTHROPIC_API_KEY is set.

PLANNER_BACKEND pins one backend and disables fallthrough, because a
deliberate choice must not quietly resolve to a different vendor's model.
The Grok CLI is only ever reached that way, never auto-selected.

Failure taxonomy (design by @Triumph1701, issue #7):
- transport or malformed output is a BACKEND failure: record the attempt and
  try the next candidate.
- a reply that parses but describes no usable actions is a PLANNER RESULT:
  return it, do not fall through, and do not blame the backend.
- an aggregate error is raised only after every candidate is exhausted.

The plan is only a proposal; nothing is sent to the FM9 until the user
confirms in the UI.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"   # API backend default
CLI_MODEL = "sonnet"      # CLI backend default: light on subscription usage


def find_claude_cli() -> str | None:
    """Locate the claude CLI: PATH first, then the desktop-app bundle."""
    path = shutil.which("claude")
    if path:
        return path
    bundles = sorted(
        Path.home().glob(
            "Library/Application Support/Claude/claude-code/*/claude.app/Contents/MacOS/claude"),
        key=lambda p: p.parent.parent.parent.name)
    return str(bundles[-1]) if bundles else None

def find_grok_cli() -> str | None:
    """Locate the grok CLI: PATH first, then the standard install location."""
    path = shutil.which("grok")
    if path:
        return path
    bundled = Path.home() / ".grok" / "bin" / "grok"
    return str(bundled) if bundled.exists() else None


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string",
                    "description": "One-sentence recap of what will change"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string",
                             "enum": ["set_param", "set_scene", "set_bypass",
                                      "set_channel", "set_tempo", "set_type",
                                      "add_block", "bind_pedal", "unbind_pedal",
                                      "rename_preset", "rename_scene", "store"]},
                    "block": {"type": ["string", "null"],
                              "description": "Block name for set_param/set_bypass/set_channel, e.g. amp, gate, input, delay, reverb, cab, drive, peq, geq, comp"},
                    "instance": {"type": "integer",
                                 "description": "Block instance, 1-4 (1 if unsure)"},
                    "param": {"type": ["string", "null"],
                              "description": "Symbolic param name from the reference list, e.g. DISTORT_DRIVE"},
                    "value": {"type": ["number", "null"],
                              "description": "Target display value for set_param (in the param's display units), scene number 1-8 for set_scene, channel 0-3 for set_channel, BPM for set_tempo"},
                    "bypassed": {"type": ["boolean", "null"],
                                 "description": "For set_bypass: true = bypass the block, false = engage it"},
                    "type_name": {"type": ["string", "null"],
                                  "description": "For set_type: exact model name from the roster. For rename_preset/rename_scene: the new name (max 32 chars)"},
                    "position": {"type": ["string", "null"],
                                 "description": "For add_block: pre, post, or any (relative to the amp)"},
                    "reason": {"type": "string",
                               "description": "Short justification tied to the user's request"},
                },
                "required": ["kind", "block", "instance", "param", "value",
                             "bypassed", "type_name", "position", "reason"],
                "additionalProperties": False,
            },
        },
        "clarification": {
            "type": ["string", "null"],
            "description": "Set ONLY if the request is too ambiguous to act on; actions must be empty then",
        },
    },
    "required": ["summary", "actions", "clarification"],
    "additionalProperties": False,
}

_ACTION_SCHEMA = PLAN_SCHEMA["properties"]["actions"]["items"]

#: The action kinds, straight from the schema. Was hand-copied in two other
#: places; the prompt's copy had drifted to six of eleven.
ACTION_KINDS = tuple(_ACTION_SCHEMA["properties"]["kind"]["enum"])

_JSON_TYPE_NAMES = {"string": "str", "integer": "int", "number": "number",
                    "boolean": "bool", "null": "null"}


def _type_label(spec: dict) -> str:
    """A JSON Schema type as the prompt spells it: `str`, `number|null`."""
    declared = spec.get("type", "string")
    if isinstance(declared, list):
        return "|".join(_JSON_TYPE_NAMES.get(t, t) for t in declared)
    return _JSON_TYPE_NAMES.get(declared, declared)


def plan_shape_line() -> str:
    """The reply shape the prompt asks for, derived from PLAN_SCHEMA.

    This line used to be hand-written, and it had drifted: it advertised six
    action kinds while the schema and the validator both accepted eleven, so
    a model was told add_block, bind_pedal, the renames and store did not
    exist. On the Grok backend the contradiction was flat-out visible, since
    --json-schema enforces PLAN_SCHEMA while the prose said six.

    Deriving it kills the class rather than the instance: the prompt cannot
    disagree with the schema again, because there is only one list left.
    """
    fields = []
    for name, spec in _ACTION_SCHEMA["properties"].items():
        if name == "kind":
            fields.append(f'"kind": "{"|".join(ACTION_KINDS)}"')
        else:
            fields.append(f'"{name}": {_type_label(spec)}')
    top = PLAN_SCHEMA["properties"]
    return ('{"summary": ' + _type_label(top["summary"])
            + ', "actions": [{' + ", ".join(fields) + '}], "clarification": '
            + _type_label(top["clarification"]) + '}')


SYSTEM = """You translate a guitarist's natural-language tone requests into concrete Fractal FM9 parameter changes.

You receive the current device state (preset, scene, blocks present with bypass state, and current values of common parameters) and a reference list of controllable parameters with their display ranges. Respond only with a plan.

Rules:
- Only propose changes for blocks that exist in the current preset. If the preset has no GATE block, gate requests map to the INPUT block's noise gate (INPUT_THRESH etc. on instance 1).
- "Tighten the gate" = raise gate threshold (less negative dB). "Loosen" = lower it. For drop tunings (Drop C etc.), gate low-cut/threshold changes should be conservative.
- Knob params (Gain, Bass, Mid, Treble, Presence, Depth, Master) are 0..10. "Slightly"/"a touch" = about 0.3-0.7 from current value; "a bit"/"some" = about 1.0; "a lot" = 2.0+. Never exceed the display range.
- dB params: "slightly" = 1-2 dB, "a bit" = 2-3 dB, "a lot" = 4-6 dB.
- "Reduce bass before the amp" means EQ or input-side changes (amp DISTORT_BASS is in the amp's tonestack; a PEQ/GEQ before the amp is pre-amp). If no pre-amp EQ block exists, use the amp's Bass and say so in the reason.
- Scene-specific requests (e.g. "make scene 2 lower gain") require that scene to be active for parameter edits; propose a set_scene to that scene first, then the parameter change, then note in the summary that the device will stay on that scene.
- All changes are live edit-buffer changes and are not saved to the preset.
- If the request is ambiguous or asks for something unsupported (file operations, saving presets, buying gear), set clarification and return no actions.
- Values must always be the ABSOLUTE target display value, computed from the current value shown in the device state.

Amp/drive/reverb model selection (set_type):
- Use set_type with the EXACT model name from the roster. The amp roster lists each entry as `type_name = the real-world amp it models`; Fractal's names are deliberately oblique, so match the artist/era/sound against the real amp on the right, then send the name on the LEFT verbatim as type_name (e.g. Van Halen Balance era = a Peavey 5150, whose roster entry is "PVH 6160 Block Lead"). A few entries have no real-world amp listed; do not invent one for them. After a type change, also set sensible gain/EQ values for that sound.
- A type change replaces the block's model on its CURRENT channel and affects every scene that uses that channel. It cannot be undone by scene changes, only by re-selecting the preset (which discards all edits).

Scenes and multi-scene requests:
- Scenes share the same blocks; each scene stores its own per-block bypass states and channel choices. Block PARAMETERS and TYPES are per-channel, shared across scenes.
- To build "scene X with effect A, scene Y with effect B": set_scene X, set bypass states for X, then set_scene Y, set bypass states for Y. The device ends on the last selected scene. Note in the summary which scene is which.
- Adding blocks: use add_block (block name + optional position "pre"/"post" relative to the amp) when a requested effect has no block in the preset. It places the block on a free pass-through point in the signal chain; if the executor reports there is no free spot, relay that honestly. Freshly added blocks may need a set_type and parameter settings next.
- Expression pedal: use bind_pedal (block + param + optional value = floor percent 0-100) to put a continuous parameter under Pedal 2, and unbind_pedal (block + param) to take it back off. Pedal 1 is the player's global volume and must NEVER be referenced or rebound. unbind_pedal only removes Pedal 2 bindings; anything driven by another source was set up on the FM9 itself and is refused.
- rename_preset / rename_scene (new name in type_name; scene number in value). Tool-created presets are prefixed FM9AI- automatically.
- NAME WHAT YOU BUILD. If the request is for a tone with an identity - a named player, a band, a song, a style, or a whole rig with several scenes - include a rename_preset naming it after that, and rename_scene for each scene you set up, after what the scene is for. A preset built for one player's sound and left carrying the previous preset's name is how somebody ends up with a Petrucci build saved as "Devs Gift Of Tone". Do NOT rename for an adjustment to the tone already loaded ("a bit more presence", "tighten the gate"): that is the same preset, adjusted.
- store (slot number in value) persists the edit buffer to a preset slot. Only the slots listed as storable in the reference are allowed; every other slot is refused by the hardware layer, and if the reference says storing is disabled, never propose store. Only propose store when the user explicitly asks to save, and the UI will ask the user to confirm the overwrite separately.
- If a requested change is impossible, say so in the summary. Never silently substitute a different effect without saying so.

THE FIRST-CLASS BUILD STANDARD. This applies to any request with an identity - a named player, band, song, style, or a rig of several scenes. It does NOT apply to small adjustments of the loaded tone ("a bit more presence", "tighten the gate"): for those, change exactly what was asked and stop.
- The goal is a rig the player never has to finish by hand. A build that picks an amp model and nudges the gain is half a build; go above what was asked, and say why in the reasons.
- Before emitting anything, silently work out the complete tone: the real amps, cabs, drives and effects behind that sound, which roster entries capture them, and how each scene differs. Then implement ALL of it.
- Voice the full amp stack in every scene you set up: gain, bass, mid, treble, presence, master, and depth where it matters. An amp left at factory defaults in a scene you built is unfinished work. Choose the cabinet deliberately when the cab roster is available; the speaker is half the sound.
- Set the effects you enable, never merely enable them. Where the style has a signature tempo, set_tempo and compute delay times from it (dotted eighth = 45000/bpm ms, quarter = 60000/bpm ms); set feedback and mix per scene. Reverb gets a type, a decay and a mix. Modulation gets a rate and depth. Clean jangle gets a compressor with real attack and level values. The input gate is tight for chugging styles and nearly open for dynamic clean work.
- Balance the build so it gigs: rhythm scenes within about 1 dB of each other on amp level, leads 2-3 dB above, cleans matched sensibly. Put the balancing in the reasons.
- Bind Pedal 2 to the one continuous parameter this sound most wants under a foot (delay mix for swells, wah for the funk scene) when it genuinely serves the style; skip it when nothing does.
- Depth never licenses invention. Every parameter you set must exist in the reference; where you are interpreting rather than reporting the artist's rig, the reason says so."""


BACKENDS = ("openai", "cli", "grok", "api")

FAILURE_CLASSES = (
    "unavailable",         # not configured, or its binary is missing
    "transport",           # could not be reached at all
    "timeout",
    "http_status",         # reached it; it refused
    "backend_error",       # it ran and reported its own failure
    "unreadable_output",   # replied, but no JSON object in the reply
    "empty_output",        # replied with nothing
)


#: The endpoint backend speaks one protocol for many vendors, so its errors
#: must name the SERVICE. "openai [http_status] 429" while planning with
#: Gemini reads as the wrong company failing (the owner asked exactly that,
#: 2026-09-02): the quota that ran out was Google's.
SERVICE_HOSTS = {
    "generativelanguage.googleapis.com": "Gemini",
    "api.openai.com": "ChatGPT API",
    "api.x.ai": "Grok",
    "api.deepseek.com": "DeepSeek",
    "api.moonshot.ai": "Kimi",
    "openrouter.ai": "OpenRouter",
}


def service_label(backend: str, target: str | None) -> str:
    """What to call a failing backend, in the vendor's name where known."""
    if backend != "openai" or not target:
        return backend
    host = urllib.parse.urlsplit(target).hostname or ""
    known = SERVICE_HOSTS.get(host)
    if known:
        return known
    return host or backend


class BackendFailure(RuntimeError):
    """This backend produced no plan, so the next candidate may run.

    Deliberately NOT raised for a reply that parses into JSON but describes
    no usable actions: that is a planner result, not a transport failure, and
    falling through on it would burn a working backend for a bad answer.
    """

    def __init__(self, backend: str, failure_class: str, detail: str,
                 target: str | None = None, model: str | None = None):
        if failure_class not in FAILURE_CLASSES:
            raise ValueError(f"unknown failure class {failure_class!r}")
        super().__init__(
            f"{service_label(backend, target)} [{failure_class}] {detail}")
        self.backend = backend
        self.failure_class = failure_class
        self.detail = detail
        self.target = target
        self.model = model


class PlanCancelled(RuntimeError):
    """The caller stopped waiting, so the work was stopped too.

    Raised by the streaming paths when their `cancel` event is set. It is not
    a BackendFailure on purpose: a cancelled backend must not trigger the
    fallthrough chain, because the person who pressed STOP would then be
    handed a fresh multi-minute attempt on the next candidate.
    """


@dataclass
class Attempt:
    """One backend's turn: what was tried, and how it went."""
    backend: str
    target: str | None = None          # base URL, binary path, or "sdk"
    model: str | None = None
    failure_class: str | None = None   # None once it produced the plan
    detail: str = ""

    def as_dict(self) -> dict:
        return {"backend": self.backend, "target": self.target,
                "model": self.model, "failure_class": self.failure_class,
                "detail": self.detail}


def _env_path() -> Path:
    """The .env file planner config may live in. Indirected so tests can
    point it somewhere harmless: _env falls back to this file whenever a
    variable is unset OR empty, so setenv("", ...) cannot mask a real line."""
    return Path(__file__).resolve().parent.parent / ".env"


def _unquote(value: str) -> str:
    """A dotenv value: quotes off, trailing comment off, in that order.

    Both halves are ordinary dotenv style and they combine, so the quotes
    have to be found FIRST or `"240"  # five minutes` keeps its quotes -
    which is silently poisonous in exactly the way an unstripped quote
    always is: PLANNER_API_KEY sends `Bearer "k"` and 401s, a quoted base
    URL fails as an unknown url type while the router is up, and a quoted
    timeout falls back to the default.

    When a value opens with a quote, that quote pair delimits it and
    anything after the closing quote is comment - which also keeps a `#`
    that lives INSIDE the quotes, where it is data rather than a comment.
    """
    val = value.strip()
    if val[:1] in ('"', "'"):
        close = val.find(val[0], 1)
        if close != -1:
            return val[1:close]
    if " #" in val:                      # PLANNER_TIMEOUT=300  # five minutes
        val = val.split(" #", 1)[0].strip()
    return val


def _env(name: str, default: str = "") -> str:
    """env var first, then a NAME= line in .env at the repo root.

    Same sourcing convention as device.get_store_slots(), so planner config
    can live in the .env file the store whitelist already uses.

    A variable PRESENT in the environment and empty means deliberately blank
    and stops the search; only an ABSENT one falls through to .env. Treating
    the two the same left a layer above with no way to say "not set": the
    settings panel selecting Auto could not clear a PLANNER_BACKEND pin
    written into .env, because every value it could write was either a pin or
    indistinguishable from having written nothing (@Triumph1701 on #25). A
    blank still resolves to `default`, so an empty CLAUDE_CLI_MODEL means the
    built-in model rather than passing --model "" to the CLI.
    """
    if name in os.environ:
        return _unquote(os.environ[name]) or default
    val = ""
    env_file = _env_path()
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                val = _unquote(line.split("=", 1)[1])
                break
    return val or default


def _env_int(name: str, default: int) -> int:
    """An int setting that cannot take the app down.

    device.get_store_slots() tolerates a malformed value; this did not, and
    it was parsed at import, so `PLANNER_TIMEOUT=300  # comment` in .env
    crashed `import fm9.planner` - taking server.py with it, for users who
    never plan anything.
    """
    raw = _env(name)
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        log.warning("%s=%r is not a number; using %d", name, raw, default)
        return default
    if val <= 0:
        log.warning("%s=%d must be positive; using %d", name, val, default)
        return default
    return val


def timeout_s() -> int:
    """Wall-clock seconds allowed per backend attempt, read per call so a
    changed value does not wait for a restart."""
    return _env_int("PLANNER_TIMEOUT", 180)


def cli_model() -> str:
    """Model for the Claude CLI backend. The CLI takes --model, so this is
    configurable rather than fixed; read per call so a change does not wait
    for a restart."""
    return _env("CLAUDE_CLI_MODEL", CLI_MODEL)


def api_model() -> str:
    """Model for the Claude API backend."""
    return _env("CLAUDE_API_MODEL", MODEL)



def _json_objects(text: str):
    """Yield each top-level JSON object in the text, in order.

    Restartable by design. A single-pass brace counter cannot be: one
    unclosed "{" leaves the depth pinned above zero and one unterminated
    quote swallows the rest of the input, so an abandoned draft - which is
    the other thing a reasoning model does before restarting - takes the
    real answer with it. Letting the stdlib decoder try each "{" in turn
    costs a bad start only that start.
    """
    decoder = json.JSONDecoder()
    i, end = 0, len(text)
    while i < end:
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, stop = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        yield obj
        # Resume past what we just consumed, so the objects inside an
        # actions list are not offered as candidates in their own right.
        i = max(stop, i + 1)


def _extract_json(text: str) -> dict:
    """The plan object out of whatever the model said around it.

    Slicing from the first brace to the last one fails on real local-model
    output: a reasoning model will draft one object and then emit its final
    answer, and that span covers both ("Extra data: line 2 column 1",
    observed against LM Studio on 2026-08-25). So take the objects one at a
    time and prefer the last plan-shaped one, since the answer comes last.
    """
    candidates = list(_json_objects(text))
    if not candidates:
        raise ValueError(f"no JSON object in model output: {text[:200]}")
    for obj in reversed(candidates):
        if "actions" in obj or "summary" in obj:
            return obj
    # No envelope anywhere. Some models emit the ACTIONS THEMSELVES - one
    # object per action, or one bare action - instead of wrapping them in
    # {summary, actions}. Gemini 3.5 Flash did exactly this on an 8-scene
    # build (2026-09-02): dozens of well-formed actions, and this function
    # kept only the last one and called it an empty plan. If what the model
    # said is action-shaped, believe it and build the envelope ourselves;
    # every action still goes through _validate and validate_action after.
    acts = [o for o in candidates if o.get("kind") in ACTION_KINDS]
    if acts:
        return {"summary": "", "actions": acts}
    return candidates[-1]


def _validate(plan_obj: dict) -> dict:
    plan_obj.setdefault("summary", "")
    plan_obj.setdefault("clarification", None)
    actions = plan_obj.get("actions") or []
    clean = []
    for a in actions:
        if not isinstance(a, dict) or a.get("kind") not in ACTION_KINDS:
            continue
        a.setdefault("block", None)
        a.setdefault("param", None)
        a.setdefault("value", None)
        a.setdefault("bypassed", None)
        a.setdefault("type_name", None)
        a.setdefault("position", None)
        # instance and reason are NOT nullable on the Action model, and the
        # prompt shows most siblings as nullable - which invites an explicit
        # null. setdefault only fills ABSENT keys, so a null used to survive
        # into Action(**a), raise a pydantic error, and cost the whole plan a
        # 502 with its diagnostics discarded.
        if a.get("instance") is None:
            a["instance"] = 1
        if a.get("reason") is None:
            a["reason"] = ""
        clean.append(a)
    plan_obj["actions"] = clean
    return plan_obj


SHELL_ENV_KEYS = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG",
                  "LC_ALL", "TERM", "TMPDIR")

# How a machine reaches the network at all. Stripping these turns a working
# planner into a backend_error on any host behind a proxy or a TLS-inspecting
# firewall - and then falls through to a paid API key nobody meant to use.
NETWORK_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                    "http_proxy", "https_proxy", "no_proxy",
                    "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE")

# Where the Claude CLI keeps its config and how it authenticates, including
# the enterprise routes. These are configuration, not foreign secrets: the
# CLI documentedly honours them, and os.environ used to pass them through.
CLAUDE_ENV_KEYS = NETWORK_ENV_KEYS + (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME",
    "CLAUDE_CLI_MODEL", "CLAUDE_API_MODEL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
    "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AWS_BEARER_TOKEN_BEDROCK",
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
    "CLOUD_ML_REGION",
)

# The Grok CLI needs none of the above: its own keys, and that is all.
# Same reasoning as CLAUDE_ENV_KEYS, which is the point: narrowing per tool
# means narrowing which CREDENTIALS it sees, not starving it of the shell.
# Withholding the proxy variables from grok reproduced the exact failure
# NETWORK_ENV_KEYS exists to prevent (@Triumph1701 on #25). No Anthropic or
# cloud keys here: a second vendor's binary has no business with them.
GROK_ENV_KEYS = NETWORK_ENV_KEYS + ("XAI_API_KEY", "GROK_API_KEY")


def cli_env(binary_keys: tuple[str, ...] = (),
            source: dict[str, str] | None = None) -> dict[str, str]:
    """The environment a planner subprocess gets: an allowlist, not a copy.

    A CLI needs a working shell environment plus its own configuration and
    credentials. Handing it os.environ wholesale also hands it every other
    secret in the process - an xAI binary receiving ANTHROPIC_API_KEY, for
    instance, which it has no business seeing.

    The allowlist has to be wide enough to keep working setups working:
    proxies, custom CA bundles, a relocated config dir and the Bedrock and
    Vertex routes are all configuration a user already had, not leakage.
    Narrow it per tool via binary_keys, not by starving the shell.
    """
    src = os.environ if source is None else source
    allow = SHELL_ENV_KEYS + binary_keys
    return {k: src[k] for k in allow if src.get(k)}


def _cli_error_message(proc: subprocess.CompletedProcess) -> str:
    """Best available error text from a failed CLI run.

    The CLI reports failures like an expired login inside the JSON envelope on
    stdout (is_error / result) and leaves stderr empty, so stderr alone is
    usually blank.
    """
    parts = []
    try:
        envelope = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        envelope = None
    if isinstance(envelope, dict):
        for key in ("result", "error", "api_error_status", "terminal_reason"):
            val = envelope.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
                break
    stderr = (proc.stderr or "").strip()
    if stderr:
        parts.append(stderr)
    if not parts:
        parts.append(f"exit code {proc.returncode}, no output")
    return " | ".join(parts)[:300]


#: Talking it through, before committing to anything.
#:
#: A tone is an opinion, and the first sentence somebody types is rarely the
#: one they mean. "Warmer" from a player chasing a Dumble and "warmer" from
#: one chasing a Vox are different edits, and a planner that guesses on the
#: first message spends its answer on a question nobody asked.
#:
#: This is the SAME transports, the same backends and the same fallthrough as
#: planning. It only differs in what it asks for: prose, and a judgement about
#: whether there is enough to go on yet. It proposes NOTHING. Nothing here can
#: reach hardware, because nothing here produces actions.
CHAT_SYSTEM = """You are helping a guitarist decide what they want their FM9 to sound like, BEFORE any change is made.

You receive the current device state and a reference of controllable parameters. You are having a conversation, not writing a plan. No changes happen as a result of anything you say here.

How to be useful:
- Talk like a good tech at a rehearsal: short, concrete, plain English. Two or three sentences is usually right. Never a wall of text.
- Ask about what they can HEAR, not about parameter names. "Is it too woolly on low notes, or too spiky on the top?" beats "shall I lower DISTORT_BASS?".
- Use what is actually in their preset. Name their real amp and cab. If they ask for something the preset cannot do without adding a block, say so now rather than later.
- One question at a time. Offer a couple of named options when it helps ("more of a Vox chime, or a Dumble warmth?").
- When they describe something you can already act on, say what you would change in plain terms and ask if that is the idea. Do not list parameter values.
- If they are clearly ready, say so plainly and stop asking questions.

Set `ready` true only when you could write a concrete plan right now without guessing at anything that matters. Put in `request` a single clear sentence describing the agreed tone change, written as an instruction, capturing everything decided in the conversation.

Put in `name` what this preset should be CALLED, when the conversation is about a tone with an identity: a player, a band, a song, or a distinctive style. Two or three words, the identity itself and not a description of it ("Marco Sfogli", "Van Halen Brown", "Comfortably Numb"). Name the player or the song, never the amp you chose to get there. Leave `name` EMPTY when the conversation is about adjusting the preset already loaded, because that is the same preset with a change, not a new one.

Put in `scenes` every scene the build will set up, with its number and what it should be CALLED: [{"n": 1, "name": "Jump Clean"}, {"n": 2, "name": "Brown Rhythm"}]. Name each one after what it is FOR, in two or three words a player would recognise on a dark stage. Scenes keep the previous preset's names unless something changes them, so a Van Halen build left sitting under scene names from an unrelated preset is genuinely confusing to play. Leave `scenes` EMPTY when the conversation sets up no scenes: an adjustment to the tone already loaded changes no scene names."""

CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "ready": {"type": "boolean"},
        "request": {"type": "string"},
        "name": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["n", "name"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reply", "ready", "request", "name", "scenes"],
    "additionalProperties": False,
}


class ReplyStreamer:
    """Pulls the `reply` string out of a JSON object as it arrives.

    Conversation asks for `{"reply": ..., "ready": ..., "request": ...}`, and a
    model streams that as raw characters. Waiting for the closing brace before
    showing anything means watching a spinner for the whole reply, which is the
    thing streaming exists to stop.

    `reply` is deliberately FIRST in CHAT_SCHEMA so it can be read before the
    rest exists. This walks the text once, emits the decoded contents of that
    one string as they appear, and stops at its closing quote. It never parses
    the whole object: the caller still does that at the end, from the complete
    text, so a malformed reply fails exactly where it failed before.
    """

    _ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b",
                "f": "\f", "n": "\n", "r": "\r", "t": "\t"}

    def __init__(self, field: str = "reply") -> None:
        self._needle = f'"{field}"'
        self._buf = ""          # everything seen, until the value starts
        self._inside = False    # we are between the value's quotes
        self._done = False      # the closing quote has been passed
        self._escape = False    # the previous character was a backslash
        self._unicode = ""      # collecting the four digits of a \uXXXX

    def feed(self, chunk: str) -> str:
        """New raw characters in; newly visible reply text out."""
        if self._done or not chunk:
            return ""
        if not self._inside:
            self._buf += chunk
            at = self._buf.find(self._needle)
            if at < 0:
                # Keep only enough to match a needle split across two chunks.
                self._buf = self._buf[-len(self._needle):]
                return ""
            rest = self._buf[at + len(self._needle):]
            quote = rest.find('"')
            if quote < 0:                      # the colon arrived, the value did not
                return ""
            self._inside = True
            chunk = rest[quote + 1:]
            self._buf = ""
        out = []
        for ch in chunk:
            if self._unicode is not None and len(self._unicode) and len(self._unicode) < 5:
                self._unicode += ch
                if len(self._unicode) == 5:
                    try:
                        out.append(chr(int(self._unicode[1:], 16)))
                    except ValueError:
                        out.append(self._unicode[1:])
                    self._unicode = ""
                continue
            if self._escape:
                self._escape = False
                if ch == "u":
                    self._unicode = "u"
                else:
                    out.append(self._ESCAPES.get(ch, ch))
                continue
            if ch == "\\":
                self._escape = True
                continue
            if ch == '"':
                self._done = True
                break
            out.append(ch)
        return "".join(out)

    @property
    def finished(self) -> bool:
        return self._done


def chat_shape_line() -> str:
    return ('{"reply": string, "ready": boolean, "request": string, '
            '"name": string, "scenes": [{"n": int, "name": string}]}')


def _full_prompt(prompt: str, device_state: str, param_reference: str,
                 system: str = "", shape: str = "") -> str:
    """The one prompt every text-completion backend sends.

    Kept verbatim from the CLI path so the backends differ only in transport,
    never in what the model was asked. `system` and `shape` default to the
    planning pair; conversation passes its own and reuses everything else.
    """
    return (
        f"{system or SYSTEM}\n\n"
        f"Controllable parameter reference:\n{param_reference}\n\n"
        f"Current device state:\n{device_state}\n\n"
        f"Request: {prompt}\n\n"
        "Respond with ONLY a single JSON object, no markdown fences and no "
        "other text, with this shape:\n"
        + (shape or plan_shape_line())
    )


def cli_envelope_model(envelope: dict, fallback: str = "") -> str:
    """Which model the claude CLI actually used.

    Verified against a real envelope: there is no top-level `model` key, and
    `modelUsage` is where the resolved id appears - the same shape as the
    grok CLI. Reading `model` alone reports the alias we asked for ("sonnet")
    dressed up as the model that answered.
    """
    usage = envelope.get("modelUsage")
    if isinstance(usage, dict) and usage:
        return next(iter(usage))
    model = envelope.get("model")
    return model if isinstance(model, str) and model else (fallback or cli_model())


def _plan_via_cli(prompt: str, device_state: str,
                  param_reference: str, system: str = "",
                  shape: str = "", schema: dict | None = None) -> tuple[dict, str]:
    full_prompt = _full_prompt(prompt, device_state, param_reference, system, shape)
    cli = find_claude_cli()
    if not cli:
        raise BackendFailure("cli", "unavailable", "claude binary not found")
    try:
        proc = subprocess.run(
            [cli, "-p", full_prompt, "--output-format", "json",
             "--model", cli_model()],
            capture_output=True, text=True, timeout=timeout_s(),
            cwd="/tmp",
            env={**cli_env(CLAUDE_ENV_KEYS),
                 "CLAUDE_CODE_ENTRYPOINT": "fm9-tone"},
        )
    except subprocess.TimeoutExpired:
        raise BackendFailure("cli", "timeout",
                             f"no reply within {timeout_s()}s", target=cli)
    if proc.returncode != 0:
        raise BackendFailure("cli", "backend_error", _cli_error_message(proc),
                             target=cli)
    try:
        envelope = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        raise BackendFailure("cli", "unreadable_output",
                             proc.stdout.strip()[:200] or "empty stdout",
                             target=cli)
    if envelope.get("is_error"):
        raise BackendFailure("cli", "backend_error", _cli_error_message(proc),
                             target=cli)
    result_text = envelope.get("result", "")
    if not result_text.strip():
        raise BackendFailure("cli", "empty_output", "envelope carried no result",
                             target=cli)
    try:
        return _extract_json(result_text), cli_envelope_model(envelope)
    except ValueError as exc:
        raise BackendFailure("cli", "unreadable_output", str(exc)[:200],
                             target=cli)


def _cli_stream_text(full_prompt: str, on_text=None, cancel=None) -> tuple[str, str]:
    """Run the claude CLI and hand its reply over as it is written.

    Returns (result_text, model). Calls `on_text(piece)` for every text delta
    the CLI emits, which is what lets a caller count actions or show words
    while a multi-minute plan is still being thought up. The blocking runner
    stays untouched: this is only ever entered from the streaming paths, and
    any failure here raises BackendFailure so those paths can fall back to the
    ordinary blocking call with its full candidate chain.

    `cancel` is a threading.Event. When it is set, the subprocess is KILLED
    and PlanCancelled is raised. That is the whole difference between a STOP
    button that stops and one that only stops watching: before this, an
    aborted browser request left the CLI running to completion while holding
    the settings lock, so the very next attempt silently queued behind a
    ghost.

    Event shapes verified against claude CLI 2.1.255 on this machine, not
    assumed: text arrives as {"type":"stream_event","event":{"type":
    "content_block_delta","delta":{"type":"text_delta","text":...}}} and the
    run closes with a {"type":"result"} envelope carrying the whole reply,
    is_error and modelUsage, the same envelope the blocking path parses.
    """
    import queue as _q
    import threading as _th

    cli = find_claude_cli()
    if not cli:
        raise BackendFailure("cli", "unavailable", "claude binary not found")
    args = [cli, "-p", full_prompt,
            "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--model", cli_model()]
    try:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd="/tmp",
            env={**cli_env(CLAUDE_ENV_KEYS),
                 "CLAUDE_CODE_ENTRYPOINT": "fm9-tone"})
    except OSError as exc:
        raise BackendFailure("cli", "unavailable", str(exc)[:200], target=cli)

    # A pipe read blocks with no timeout, so the deadline and the cancel
    # check need the reads on their own thread and this one on a queue.
    lines: _q.Queue = _q.Queue()

    def _read():
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    _th.Thread(target=_read, daemon=True).start()
    deadline = time.monotonic() + timeout_s()
    result_text, model, is_error, err_detail = "", "", False, ""
    pieces: list[str] = []
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise PlanCancelled("stopped while the model was working")
            if time.monotonic() > deadline:
                raise BackendFailure("cli", "timeout",
                                     f"no reply within {timeout_s()}s",
                                     target=cli)
            try:
                line = lines.get(timeout=0.5)
            except _q.Empty:
                continue
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            etype = event.get("type")
            if etype == "stream_event":
                inner = (event.get("event") or {})
                delta = (inner.get("delta") or {})
                piece = delta.get("text")
                if isinstance(piece, str) and piece:
                    pieces.append(piece)
                    if on_text is not None:
                        on_text(piece)
            elif etype == "result":
                result_text = event.get("result") or ""
                is_error = bool(event.get("is_error"))
                model = cli_envelope_model(event)
                for key in ("result", "api_error_status", "terminal_reason"):
                    val = event.get(key)
                    if is_error and isinstance(val, str) and val.strip():
                        err_detail = val.strip()[:300]
                        break
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()

    if is_error:
        raise BackendFailure("cli", "backend_error",
                             err_detail or "the CLI reported an error",
                             target=cli)
    # The result envelope is authoritative; the accumulated deltas cover a
    # CLI that streamed the text but died before writing the envelope.
    text = result_text.strip() or "".join(pieces).strip()
    if not text:
        stderr = ""
        try:
            stderr = (proc.stderr.read() or "").strip()[:200]
        except Exception:
            pass
        raise BackendFailure("cli", "empty_output",
                             stderr or "no result and no streamed text",
                             target=cli)
    return text, model or cli_model()


def _cli_can_stream() -> bool:
    """Whether the streaming paths should try the claude CLI at all."""
    return bool(find_claude_cli())


def grok_model(envelope: dict, fallback: str = "") -> str:
    """Which model actually answered.

    grok 1.0.5 reports no top-level `model`; the model id is the KEY under
    `modelUsage`. Verified against the real CLI, not assumed.
    """
    usage = envelope.get("modelUsage")
    if isinstance(usage, dict) and usage:
        return next(iter(usage))
    model = envelope.get("model")
    return model if isinstance(model, str) and model else (fallback or "grok")


def parse_grok_envelope(stdout: str) -> dict:
    """The grok headless envelope, tolerating any preamble around it."""
    trimmed = stdout.strip()
    try:
        return json.loads(trimmed)
    except (json.JSONDecodeError, ValueError):
        start, end = trimmed.find("{"), trimmed.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"no JSON envelope: {trimmed[:200]}")
        return json.loads(trimmed[start:end + 1])


def _plan_via_grok_cli(prompt: str, device_state: str,
                       param_reference: str, system: str = "",
                  shape: str = "", schema: dict | None = None) -> tuple[dict, str]:
    """Grok CLI in headless mode, on the user's existing Grok subscription.

    Reached only by PLANNER_BACKEND=grok or through a router - never
    auto-selected, for the same reason a `claude` binary on PATH does not
    outrank a configured endpoint.

    Unlike the Claude CLI path this one CONSTRAINS its output: --json-schema
    binds the reply to PLAN_SCHEMA (verified on grok 1.0.5 with this exact
    schema, additionalProperties and required arrays included), so malformed
    JSON is the model's failure to obey a constraint rather than an
    instruction. --verbatim keeps the prompt as written; plan mode and
    subagents are off because a planner wants one answer, not an agent
    session.
    """
    grok = find_grok_cli()
    if not grok:
        raise BackendFailure("grok", "unavailable", "grok binary not found")
    model = _env("GROK_CLI_MODEL")
    args = [grok,
            "-p", _full_prompt(prompt, device_state, param_reference, system, shape),
            "--json-schema", json.dumps(schema or PLAN_SCHEMA),  # implies json
            "--verbatim", "--no-subagents", "--no-plan",
            "--disable-web-search", "--max-turns", "8"]
    if model:
        args += ["-m", model]
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout_s(),
            cwd="/tmp", env=cli_env(GROK_ENV_KEYS))
    except subprocess.TimeoutExpired:
        raise BackendFailure("grok", "timeout",
                             f"no reply within {timeout_s()}s", grok, model)
    stderr = (proc.stderr or "").strip()[:200]
    try:
        envelope = parse_grok_envelope(proc.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        detail = f"{exc}" + (f" | {stderr}" if stderr else "")
        if proc.returncode != 0:
            raise BackendFailure("grok", "backend_error",
                                 f"exit {proc.returncode}: {stderr or detail}",
                                 grok, model)
        raise BackendFailure("grok", "unreadable_output", detail[:300],
                             grok, model)
    if envelope.get("type") == "error" or envelope.get("is_error"):
        message = envelope.get("message") or envelope.get("error") or "no detail"
        raise BackendFailure("grok", "backend_error", str(message)[:300],
                             grok, grok_model(envelope, model))
    text = envelope.get("text") or ""
    if not text.strip():
        raise BackendFailure("grok", "empty_output",
                             f"envelope carried no text (stopReason "
                             f"{envelope.get('stopReason')!r})",
                             grok, grok_model(envelope, model))
    try:
        return _extract_json(text), grok_model(envelope, model)
    except ValueError as exc:
        raise BackendFailure("grok", "unreadable_output", str(exc)[:200],
                             grok, grok_model(envelope, model))


CLIPROXY_DEFAULT_URL = "http://127.0.0.1:8317/v1"   # CLIProxyAPI's default

JSON_ONLY = ("Respond with a single JSON object only. No markdown fences, no "
             "preamble, no reasoning.")


def _openai_base_url() -> str:
    """Configured OpenAI-compatible endpoint, or "" when there is none."""
    return _env("PLANNER_BASE_URL").rstrip("/")


def completion_text(choice: dict | None) -> str:
    """Text out of one chat-completion choice, the tolerant way.

    `content` is a string on most servers and a list of parts on some. Local
    reasoning models (llama.cpp, LM Studio) routinely spend the whole token
    budget on `reasoning_content` and leave `content` empty, so that is a
    fallback rather than a dead end.
    """
    message = (choice or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
        joined = "".join(parts)
        if joined.strip():
            return joined
    reasoning = message.get("reasoning_content")
    return reasoning if isinstance(reasoning, str) else ""


def _read_until(resp, deadline: float, chunk: int = 65536) -> str:
    """Read a response body under a WALL-CLOCK deadline.

    urlopen(timeout=...) bounds each socket operation, not the attempt. A
    wedged router that sends headers promptly and then trickles the body a
    few bytes at a time never trips it, so /api/plan hangs for minutes with
    no timeout failure and no fall-through - while the README promises
    "seconds allowed per backend attempt". Checking the deadline between
    reads keeps that promise.
    """
    parts = []
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("reply body exceeded the attempt deadline")
        block = resp.read(chunk)
        if not block:
            return b"".join(parts).decode("utf-8", "replace")
        parts.append(block)


def _plan_via_openai(prompt: str, device_state: str,
                     param_reference: str, system: str = "",
                  shape: str = "", schema: dict | None = None) -> tuple[dict, str]:
    """Any OpenAI-compatible chat-completions endpoint.

    This is the path to CLIProxyAPI - and through it to Claude Code, Codex,
    Grok, Gemini or Kimi over their own OAuth logins - as well as to a local
    LLM or OpenRouter. PLANNER_API_KEY is optional by design: an OAuth router
    authenticates upstream and often wants no key at all.
    """
    base = _openai_base_url()
    if not base:
        raise BackendFailure(
            "openai", "unavailable",
            f"PLANNER_BASE_URL is not set (CLIProxyAPI defaults to "
            f"{CLIPROXY_DEFAULT_URL})")
    model = _env("PLANNER_MODEL", "local")
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": f"{SYSTEM}\n\n{JSON_ONLY}"},
            {"role": "user",
             "content": _full_prompt(prompt, device_state, param_reference, system, shape)},
        ],
        "temperature": 0.2,
        "max_tokens": int(_env("PLANNER_MAX_TOKENS", "8192")),
    }).encode()
    headers = {"content-type": "application/json"}
    key = _env("PLANNER_API_KEY")
    if key:
        headers["authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{base}/chat/completions", data=payload,
                                 headers=headers, method="POST")
    limit = timeout_s()
    deadline = time.monotonic() + limit
    try:
        with urllib.request.urlopen(req, timeout=limit) as resp:
            raw = _read_until(resp, deadline)
    except urllib.error.HTTPError as exc:                   # reached; refused
        body = exc.read().decode("utf-8", "replace").strip()[:300]
        raise BackendFailure("openai", "http_status",
                             f"{exc.code} {body or exc.reason}", base, model)
    except urllib.error.URLError as exc:                    # never reached
        if isinstance(exc.reason, TimeoutError):
            raise BackendFailure("openai", "timeout",
                                 f"no reply within {timeout_s()}s", base, model)
        raise BackendFailure("openai", "transport",
                             f"unreachable: {exc.reason}", base, model)
    except TimeoutError as exc:
        raise BackendFailure("openai", "timeout",
                             f"{exc or f'no reply within {limit}s'}", base, model)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise BackendFailure("openai", "unreadable_output",
                             raw.strip()[:200] or "empty body", base, model)
    choices = data.get("choices") or []
    text = completion_text(choices[0] if choices else None)
    if not text.strip():
        raise BackendFailure(
            "openai", "empty_output",
            "reply carried no content; a reasoning model needs a larger "
            "PLANNER_MAX_TOKENS, or check PLANNER_MODEL", base, model)
    try:
        return _extract_json(text), data.get("model") or model
    except ValueError as exc:
        raise BackendFailure("openai", "unreadable_output", str(exc)[:200],
                             base, model)


def _plan_via_api(prompt: str, device_state: str,
                  param_reference: str, system: str = "",
                  shape: str = "", schema: dict | None = None) -> tuple[dict, str]:
    try:
        import anthropic
    except ImportError as exc:
        raise BackendFailure("api", "unavailable", str(exc))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        key = _env("ANTHROPIC_API_KEY")      # shared parser: quotes stripped
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
    # Bounded like every other backend. Without this the SDK default plus its
    # retries applies, so a stuck call hangs /api/plan with no timeout failure
    # and no fall-through - the contract this module introduced for the others.
    client = anthropic.Anthropic(timeout=float(timeout_s()), max_retries=1)
    try:
        response = client.messages.create(
            model=api_model(),
            max_tokens=2048,
            system=[
                {"type": "text", "text": system or SYSTEM,
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text",
                 "text": f"Controllable parameter reference:\n{param_reference}",
                 "cache_control": {"type": "ephemeral"}},
            ],
            output_config={"format": {"type": "json_schema",
                                      "schema": schema or PLAN_SCHEMA}},
            messages=[{
                "role": "user",
                "content": f"Current device state:\n{device_state}\n\nRequest: {prompt}",
            }],
        )
    except anthropic.APITimeoutError as exc:
        raise BackendFailure("api", "timeout",
                             f"no reply within {timeout_s()}s ({exc})",
                             target="sdk", model=api_model())
    except anthropic.APIConnectionError as exc:
        raise BackendFailure("api", "transport", str(exc),
                             target="sdk", model=api_model())
    if response.stop_reason == "refusal":
        return ({"summary": "Request declined by the model.", "actions": [],
                 "clarification": "The model declined this request. "
                                  "Try rephrasing."}, api_model())
    try:
        text = next(b.text for b in response.content if b.type == "text")
    except StopIteration:
        raise BackendFailure("api", "empty_output", "no text block in reply",
                             target="sdk", model=api_model())
    try:
        return json.loads(text), getattr(response, "model", api_model())
    except (json.JSONDecodeError, ValueError):
        raise BackendFailure("api", "unreadable_output", text.strip()[:200],
                             target="sdk", model=api_model())


def _api_available() -> bool:
    """Whether an Anthropic key is actually configured.

    This used to return True whenever a .env file merely existed. Now that
    every PLANNER_* setting lives in that same file, a router-only install
    would always offer a doomed `api` candidate whose authentication noise
    buries the actionable "openai [transport] unreachable" beside it.
    """
    return bool(_env("ANTHROPIC_API_KEY"))


_RUNNERS = {
    "openai": _plan_via_openai,
    "grok": _plan_via_grok_cli,
    "cli": _plan_via_cli,
    "api": _plan_via_api,
}

# What each backend aims at, for the attempt record. A failure carries its own
# target; a success has to be resolved the same way the runner resolved it.
_TARGETS = {
    "openai": _openai_base_url,
    "grok": find_grok_cli,
    "cli": find_claude_cli,
    "api": lambda: "sdk",
}


def candidates() -> list[str]:
    """Backends to try, in order.

    PLANNER_BACKEND pins exactly one and disables fallthrough: choosing a
    backend on purpose must not quietly resolve to a different vendor's
    model. Unpinned, a configured router outranks a `claude` binary that
    merely happens to be on PATH, and the Grok CLI is never auto-selected for
    the same reason - it is reachable by pin or through a router.
    """
    pinned = _env("PLANNER_BACKEND").lower()
    if pinned:
        if pinned not in BACKENDS:
            raise RuntimeError(
                f"PLANNER_BACKEND={pinned!r} is not one of {', '.join(BACKENDS)}")
        return [pinned]
    order = []
    if _openai_base_url():
        order.append("openai")
    if find_claude_cli():
        order.append("cli")
    if _api_available():
        order.append("api")
    return order


def _plan_quality(plan_obj: dict) -> str:
    """Well-formed replies still divide into usable and not.

    A reply carrying neither actions nor a clarification parsed fine but says
    nothing: a planner-quality signal, not a transport failure. Callers get it
    labelled rather than retried, so a working backend is not burned for a bad
    answer.
    """
    if plan_obj.get("actions"):
        return "actions"
    if (plan_obj.get("clarification") or "").strip():
        return "clarification"
    return "empty"


def _scene_names(raw) -> list[dict]:
    """Scene names out of a model reply, keeping only what is usable.

    A scene number outside 1..8 does not exist on an FM9, and a nameless entry
    would rename a scene to nothing. Both are dropped here rather than
    surviving to become a validation error on a card somebody has to read.
    """
    out, seen = [], set()
    for item in (raw or [])[:8]:
        if not isinstance(item, dict):
            continue
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            continue
        name = str(item.get("name") or "").strip()[:32]
        if not (1 <= n <= 8) or not name or n in seen:
            continue
        seen.add(n)
        out.append({"n": n, "name": name})
    return sorted(out, key=lambda x: x["n"])


def _chat_prompt(messages: list[dict]) -> str:
    """The conversation so far, as one prompt. Shared by both paths."""
    turns = []
    for m in messages[-24:]:                 # a rehearsal chat, not a novel
        who = "Guitarist" if m.get("role") == "user" else "You"
        text = str(m.get("content") or "").strip()
        if text:
            turns.append(f"{who}: {text[:4000]}")
    if not turns:
        raise RuntimeError("nothing to talk about")
    return ("Conversation so far:\n" + "\n\n".join(turns)
            + "\n\nReply to the guitarist's latest message.")


#: Every action carries exactly one of these, so occurrences of it in the
#: raw text are actions written so far.
_ACTION_MARK = '"kind"'

#: The value that follows it, for saying what was just written.
_KIND_VALUE = re.compile(r'"kind"\s*:\s*"([a-z_]+)"')


def plan_stream(prompt: str, device_state: str, param_reference: str,
                cancel=None):
    """Plan, counting the changes as the model writes them.

    Yields ("count", n) as actions appear and finally ("done", plan). A plan
    is one call that either answers or does not, so there is no partial result
    to act on, but there IS honest progress to show: a four-scene build takes
    283 seconds and writes 71 actions, and watching that number climb is the
    difference between a wait and a hang.

    The count comes from the text itself. Every action carries exactly one
    `"kind":`, so occurrences of it are actions written so far. That is a real
    measurement rather than a percentage invented from elapsed time, which
    would be a guess dressed as information and would still be at 40% when the
    thing finished.

    There is no total, so there is no percentage. Saying "31 changes so far"
    is worth more than a bar that lies about how much is left.

    The OpenAI-compatible backend and the claude CLI both stream. The CLI
    matters most: it is the zero-configuration default, so before it could
    stream the count never fired on exactly the installs this feature was
    built for. Everything else falls through to the ordinary blocking plan,
    which is why this yields the same ("done", plan) either way.

    `cancel` is a threading.Event; setting it stops the streaming backends
    for real (the CLI subprocess is killed) and raises PlanCancelled.
    """
    import urllib.error
    import urllib.request

    pinned = _env("PLANNER_BACKEND").lower()
    base = _openai_base_url()
    if not base or (pinned not in ("", "openai")):
        if pinned in ("", "cli") and _cli_can_stream():
            # Streaming beats fallthrough here: in auto order the CLI is the
            # next candidate after a router anyway, and a cancelled run must
            # not burn the remaining candidates (see PlanCancelled).
            try:
                yield from _plan_stream_cli(prompt, device_state,
                                            param_reference, cancel)
                return
            except PlanCancelled:
                raise
            except BackendFailure as exc:
                log.info("planner: cli streaming failed (%s); "
                         "falling back to the blocking chain", exc)
        yield ("done", plan(prompt, device_state, param_reference))
        return

    model = _env("PLANNER_MODEL", "local")
    payload = json.dumps({
        "model": model,
        "stream": True,
        "messages": [
            {"role": "system", "content": f"{SYSTEM}\n\n{JSON_ONLY}"},
            {"role": "user",
             "content": _full_prompt(prompt, device_state, param_reference)},
        ],
        "temperature": 0.2,
        "max_tokens": int(_env("PLANNER_MAX_TOKENS", "8192")),
    }).encode()
    headers = {"content-type": "application/json"}
    key = _env("PLANNER_API_KEY")
    if key:
        headers["authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{base}/chat/completions", data=payload,
                                 headers=headers, method="POST")
    limit = timeout_s()
    deadline = time.monotonic() + limit
    whole, seen = [], 0
    try:
        with urllib.request.urlopen(req, timeout=limit) as resp:
            for line in resp:
                if cancel is not None and cancel.is_set():
                    raise PlanCancelled("stopped while the model was working")
                if time.monotonic() > deadline:
                    raise TimeoutError(f"no complete plan within {limit}s")
                line = line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    parsed = json.loads(body)
                except (json.JSONDecodeError, ValueError):
                    continue
                choices = parsed.get("choices") or []
                delta = (choices[0].get("delta") or {}) if choices else {}
                piece = delta.get("content")
                if not isinstance(piece, str) or not piece:
                    continue
                whole.append(piece)
                # Counted by reading the text so far, not by tracking markers
                # through chunk boundaries. Two earlier bugs came from that
                # bookkeeping: a carry longer than the marker counted every
                # action twice, and a marker arriving split in half was lost.
                # A regex over a growing string cannot do either, and a plan
                # is tens of kilobytes, so rescanning it costs nothing.
                #
                # It counts COMPLETED actions: `"kind"` is written before its
                # value, so counting the marker reported an action a fraction
                # before there was anything to say about it, and the first
                # entry in the log was always blank.
                kinds = _KIND_VALUE.findall("".join(whole))
                if len(kinds) > seen:
                    seen = len(kinds)
                    yield ("count", {"n": seen, "kind": kinds[-1]})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()[:300]
        raise BackendFailure("openai", "http_status",
                             f"{exc.code} {detail or exc.reason}", base, model)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BackendFailure("openai", "transport",
                             f"{getattr(exc, 'reason', exc)}", base, model)

    text = "".join(whole)
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        raise BackendFailure("openai", "unreadable_output",
                             text.strip()[:200] or "empty body", base, model)
    plan_obj = _validate(raw)
    plan_obj["backend"] = "openai"
    plan_obj["model"] = model
    plan_obj["plan_quality"] = _plan_quality(plan_obj)
    plan_obj["attempts"] = [Attempt("openai", base, model).as_dict()]
    yield ("done", plan_obj)


def _plan_stream_cli(prompt: str, device_state: str, param_reference: str,
                     cancel=None):
    """The claude CLI half of plan_stream: same events, same counting.

    A generator cannot hand text out of a callback, so the pieces land in a
    list the loop drains: _cli_stream_text runs on its own thread and this
    thread turns accumulated text into ("count", ...) events as they appear.
    """
    import queue as _q
    import threading as _th

    full_prompt = _full_prompt(prompt, device_state, param_reference)
    out: _q.Queue = _q.Queue()

    def _work():
        try:
            got = _cli_stream_text(full_prompt,
                                   on_text=lambda p: out.put(("text", p)),
                                   cancel=cancel)
            out.put(("done", got))
        except Exception as exc:
            out.put(("raise", exc))

    _th.Thread(target=_work, daemon=True).start()
    whole, seen = [], 0
    text, model = "", ""
    while True:
        kind, payload = out.get()
        if kind == "raise":
            raise payload
        if kind == "done":
            text, model = payload
            break
        whole.append(payload)
        kinds = _KIND_VALUE.findall("".join(whole))
        if len(kinds) > seen:
            seen = len(kinds)
            yield ("count", {"n": seen, "kind": kinds[-1]})

    cli = find_claude_cli()
    try:
        raw = _extract_json(text)
        plan_obj = _validate(raw)
    except Exception as exc:
        # A malformed reply is this backend failing to deliver, exactly as it
        # is in _ask_backends, so the caller may fall back to the full chain.
        raise BackendFailure("cli", "unreadable_output", str(exc)[:200],
                             target=cli)
    plan_obj["backend"] = "cli"
    plan_obj["model"] = model
    plan_obj["plan_quality"] = _plan_quality(plan_obj)
    plan_obj["attempts"] = [Attempt("cli", cli, model).as_dict()]
    log.info("planner: %s answered via cli stream (model %s, %d action(s))",
             plan_obj["plan_quality"], model,
             len(plan_obj.get("actions") or []))
    yield ("done", plan_obj)


def converse_stream(messages: list[dict], device_state: str,
                    param_reference: str, cancel=None):
    """Converse, yielding words as they arrive.

    Yields ("text", chunk) as the reply forms and finally ("done", result)
    carrying the same dict `converse` returns. Raises the same way it does.

    The OpenAI-compatible backend and the claude CLI both stream words; the
    CLI does it through --output-format stream-json, so the default install
    no longer watches "thinking..." while a reply it could be reading forms.
    Anything else yields the whole thing in one piece, rather than offering a
    different feature depending on somebody's configuration.
    """
    import urllib.error
    import urllib.request

    prompt = _chat_prompt(messages)
    pinned = _env("PLANNER_BACKEND").lower()
    base = _openai_base_url()
    if not base or (pinned not in ("", "openai")):
        if pinned in ("", "cli") and _cli_can_stream():
            try:
                yield from _converse_stream_cli(prompt, device_state,
                                                param_reference, cancel)
                return
            except PlanCancelled:
                raise
            except BackendFailure as exc:
                log.info("chat: cli streaming failed (%s); "
                         "falling back to the blocking chain", exc)
        yield ("done", converse(messages, device_state, param_reference))
        return

    model = _env("PLANNER_MODEL", "local")
    payload = json.dumps({
        "model": model,
        "stream": True,
        "messages": [
            {"role": "system", "content": f"{CHAT_SYSTEM}\n\n{JSON_ONLY}"},
            {"role": "user", "content": _full_prompt(
                prompt, device_state, param_reference,
                CHAT_SYSTEM, chat_shape_line())},
        ],
        "temperature": 0.2,
        "max_tokens": int(_env("PLANNER_MAX_TOKENS", "8192")),
    }).encode()
    headers = {"content-type": "application/json"}
    key = _env("PLANNER_API_KEY")
    if key:
        headers["authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{base}/chat/completions", data=payload,
                                 headers=headers, method="POST")
    limit = timeout_s()
    deadline = time.monotonic() + limit
    streamer = ReplyStreamer()
    whole = []
    try:
        with urllib.request.urlopen(req, timeout=limit) as resp:
            for line in resp:
                if cancel is not None and cancel.is_set():
                    raise PlanCancelled("stopped while the model was replying")
                if time.monotonic() > deadline:
                    raise TimeoutError(f"no complete reply within {limit}s")
                line = line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    parsed = json.loads(body)
                except (json.JSONDecodeError, ValueError):
                    continue
                choices = parsed.get("choices") or []
                delta = (choices[0].get("delta") or {}) if choices else {}
                piece = delta.get("content")
                if not isinstance(piece, str) or not piece:
                    continue
                whole.append(piece)
                shown = streamer.feed(piece)
                if shown:
                    yield ("text", shown)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()[:300]
        raise BackendFailure("openai", "http_status",
                             f"{exc.code} {detail or exc.reason}", base, model)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BackendFailure("openai", "transport",
                             f"{getattr(exc, 'reason', exc)}", base, model)

    text = "".join(whole)
    try:
        raw = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        raise BackendFailure("openai", "unreadable_output",
                             text.strip()[:200] or "empty body", base, model)
    reply = str(raw.get("reply") or "").strip()
    if not reply:
        raise RuntimeError("the model replied with nothing to say")
    yield ("done", {
        "reply": reply,
        "ready": bool(raw.get("ready")),
        "request": str(raw.get("request") or "").strip(),
        "name": str(raw.get("name") or "").strip()[:26],
        "scenes": _scene_names(raw.get("scenes")),
        "backend": "openai", "model": model,
        "attempts": [Attempt("openai", base, model).as_dict()],
    })


def _converse_stream_cli(prompt: str, device_state: str,
                         param_reference: str, cancel=None):
    """The claude CLI half of converse_stream: same events, same reply.

    The reply streams through ReplyStreamer exactly as the router path does,
    so only the transport differs, never what the reader sees.
    """
    import queue as _q
    import threading as _th

    full_prompt = _full_prompt(prompt, device_state, param_reference,
                               CHAT_SYSTEM, chat_shape_line())
    out: _q.Queue = _q.Queue()

    def _work():
        try:
            got = _cli_stream_text(full_prompt,
                                   on_text=lambda p: out.put(("text", p)),
                                   cancel=cancel)
            out.put(("done", got))
        except Exception as exc:
            out.put(("raise", exc))

    _th.Thread(target=_work, daemon=True).start()
    streamer = ReplyStreamer()
    text, model = "", ""
    while True:
        kind, payload = out.get()
        if kind == "raise":
            raise payload
        if kind == "done":
            text, model = payload
            break
        shown = streamer.feed(payload)
        if shown:
            yield ("text", shown)

    cli = find_claude_cli()
    try:
        raw = _extract_json(text)
    except ValueError as exc:
        raise BackendFailure("cli", "unreadable_output", str(exc)[:200],
                             target=cli)
    reply = str(raw.get("reply") or "").strip()
    if not reply:
        raise RuntimeError("the model replied with nothing to say")
    yield ("done", {
        "reply": reply,
        "ready": bool(raw.get("ready")),
        "request": str(raw.get("request") or "").strip(),
        "name": str(raw.get("name") or "").strip()[:26],
        "scenes": _scene_names(raw.get("scenes")),
        "backend": "cli", "model": model,
        "attempts": [Attempt("cli", cli, model).as_dict()],
    })


def converse(messages: list[dict], device_state: str,
             param_reference: str) -> dict:
    """Talk a tone through, before anything is planned or sent.

    Same backends, same order, same fallthrough, same failure taxonomy. The
    only difference is what is asked for: prose and a judgement about whether
    there is enough to go on yet.

    It CANNOT produce actions. There is no plan shape in the reply and no path
    from here into the executor: agreeing on an idea in conversation still
    leaves the whole plan, validate and confirm pipeline in front of anything
    reaching the rig. What this returns is a better sentence to plan from.
    """
    prompt = _chat_prompt(messages)
    raw, name, model, attempts = _ask_backends(
        prompt, device_state, param_reference,
        system=CHAT_SYSTEM, shape=chat_shape_line(), schema=CHAT_SCHEMA)
    reply = str(raw.get("reply") or "").strip()
    if not reply:
        raise RuntimeError("the model replied with nothing to say")
    return {"reply": reply,
            "ready": bool(raw.get("ready")),
            "request": str(raw.get("request") or "").strip(),
            "name": str(raw.get("name") or "").strip()[:26],
            "scenes": _scene_names(raw.get("scenes")),
            "backend": name, "model": model,
            "attempts": [a.as_dict() for a in attempts]}


def _ask_backends(prompt: str, device_state: str, param_reference: str,
                  system: str = "", shape: str = "",
                  schema: dict | None = None, validate=None,
                  ) -> tuple[dict, str, str, list[Attempt]]:
    """Each candidate in turn until one answers. Shared by plan and converse.

    Extracted so conversation reuses the fallthrough, the attempt record and
    the failure taxonomy rather than growing a second, subtly different copy
    of them.

    `validate` runs INSIDE the try, and that placement is load-bearing: a
    reply can parse as JSON and still be shaped wrongly enough to raise
    ({"actions": 42} is valid JSON and a truthy non-iterable). That is this
    backend failing to deliver, not a reason to abandon the rest of them.
    """
    order = candidates()
    if not order:
        raise RuntimeError(
            "No planner backend: install the claude CLI, set ANTHROPIC_API_KEY, "
            "or point PLANNER_BASE_URL at an OpenAI-compatible endpoint")
    attempts: list[Attempt] = []
    for name in order:
        runner = _RUNNERS.get(name)
        if runner is None:                 # BACKENDS and _RUNNERS drifted
            attempts.append(Attempt(name, None, None, "unavailable",
                                    "no runner is registered for this backend"))
            continue
        model = None
        try:
            raw, model = runner(prompt, device_state, param_reference,
                                system, shape, schema)
            if validate is not None:
                raw = validate(raw)
        except BackendFailure as exc:
            attempts.append(Attempt(exc.backend, exc.target, exc.model,
                                    exc.failure_class, exc.detail))
            continue
        except Exception as exc:
            attempts.append(Attempt(name, None, model, "backend_error",
                                    str(exc)[:300]))
            continue
        if not isinstance(raw, dict):
            attempts.append(Attempt(name, None, model, "unreadable_output",
                                    f"reply was {type(raw).__name__}, not an object"))
            continue
        resolve = _TARGETS.get(name)
        attempts.append(Attempt(name, resolve() if resolve else None, model))
        return raw, name, model, attempts
    detail = "; ".join(f"{a.backend} [{a.failure_class}] {a.detail}"
                       for a in attempts)
    raise RuntimeError(f"every planner backend failed: {detail}")


def plan(prompt: str, device_state: str, param_reference: str) -> dict:
    """Ask each candidate backend in turn until one produces a plan.

    Returns the plan with `backend`, `model`, `plan_quality`, and the full
    `attempts` record attached. Raises only when every candidate failed at the
    transport level, with one aggregate message naming each attempt.
    """
    plan_obj, name, model, attempts = _ask_backends(
        prompt, device_state, param_reference, validate=_validate)
    plan_obj["backend"] = name
    plan_obj["model"] = model
    plan_obj["plan_quality"] = _plan_quality(plan_obj)
    plan_obj["attempts"] = [a.as_dict() for a in attempts]
    log.info("planner: %s answered via %s (model %s, %d action(s))",
             plan_obj["plan_quality"], name, model,
             len(plan_obj.get("actions") or []))
    return plan_obj

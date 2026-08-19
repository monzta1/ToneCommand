"""Natural-language layer: prompt -> concrete FM9 parameter plan.

Backend order:
1. Claude Code CLI in headless mode (uses the existing Claude subscription,
   no API key needed) when the `claude` binary is available.
2. Claude API with structured outputs, if ANTHROPIC_API_KEY is set.

The plan is only a proposal; nothing is sent to the FM9 until the user
confirms in the UI.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

MODEL = "claude-opus-5"   # API backend model
CLI_MODEL = "sonnet"      # CLI backend model: light on subscription usage


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
                                      "set_channel", "set_tempo", "set_type"]},
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
                                  "description": "For set_type: exact model name from the roster (amp, drive, or reverb)"},
                    "reason": {"type": "string",
                               "description": "Short justification tied to the user's request"},
                },
                "required": ["kind", "block", "instance", "param", "value",
                             "bypassed", "type_name", "reason"],
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
- You cannot ADD blocks to a preset. If a requested effect has no block in the current preset, do what is possible with existing blocks and clearly state the limitation in the summary (or clarification if nothing is possible). Never silently substitute a different effect without saying so."""


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]}")
    return json.loads(text[start:end + 1])


def _validate(plan_obj: dict) -> dict:
    plan_obj.setdefault("summary", "")
    plan_obj.setdefault("clarification", None)
    actions = plan_obj.get("actions") or []
    clean = []
    for a in actions:
        if not isinstance(a, dict) or a.get("kind") not in (
                "set_param", "set_scene", "set_bypass", "set_channel",
                "set_tempo", "set_type"):
            continue
        a.setdefault("block", None)
        a.setdefault("instance", 1)
        a.setdefault("param", None)
        a.setdefault("value", None)
        a.setdefault("bypassed", None)
        a.setdefault("type_name", None)
        a.setdefault("reason", "")
        clean.append(a)
    plan_obj["actions"] = clean
    return plan_obj


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


def _plan_via_cli(prompt: str, device_state: str, param_reference: str) -> dict:
    full_prompt = (
        f"{SYSTEM}\n\n"
        f"Controllable parameter reference:\n{param_reference}\n\n"
        f"Current device state:\n{device_state}\n\n"
        f"Request: {prompt}\n\n"
        "Respond with ONLY a single JSON object, no markdown fences and no "
        "other text, with this shape:\n"
        '{"summary": str, "actions": [{"kind": "set_param|set_scene|set_bypass|'
        'set_channel|set_tempo|set_type", "block": str|null, "instance": int, '
        '"param": str|null, "value": number|null, "bypassed": bool|null, '
        '"type_name": str|null, "reason": str}], "clarification": str|null}'
    )
    cli = find_claude_cli()
    proc = subprocess.run(
        [cli, "-p", full_prompt, "--output-format", "json", "--model", CLI_MODEL],
        capture_output=True, text=True, timeout=180,
        cwd="/tmp",
        env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "fm9-tone"},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {_cli_error_message(proc)}")
    try:
        envelope = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            f"claude CLI returned unreadable output: {proc.stdout.strip()[:200]}") from exc
    if envelope.get("is_error"):
        raise RuntimeError(f"claude CLI failed: {_cli_error_message(proc)}")
    result_text = envelope.get("result", "")
    return _extract_json(result_text)


def _plan_via_api(prompt: str, device_state: str, param_reference: str) -> dict:
    import anthropic
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not os.environ.get("ANTHROPIC_API_KEY") and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=[
            {"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"Controllable parameter reference:\n{param_reference}",
             "cache_control": {"type": "ephemeral"}},
        ],
        output_config={"format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
        messages=[{
            "role": "user",
            "content": f"Current device state:\n{device_state}\n\nRequest: {prompt}",
        }],
    )
    if response.stop_reason == "refusal":
        return {"summary": "Request declined by the model.", "actions": [],
                "clarification": "The model declined this request. Try rephrasing."}
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _api_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or \
        (Path(__file__).resolve().parent.parent / ".env").exists()


def plan(prompt: str, device_state: str, param_reference: str) -> dict:
    cli_error = None
    if find_claude_cli():
        try:
            return _validate(_plan_via_cli(prompt, device_state, param_reference))
        except Exception as exc:
            # A present-but-unusable CLI (expired login, bad install) should not
            # shadow a working API key.
            if not _api_available():
                raise
            cli_error = exc
    if _api_available():
        try:
            return _validate(_plan_via_api(prompt, device_state, param_reference))
        except Exception as exc:
            if cli_error is not None:
                raise RuntimeError(
                    f"{cli_error}; API fallback also failed: {exc}") from exc
            raise
    raise RuntimeError("No planner backend: install the claude CLI or set ANTHROPIC_API_KEY")

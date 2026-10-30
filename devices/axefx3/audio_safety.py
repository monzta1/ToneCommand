"""Conservative, static audio-parameter policy; no I/O or device dependencies.

This is NOT a limiter, an audio measurement, or a guarantee against loud output,
feedback, or damage. A successful readback does not change that. Limits concern
individual *display values*, not wire words, acoustic volume, summed paths, or
the transient state while changing a model, preset, channel, or scene.

Integration contract:
* Run action_error for EVERY action before snapshots/foundations/other writes,
  and again in the executor. Keep schema, capability and device-range checks.
* Run parameter_error in display setters AND wire/undo setters, after decoding
  the latter with an authoritative device/firmware-specific parameter spec.
* Callers resolve canonical family/spec from their device-specific catalog,
  then pass them to action_error(action_dict, family=None, spec=None).
* Both server and device preset-import boundaries must call opaque_preset_error
  before any prepare/upload/store command: a dump activates the live edit buffer.
* None means only "no violation found by this static policy", not permission
  to write. Bounded/unassessed modifier removal is refused: a controller-driven
  display cannot prove the underlying stored value. Scene/model/preset activation,
  existing modifiers and intermediate routing need a separate state-aware gate.
  A later attenuation cannot protect earlier writes.

There is deliberately no disable flag, environment setting, or clamp. A caller
must report refusals, not silently substitute a different requested value.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from numbers import Real
import re


MAX_LEVEL_DB = 0.0
MAX_FEEDBACK_PERCENT = 60.0
MAX_MASTER_FEEDBACK_PERCENT = 100.0

# These networks are not assessed by a single feedback-amount cap. This is a
# conservative automation restriction, not a claim that the blocks are faulty.
BLOCKED_LOOP_FAMILIES = frozenset({
    "FDBKSEND", "FDBKRET", "PLEX", "MULTITAP", "MEGATAP", "TENTAP", "RESONATOR",
})

REFERENCE = (
    "Conservative static audio policy (always enforced): level-like dB values "
    "and dB gain must be <= 0 dB; ordinary feedback must be between -60% and "
    "+60%; master feedback must be between 0% and 100%. Values must be finite. "
    "Level and feedback controls with unknown units are refused, not guessed. "
    "Do not assign or clear modifiers on these safety-controlled parameters; "
    "a controller-active display does not prove the underlying stored value. Do not add, "
    "engage, change model or switch channels on Feedback Send/Return, Plex, "
    "Multitap, Megatap, Ten-Tap or Resonator blocks. Generic parameter writes "
    "(including BYPASS), raw restores and modifier assignments/removals on these blocks "
    "are blocked; only explicit set_bypass=True is allowed. On other blocks, "
    "reductions/mutes within the parameter's device range are allowed. "
    "Opaque preset imports are blocked: their contents cannot be assessed and "
    "upload activates the live edit buffer, even without a final preset reload. "
    "Non-dB drive/gain, EQ, mix and thresholds remain subject to normal device "
    "validation (dB EQ gain still has the 0 dB ceiling). This is not a measured "
    "limiter or a physical-volume/damage guarantee. Readback is not audible "
    "measurement. Scene/model/preset transitions and existing modifiers require "
    "separate safe staging; do not rely on a later level reduction."
)


def reference() -> str:
    """Human-readable planner reference for the same always-on policy."""
    return REFERENCE


def opaque_preset_error() -> str:
    """Always refuse opaque preset imports until a content validator exists.

    Structural checks, slot allowlists and readback do not establish that the
    embedded parameters/routing/modifiers comply with this policy. There is no
    override; in particular, omitting a final reload does not isolate a dump.
    """
    return ("Audio safety: opaque preset import is blocked because its parameter, "
            "routing and modifier contents cannot be assessed. Upload activates "
            "the live edit buffer before any final preset reload. A content safety "
            "validator is required; nothing may be prepared, uploaded or stored.")


def policy_info() -> dict:
    """Fresh JSON-serializable UI metadata, not a live safety assessment."""
    return {
        "id": "conservative-static-v1",
        "always_enforced": True,
        "summary": "Static limits: levels/dB gain <= 0 dB, feedback +/-60%, "
                   "master feedback 0..100%; no bounded modifier assignment/removal. "
                   "Unassessed loop blocks: only explicit set_bypass=True, "
                   "no parameter writes/restores or modifiers. Opaque preset imports blocked.",
        "max_level_db": MAX_LEVEL_DB,
        "max_feedback_percent": MAX_FEEDBACK_PERCENT,
        "master_feedback_percent": {"min": 0.0, "max": MAX_MASTER_FEEDBACK_PERCENT},
        "bounded_modifiers_allowed": False,
        "bounded_modifier_removal_allowed": False,
        "opaque_preset_imports_allowed": False,
        "opaque_preset_import_error": opaque_preset_error(),
        "blocked_loop_families": sorted(BLOCKED_LOOP_FAMILIES),
        "reference": REFERENCE,
        "limitations": [
            "Static display-value checks only; no audio measurement or limiter.",
            "No guarantee of physical volume, feedback stability, or damage prevention.",
            "Readback does not measure audible output or controller movement.",
            "Existing state, modifiers and scene/model/preset transitions "
            "need separate state-aware validation and safe staging.",
        ],
    }


def _field(spec: object, name: str) -> object:
    return spec.get(name) if isinstance(spec, Mapping) else getattr(spec, name, None)


def _compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper()) if isinstance(value, str) else ""


def _unit(spec: object) -> str:
    raw = _field(spec, "unit")
    if not isinstance(raw, str):
        return ""
    if raw.strip() == "%":
        return "percent"
    token = _compact(raw)
    if token in {"DB", "DECIBEL", "DECIBELS"}:
        return "db"
    if token in {"PERCENT", "PERCENTAGE", "PCT", "BIPOLARPERCENT"}:
        return "percent"
    return ""


_FEEDBACK_AMOUNT = re.compile(r"(?:FEEDBACK|FDBK|FEED)(?:[LR0-9]*|AMOUNT)$")
_MASTER_FEEDBACK = re.compile(r"^(?:MASTER|MSTR|M)(?:FEEDBACK|FDBK|FEED)$")
_LEVEL_AMOUNT = re.compile(r"(?:LEVEL|LVL)[LR0-9]*$")
_GAIN_AMOUNT = re.compile(r"(?:GAIN[LR0-9]*|MAKEUP)$")


def _control(spec: object) -> str | None:
    """Classify amount controls, not feedback frequency/mode or dB thresholds.

    Names AND labels matter: some catalogs label a comb-gain field Feedback.
    Do not infer units from ranges (e.g. -80..20), or promote 'numeric' to dB/%.
    Non-dB gain/drive controls are intentionally not output-level controls.
    """
    name = str(_field(spec, "name") or "")
    # Canonical names have a family prefix; removing it avoids treating the
    # FDBKRET family itself as a feedback amount and recognises PITCH_MFDBK.
    tail = name.split("_", 1)[-1]
    tokens = (_compact(tail), _compact(_field(spec, "label")))
    if any(_MASTER_FEEDBACK.fullmatch(t) for t in tokens):
        return "master_feedback"
    if any(_FEEDBACK_AMOUNT.search(t) for t in tokens):
        return "feedback"
    if any("THRESH" in t for t in tokens):
        return None
    if any(_LEVEL_AMOUNT.search(t) for t in tokens):
        return "level"
    if _unit(spec) == "db" and any(_GAIN_AMOUNT.search(t) for t in tokens):
        return "level"
    return None


def _name(spec: object) -> str:
    return str(_field(spec, "name") or _field(spec, "label") or "parameter")


def parameter_error(spec: object, value: object) -> str | None:
    """Reject unsafe display values; never clamp, convert units or perform I/O.

    ``spec`` is a ParamSpec-like object or mapping with name, label, and unit.
    Device ranges/encoding/support remain the caller's responsibility. Even
    benign controls reject nonnumeric/nonfinite values; bool is not a number
    here. Unassessed loop families refuse every parameter, including BYPASS
    and apparently benign reductions: only explicit set_bypass=True is allowed.
    On other blocks, finite negative dB values (including a device's mute value)
    are not restricted by this upper bound. IEEE -inf is NOT a mute encoding.
    """
    if not _has_identity(spec):
        return "Audio safety: unresolved parameter; cannot assess the write."
    name = _name(spec)
    try:
        finite = not isinstance(value, bool) and isinstance(value, Real) and math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        finite = False
    if not finite:
        return f"Audio safety: {name} requires a finite numeric display value."
    loop = _blocked_loop_family(spec)
    if loop:
        return _loop_error(loop)
    control = _control(spec)
    if control is None:
        return None
    # Captured AFX3 Drive uses a knob, not dB. Never apply this exception
    # to an FM9 generic spec or other level/modifier/model. It is not unity
    # calibration or a loudness guarantee; firmware/model gates still apply.
    if (control=='level' and _field(spec,'family')=='FUZZ'
            and _field(spec,'name')=='FUZZ_LEVEL' and _field(spec,'unit')=='0-10'
            and _field(spec,'effect_id')==118 and _field(spec,'param_id')==3
            and _field(spec,'set_divisor')==10
            and _field(spec,'firmware_versions') in (('32.06',),('33.00-beta.20261006',))):
        return None if 0<=value<=5 else 'Audio safety: captured Drive level knob is limited to 0..5.'
    expected = "db" if control == "level" else "percent"
    if _unit(spec) != expected:
        return (f"Audio safety: {name} has unrecognized units {_field(spec, 'unit')!r}; "
                f"a verified {'dB' if expected == 'db' else 'percent'} scale is required.")
    if control == "level" and value > MAX_LEVEL_DB:
        return f"Audio safety: {name} exceeds the {MAX_LEVEL_DB:g} dB level/gain ceiling."
    if control == "feedback" and abs(value) > MAX_FEEDBACK_PERCENT:
        return f"Audio safety: {name} feedback must be within +/-{MAX_FEEDBACK_PERCENT:g}%."
    if control == "master_feedback" and not 0 <= value <= MAX_MASTER_FEEDBACK_PERCENT:
        return f"Audio safety: {name} master feedback must be 0..{MAX_MASTER_FEEDBACK_PERCENT:g}%."
    return None


def _has_identity(spec: object) -> bool:
    """Scalar placeholders and incomplete resolver results are not specs."""
    return any(isinstance(_field(spec, key), str) and _field(spec, key).strip()
               for key in ("name", "label"))


def modifier_error(spec: object) -> str | None:
    """Refuse assignments whose full controller sweep is not safety-bounded."""
    if not _has_identity(spec):
        return "Audio safety: unresolved parameter; cannot assess modifier assignment."
    loop = _blocked_loop_family(spec)
    if loop:
        return _loop_error(loop)
    if _control(spec) is not None:
        return (f"Audio safety: modifier assignments to {_name(spec)} are blocked; "
                "the complete controller curve cannot be bounded by a stored value.")
    return None


# Only spelling/alias handling, not a second device capability catalog. Use the
# caller's resolve_block for full catalog aliases and instance validation.
_BLOCK_ALIASES = {
    "AMP": "DISTORT", "AMPLIFIER": "DISTORT", "CAB": "CABINET",
    "DRIVE": "FUZZ", "PEDAL": "FUZZ", "COMPRESSOR": "COMP",
    "GRAPHICEQ": "GEQ", "PARAMETRICEQ": "PEQ", "EQ": "PEQ",
    "SEND": "FDBKSEND", "FEEDBACKSEND": "FDBKSEND", "FDBKSEND": "FDBKSEND",
    "RETURN": "FDBKRET", "FEEDBACKRETURN": "FDBKRET", "FDBKRETURN": "FDBKRET",
    "PLEXDELAY": "PLEX", "MULTITAPDELAY": "MULTITAP", "MULTIDELAY": "MULTITAP",
    "MEGATAPDELAY": "MEGATAP", "TENTAPDELAY": "TENTAP",
}


def _family(name: str) -> str:
    token = _compact(name)
    return _BLOCK_ALIASES.get(token, token)


def _blocked_loop_family(spec: object = None, *families: object) -> str | None:
    """Use both canonical metadata and the symbolic prefix, never kind/unit.

    The FM9 catalog describes some BYPASS parameters as float with enum units.
    Neither that mismatch nor a missing family on a minimal spec may turn a
    generic parameter/restore/modifier operation into a loop-activation path.
    """
    name = _field(spec, "name")
    prefix = name.split("_", 1)[0] if isinstance(name, str) and "_" in name else None
    for raw in (*families, _field(spec, "family"), prefix):
        family = _family(raw)
        if family in BLOCKED_LOOP_FAMILIES or family.startswith("FDBK"):
            return family
    return None


def _loop_error(family: str) -> str:
    return (f"Audio safety: {family} is an unassessed feedback-loop block; "
            "parameter writes/restores, modifier assignments/removals, adding/engaging "
            "and model/channel changes are blocked. Only explicit set_bypass=True is allowed.")


def action_error(
    action_dict: Mapping,
    family: str | None = None,
    spec: object = None,
) -> str | None:
    """Static guard for canonical action dictionaries; does not execute them.

    ``spec`` is the caller-resolved device parameter, REQUIRED for set_param,
    bind_pedal and unbind_pedal. ``family`` is the canonical block family.
    Common block spellings are also checked so an alias cannot hide a loop.
    This function never resolves catalogs or calls supplied code.

    Bounded/unassessed unbinding is refused even if a caller supplies a value:
    a controller-active display is not proof of the underlying stored value.
    Unrelated actions (including store, set_scene and imports)
    are outside this stateless predicate; callers must gate their complete
    resulting state separately (opaque imports use opaque_preset_error).
    Never treat a None result as a safety permit.
    """
    if not isinstance(action_dict, Mapping):
        return "Audio safety: action must be a mapping."
    action = action_dict
    kind = action.get("kind")
    if not isinstance(kind, str):
        return "Audio safety: action kind must be a string."
    if kind not in {"set_param", "bind_pedal", "unbind_pedal", "add_block", "set_bypass", "set_type", "set_channel"}:
        return None
    block = action.get("block") or family or _field(spec, "family")
    instance = action.get("instance", 1)
    if not isinstance(block, str) or not block.strip():
        return "Audio safety: block is unresolved."
    if isinstance(instance, bool) or not isinstance(instance, int) or instance < 1:
        return "Audio safety: block instance must be a positive integer."
    if family is not None and (not isinstance(family, str) or not family.strip()):
        return "Audio safety: canonical block family must be a nonempty string."
    original_family = _family(block)
    family = _family(family or block)
    if kind == "set_bypass" and not isinstance(action.get("bypassed"), bool):
        return "Audio safety: bypass requires an explicit boolean."
    loop = _blocked_loop_family(spec, family, original_family)
    if loop and not (kind == "set_bypass" and action.get("bypassed") is True):
        return _loop_error(loop)
    if kind not in {"set_param", "bind_pedal", "unbind_pedal"}:
        return None
    if kind in {"bind_pedal", "unbind_pedal"}:
        error = modifier_error(spec)
        if kind == "unbind_pedal" and error:
            return (f"Audio safety: refusing to clear modifier for {_name(spec)}. "
                    f"{error} A controller-active display does not prove the underlying stored value.")
        return error
    return parameter_error(spec, action.get("value"))

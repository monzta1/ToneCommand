"""Turning a sentence into IR-2 parameter changes (#198).

The FM9 planner prompt is about blocks, scenes, cabs, modifiers and a
roster of 331 amps. None of that exists here. This pedal is one amp
voicing out of eleven, a three-band tone stack, gain, level and an
ambience control, and that is the entire surface.

So it gets its own prompt and its own schema rather than a translation
layer over the FM9's. The vocabulary is read from the device through
`named_params()`, so it cannot drift from what the adapter will accept:
the planner is told exactly the names and ranges that `validate_action`
will check against.

WHAT THE MODEL IS NOT ALLOWED TO DO. Invent a parameter, invent an amp
name, or give a value outside a published range. All three are refused
downstream by `validate_action` before anything reaches the wire, but
they are also stated here, because a plan full of refusals is a bad
experience even when it is a safe one.
"""
from __future__ import annotations

import json

SYSTEM = """You translate a guitarist's natural-language tone request into \
concrete BOSS IR-2 parameter changes.

THE DEVICE. The IR-2 is a compact pedal, not a modeller. It has exactly one \
amp voicing chosen from eleven, a three-band tone stack, a gain control, an \
output level and an ambience (reverb) control. There are no effect blocks, \
no scenes, no signal grid, no drives, no modulation and no preset library. \
Do not propose any of those; they do not exist on this device.

WHAT YOU MAY EMIT. Only actions of kind "set_device_param". Each one names a \
parameter in `param` and carries either `value` (a whole number inside that \
parameter's published range) or, for AMP only, `type_name` (an exact voicing \
name from the list). Never both.

HOW TO CHOOSE THE VOICING. AMP is the decision that makes the sound; \
everything else shapes it. Each voicing is listed with the cabinet impulse \
response it ships with, which tells you what it is modelled on. Match the \
request against those, then set the tone stack and gain to suit. A request \
that names an artist, a record or an era is a request for the voicing that \
gets closest, plus the knob positions that finish the job.

VALUES. Every continuous parameter is 0 to 127 on the wire, where 64 is the \
centre detent and matches the marking straight up. The pedal publishes no \
curve behind its panel markings, so do not claim a value is "5 on the dial" \
or convert to a percentage; work in the 0 to 127 the device actually takes.

FINISH THE JOB. A voicing change with no tone-stack change is unfinished \
work: set BASS, MIDDLE, TREBLE and GAIN deliberately for the sound you are \
building. Leave LEVEL alone unless the request is about loudness, since it \
is the player's output balance. Use AMBIENCE sparingly and only when the \
request implies space; a dry request wants it low.

BE HONEST. If the request needs something this pedal does not have (a delay, \
a chorus, a second amp, a scene change), say so in `summary` and do the best \
the device can, rather than proposing an action that will be refused."""


def param_reference(adapter) -> str:
    """The device's own vocabulary, read from the device."""
    rows = adapter.named_params()
    lines = ["THE IR-2'S COMPLETE PARAMETER SET. This is everything it has.",
             ""]
    for r in rows:
        if r["options"]:
            cabs = r.get("option_cabs") or {}
            lines.append(f"{r['name']}: one of these {len(r['options'])} "
                         "voicings, sent verbatim in type_name.")
            for name in r["options"]:
                cab = cabs.get(name)
                lines.append(f"  {name}" + (f"  (ships with the cab IR "
                                            f"\"{cab}\")" if cab else ""))
        else:
            lines.append(f"{r['name']}: {r['lo']} to {r['hi']} on the wire, "
                         f"centre {r['init']}.")
    lines += ["",
              "There is nothing else. No blocks, no scenes, no drives, no "
              "modulation, no cab selection (the cab follows the voicing)."]
    return "\n".join(lines)


def device_state(adapter) -> str:
    """What the pedal is set to right now, so a plan is a change rather
    than a guess about where it is starting from."""
    try:
        patch = adapter.patch()
        number, _amp = adapter.current_preset()
    except Exception as e:                    # noqa: BLE001  reported, not swallowed
        return f"The IR-2's current settings could not be read: {e}"
    lines = [f"THE PEDAL RIGHT NOW (stored patch {number}):"]
    for name, value in patch.items():
        lines.append(f"  {name} = {value}")
    return "\n".join(lines)


#: The only shape a plan for this device may take.
SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string",
                    "description": "One or two sentences for the player: what "
                                   "this build is and anything the pedal "
                                   "cannot do that they asked for"},
        "clarification": {"type": ["string", "null"],
                          "description": "A question to ask INSTEAD of "
                                         "building. When set, actions must be "
                                         "empty"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["set_device_param"]},
                    "param": {"type": "string",
                              "description": "BASS, MIDDLE, TREBLE, LEVEL, "
                                             "GAIN, AMBIENCE or AMP"},
                    "value": {"type": ["number", "null"],
                              "description": "0 to 127 for everything except "
                                             "AMP. Null when using type_name"},
                    "type_name": {"type": ["string", "null"],
                                  "description": "AMP only: the exact voicing "
                                                 "name. Null otherwise"},
                    "reason": {"type": "string",
                               "description": "Why, in the player's language"},
                },
                "required": ["kind", "param"],
            },
        },
    },
    "required": ["summary", "actions"],
}

SHAPE = ('{"summary": str, "clarification": str|null, "actions": '
         '[{"kind": "set_device_param", "param": str, "value": number|null, '
         '"type_name": str|null, "reason": str}]}')


def validate(plan_obj: dict) -> dict:
    """Keep only what this device can take.

    Mirrors the FM9 validator's contract, including the rule that a
    clarifying question means nothing has been decided and therefore zero
    actions: a reply carrying both would show the question AND offer the
    actions for confirm and send.
    """
    plan_obj.setdefault("summary", "")
    plan_obj.setdefault("clarification", None)
    if (plan_obj.get("clarification") or "").strip():
        plan_obj["actions"] = []
    clean = []
    for a in plan_obj.get("actions") or []:
        if not isinstance(a, dict) or a.get("kind") != "set_device_param":
            continue
        if not a.get("param"):
            continue
        a.setdefault("value", None)
        a.setdefault("type_name", None)
        a.setdefault("reason", "")
        a["block"] = None
        a["instance"] = 1
        clean.append(a)
    plan_obj["actions"] = clean
    return plan_obj


def as_json(obj) -> str:
    return json.dumps(obj, indent=2)

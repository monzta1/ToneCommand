"""Turning a sentence into ToneX One changes (#334).

The vocabulary is read from the pedal through `named_params()` and its
twenty presets, so it cannot drift from what the adapter will accept.
"""
from __future__ import annotations

import json

SYSTEM = """You translate a guitarist's request into concrete changes on an \
IK Multimedia ToneX One.

THE DEVICE. A one-switch pedal holding twenty presets. Each preset is a tone \
model (a captured amp, sometimes with its cab, or a captured pedal) plus a \
noise gate, compressor, EQ, reverb, modulation and delay. Three presets sit \
in slots: A and B in DUAL mode, where the footswitch flips between them and \
the amp is always on; C (the stomp slot) in STOMP mode, where the switch turns \
it on and off. The settings you can change belong to the preset PLAYING NOW. \
New tone models cannot be loaded from here (that is IK's TONEX Editor); \
choose among the twenty presets listed.

WHAT YOU MAY EMIT. Only actions of kind "set_device_param". Each names a \
parameter in `param` and carries either `value` (a number inside its range) \
or `type_name` (an exact option from its list, for parameters that have \
options, including SLOT_A, SLOT_B and SLOT_C whose options are the presets). \
Never both.

ORDER MATTERS. Settings apply to the preset playing. To change a different \
preset's settings, first make it play: put it in the active slot (SLOT_A when \
ACTIVE_SLOT is A, and so on) or switch ACTIVE_SLOT, then set its settings.

CHOOSING A PRESET. Match the request against each preset's name and its \
character tag (CLEAN, DRIVE, HI-GAIN, STOMP - ...) and instrument tag. A \
player who drives the pedal with their own overdrives wants a CLEAN amp \
preset; an "(Amp)" preset usually has no cab, which matters into a PA. \
Presets tagged Electric Bass are for bass.

THE PEDAL SAVES EVERY CHANGE AT ONCE. There is no store step and no edit \
buffer to discard. Change only what the request needs.

BE HONEST. If the request needs something the One does not have (a second \
amp at once, scenes, a different tone model not on the pedal), say so in \
`summary` and do the best the pedal can."""


def param_reference(adapter) -> str:
    rows = adapter.named_params()
    lines = ["THE TONEX ONE'S PRESETS (number, name, tags):"]
    try:
        for i, name in sorted(adapter.preset_names().items()):
            tags = adapter.preset_tags(i) if hasattr(adapter, "preset_tags") else {}
            t = ", ".join(v for v in (tags.get("character"), tags.get("instrument"))
                          if v and v != "None")
            lines.append(f"  {i + 1} {name}" + (f"  [{t}]" if t else ""))
    except Exception as e:                    # noqa: BLE001  reported, not swallowed
        lines.append(f"  (the preset list could not be read: {e})")
    lines += ["", "THE PARAMETERS (everything that can be changed):"]
    for r in rows:
        about = f"  ({r['about']})" if r.get("about") else ""
        if r["options"] and r["name"].startswith("SLOT_"):
            lines.append(f"{r['name']}: one of the presets above, as \"<number> <name>\"{about}")
        elif r["options"]:
            lines.append(f"{r['name']}: one of {', '.join(r['options'])}{about}")
        else:
            lines.append(f"{r['name']}: {r['lo']} to {r['hi']}{about}")
    return "\n".join(lines)


def device_state(adapter) -> str:
    try:
        patch = adapter.patch()
        number, name = adapter.current_preset()
    except Exception as e:                    # noqa: BLE001  reported, not swallowed
        return f"The ToneX One's current settings could not be read: {e}"
    lines = [f"THE PEDAL RIGHT NOW (playing preset {number} {name}):"]
    for k, v in patch.items():
        lines.append(f"  {k} = {v}")
    return "\n".join(lines)


SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "clarification": {"type": ["string", "null"]},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["set_device_param"]},
                    "param": {"type": "string"},
                    "value": {"type": ["number", "null"]},
                    "type_name": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
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
    from devices.ir2 import planning as base
    return base.validate(plan_obj)


def as_json(obj) -> str:
    return json.dumps(obj, indent=2)

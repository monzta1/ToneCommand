"""Explicit, read-only AFX3 integration inspection. Never changes a preset.

Run only after TC and Axe-Edit release the MIDI port, with the owner's unit
powered on. No server is imported and no routing journal can be restored.
"""
import argparse
from datetime import datetime, timezone
import json
import os

from devices.axefx3.adapter import AxeFxIII
from devices.axefx3 import route_guard, cab_mix


def annotate_modifier_reads(blocks, modifier_state):
    """Stored/display reads are not measurements of a moving controller."""
    for block in blocks:
        block["modifier_state_readable"] = modifier_state["readable"]
        block["modifier_controlled_parameters"] = [
            {"slot": slot["slot"], "param_id": slot["param_id"],
             "parameter": slot["parameter"], "source": slot["source"],
             "source_name": slot["source_name"],
             "display_read": block["parameters"].get(slot["parameter"]),
             "effective_value_verified": False,
             "note": "Display read may stay fixed while the pedal moves; it does not prove a dead binding."}
            for slot in modifier_state.get("slots", [])
            if slot["active"] and slot["effect_id"] == block["effect_id"]
        ]


def inspect(dev):
    start = dev.current_preset()
    start_scene = dev.current_scene()
    firmware = dev.firmware_label()
    blocks = dev.status_dump()
    cells = dev.read_grid()
    try:
        route = {"verified": True, "effect_ids": route_guard.serial_route(cells, blocks, dev.reg)}
    except ValueError as exc:
        route = {"verified": False, "reason": str(exc)}
    route["validation_scope"] = "single_serial_route_only"
    route["note"] = "A parallel topology is not supported by this validator; rejection does not prove a broken audio path."
    observed = []
    for block in blocks or []:
        family = dev.reg.family_of_effect_id(block.effect_id)
        if not family:
            continue
        entry = {"effect_id": block.effect_id, "family": family[0],
                 "channel": block.channel, "bypassed": block.bypassed, "parameters": {}}
        entry["model"] = dev.read_model(family[0], block.effect_id)
        if entry["model"]:
            entry["model"] = {k: v for k, v in entry["model"].items() if k != "words"}
        for fam, pid in dev.reg.params:
            if fam == family[0]:
                spec = dev.reg.spec(fam, pid, family[1])
                entry["parameters"][spec.name] = dev.get_param_display(spec)
        if family[0] == "CABINET":
            entry["cab_mixer"] = cab_mix.inspect(dev, block.effect_id)
        observed.append(entry)
    try:
        slots = {"readable": True, "slots": dev.modifier_report()}
    except ValueError as exc:
        slots = {"readable": False, "reason": str(exc)}
    annotate_modifier_reads(observed, slots)
    end = dev.current_preset()
    end_scene = dev.current_scene()
    end_blocks = dev.status_dump()
    coherent = (start is not None and start == end and start_scene is not None
                and start_scene == end_scene and blocks is not None and blocks == end_blocks)
    return {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "device": dev.device_name,
            "firmware": firmware, "preset_before": start, "preset_after": end,
            "same_preset": start is not None and start == end,
            "scene": end_scene, "same_scene_and_block_status": coherent,
            "route": route, "blocks": observed, "modifiers": slots,
            "read_only": True, "stored": False, "physical_pedal_verified": False,
            "live_modulation_verified": False,
            "note": "Current channels only. No scene switches, global writes, model queries, recording or sound-match claim."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware-read-only", action="store_true", help="Explicitly permit read-only access to the real MIDI device")
    args = parser.parse_args(argv)
    if not args.hardware_read_only:
        parser.error("--hardware-read-only is required; no MIDI opened")
    if os.environ.get("TONECOMMAND_SIM") == "1":
        parser.error("Refusing to label a simulator run as hardware; no MIDI opened")
    dev = AxeFxIII()
    try:
        print(json.dumps(inspect(dev), indent=2, ensure_ascii=True))
    finally:
        dev.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

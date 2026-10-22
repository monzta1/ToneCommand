"""Reviewed-plan execution seam for the new server integration.

No LLM call, implicit flash store, automatic rollback, preset reload or global
pedal mapping. A failed readback stops the remaining actions. Physical muting
is an explicit prerequisite, not something this module can measure or enforce.
"""
from __future__ import annotations

import re
import math
from contextlib import ExitStack
from dataclasses import dataclass

from fm9.device import SetResult
from . import audio_safety, cab_selection, models, modifiers, pedal_control, protocol, route_guard, insertion
from . import fw33_profile


KINDS = {"add_block", "set_param", "set_type", "set_cab", "set_scene", "set_channel",
         "set_bypass", "rename_preset", "rename_scene", "bind_pedal", "bind_controller", "select_nam"}


def integer(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value) or not low <= value <= high:
        raise ValueError(f"Expected an integer {low}..{high}")
    return int(value)


def preset_name(name):
    name = re.sub(r"^(?:(?:AI-|FM9AI-)\s*)+", "", str(name).strip(), flags=re.I)
    if not name or any(ord(c) < 32 or ord(c) > 126 for c in name):
        raise ValueError("Preset name must contain printable ASCII characters")
    return ("AI-" + name)[:32]


@dataclass
class Resolved:
    action: dict
    family: str | None = None
    effect_id: int | None = None
    spec: object = None
    value: object = None


def resolve(reg, action):
    if not isinstance(action, dict) or action.get("kind") not in KINDS:
        raise ValueError("Unsupported action; uploads, stores and global writes are not enabled")
    a = dict(action)
    kind = a["kind"]
    if reg.firmware == fw33_profile.KEY and kind not in (fw33_profile.BUILD_KINDS - {'store'}) | {'set_type','set_cab','bind_controller'}:
        raise ValueError('Action is outside the measured FW33 numeric/NAM profile')
    result = Resolved(a)
    if kind == "rename_preset":
        result.value = preset_name(a.get("type_name") or "")
    elif kind in ("set_scene", "rename_scene"):
        result.value = integer(a.get("value"), 1, 8)
        if kind == "rename_scene":
            name = a.get("type_name")
            if not isinstance(name, str) or not name.strip() or len(name) > 32 or any(ord(c) < 32 or ord(c) > 126 for c in name):
                raise ValueError("Scene name must contain 1..32 printable ASCII characters")
    else:
        instance = integer(a.get("instance", 1), 1, 4)
        family, eid = reg.resolve_block(a.get("block", ""), instance)
        result.family, result.effect_id = family, eid
        if kind == 'select_nam':
            from . import nam_slots
            if reg.firmware != fw33_profile.KEY or family != 'NAM' or eid != 206:
                raise ValueError('NAM selector requires exact FW33 NAM Player 1')
            if set(a) - {'kind','block','instance','value','reason'}:
                raise ValueError('NAM slot action cannot install memory or change arbitrary controls')
            result.value = nam_slots.number(a.get('value'))
            return result
        if kind == "bind_controller":
            if reg.firmware==fw33_profile.KEY:
                from . import wah_voicing
                if not wah_voicing.RELEASED or eid!=94:raise ValueError('Only the released Wah1 musical controller is supported')
            source = {"External 1":12, "External 2":13}.get(a.get("source"))
            mode = a.get("auto_engage")
            pedal_control.validate(eid, source, mode)
            if set(a) - {"kind","block","instance","source","auto_engage","reason"}:
                raise ValueError("Controller binding may not change arbitrary parameters or ranges")
            result.value = (source, mode)
            return result
        if kind in ("set_param", "bind_pedal"):
            base = reg.find_param(family, a.get("param") or "")
            if base is None:
                raise ValueError("No verified parameter for this device/firmware")
            result.spec = reg.spec(family, base.param_id, instance)
        error = audio_safety.action_error(a, family=family, spec=result.spec)
        if error:
            raise ValueError(error)
        if kind == "set_param":
            protocol.set_parameter(reg, result.spec, a.get("value"))
            result.value = a["value"]
        elif kind == "set_type":
            if reg.firmware==fw33_profile.KEY:
                from . import album_planning,wah_voicing
                if not ((family=='DISTORT' and eid==58 and a.get('type_name') in album_planning.MODELS.values())
                        or (family=='FUZZ' and eid==118 and a.get('type_name')=='T808 Mod')
                        or (family=='WAH' and eid==94 and a.get('type_name')=='Cry Babe' and wah_voicing.RELEASED)
                        or (family in fw33_profile.effect_controls.MODELS and
                            (eid,a.get('type_name'))==(fw33_profile.effect_controls.MODELS[family][0],fw33_profile.effect_controls.MODELS[family][4]))):
                    raise ValueError('Only explicitly measured FW33 first-instance models')
            else: models.target(reg, family, eid, a.get("type_name"))
            result.value = a["type_name"]
        elif kind == "set_cab":
            if family != "CABINET":
                raise ValueError("Cab selection requires a Cab block")
            modern=reg.firmware==fw33_profile.KEY
            bank, ordinal = integer(a.get("bank", 0), 0, 6 if modern else 2), integer(a.get("value"), 0, 1023)
            if not modern and bank == 2 and ordinal >= 512 and not reg.cab_catalog.user2_enabled:
                raise ValueError('User2 is NAM storage, not an available cab bank on this profile.')
            side = str(a.get("cab_side") or "left").lower()
            if side not in (("left","right","both","ir1","ir2","ir3","ir4") if modern else ("left","right","both")):
                raise ValueError("Cab side must be LEFT, RIGHT or BOTH")
            if modern:
                from . import cab_inventory
                if eid!=62:raise ValueError('Only measured FW33 Cab1 is supported')
                if side.startswith('ir'):
                    cab_inventory.selection(reg,bank,ordinal,int(side[2:]))
                elif bank!=1 or ordinal not in (515,799) or side!='left':
                    raise ValueError('Expanded Cab selection requires explicit IR1-4 actions')
            else:cab_selection.frame(eid, 0, bank)
            result.value = (bank, ordinal, side)
        elif kind == "set_channel":
            result.value = integer(a.get("value"), 0, 3)
        elif kind == "set_bypass":
            if type(a.get("bypassed")) is not bool:
                raise ValueError("Bypass requires true/false")
            result.value = a["bypassed"]
        elif kind == "bind_pedal":
            if family != "WAH" or result.spec.param_id != 5:
                raise ValueError("Only an existing Wah Control binding is supported at this stage")
            source = a.get("source", "External 1")
            result.value = {"External 1": 12, "External 2": 13}.get(source)
            if result.value is None:
                raise ValueError("Choose External 1 or External 2 explicitly")
            if a.get("value") is not None:
                raise ValueError("Modifier range changes need device-built curve evidence; existing range is preserved")
    return result


def prepare(dev, actions, required_route, expected_preset):
    """All validation is read-only, including before an empty-grid build."""
    if type(expected_preset) is not int or expected_preset not in range(512):
        raise ValueError("Explicit target preset in 0..511 required")
    limit=640 if dev.reg.firmware==fw33_profile.KEY else 512
    if not isinstance(actions, list) or not actions or len(actions) > limit:
        raise ValueError(f"Plan must contain 1..{limit} explicit actions")
    resolved = [resolve(dev.reg, a) for a in actions]
    if dev.firmware_label() != dev.reg.firmware or dev.reg.firmware not in ('32.06', fw33_profile.KEY):
        raise ValueError("Firmware does not match the verified profile")
    preset = dev.current_preset()
    if not preset or preset[0] != expected_preset:
        raise ValueError("Target preset changed or could not be read")
    expected, actual = route_guard.planned_route(dev, dev.reg, required_route, actions)
    if dev.reg.firmware == fw33_profile.KEY:
        from . import fw33
        return fw33.prepare(dev, resolved, expected, actual)
    if actual and actual != expected:
        insertion.plan(dev, required_route, actions)
    for item in resolved:
        if item.effect_id is not None and item.effect_id not in expected:
            raise ValueError("Action targets a block outside the reviewed route")
    # Preflight every future explicitly selected extra-effect channel using
    # passive bulk data. Do not discover an unsupported mode halfway through.
    from . import tone_controls
    channels,extra_bulk,new_models={},{},set()
    additions={i.effect_id for i in resolved if i.action['kind']=='add_block'}
    scene_changed=False
    for item in resolved:
        kind=item.action['kind']
        if kind=='set_scene':channels.clear();scene_changed=True
        if item.family not in tone_controls.LAYOUTS:continue
        if kind=='set_channel':channels[item.effect_id]=item.value
        if kind=='set_type' and item.effect_id not in actual:
            if item.effect_id not in channels:raise ValueError('New effect model needs an explicit channel')
            new_models.add((item.effect_id,channels[item.effect_id]))
        if kind=='set_param':
            if item.effect_id not in actual:
                if (item.family not in ('FUZZ','COMP') or item.effect_id not in additions
                        or item.effect_id not in channels
                        or (item.effect_id,channels[item.effect_id]) not in new_models):
                    raise ValueError('New Drive/Compressor writes require ADD, explicit channel and captured model first')
                continue
            if item.effect_id not in channels:
                if scene_changed:raise ValueError('Extra-effect channel must be explicit after scene selection')
                channels[item.effect_id]=dev.get_channel(item.effect_id)
            if item.effect_id not in extra_bulk:extra_bulk[item.effect_id]=dev.bulk_read(item.effect_id)
            error=tone_controls.profile_error(item.spec,extra_bulk[item.effect_id],channels[item.effect_id])
            if error:raise ValueError(error)
    native = [i for i in resolved if i.action['kind'] == 'bind_controller']
    slots = pedal_control.entries(dev) if native else modifiers.preflight(dev)
    if any(s.get('effect_id') in (additions-set(actual)) & {118,46} for s in slots):
        raise ValueError('Absent block already has a modifier record; no automatic recreation')
    if native:
        if len({i.effect_id for i in native}) != len(native):
            raise ValueError('Duplicate controller binding in this plan')
        needed = 0
        for item in native:
            matches = [s for s in slots if (s['effect_id'],s['param_id']) ==
                       (item.effect_id,pedal_control.TARGETS[item.effect_id])]
            if item.effect_id in actual:
                pedal_control.preflight(dev,item.effect_id,*item.value)
            elif matches:
                raise ValueError('Absent block already has a modifier record; no automatic recreation')
            needed += not matches
        if needed > sum(s['source'] == s['effect_id'] == 0 for s in slots):
            raise ValueError('Insufficient native modifier slots; nothing sent')
    for item in resolved:
        if item.action["kind"] == "bind_pedal":
            candidates = [s for s in slots if s["active"] and s["effect_id"] == item.effect_id and s["param_id"] == 5]
            if len(candidates) != 1 or not candidates[0]["curve_structurally_usable"]:
                raise ValueError("A device-built, working Wah curve is needed before building this plan; no changes sent")
            item.action["modifier_slot"] = candidates[0]["slot"]
    # A model reset followed only by engage would leave the quiet staging level
    # as the final tone. Require an explicit final level in the same channel.
    channels = {}
    for index, item in enumerate(resolved):
        kind, eid = item.action["kind"], item.effect_id
        if kind == "set_scene":
            channels.clear()
        elif kind == "set_channel":
            channels[eid] = item.value
        elif kind == "set_type":
            if eid not in channels:
                raise ValueError("Model choice requires an explicit preceding channel selection")
            level_pid = models.LAYOUTS[item.family][3]
            final_level = False
            for later in resolved[index + 1:]:
                lk = later.action["kind"]
                if lk == "set_scene" or (later.effect_id == eid and lk in ("set_channel", "set_type", "set_bypass")):
                    break
                if later.effect_id == eid and lk == "set_param" and later.spec.param_id == level_pid:
                    final_level = True
            if not final_level:
                raise ValueError("Model reset requires an explicit final level before engaging or leaving the channel")
    return resolved, expected, actual


def execute(dev, actions, required_route, *, expected_preset, external_audio_muted):
    if external_audio_muted is not True:
        raise PermissionError("Confirm external audio remains muted throughout the build")
    with dev._lock:
        resolved, expected, actual = prepare(dev, actions, required_route, expected_preset)
        results = []
        album_proof=None
        with ExitStack() as stack:
            stack.enter_context(dev.edit_session(external_audio_muted=True, expected_preset=expected_preset))
            from . import serial_build
            stack.enter_context(serial_build.execution(dev,expected))
            if actual != expected:
                try:
                    built = dev.build_route(required_route, actions)
                except (OSError, RuntimeError, ValueError, KeyError) as exc:
                    built = SetResult(False, f"Route construction stopped: {exc}", None, None)
                if not built.ok:
                    return {"ok": False, "results": [], "detail": built.detail, "phase": "build_route",
                            "skipped": len(actions), "stored": False, "physical_volume_verified": False,
                            "recovery": "Partial routing may remain in the edit buffer. Keep external audio muted; no automatic rollback."}
            from . import album_build
            album_enabled=dev.reg.firmware==fw33_profile.KEY and tuple(expected)==serial_build.ROUTE and any(i.action['kind']=='set_type' for i in resolved)
            album=stack.enter_context(album_build.execution(dev,resolved,album_enabled))
            for item in resolved:
                a, eid, kind = item.action, item.effect_id, item.action["kind"]
                try:
                    def operation():
                        if album and kind=='set_type': return album.model(item.value)
                        if album and kind=='set_bypass' and eid==118:
                            got=album.drive_bypass(item.value)
                            return SetResult(got is item.value,'Drive state independently read back',None,got)
                        if album and kind=='set_bypass' and eid==94 and album.wah:
                            got=album.wah_bypass(item.value)
                            return SetResult(got is item.value,'Wah state independently read back',None,got)
                        if album and kind=='set_bypass' and eid in (46,50):
                            got=album_build.reviewed_effects.typed_bypass(album,eid,item.value)
                            return SetResult(got is item.value,'Typed auxiliary state; full independent verification follows',None,got)
                        if album and kind=='set_cab': return album.cab(*item.value)
                        if album and kind=='set_channel':
                            got=album.channel(eid,item.value)
                            return SetResult(got==item.value,'Independent channel readback',None,got)
                        if album and kind=='set_scene':
                            album.write(protocol.envelope(0x0c,[item.value-1]))
                            for _ in range(5):
                                import time
                                time.sleep(.2)
                                got=dev.current_scene()
                                if got==item.value: return SetResult(True,'Independent scene readback',None,got)
                            return SetResult(False,'Scene readback failed; no write retry',None,got)
                        return apply(dev,item,expected)
                    result=album.run(item,operation) if album else operation()
                except (OSError, RuntimeError, ValueError, KeyError) as exc:
                    result = SetResult(False, f"Execution stopped: {exc}", None, None)
                results.append({"action": a, "ok": result.ok, "detail": result.detail,
                                "before": result.display_before, "after": result.display_after})
                if not result.ok:
                    break
            ok = len(results) == len(actions) and all(r["ok"] for r in results)
            if ok:
                try:
                    route_guard.check_route(dev, dev.reg, required_route, complete=True)
                except (OSError, RuntimeError, ValueError, KeyError) as exc:
                    ok = False
                    results.append({"ok": False, "detail": str(exc), "phase": "final_route"})
            if ok and album: album_proof=album.proof()
        return {"ok": ok, "results": results, "skipped": max(0, len(actions) - len(results)),
                "stored": False, "physical_volume_verified": False,
                **({'album_verification':album_proof} if album_proof else {}),
                "recovery": "No automatic rollback; partial edit-buffer changes may remain. Nothing stored."}


def apply(dev,item,expected):
    """Existing action dispatch, also used under bounded album state checks."""
    from . import serial_build
    a,eid,kind=item.action,item.effect_id,item.action['kind']
    if kind == "add_block":
        result = SetResult(True, "Present in the verified required route", None, eid)
    elif kind == "set_param": result = dev.set_param_display(item.spec, item.value)
    elif kind == "set_type": result = dev.set_model(item.family, eid, item.value)
    elif kind == 'select_nam': result = dev.select_nam_slot(item.value)
    elif kind == "set_cab": result = dev.set_cab(eid, *item.value)
    elif kind == "bind_pedal":
        result = dev.assign_existing_modifier(a["modifier_slot"], eid, 5, item.value)
    elif kind == "bind_controller":
        result = dev.bind_pedal_control(eid, *item.value)
    else:
        if kind == "set_scene": actual_value = dev.set_scene(item.value)
        elif kind == "set_channel": actual_value = dev.set_channel(eid, item.value)
        elif kind == "set_bypass":
            actual_value = (serial_build.bypass(dev,eid,item.value)
                if tuple(expected) == serial_build.ROUTE and dev.reg.firmware == fw33_profile.KEY
                else dev.set_bypass(eid, item.value))
        elif kind == "rename_preset":
            got = dev.rename_preset(item.value)
            actual_value = got[1] if got else None
        elif kind == "rename_scene":
            got = dev.rename_scene(item.value, a["type_name"])
            actual_value = got[1] if got and got[0] == item.value else None
        wanted = a["type_name"] if kind == "rename_scene" else item.value
        ok = actual_value is not None and actual_value == wanted
        result = SetResult(ok, "Independent readback matched" if ok else "Readback mismatch; stopped", None, actual_value)
    return result

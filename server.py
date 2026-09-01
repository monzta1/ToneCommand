#!/usr/bin/env python3
"""FM9 natural-language tone controller - local web server.

Run:  .venv/bin/python server.py   then open http://127.0.0.1:8909

Safety contract: edit-buffer only. No store/save command is implemented;
nothing is ever written to a preset slot on the unit.
"""
from __future__ import annotations

import threading
import uuid
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from fm9.device import FM9, FM9NotFound
from fm9.registry import Registry
from fm9 import (ai_settings, designs, editbuffer, health, planner,
                 recipes as recipebook, rigprofile, scratch_build, share)
# `slots` is a local variable in more than one function here, so the module
# gets a name that cannot be shadowed by one.
from fm9 import slots as slotops
from tools import path_audit
from fm9 import protocol as proto
from fm9.signal_path import resolve_aliases

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="FM9 Tone Control")

reg = Registry()
_lock = threading.Lock()
# Planner configuration lives in os.environ, which the settings panel rewrites
# and the planner rereads inside each backend runner. A save landing mid-plan
# could therefore tear the view: candidates() has already chosen a backend,
# then the runner picks up the new key and the old URL (@Triumph1701 on #25).
# Held for the whole planner call, and a save that cannot get it says so
# rather than hanging for the length of a plan.
_settings_lock = threading.Lock()
_fm9: FM9 | None = None

FRIENDLY = {"DISTORT": "Amp", "CABINET": "Cab", "FUZZ": "Drive", "GATE": "Gate",
            "INPUT": "Input", "OUTPUT": "Output", "COMP": "Compressor",
            "GEQ": "Graphic EQ", "PEQ": "Parametric EQ", "REVERB": "Reverb",
            "DELAY": "Delay", "CHORUS": "Chorus", "FLANGER": "Flanger",
            "PHASER": "Phaser", "WAH": "Wah", "PITCH": "Pitch",
            "FILTER": "Filter", "VOLUME": "Volume", "TREMOLO": "Tremolo",
            "FDBKSEND": "Send", "FDBKRET": "Return", "PLEX": "Plex Delay",
            "MULTITAP": "Multitap", "ROTARY": "Rotary", "LOOPER": "Looper"}

# Params surfaced to the planner and read for the state snapshot, per family.
INTEREST = {
    "DISTORT": [11, 12, 13, 14, 15, 26, 30, 1],
    "INPUT": [0, 1, 2, 3],
    "GATE": [0, 1, 3, 9],
    "FUZZ": [0, 1, 2, 3],
    "GEQ": list(range(0, 10)) + [11],
    "PEQ": list(range(0, 5)),
    "DELAY": [0, 1, 12, 32],
    "REVERB": [0, 1, 11],
    "PHASER": [2, 5, 6, 11, 12],
    "FLANGER": [1, 3, 4, 11, 12],
    "CHORUS": [2, 4, 10, 11],
    # The sweep itself (5) matters more than the level: it is the parameter a
    # pedal or an envelope is attached to, so leaving it off the page meant
    # the one control that answers "is this a pedal wah or an auto-wah" was
    # never drawn. 1/2 bound the sweep, 3 is the resonance.
    "WAH": [5, 1, 2, 3, 6, 10],
    "TREMOLO": [2, 3, 7],
    "ROTARY": [0, 5, 6],
}


# What drives a parameter, when something other than the stored value does.
#
# Only ordinal 11 is grounded: this tool binds it and reads it back in
# _bind_pedal, so Pedal 2 is a fact rather than a guess. Every other source is
# reported by its number. The display-name query would be the obvious way to
# name the rest and it is a trap: for modifier source enums it returns "NONE"
# regardless of the actual source (docs/PROTOCOL.md finding 5). Naming an
# unknown ordinal would be inventing a fact about someone's rig, so it stays a
# number until a roster is harvested off the FM9's own screen.
MOD_SOURCES = {11: "Pedal 2"}   # PEDAL_2_SOURCE; kept in step by test


def read_modifiers(fm9: FM9) -> dict:
    """Which parameters are driven by something other than their own value.

    A modifier takes the parameter over: the FM9 sources it from the pedal,
    envelope or LFO, and the value stored on the block stops being what you
    hear. So a slider we draw for a modified parameter is a control that does
    nothing, which is the worst kind, and the page has to say so.

    All 32 slots read in about 0.14s, cheap enough for the state poll.
    """
    from fm9 import protocol as fp
    out = {}
    for slot in range(1, fp.MOD_SLOT_COUNT + 1):
        # Per slot, because one unreadable slot is a gap in this map and not a
        # reason to lose the other thirty-one.
        try:
            vals = fm9.bulk_read(fp.mod_slot_eid(slot))
            if not vals or len(vals) <= fp.MOD_PID_TARGET_PARAM:
                continue
            eid = vals[fp.MOD_PID_TARGET_EFFECT]
            # A never-used slot is all zeroes, and effect id 0 is not a block.
            if not eid:
                continue
            fam = reg.family_of_effect_id(eid)
            if not fam:
                continue
            fname, inst = fam
            spec = reg.spec(fname, vals[fp.MOD_PID_TARGET_PARAM], inst)
            src = vals[fp.MOD_PID_SOURCE]
        except Exception:
            continue
        out[spec.name] = {
            "slot": slot,
            "source": int(src),
            "source_name": MOD_SOURCES.get(src, f"source #{src}"),
            "known": src in MOD_SOURCES,
        }
    return out


def _safe_modifiers(fm9: FM9) -> dict:
    """read_modifiers, but never the reason a poll fails."""
    try:
        return read_modifiers(fm9)
    except Exception:
        return {}


#: Last time the MIDI bus was re-enumerated, so a disconnected poll can look
#: for a newly arrived device without doing it several times a second when
#: more than one endpoint asks at once.
_last_rescan = {"at": 0.0}
RESCAN_EVERY = 2.0


def get_fm9() -> FM9:
    global _fm9
    if _fm9 is None:
        import os
        if os.environ.get("TONECOMMAND_SIM") == "1":
            from fm9.sim import SimFM9
            _fm9 = SimFM9(reg)     # virtual device: UI/planner dev offline
        else:
            # Look at the bus again before trying. Without this the retry is
            # pointless: the rtmidi backend enumerates through a CoreMIDI
            # client it holds for the life of the process, so a device plugged
            # in after startup is invisible however many times we reconstruct.
            # Reloading costs about eleven milliseconds and leaks nothing,
            # which is well worth paying on a poll that is failing anyway.
            now = time.monotonic()
            if now - _last_rescan["at"] >= RESCAN_EVERY:
                _last_rescan["at"] = now
                rescan_midi()
            _fm9 = FM9(reg)
    return _fm9


def rescan_midi() -> None:
    """Make mido look at the MIDI bus again.

    FM9.__init__ calls mido.get_input_names() fresh every time, so it looked
    like discovery could not go stale. It can: the rtmidi backend holds a
    CoreMIDI client for the life of the process and enumerates through it, so
    a server started while the FM9 was switched off never sees it appear. The
    device was plugged in, visible to every other process on the machine, and
    invisible to this one until it was restarted.

    Reloading the backend builds a new client, which is the only way to pick
    up a port that arrived after startup.
    """
    try:
        import mido
        mido.set_backend("mido.backends.rtmidi", load=True)
    except Exception:
        # A backend that will not reload is no worse than before: the next
        # open still tries, it just may not see a newly arrived port.
        pass


def drop_fm9():
    global _fm9
    if _fm9 is not None:
        try:
            _fm9.close()
        except Exception:
            pass
        _fm9 = None


def param_reference() -> str:
    """Static text listing controllable params, for the planner (cacheable)."""
    lines = []
    for fam, pids in INTEREST.items():
        for pid in pids:
            s = reg.spec(fam, pid)
            if s.dmin is None:
                continue
            label = s.label or s.name
            lines.append(f"{s.name} (block={FRIENDLY.get(fam, fam).lower()}, "
                         f"\"{label}\", {s.dmin}..{s.dmax} {s.unit or ''}, {s.scale})")
    lines.append("Scenes: 1-8 via set_scene. Block bypass via set_bypass. "
                 "Block channel A-D (0-3) via set_channel. Tempo via set_tempo.")
    from fm9.device import get_store_slots
    _slots = sorted(get_store_slots())
    lines.append(f"Storable slots (store action): "
                 f"{_slots[0]}-{_slots[-1]}" if _slots else
                 "Storing is DISABLED on this install (no slots configured); never propose store.")
    lines.append("\nAmp models selectable via set_type (block=amp). One per line as "
                 "`type_name = the real-world amp it models`; use the name to the "
                 "LEFT of the '=' as type_name, verbatim:")
    lines.extend(reg.amp_description(o) for o in reg.amp_roster)
    lines.append("\nDrive models selectable via set_type (block=drive). One per line as "
                 "`type_name = the real pedal it models` where known; use the LEFT name "
                 "verbatim as type_name. Entries without an '=' have no confirmed "
                 "real-world mapping; do not invent one:")
    lines.extend(reg.drive_description(o) for o in reg.drive_roster)
    et = reg.effect_type_models
    if et:
        lines.append("\nDelay/chorus type real-world references (NAME-keyed; "
                     "types cannot be SET yet, use for describing and "
                     "recommending only):")
        for section in ("delay_types", "chorus_types", "multitap_types"):
            for name, model in (et.get(section) or {}).items():
                lines.append(f"{name} = {model}")
    lines.append("\nReverb types selectable via set_type (block=reverb):")
    lines.append(", ".join(str(v) for v in reg.reverb_roster.values()))
    if reg.dynacabs:
        lines.append("\nDynaCab cabinets and the real cabs they capture "
                     "(cab selection is NOT a plannable action yet; use "
                     "only to describe or recommend, never to propose a "
                     "set):")
        for name, rec in reg.dynacabs.items():
            model = rec.get("model")
            lines.append(f"{name} = {model}" if model else name)
    return "\n".join(lines)


PARAM_REFERENCE = param_reference()


def shared_scenes(fm9: FM9) -> dict:
    """For each block, the scenes currently using each of its channels.

    The FM9 stores bypass and channel per scene, but block PARAMETERS live on
    the CHANNEL. So "make this scene grittier" moves every other scene sitting
    on that channel too, and nothing in the UI showed that before.

    COSTS A SCENE SWEEP. There is no way to read another scene's channel
    assignments without visiting it, so this walks all eight and returns to
    where it started. That is audible, so it must NEVER run on the state poll:
    it is called deliberately and cached per preset. Any scene that does not
    answer is skipped rather than guessed at.
    """
    here = fm9.scene_name()
    active = here[0] if here else 1
    by_block: dict = {}
    try:
        for sc in range(1, 9):
            try:
                fm9.set_scene(sc)
                blocks = fm9.status_dump() or []
            except Exception:
                continue
            for b in blocks:
                key = str(b.effect_id)
                by_block.setdefault(key, {}).setdefault(str(b.channel), []).append(sc)
    finally:
        try:
            fm9.set_scene(active)
        except Exception:
            pass
    return by_block


def scene_names(fm9: FM9) -> list[dict]:
    """Names of all eight scenes, for labelling the UI's scene buttons.

    Queried by number, so the loaded scene is untouched. A scene that does
    not answer is reported as None rather than guessed at or skipped, so the
    button still renders and says nothing it cannot back up.
    """
    out = []
    for n in range(1, 9):
        try:
            got = fm9.scene_name(n)
        except Exception:
            got = None
        out.append({"number": n, "name": got[1] if got else None})
    return out


def snapshot(fm9: FM9) -> dict:
    preset = fm9.current_preset()
    if preset is None:
        # Nothing came back. An open port is not a connected device: pulling
        # the USB leaves the handle valid and every read simply times out, so
        # the old code built a snapshot with no preset, no scene and no blocks
        # and still reported connected, leaving the link light green over an
        # empty page.
        #
        # Raised BEFORE the rest of the reads rather than after, because the
        # rest are eight scene names and a status dump, each waiting out its
        # own timeout: finding out slowly would freeze the poll for ten
        # seconds an unplugged device does not deserve.
        raise FM9NotFound("the FM9 stopped answering; is it still plugged in?")
    scene = fm9.scene_name()
    blocks = fm9.status_dump() or []
    out_blocks = []
    values = {}
    # What each value IS, so the UI can offer a control instead of a readout.
    # The browser used to carry its own table of maxima, which meant it could
    # only draw the seven amp knobs it knew about and drew every one of them
    # as though it ran 0-10. Ranges belong to the registry, so they are sent
    # from here and the UI stops guessing.
    meta = {}
    seen_fams = set()
    for b in blocks:
        fam = reg.family_of_effect_id(b.effect_id)
        if not fam:
            continue
        fname, inst = fam
        label = f"{FRIENDLY.get(fname, fname)} {inst}"
        out_blocks.append({"family": fname, "instance": inst, "label": label,
                           "bypassed": b.bypassed, "channel": "ABCD"[b.channel],
                           # the UI needs these to drive the block directly
                           "effect_id": b.effect_id,
                           "channel_index": b.channel,
                           "channels": max(1, b.channels_supported)})
        if fname == "CABINET" and "cab" not in values:
            vals = fm9.bulk_read(b.effect_id)
            if vals:
                chans = max(1, fm9._channels.get(b.effect_id, 1))
                stride = len(vals) // chans if chans > 1 else len(vals)
                base = min(b.channel, chans - 1) * stride
                bank, slot = vals[base + 0], vals[base + 4]
                values["cab"] = reg.cab_description(slot, bank)
                # the UI needs the address, not just the description, so the
                # audition list can show which one is loaded
                meta["__cab__"] = {"bank": int(bank), "ordinal": int(slot)}
        if fname in INTEREST and fname not in seen_fams:
            seen_fams.add(fname)
            vals = fm9.bulk_read(reg.effect_id(fname, inst))
            if vals:
                chans = max(1, fm9._channels.get(reg.effect_id(fname, inst), 1))
                stride = len(vals) // chans if chans > 1 else len(vals)
                base = min(b.channel, chans - 1) * stride
                if fname == "DISTORT" and base + 10 < len(vals):
                    values["AMP_MODEL"] = reg.amp_roster.get(
                        str(vals[base + 10]), f"ordinal {vals[base + 10]}")
                # The same trick for every other block whose type has real
                # names. Read the wire and map through the roster, never the
                # display-name query: that returns a stale constant rather
                # than the current type (docs/PROTOCOL.md finding 5).
                tp = TYPE_PARAMS.get(fname)
                if tp and fname != "DISTORT":
                    pid, roster_attr = tp
                    if base + pid < len(vals):
                        roster = getattr(reg, roster_attr) or {}
                        wire = vals[base + pid]
                        values[f"{fname}_TYPE_NAME"] = roster.get(
                            str(wire), f"ordinal {wire}")
                for pid in INTEREST[fname]:
                    s = reg.spec(fname, pid, inst)
                    idx = base + pid
                    if s.dmin is not None and idx < len(vals):
                        from fm9.protocol import normalized_to_display
                        values[f"{s.name}"] = round(
                            normalized_to_display(vals[idx] / 65534, s.dmin, s.dmax, s.scale), 2)
                        meta[s.name] = {
                            "family": fname, "instance": inst, "param": s.name,
                            "min": s.dmin, "max": s.dmax, "scale": s.scale,
                            "unit": s.unit or "",
                            # the label the FM9 itself uses, so the panel reads
                            # like the unit rather than like our variable names
                            "label": (s.label or s.name.split("_", 1)[-1]),
                        }
    out_state = {
        "connected": True,
        # label, not just number: the wire numbers presets 0-511 and every
        # tool the owner cross-checks against numbers them 1-512.
        "preset": ({"number": preset[0], "editor": proto.editor_number(preset[0]),
                    "label": proto.slot_label(preset[0]), "name": preset[1]}
                   if preset else None),
        "scene": {"number": scene[0], "name": scene[1]} if scene else None,
        # All eight names so the UI can label its scene buttons with what the
        # owner called them rather than with the numbers 1-8. Read-only: this
        # queries names, it does not switch the active scene.
        "scenes": scene_names(fm9),
        "blocks": out_blocks,
        "values": values,
        "cab_sel": meta.pop("__cab__", None),
        "params": meta,
        # Read every poll rather than cached against the preset number: a
        # modifier can be added or removed from the front panel without the
        # preset changing, and a stale "nothing is bound here" is exactly the
        # statement this exists to stop the page making.
        #
        # Wrapped because /api/state turns ANY exception into drop_fm9() and a
        # red link light. Knowing what drives a parameter is a convenience;
        # losing the whole page and the port because one modifier read
        # hiccuped is not a trade worth making.
        "mods": _safe_modifiers(fm9),
    }
    # Remember the last reading taken from real hardware, so a design can be
    # planned against something true when the rig is off.
    _last_snapshot["state"] = out_state
    _last_snapshot["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return out_state


def state_text(snap: dict) -> str:
    p, s = snap.get("preset"), snap.get("scene")
    lines = []
    if p:
        lines.append(f"Preset {p.get('label', p['number'])}: \"{p['name']}\"")
    if s:
        lines.append(f"Scene {s['number']}: \"{s['name']}\"")
    lines.append("Blocks in preset: " + ", ".join(
        f"{b['label']}{' (bypassed)' if b['bypassed'] else ''} ch{b['channel']}"
        for b in snap["blocks"]))
    lines.append("Current values: " + ", ".join(
        f"{k}={v}" for k, v in snap["values"].items()))
    return "\n".join(lines)


class PromptBody(BaseModel):
    prompt: str


class Action(BaseModel):
    kind: str
    block: str | None = None
    instance: int = 1
    param: str | None = None
    value: float | None = None
    bypassed: bool | None = None
    type_name: str | None = None   # model name for set_type; new name for renames
    position: str | None = None    # add_block: "pre" | "post" | "any" (vs amp)
    bank: int | None = None        # set_cab: which cab roster the ordinal is in
    reason: str = ""


# family -> (type param id, roster attribute)
TYPE_PARAMS = {"DISTORT": (10, "amp_roster"), "FUZZ": (0, "drive_roster"),
               "REVERB": (10, "reverb_roster")}


def resolve_type_ordinal(family: str, name: str) -> tuple[int, str] | None:
    pid, roster_attr = TYPE_PARAMS.get(family, (None, None))
    if pid is None:
        return None
    roster: dict = getattr(reg, roster_attr)
    needle = name.strip().lower()
    for ordinal, label in roster.items():
        if str(label).lower() == needle:
            return (int(ordinal), str(label))
    # A bare ordinal, which is what the audition list sends: it already knows
    # exactly which model it means and should not have to round trip through a
    # name and back. Checked AFTER the exact-name match above, so an amp
    # actually called "59" still wins over ordinal 59.
    if needle.isdigit() and needle in roster:
        return (int(needle), str(roster[needle]))
    matches = [(int(o), str(l)) for o, l in roster.items()
               if needle in str(l).lower()]
    if matches:
        return min(matches, key=lambda m: len(m[1]))
    if family == "FUZZ":
        by_model = [(int(o), str(roster.get(o, o)))
                    for o, rec in reg.drive_models.items()
                    if needle in str(rec.get("model", "")).lower()]
        if len(by_model) == 1:
            return by_model[0]
    if family == "DISTORT":
        # The planner sees amps as "Fractal name = real amp"; accept the right
        # hand side too, in case it answers with the amp it was actually after.
        by_model = [(int(o), str(roster.get(o, o)))
                    for o, rec in reg.amp_models.items()
                    if needle in str(rec.get("model", "")).lower()]
        if len(by_model) == 1:
            return by_model[0]
    tokens = set(needle.split())
    scored = [(len(tokens & set(str(l).lower().split())), int(o), str(l))
              for o, l in roster.items()]
    best = max(scored)
    return (best[1], best[2]) if best[0] > 0 else None


class ApplyBody(BaseModel):
    actions: list[Action]
    expected_preset: int | None = None


@app.get("/")
def index():
    return FileResponse(ROOT / "ui" / "index.html")


@app.get("/logo.png")
def logo():
    """The mark, for the page header and the browser tab."""
    return FileResponse(ROOT / "ui" / "logo.png", media_type="image/png")


@app.post("/api/reconnect")
def api_reconnect():
    """Look for the FM9 again, now.

    The five second poll retries on its own, but it retries through a stale
    view of the MIDI bus, so it can never find a device that appeared after
    the server started. This drops the handle, rescans, and reports what it
    found, which is also the honest answer when it finds nothing.
    """
    with _lock:
        drop_fm9()
        rescan_midi()
        try:
            snap = snapshot(get_fm9())
        except FM9NotFound as e:
            drop_fm9()
            return {"connected": False, "why": str(e)}
        except Exception as e:
            drop_fm9()
            return {"connected": False, "why": str(e)}
    return {"connected": True, "preset": snap.get("preset")}


@app.get("/api/state")
def api_state():
    with _lock:
        try:
            snap = snapshot(get_fm9())
            return snap
        except FM9NotFound:
            drop_fm9()
            return {"connected": False}
        except Exception as e:
            drop_fm9()
            return JSONResponse({"connected": False, "error": str(e)}, status_code=500)


@app.post("/api/plan")
def api_plan(body: PromptBody):
    # A loaded profile outranks both the live device and the remembered
    # reading: you asked to design for someone else's rig, so designing for
    # your own instead would be answering a different question.
    if _profile["loaded"]:
        prof = _profile["loaded"]
        try:
            with _settings_lock:
                result = planner.plan(body.prompt,
                                      rigprofile.as_state_text(prof),
                                      PARAM_REFERENCE)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=502)
        result["device"] = {"preset": {"name": prof.get("preset_name"),
                                       "label": "shared profile"},
                            "scene": None}
        result["offline"] = True
        result["profile"] = {"author": prof.get("author"),
                             "preset_name": prof.get("preset_name"),
                             "captured": prof.get("captured")}
        result["values"] = {}      # a profile carries none, by design
        for a in result.get("actions", []):
            errs, warns = validate_action(Action(**a))
            a["validation_errors"] = errs
            a["validation_warnings"] = warns
            if a.get("block"):
                try:
                    a["effect_id"] = reg.resolve_block(
                        a["block"], int(a.get("instance") or 1))[1]
                except Exception:
                    pass
        return result

    offline = False
    with _lock:
        try:
            snap = snapshot(get_fm9())
        except FM9NotFound:
            drop_fm9()
            # The device is the only hardware dependency in this whole path:
            # the planner, validation and the grounding catalogs are all local.
            # So with a real reading of a preset to stand on, planning works
            # unplugged. Without one it does not, and inventing state is the
            # exact thing this project refuses everywhere else.
            snap = _last_snapshot["state"]
            offline = True
    # Three kinds of context, in descending order of how much is known:
    # a live or remembered reading, or nothing at all. The last is not a
    # refusal: a request that stands on its own, like building a tone from
    # scratch into a named scene, needs nothing from the rig. What the
    # planner must never do is answer a RELATIVE request against a zero,
    # so it is told exactly what it has rather than being handed an
    # empty-looking state and left to assume.
    context = state_text(snap) if snap else rigprofile.as_blank_text()
    try:
        with _settings_lock:
            result = planner.plan(body.prompt, context, PARAM_REFERENCE)
        result["device"] = ({"preset": snap["preset"], "scene": snap["scene"]}
                            if snap else {"preset": None, "scene": None})
        # Say so loudly. A plan built against a remembered reading is not the
        # same object as one built against a live one, and the difference has
        # to survive all the way to the button.
        result["offline"] = offline
        result["anchored_at"] = _last_snapshot["at"] if offline else None
        result["no_state"] = snap is None
        result["values"] = snap.get("values", {}) if snap else {}
        for a in result.get("actions", []):
            errs, warns = validate_action(Action(**a))
            a["validation_errors"] = errs
            a["validation_warnings"] = warns
            # The store confirmation is the one destructive prompt in the
            # product, so the slot it names has to match what the owner sees
            # in FM9-Edit. Rendered here rather than in the browser, so the
            # numbering rule stays in protocol.py alone.
            if a.get("kind") == "store" and isinstance(a.get("value"), (int, float)):
                a["slot_label"] = proto.slot_label(int(a["value"]))
            # Resolve the block to its effect id so the UI can say which other
            # scenes share its channel and will move with a parameter edit.
            # Resolved here for the same reason as the label: one place.
            if a.get("block"):
                try:
                    # resolve_block already returns (family, effect_id)
                    a["effect_id"] = reg.resolve_block(
                        a["block"], int(a.get("instance") or 1))[1]
                except Exception:
                    pass
        # A splice moves blocks the user did not ask about, and may spend a
        # pass-through cell that cannot be put back, so the consequences are
        # attached HERE rather than discovered at apply time: the plan is what
        # gets confirmed, and consent to "add a block" is not consent to
        # rearrange the row.
        adds = [a for a in result.get("actions", []) if a.get("kind") == "add_block"]
        if adds:
            with _lock:
                try:
                    fm9 = get_fm9()
                    for a in adds:
                        intent = _splice_plan_for(fm9, Action(**a))
                        if intent is not None:
                            a["splice"] = intent
                            if not intent["ok"]:
                                a["validation_errors"] = a["validation_errors"] + [
                                    f"cannot place this block: {intent['detail']}"]
                except FM9NotFound:
                    drop_fm9()
        return result
    except Exception as e:
        return JSONResponse({"error": f"planner failed: {e}"}, status_code=502)


TEMPO_RANGE = (30, 250)   # Fractal tempo limits


def validate_action(a: Action) -> tuple[list[str], list[str]]:
    """Validate an action against the parameter reference BEFORE anything is
    sent. Returns (errors, warnings). Errors block transmission of that
    action; warnings are surfaced but do not block. Never auto-corrects.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if a.kind == "set_scene":
        scene = a.value if a.value is not None else a.instance
        if not isinstance(scene, (int, float)) or not 1 <= int(scene) <= 8:
            errors.append(f"scene must be 1..8, got {scene}")
        return errors, warnings
    if a.kind == "store":
        from fm9.device import get_store_slots
        allowed = get_store_slots()
        slot = int(a.value) if a.value is not None else None
        if not allowed:
            errors.append("storing is disabled: configure TONECOMMAND_STORE_SLOTS "
                          "with slots on your unit that are safe to overwrite")
        elif slot is None or slot not in allowed:
            errors.append(f"store only allowed to configured slots "
                          f"{sorted(allowed)[0]}-{sorted(allowed)[-1]}, got {a.value}")
        else:
            warnings.append(f"store will OVERWRITE whatever is saved in slot {slot}")
        return errors, warnings
    if a.kind == "rename_preset":
        if not a.type_name or not a.type_name.strip():
            errors.append("rename_preset requires a name in type_name")
        elif len(a.type_name) > 32:
            errors.append(f"preset name exceeds 32 chars: {a.type_name!r}")
        return errors, warnings
    if a.kind == "rename_scene":
        if a.value is None or not 1 <= int(a.value) <= 8:
            errors.append(f"rename_scene requires scene 1..8 in value, got {a.value}")
        if not a.type_name or len(a.type_name) > 32:
            errors.append("rename_scene requires a name (max 32 chars) in type_name")
        return errors, warnings
    if a.kind == "set_tempo":
        if a.value is None or not TEMPO_RANGE[0] <= a.value <= TEMPO_RANGE[1]:
            errors.append(f"tempo must be {TEMPO_RANGE[0]}..{TEMPO_RANGE[1]} BPM, got {a.value}")
        return errors, warnings
    # block-addressed actions
    try:
        fam, _eid = reg.resolve_block(a.block or "", a.instance)
    except (KeyError, ValueError) as e:
        errors.append(str(e))
        return errors, warnings
    if a.kind == "add_block":
        if a.position not in (None, "pre", "post", "any"):
            errors.append(f"position must be pre/post/any, got {a.position!r}")
    elif a.kind in ("bind_pedal", "unbind_pedal"):
        spec = reg.find_param(fam, a.param or "")
        if spec is None:
            for (f, pid), pdata in reg.params.items():
                if f == fam and pdata.get("name") == a.param:
                    spec = reg.spec(f, pid, a.instance)
                    break
        if spec is None:
            errors.append(f"unknown parameter {a.param!r} on block {a.block}")
        elif spec.kind == "enum":
            errors.append(f"{spec.name} is a selector; pedals bind to continuous parameters")
        if a.value is not None and not 0 <= a.value <= 100:
            errors.append(f"pedal floor must be 0..100 percent, got {a.value}")
    elif a.kind == "set_bypass":
        if not isinstance(a.bypassed, bool):
            errors.append("set_bypass requires bypassed true/false")
    elif a.kind == "set_channel":
        if a.value is None or int(a.value) not in (0, 1, 2, 3):
            errors.append(f"channel must be 0..3 (A-D), got {a.value}")
    elif a.kind == "set_type":
        if fam not in TYPE_PARAMS:
            errors.append(f"model selection not supported on block {a.block}")
        elif resolve_type_ordinal(fam, a.type_name or "") is None:
            errors.append(f"unknown model name: {a.type_name!r}")
    elif a.kind == "set_cab":
        bank = 0 if a.bank is None else int(a.bank)
        roster = reg.cab_rosters.get(str(bank))
        if roster is None:
            errors.append(f"no cab bank {bank}; banks are "
                          f"{sorted(reg.cab_rosters, key=int)}")
        elif a.value is None or str(int(a.value)) not in roster:
            errors.append(f"cab {a.value} is not in bank {bank} "
                          f"({len(roster)} entries)")
    elif a.kind == "set_param":
        spec = None
        for (f, pid), pdata in reg.params.items():
            if f == fam and pdata.get("name") == a.param:
                spec = reg.spec(f, pid, a.instance)
                break
        if spec is None and a.param:
            spec = reg.find_param(fam, a.param)
        if spec is None:
            errors.append(f"unknown parameter {a.param!r} on block {a.block}")
        elif a.value is None or not isinstance(a.value, (int, float)):
            errors.append(f"{a.param} requires a numeric value, got {a.value!r}")
        elif spec.kind == "enum":
            errors.append(f"{spec.name} is a selector, not a continuous parameter; use set_type or a supported action")
        elif spec.dmin is None or spec.dmax is None:
            warnings.append(f"{spec.name} has no calibrated range in the reference; value {a.value} sent unvalidated")
        elif not spec.dmin <= a.value <= spec.dmax:
            errors.append(f"{spec.name} value {a.value} outside its range {spec.dmin}..{spec.dmax} {spec.unit or ''}")
    if a.kind == "add_block":
        warnings.append(
            "new blocks arrive with factory-default settings and will sound "
            "plain until voiced (clone a reference preset's settings or dial "
            "by ear); default voicing is not a finished sound")
    if a.kind == "bind_pedal":
        warnings.append(
            "pedal-binding curve direction is NOT verified on this hardware "
            "(issue #11): sweep may be reversed or dead; confirm by ear "
            "immediately after applying")
    # Writing to a parameter a modifier owns lands, verifies by read-back, and
    # changes nothing anybody can hear: the FM9 sources the value from the
    # pedal, envelope or LFO instead. The browser already refuses to draw a
    # slider for one, but a plan can still name it, and "verified" on a change
    # with no audible effect is the most misleading thing this tool can say.
    # Same failure, different cause: a bypassed block is not in the signal, so
    # a write to it lands, verifies, and changes nothing anyone can hear. The
    # symptom that found it was "changing the drive has no effect", on a preset
    # whose Drive block was simply switched off.
    if a.kind == "set_param":
        state = _last_snapshot.get("state") or {}
        for b in state.get("blocks") or []:
            if b.get("family") == fam and b.get("instance") == a.instance \
                    and b.get("bypassed"):
                warnings.append(
                    f"{fam} {a.instance} is BYPASSED (as of the last reading), "
                    f"so it is not in the signal. The write will land and "
                    f"verify, and you will hear no difference until the block "
                    f"is engaged.")
                break
    if a.kind == "set_param" and a.param:
        driven = ((_last_snapshot.get("state") or {}).get("mods") or {}).get(a.param)
        if driven:
            warnings.append(
                f"{a.param} is driven by {driven['source_name']} on modifier "
                f"slot {driven['slot']} (as of the last reading). The write "
                f"will land and verify, and you will hear no difference, "
                f"because the FM9 takes this parameter from the modifier. "
                f"Remove the binding first if you meant to set it by hand.")
    return errors, warnings


#: Where a block was asked to go, as a phrase rather than an enum. Interpolating
#: the raw value produced "no free pass-through cell any of the amp".
_POSITION_PHRASE = {"pre": "before the amp", "post": "after the amp",
                    "any": "anywhere on the grid"}


def _no_placement_detail(a: Action, pos: str, cells: list | None) -> str:
    """Why a block could not be placed, in terms of the wall actually hit.

    An EMPTY preset is not a full one. It has no grid cells at all, not even
    the pass-through shunts (PROTOCOL finding 18), so "no free pass-through
    cell" describes a preset packed with blocks and says nothing useful about
    a slot that is simply blank. The two need different answers, because only
    one of them is the user's fault.
    """
    where = _POSITION_PHRASE.get(pos, f"at position {pos!r}")
    if cells is None:
        # A read that did not answer is a THIRD wall, and the worst one to
        # get wrong: finding 18 says an empty slot's grid read SUCCEEDS with
        # zero cells, so folding a timeout into "empty" is a confident wrong
        # diagnosis that then tells the owner to go and load another preset.
        return (f"the grid did not answer, so where {a.block} could go is "
                f"unknown; nothing was sent. Check the FM9 is connected and "
                f"not in use by FM9-Edit, then retry")
    if not cells:
        return (f"this preset is empty: it has no grid cells at all, not even "
                f"pass-through cells, so there is nothing to place {a.block} "
                f"onto. Load a preset with a signal chain, or use BUILD A "
                f"STARTING CHAIN in the EMPTY SLOT panel to make one from "
                f"nothing")
    return (f"no free pass-through cell {where} to place {a.block} on; "
            f"refusing rather than rewiring the grid")


AMP_FAMILY = "DISTORT"


def _amp_cell(fm9: FM9, cells):
    """The first amp on the grid, alias-aware.

    Grid ids alias mod 128, so FX Return (186) reads as 58 and would pass for
    an amp in a naive scan, putting "before the amp" in front of the wrong
    block. resolve_aliases settles it against the status dump.
    """
    present = {b.effect_id for b in fm9.status_dump() or []}
    resolved = resolve_aliases(cells, present)
    amps = []
    for c in cells:
        if c.effect_id is None:
            continue
        true_id = resolved.get((c.row, c.col), c.effect_id)
        fam = reg.family_of_effect_id(true_id)
        if fam and fam[0] == AMP_FAMILY:
            amps.append(c)
    return min(amps, key=lambda c: c.col) if amps else None


def _splice_plan_for(fm9: FM9, a: Action) -> dict | None:
    """What add_block would have to displace, or None if it need not.

    Called at plan time so the consequences are visible BEFORE anyone
    confirms: a splice moves someone else's blocks, and it may spend a
    pass-through cell that cannot be put back.
    """
    try:
        fam, eid = reg.resolve_block(a.block or "", a.instance)
    except Exception:
        return None
    cells = fm9.read_grid() or []
    if not cells:
        return None
    amp = _amp_cell(fm9, cells)
    if amp is None:
        return None
    pos = a.position or "any"
    shunts = [(c.row, c.col) for c in cells if c.is_shunt]
    if pos == "pre":
        shunts = [(r, c) for r, c in shunts if c < amp.col]
    elif pos == "post":
        shunts = [(r, c) for r, c in shunts if c > amp.col]
    if shunts:
        return None                    # a free pass-through exists: no splice
    row = amp.row + 1
    at_col = amp.col + 1 if pos != "post" else amp.col + 2
    intent = fm9.plan_splice(row, at_col)
    intent["effect_id"] = eid
    intent["block"] = f"{fam} {a.instance}"
    return intent


def _add_block(fm9: FM9, a: Action) -> dict:
    """Insert a block onto a free shunt cell. Refuses when no sane placement
    exists rather than guessing (no cable drawing in the planner path)."""
    fam, eid = reg.resolve_block(a.block or "", a.instance)
    blocks = fm9.status_dump() or []
    if any(b.effect_id == eid for b in blocks):
        return {"ok": False, "detail": f"{a.block} {a.instance} already exists in this preset"}
    cells = fm9.read_grid()
    if cells is None:
        return {"ok": False, "detail": _no_placement_detail(a, a.position or "any", None)}
    amp_cols = [c.col for c in cells if c.effect_id in (58, 59, 60, 61)]
    amp_col = min(amp_cols) if amp_cols else None
    shunts = [(c.row, c.col) for c in cells if c.is_shunt]
    pos = a.position or "any"
    if pos == "pre" and amp_col is not None:
        shunts = [(r, c) for r, c in shunts if c < amp_col]
    elif pos == "post" and amp_col is not None:
        shunts = [(r, c) for r, c in shunts if c > amp_col]
    if not shunts:
        # No free pass-through: splice instead of refusing, but only on the
        # terms the plan already showed the user (issue #10). When even a
        # splice cannot be done, the refusal still names the wall it actually
        # hit rather than describing a packed preset to someone holding an
        # empty one.
        intent = _splice_plan_for(fm9, a)
        if intent is None or not intent["ok"]:
            detail = ((intent or {}).get("detail")
                      or _no_placement_detail(a, pos, cells))
            return {"ok": False, "detail": detail,
                    "reason": (intent or {}).get("reason", "no_placement")}
        res = fm9.splice_block(intent["row"], intent["at_col"], eid)
        res["spliced"] = True
        res["detail"] = (f"{a.block} spliced in at row {intent['row']} col "
                         f"{intent['at_col']}; " + res.get("detail", ""))
        return res
    row, col = sorted(shunts, key=lambda rc: rc[1])[0]
    fm9.place_block(row + 1, col + 1, eid)
    after = fm9.read_grid() or []
    placed = [c for c in after
              if c.effect_id == eid and (c.row, c.col) == (row, col)]
    if not placed:
        # the FM9 refuses over-budget inserts SILENTLY: nothing lands, no
        # error (hardware-observed 2026-08-21, amp2 on a loaded preset)
        still_shunt = any(c.is_shunt and (c.row, c.col) == (row, col) for c in after)
        if still_shunt:
            return {"ok": False,
                    "detail": f"insert of {a.block} landed nothing at row "
                              f"{row + 1} col {col + 1}; the FM9 refuses "
                              f"over-DSP-budget inserts silently - the preset "
                              f"is likely too heavy for this block (free up "
                              f"a block and retry)"}
    ok = bool(placed) and placed[0].cable_in_mask != 0
    # shunt-replacement can drop the OUTGOING cable (hardware-observed
    # 2026-08-21: downstream cell left with no input = silent preset).
    # Verify the next cell still has an input; redraw same-row if not.
    if ok:
        nxt = next((c for c in after if (c.row, c.col) == (row, col + 1)), None)
        if nxt is not None and nxt.cable_in_mask == 0:
            fm9.connect_cells(row + 1, col + 1, row + 1)
            after2 = fm9.read_grid() or []
            nxt2 = next((c for c in after2 if (c.row, c.col) == (row, col + 1)), None)
            if nxt2 is None or nxt2.cable_in_mask == 0:
                return {"ok": False,
                        "detail": f"placed at row {row + 1} col {col + 1} but the "
                                  f"outgoing cable was lost and could not be "
                                  f"redrawn; downstream is disconnected"}
    return {"ok": ok,
            "detail": f"placed at row {row + 1} col {col + 1}, cables verified "
                      f"in and out" if ok else "placement failed grid verification"}


def _resolve_param(fam: str, name: str, instance: int):
    """A parameter by name within a family, however the caller spelled it."""
    for (f, pid), pdata in reg.params.items():
        if f == fam and pdata.get("name") == name:
            return reg.spec(f, pid, instance)
    return reg.find_param(fam, name) if name else None


#: Pedal 2. Pedal 1 is the player's global volume and is never referenced by
#: anything here, in either direction.
PEDAL_2_SOURCE = 11

#: Slots this tool wrote WITHOUT a donor curve, per preset.
#:
#: A slot built from MOD_DEFAULT_FIELDS is indistinguishable on the wire from
#: one the device built, so the next bind would happily clone it and report
#: "curve cloned from slot N" about a curve that is really this project's
#: linear default. The provenance would launder itself one slot at a time.
#: Remembered rather than read, because the wire cannot answer it.
_synthetic_slots: dict = {"preset": None, "slots": set()}


def _synthetic_for(preset: int | None) -> set:
    """Reset the memory when the loaded preset changes: slot numbers mean
    nothing across presets."""
    if _synthetic_slots["preset"] != preset:
        _synthetic_slots["preset"] = preset
        _synthetic_slots["slots"] = set()
    return _synthetic_slots["slots"]


def _bind_pedal(fm9: FM9, a: Action) -> dict:
    """Put a continuous parameter under Pedal 2.

    Two things this deliberately does NOT claim.

    It does not verify the sweep. Live modulation is invisible to every read
    the protocol offers, and a dead binding reads byte-identical to a live one
    (findings 12 and 17), so a field read-back proves the slot was written and
    nothing whatsoever about whether the pedal moves the parameter. The only
    verification is a foot and an ear.

    It does not claim to be undoable. The undo snapshot covers parameters,
    bypass and channel; a modifier slot is none of those. Removing the binding
    is what takes it back, which is why unbinding exists as its own action
    rather than being left to UNDO.
    """
    from fm9 import protocol as fp
    fam, eid = reg.resolve_block(a.block or "", a.instance)
    spec = _resolve_param(fam, a.param or "", a.instance)
    if spec is None:
        return {"ok": False, "detail": f"unknown param {a.param}"}

    slot, free = None, 0
    for m in range(1, fp.MOD_SLOT_COUNT + 1):
        vals = fm9.read_modifier(m)
        if vals and len(vals) > fp.MOD_PID_TARGET_EFFECT:
            if vals[fp.MOD_PID_TARGET_EFFECT] == eid and \
                    vals[fp.MOD_PID_TARGET_PARAM] == spec.param_id:
                return {"ok": False,
                        "detail": f"{spec.name} is already on modifier slot {m}"}
            if vals[fp.MOD_PID_TARGET_EFFECT] == 0:
                free += 1
                if slot is None:
                    slot = m
    if slot is None:
        return {"ok": False,
                "detail": f"all {fp.MOD_SLOT_COUNT} modifier slots are in use; "
                          f"remove a binding to free one"}

    # Clone the curve off a slot the device itself built, where the preset has
    # one. Finding 12: from scratch comes out reversed or dead. Slots this
    # tool built without a donor are excluded, or a default would launder
    # itself into something the log calls a clone.
    preset = fm9.current_preset()
    synthetic = _synthetic_for(preset[0] if preset else None)
    found = fm9.find_donor_slot(skip={slot} | synthetic)
    donor_slot, donor = found if found else (None, None)
    floor = (a.value or 0.0) / 100.0
    cloned = fm9.bind_modifier(slot, eid, spec.param_id, PEDAL_2_SOURCE,
                               donor=donor,
                               min_norm=floor if a.value else None)

    vals = fm9.read_modifier(slot) or []
    written = (len(vals) > fp.MOD_PID_TARGET_PARAM
               and vals[fp.MOD_PID_TARGET_EFFECT] == eid
               and vals[fp.MOD_PID_TARGET_PARAM] == spec.param_id
               and vals[fp.MOD_PID_SOURCE] == PEDAL_2_SOURCE)
    if not written:
        return {"ok": False, "detail": "the slot did not take the binding"}
    if cloned:
        how = f"curve cloned from slot {donor_slot}"
    else:
        synthetic.add(slot)
        how = ("no slot to clone from, so the curve is this project's linear "
               "default: finding 12 says from-scratch bindings come out "
               "reversed or dead about as often as not")
    return {"ok": True,
            "detail": f"Pedal 2 -> {spec.name} on modifier slot {slot}"
                      f"{f', floor {a.value:.0f}%' if a.value else ''} "
                      f"({how}). The slot is written; the SWEEP is unverified "
                      f"and cannot be read. Rock the pedal and listen. "
                      f"{free - 1} of {fp.MOD_SLOT_COUNT} slots still free.",
            "unverifiable": True}


def _unbind_pedal(fm9: FM9, a: Action) -> dict:
    """Take a parameter back off its modifier, so its own value governs again.

    The way back from a bind. Refuses to detach a source this project cannot
    name, because an unrecognised source is one the owner set up on the front
    panel, and silently removing someone's own routing is not an undo.
    """
    from fm9 import protocol as fp
    fam, eid = reg.resolve_block(a.block or "", a.instance)
    spec = _resolve_param(fam, a.param or "", a.instance)
    if spec is None:
        return {"ok": False, "detail": f"unknown param {a.param}"}
    for m in range(1, fp.MOD_SLOT_COUNT + 1):
        vals = fm9.read_modifier(m)
        if not vals or len(vals) <= fp.MOD_PID_TARGET_PARAM:
            continue
        if vals[fp.MOD_PID_TARGET_EFFECT] != eid or \
                vals[fp.MOD_PID_TARGET_PARAM] != spec.param_id:
            continue
        src = vals[fp.MOD_PID_SOURCE]
        if src != PEDAL_2_SOURCE:
            return {"ok": False,
                    "detail": f"{spec.name} is driven by source #{src}, not "
                              f"Pedal 2. That binding was made somewhere this "
                              f"tool cannot read, so it is not this tool's to "
                              f"remove: clear it on the FM9."}
        fm9.clear_modifier(m)
        preset = fm9.current_preset()
        _synthetic_for(preset[0] if preset else None).discard(m)
        vals = fm9.read_modifier(m) or []
        gone = (len(vals) > fp.MOD_PID_TARGET_EFFECT
                and vals[fp.MOD_PID_TARGET_EFFECT] == 0)
        return {"ok": gone,
                "detail": f"Pedal 2 removed from {spec.name} (slot {m})" if gone
                          else "the slot did not clear"}
    return {"ok": False, "detail": f"{spec.name} has no modifier on it"}


def run_action(fm9: FM9, a: Action) -> dict:
    if a.kind == "rename_preset":
        name = a.type_name.strip()
        if not name.upper().startswith("FM9AI"):
            name = ("FM9AI-" + name)[:32]
        fm9.rename_preset(name)
        got = fm9.current_preset()
        return {"ok": bool(got and got[1] == name), "detail": f"preset renamed to {name!r}"}
    if a.kind == "rename_scene":
        fm9.rename_scene(int(a.value), a.type_name.strip()[:32])
        got = fm9.scene_name(int(a.value))
        return {"ok": bool(got and got[1] == a.type_name.strip()[:32]),
                "detail": f"scene {int(a.value)} renamed to {a.type_name.strip()[:32]!r}"}
    if a.kind == "store":
        stored = fm9.store_preset(int(a.value))
        return {"ok": bool(stored and stored[0] == int(a.value)),
                "detail": f"stored to slot {int(a.value)}: {stored[1] if stored else '?'}"}
    if a.kind == "set_scene":
        scene_no = int(a.value) if a.value is not None else int(a.instance)
        got = fm9.set_scene(scene_no)
        name = fm9.scene_name()
        return {"ok": got == scene_no,
                "detail": f"scene {got}" + (f" \"{name[1]}\"" if name else "")}
    if a.kind == "set_tempo":
        from fm9 import protocol as p
        fm9._send(p.build_set_tempo(int(a.value)))
        return {"ok": True, "detail": f"tempo {int(a.value)} bpm sent"}

    fam, eid = reg.resolve_block(a.block or "", a.instance)
    if a.kind == "set_bypass":
        got = fm9.set_bypass(eid, bool(a.bypassed))
        return {"ok": got == bool(a.bypassed),
                "detail": "bypassed" if got else "engaged"}
    if a.kind == "set_channel":
        got = fm9.set_channel(eid, int(a.value))
        return {"ok": got == int(a.value), "detail": f"channel {'ABCD'[got]}"}
    if a.kind == "add_block":
        return _add_block(fm9, a)
    if a.kind == "bind_pedal":
        return _bind_pedal(fm9, a)
    if a.kind == "unbind_pedal":
        return _unbind_pedal(fm9, a)
    if a.kind == "set_cab":
        # Bank and slot are two parameters on the CABINET block, and the slot
        # ordinal lives in the RAW wire value rather than on the 0-1023 display
        # scale, so this goes through the discrete path. Verified on hardware:
        # a discrete write of 200 reads back as exactly 200.
        bank = 0 if a.bank is None else int(a.bank)
        ordinal = int(a.value)
        bspec = reg.spec("CABINET", 0, a.instance)
        tspec = reg.spec("CABINET", 4, a.instance)
        before_o = fm9.get_param_wire(tspec)
        before_b = fm9.get_param_wire(bspec)
        if before_b != bank:
            fm9.set_param_ordinal(bspec, bank)
        fm9.set_param_ordinal(tspec, ordinal)
        import time as _t
        landed_o = landed_b = None
        for _ in range(4):
            _t.sleep(0.15)
            landed_o = fm9.get_param_wire(tspec)
            landed_b = fm9.get_param_wire(bspec)
            if landed_o == ordinal and landed_b == bank:
                break
        ok = landed_o == ordinal and landed_b == bank
        return {"action": a.model_dump(), "ok": ok,
                "detail": (f"cab -> {reg.cab_description(landed_o, landed_b)}"
                           if ok else
                           f"read-back mismatch: wanted bank {bank} cab "
                           f"{ordinal}, unit reports bank {landed_b} cab "
                           f"{landed_o}"),
                "before": reg.cab_description(before_o, before_b),
                "after": reg.cab_description(landed_o, landed_b)}
    if a.kind == "set_type":
        pid, _ = TYPE_PARAMS.get(fam, (None, None))
        if pid is None:
            return {"ok": False, "detail": f"type select not supported on {fam}"}
        resolved = resolve_type_ordinal(fam, a.type_name or "")
        if resolved is None:
            return {"ok": False, "detail": f"unknown model name: {a.type_name}"}
        ordinal, label = resolved
        spec = reg.spec(fam, pid, a.instance)
        before_wire = fm9.get_param_wire(spec)
        before = reg.amp_roster.get(str(before_wire)) if fam == "DISTORT" else before_wire
        fm9.set_param_ordinal(spec, ordinal)
        import time as _t
        ok = False
        after_label = None
        for _ in range(4):
            _t.sleep(0.15)
            wire = fm9.get_param_wire(spec)
            if wire == ordinal:
                ok = True
            roster: dict = getattr(reg, TYPE_PARAMS[fam][1])
            after_label = roster.get(str(wire), wire)
            if ok:
                break
        return {"ok": ok, "detail": f"model: {after_label}",
                "before": before, "after": after_label}
    if a.kind == "set_param":
        spec = None
        for (f, pid), pdata in reg.params.items():
            if f == fam and (pdata.get("name") == a.param):
                spec = reg.spec(f, pid, a.instance)
                break
        if spec is None and a.param:
            spec = reg.find_param(fam, a.param)
        if spec is None:
            return {"ok": False, "detail": f"unknown param {a.param} on {fam}"}
        r = fm9.set_param_display(spec, float(a.value))
        return {"ok": r.ok, "detail": r.detail,
                "before": r.display_before, "after": r.display_after}
    return {"ok": False, "detail": f"unknown action {a.kind}"}


import os as _os

GIG_SAFE_KINDS = {"set_scene"}
_gig_mode = {"on": _os.environ.get("TONECOMMAND_GIG_MODE") == "1"}


# Slot names change only when someone stores a preset, and a full sweep of
# 512 costs about 15 seconds of MIDI, so it is read once and kept. Refresh is
# explicit rather than automatic: silently re-scanning would stall a prompt.
_preset_cache: dict = {"slots": None}


@app.get("/api/store-slots")
def api_store_slots():
    """The slots this unit's owner has designated as safe to overwrite.

    Storing is the only destructive thing this tool does, so the UI is never
    allowed to offer a free-text slot number: it offers this list or nothing.
    Each entry carries what is in the slot NOW, because "overwrite 139" means
    nothing until you can see what 139 currently holds.

    Names come from the same cache the preset browser uses, read by number
    without disturbing the loaded preset.
    """
    from fm9.device import get_store_slots, get_store_slots_spec
    allowed = sorted(get_store_slots())
    spec, source = get_store_slots_spec()
    if not allowed:
        return {"slots": [], "configured": False, "spec": spec, "source": source,
                "why": "storing is disabled until you designate slots on your "
                       "unit that are safe to overwrite"}
    known = {}
    if _preset_cache["slots"]:
        known = {s["number"]: s for s in _preset_cache["slots"]}
    out = []
    for n in allowed:
        s = known.get(n)
        out.append({
            "number": n,
            "editor": proto.editor_number(n),
            # both numbers, because this is the prompt where being one out is
            # expensive and it is the rule everywhere else that costs
            "label": proto.slot_label(n),
            "name": (s or {}).get("name"),
            "empty": (s or {}).get("empty"),
        })
    return {"slots": out, "configured": True, "named": bool(known),
            # where the boundary came from, so the owner can see whether they
            # set it here, in a file, or never at all
            "spec": spec, "source": source, "total": 512}


class StoreSlotsBody(BaseModel):
    spec: str
    #: Ask what this WOULD do without doing it. The first version of this
    #: endpoint applied and then reported, which is backwards for the control
    #: that governs every preset on the unit: by the time you read what you
    #: had exposed, you had exposed it.
    preview: bool = False


@app.post("/api/store-slots")
def api_set_store_slots(body: StoreSlotsBody):
    """Change which slots may be overwritten.

    The most dangerous endpoint in the app: it moves the boundary that protects
    every preset on the unit. So it reports what the change would newly expose
    BEFORE it is confirmed, rather than after, and it refuses outright when the
    boundary is pinned in the environment.
    """
    from fm9.device import (get_store_slots, parse_store_slots,
                            set_store_slots_spec)
    before = get_store_slots()
    try:
        wanted = parse_store_slots(body.spec)
    except Exception as e:
        return JSONResponse({"error": f"could not read that: {e}"}, status_code=400)
    if body.spec.strip() and not wanted:
        return JSONResponse(
            {"error": f"nothing usable in {body.spec!r}. Wire numbers 0-511, "
                      f"like \"133,139-170\""}, status_code=400)
    with _lock:
        added = sorted(wanted - before)
        known = {s["number"]: s for s in (_preset_cache["slots"] or [])}
        if body.preview:
            return {
                "preview": True, "spec": body.spec, "count": len(wanted),
                "newly_exposed": [
                    {"label": proto.slot_label(n),
                     "name": (known.get(n) or {}).get("name")} for n in added],
                "removed": len(before - wanted),
            }
        try:
            spec, source = set_store_slots_spec(body.spec)
        except PermissionError as e:
            return JSONResponse({"error": str(e)}, status_code=409)
        known = {s["number"]: s for s in (_preset_cache["slots"] or [])}
        return {
            "spec": spec, "source": source, "count": len(wanted),
            # named presets that just became overwritable, by name, because
            # "5 more slots" and "the Worship Tutorials packs" are different
            # sentences and only one of them is a warning
            "newly_exposed": [
                {"label": proto.slot_label(n),
                 "name": (known.get(n) or {}).get("name")}
                for n in added],
            "removed": len(before - wanted),
        }


@app.get("/api/presets")
def api_presets(refresh: bool = False):
    """Every slot name, read by number without disturbing the loaded preset."""
    if _preset_cache["slots"] is not None and not refresh:
        return {"slots": _preset_cache["slots"], "cached": True}
    with _lock:
        try:
            fm9 = get_fm9()
            slots = []
            for s in fm9.scan_slots(0, 511):
                slots.append({
                    "number": s.number,                       # wire
                    "editor": proto.editor_number(s.number),  # what the unit shows
                    "label": proto.slot_label(s.number),      # both, for prompts
                    "name": s.name,
                    "empty": proto.is_empty_slot_name(s.name),
                })
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
        except Exception as e:
            drop_fm9()
            return JSONResponse({"error": str(e)}, status_code=500)
    _preset_cache["slots"] = slots
    return {"slots": slots, "cached": False}


class PresetBody(BaseModel):
    number: int


@app.post("/api/preset")
def api_preset(body: PresetBody):
    """Load a preset.

    Not a planner action on purpose. Selecting a preset DISCARDS the edit
    buffer, so it is a deliberate act by a person, not something a language
    model gets to decide mid-plan. Gig mode refuses it for the same reason it
    refuses everything but a scene change.
    """
    if _gig_mode["on"]:
        return JSONResponse(
            {"error": "GIG MODE is on: refusing to change preset. Only scene "
                      "changes are allowed during a performance."},
            status_code=423)
    with _lock:
        try:
            fm9 = get_fm9()
            fm9.select_preset(body.number)
            got = fm9.current_preset()
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    # Report what the unit says it loaded, not what we asked for: a dropped
    # program change would otherwise look like success.
    if not got or got[0] != body.number:
        return JSONResponse(
            {"error": f"asked for {proto.slot_label(body.number)} but the unit "
                      f"reports {proto.slot_label(got[0]) if got else 'nothing'}"},
            status_code=409)
    return {"preset": {"number": got[0], "editor": proto.editor_number(got[0]),
                       "label": proto.slot_label(got[0]), "name": got[1]}}


_shared_cache: dict = {"preset": None, "map": None}

#: The last state read from real hardware, kept so a design can be planned
#: against a true reading rather than an invented one when the rig is off.
_last_snapshot: dict = {"state": None, "at": None}


# --- undo and A/B ----------------------------------------------------------
# In memory and lost on restart, deliberately. An undo history that outlived
# the session would be offering to revert a rig it has not looked at since.
_snaps: dict = {"undo": None, "a": None, "b": None}


def _take(slot: str) -> dict:
    """Capture the edit buffer into a slot. Silent, about a quarter second."""
    snap = editbuffer.capture(get_fm9(), reg)
    _snaps[slot] = snap
    return snap


@app.get("/api/snapshots")
def api_snapshots():
    """Which slots hold something, and what undoing would actually do.

    The pending description is computed live rather than stored, because the
    buffer moves under it: a snapshot taken two edits ago describes a larger
    undo now than it did then, and a button whose label is stale about its own
    blast radius is worse than one with no label.
    """
    with _lock:
        out = {}
        # One read of the buffer for all three slots. Reading it per slot
        # tripled the MIDI traffic to answer the same question three times.
        try:
            now = editbuffer.capture(get_fm9(), reg)
            err = None
        except Exception as e:
            now, err = None, str(e)
        for slot, snap in _snaps.items():
            if snap is None:
                out[slot] = None
                continue
            row = {"preset": snap.get("preset"),
                   "preset_name": snap.get("preset_name"),
                   "scene": snap.get("scene")}
            if now is None:
                row["stale"] = True
                row["pending"] = err
            elif now.get("preset") != snap.get("preset"):
                row["stale"] = True
                row["pending"] = (f"captured on preset {snap.get('preset')}, "
                                  f"{now.get('preset')} is loaded")
            else:
                row["stale"] = False
                row["pending"] = editbuffer.summarise(
                    editbuffer.diff(reg, snap, now))
            out[slot] = row
        return out


@app.post("/api/snapshot")
def api_snapshot(body: dict):
    """Store the current edit buffer in slot a or b."""
    slot = str(body.get("slot", "")).lower()
    if slot not in ("a", "b"):
        return JSONResponse({"error": "slot must be a or b"}, status_code=400)
    with _lock:
        try:
            snap = _take(slot)
            return {"slot": slot, "preset": snap.get("preset"),
                    "blocks": len(snap.get("blocks") or [])}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/restore")
def api_restore(body: dict):
    """Put the edit buffer back to a stored snapshot.

    Gig mode refuses. A restore writes parameters, and gig mode's whole
    position is that nothing but a scene change reaches hardware while someone
    is playing; an undo is no less a write for being a well-intentioned one.
    """
    slot = str(body.get("slot", "")).lower()
    if slot not in _snaps:
        return JSONResponse({"error": f"unknown slot {slot!r}"}, status_code=400)
    with _lock:
        if _gig_mode["on"]:
            return JSONResponse(
                {"error": "GIG MODE is on: refusing to restore. An undo writes "
                          "parameters like any other change."}, status_code=423)
        snap = _snaps.get(slot)
        if snap is None:
            return JSONResponse({"error": f"nothing captured in {slot}"},
                                status_code=409)
        try:
            fm9 = get_fm9()
            # Recalling A must not lose where you were, or A/B is a one-way
            # trip and the comparison can only be made once.
            if slot in ("a", "b"):
                other = "b" if slot == "a" else "a"
                if _snaps.get(other) is None:
                    _take(other)
            res = editbuffer.restore(fm9, reg, snap)
            return {"slot": slot, "ok": res.ok,
                    "applied": res.applied, "failed": res.failed}
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=409)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/models")
def api_models(kind: str = "amp"):
    """The model rosters, for auditioning.

    Sent whole and once. There are 331 amps and 2237 cabs, and paging that
    would make the search feel like the device's own list, which is the thing
    this is trying to beat: on the unit you turn a knob through a thousand
    entries because there is nowhere to type.
    """
    # Every block whose TYPE we can actually name. A roster maps an ordinal to
    # a real name; without one the ordinal is meaningless to a human, so those
    # blocks get no picker rather than a list of numbers.
    ROSTERS = {"amp": ("amp_roster", "AMP"), "drive": ("drive_roster", "DRIVE"),
               "reverb": ("reverb_roster", "REVERB")}
    if kind in ROSTERS:
        attr, label = ROSTERS[kind]
        roster = getattr(reg, attr) or {}
        return {"kind": kind, "banks": [{
            "bank": None, "name": label,
            "models": [{"ordinal": int(o), "name": n}
                       for o, n in sorted(roster.items(), key=lambda x: int(x[0]))]}]}
    if kind == "cab":
        out = []
        for b in sorted(reg.cab_rosters, key=int):
            out.append({
                "bank": int(b),
                "name": reg.cab_bank_names.get(b, f"BANK {b}"),
                "models": [{"ordinal": int(o), "name": n,
                            # the long description is what tells a Vibrolux
                            # from a Vibrolux, so it is searchable too
                            "detail": reg.cab_model(o, b) or ""}
                           for o, n in sorted(reg.cab_rosters[b].items(),
                                              key=lambda x: int(x[0]))]})
        return {"kind": "cab", "banks": out}
    return JSONResponse({"error": f"unknown kind {kind!r}"}, status_code=400)


@app.get("/api/grid")
def api_grid():
    """The routing grid as it actually is, with the live path marked.

    SIGNAL CHAIN was a wrapped list of block names, which tells you what is in
    the preset but not how any of it is wired, and the wiring is the part that
    goes wrong: a severed cable and a bypassed Return both leave every block
    present and correct while the scene makes no sound.

    Read-only and silent. Reads the loaded scene only, so it costs one grid
    read and one status dump and can ride along with the normal poll.
    """
    with _lock:
        try:
            fm9 = get_fm9()
            cells = fm9.read_grid() or []
            status = fm9.status_dump() or []
            st = {b.effect_id: b for b in status}
            w = path_audit.walk(cells, st, reg)
            live, resolved = w["live"], w["resolved"]
            out = []
            for c in cells:
                if c.effect_id is None and not c.is_shunt:
                    continue
                eid = resolved.get((c.row, c.col)) if c.effect_id else None
                fam = reg.family_of_effect_id(eid) if eid else None
                blk = st.get(eid) if eid else None
                out.append({
                    "row": c.row, "col": c.col,
                    "shunt": bool(c.effect_id is None and c.is_shunt),
                    "effect_id": eid,
                    "family": fam[0] if fam else None,
                    "instance": fam[1] if fam else None,
                    "label": (f"{FRIENDLY.get(fam[0], fam[0])} {fam[1]}"
                              if fam else None),
                    "bypassed": bool(blk.bypassed) if blk else None,
                    "channel": "ABCD"[blk.channel] if blk else None,
                    # feeds names the cells one column left that reach this
                    # one, resolved here so the browser never has to know how
                    # the cable bitmask is packed
                    "feeds": [r for r in range(8)
                              if c.cable_in_mask & (1 << (r + 1))],
                    "live": (c.row, c.col) in live,
                })
            return {"cells": out, "alive": w["alive"], "why": w["why"],
                    "rows": 1 + max((c["row"] for c in out), default=0),
                    "cols": 1 + max((c["col"] for c in out), default=0)}
        except Exception as e:
            return {"error": str(e)}


class ClearBody(BaseModel):
    slot: int
    confirm_name: str


@app.get("/api/slot/{slot}")
def api_slot(slot: int):
    """What is stored in a slot, without loading it (finding 15).

    So a confirmation can name what is about to be destroyed rather than
    asking someone to trust a number.
    """
    with _lock:
        try:
            return slotops.describe(get_fm9(), slot)
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)


class RenameBody(BaseModel):
    slot: int
    name: str


@app.post("/api/rename-slot")
def api_rename_slot(body: RenameBody):
    """Rename a stored preset.

    Reaches flash, because the FM9 keeps the name inside the preset rather
    than beside it: renaming means selecting it, setting the name, and storing
    the whole preset back. So it carries the store whitelist and the gig gate
    like anything else that writes, even though the intent is only to change
    some text.
    """
    if _gig_mode["on"]:
        return JSONResponse(
            {"error": "GIG MODE: renaming stores the preset, which is a write "
                      "to flash. Not while you are playing."}, status_code=423)
    with _lock:
        try:
            res = slotops.rename(get_fm9(), body.slot, body.name)
        except PermissionError as exc:
            return JSONResponse({"ok": False, "detail": str(exc)},
                                status_code=403)
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"ok": False, "detail": "the FM9 is not answering"},
                                status_code=409)
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)
    _preset_cache["slots"] = None
    return res if res["ok"] else JSONResponse(res, status_code=409)


@app.post("/api/clear-slot")
def api_clear_slot(body: ClearBody):
    """Empty a preset slot, permanently.

    The second irreversible operation here, and the only one that destroys
    rather than overwrites: a store replaces a preset with the one you are
    holding, this replaces it with nothing.

    `confirm_name` must match the name the slot currently holds. Not
    ceremony: the numbers differ by one between the wire and every screen the
    owner reads, and a clear aimed one slot off is unrecoverable. Making the
    caller echo the name back means the thing being destroyed was actually
    looked at.
    """
    if _gig_mode["on"]:
        return JSONResponse(
            {"error": "GIG MODE: refusing to erase a preset while you are "
                      "playing."}, status_code=423)
    with _lock:
        try:
            fm9 = get_fm9()
            found = slotops.describe(fm9, body.slot)
            if not found["ok"]:
                return JSONResponse(found, status_code=409)
            if (found.get("name") or "").strip() != body.confirm_name.strip():
                return JSONResponse(
                    {"ok": False,
                     "detail": (f"refusing to clear {found['label']}: it holds "
                                f"{found.get('name')!r}, not "
                                f"{body.confirm_name!r}. Nothing was changed.")},
                    status_code=409)
            res = slotops.clear(fm9, body.slot)
        except PermissionError as exc:
            return JSONResponse({"ok": False, "detail": str(exc)},
                                status_code=403)
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"ok": False, "detail": "the FM9 is not answering"},
                                status_code=409)
        except Exception as exc:
            return JSONResponse({"ok": False, "detail": str(exc)}, status_code=500)
    # The preset browser reads names from here, and one of them just stopped
    # being true.
    _preset_cache["slots"] = None
    return res if res["ok"] else JSONResponse(res, status_code=409)


class ScratchBody(BaseModel):
    slot: int | None = None


@app.post("/api/build-scratch")
def api_build_scratch(body: ScratchBody):
    """Build a starting chain into an empty slot (issue #36).

    An empty FM9 slot has no grid cells at all, so add_block has nothing to
    replace and splice has nothing to displace: both refuse, correctly, and
    until now the only way forward was a terminal. The logic is the same one
    the CLI has always run, moved somewhere shipped code can reach it.

    A POST, and not only because it writes. It switches the loaded preset,
    which discards whatever is in the edit buffer, and that is not something a
    prefetch or a refresh may do on someone's behalf.
    """
    if _gig_mode["on"]:
        return JSONResponse(
            {"error": "GIG MODE: building a preset selects a different slot "
                      "and discards the edit buffer. Not while you are playing."},
            status_code=423)
    with _lock:
        try:
            # get_fm9() hands back an already-open device, the way every other
            # route uses it. Wrapping it in `with` re-enters the context and
            # reopens the MIDI port on an endpoint that is already held, which
            # took the whole server process down with no traceback rather than
            # raising anything catchable.
            res = scratch_build.build(get_fm9(), reg, slot=body.slot)
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "the FM9 is not answering"},
                                status_code=409)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
    if not res["ok"]:
        return JSONResponse(res, status_code=409)
    return res


@app.post("/api/health")
def api_health():
    """Scan the loaded preset: dead scenes, cloned scenes, level outliers.

    POST rather than GET because this is not a read. It walks the rig through
    all eight scenes to reach them, which is audible, so it must never be
    something a browser can do by prefetching a link or replaying a refresh.
    It is not cached either: a scan you did not just run is a scan describing
    a preset you may since have edited, and a stale green tick is worse than
    no tick at all.

    Gig mode refuses it. The scan makes noise and takes several seconds, which
    on stage is the definition of the thing gig mode exists to prevent.
    """
    with _lock:
        if _gig_mode["on"]:
            return JSONResponse(
                {"error": "GIG MODE is on: refusing to scan. A scan walks the "
                          "rig through every scene and is audible, which on "
                          "stage is exactly what gig mode exists to prevent."},
                status_code=423)
        try:
            return health.scan(get_fm9(), reg)
        except Exception as e:
            return {"error": str(e)}


@app.get("/api/shared")
def api_shared():
    """Which scenes share each block's channel, for the blast-radius hint.

    Cached per preset because computing it sweeps all eight scenes, which is
    audible. The UI asks for it once per preset, never on a timer.
    """
    with _lock:
        try:
            fm9 = get_fm9()
            cur = fm9.current_preset()
            key = cur[0] if cur else None
            if _shared_cache["preset"] == key and _shared_cache["map"] is not None:
                return {"preset": key, "shared": _shared_cache["map"], "cached": True}
            got = shared_scenes(fm9)
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    _shared_cache["preset"], _shared_cache["map"] = key, got
    return {"preset": key, "shared": got, "cached": False}


@app.post("/api/gig")
def api_gig(body: dict):
    """Performance lockout: while on, only scene changes reach hardware."""
    _gig_mode["on"] = bool(body.get("on"))
    return {"gig_mode": _gig_mode["on"]}


class DesignBody(BaseModel):
    name: str
    summary: str = ""
    author: str = ""
    actions: list[dict]
    preset: dict | None = None
    anchor: dict | None = None
    offline: bool = False
    profile: dict | None = None
    backend: str | None = None
    model: str | None = None


#: A profile loaded from someone else, replacing live state as the thing the
#: planner designs against. Session only: it is a lens, not a setting.
_profile: dict = {"loaded": None}


@app.get("/api/recipes")
def api_recipes(refresh: bool = False):
    """Every recipe: the ones shared in the repository, and your own.

    Reading needs no account. Recipes live in a public folder, so the app
    fetches them directly rather than sending anyone to a web UI to click
    around, which is what asking a guitarist to file an issue amounted to.
    """
    if refresh:
        recipebook._cache["items"] = None
    shared, why = recipebook.fetch_shared()
    mine = recipebook.read_local()
    seen = {r.get("_file") for r in mine}
    items = mine + [r for r in shared if r.get("_file") not in seen]
    # Ranking is a nicety. A catalogue that will not load because a counter is
    # down is a broken tool, so this is merged in if it arrives and ignored if
    # it does not.
    stats, _ = share.fetch_stats()
    for r in items:
        s = stats.get(r.get("name")) or {}
        r["plays"] = s.get("plays")
        r["recent"] = s.get("recent")
    items.sort(key=lambda r: (-(r.get("recent") or 0), -(r.get("plays") or 0),
                              (r.get("title") or "").lower()))
    return {"recipes": items, "shared_error": why, "repo": recipebook.REPO,
            "ranked": bool(stats)}


class RecipeBody(BaseModel):
    recipe: dict


@app.post("/api/recipes/plan")
def api_recipe_plan(body: RecipeBody):
    """Turn a recipe into a plan for THIS rig, validated before anything runs.

    A recipe names blocks and models by their grounded names, so validation
    against this device's schema is what makes one portable. A step naming a
    block you do not have is reported here rather than failing on the wire.
    """
    actions = []
    for a in recipebook.steps_of(body.recipe):
        try:
            errs, warns = validate_action(Action(**a))
        except Exception as e:
            errs, warns = [f"step could not be read: {e}"], []
        item = {**a, "validation_errors": errs, "validation_warnings": warns}
        if a.get("block"):
            try:
                item["effect_id"] = reg.resolve_block(
                    a["block"], int(a.get("instance") or 1))[1]
            except Exception:
                pass
        if a.get("kind") == "store" and isinstance(a.get("value"), (int, float)):
            item["slot_label"] = proto.slot_label(int(a["value"]))
        actions.append(item)
    blocked = sum(1 for a in actions if a["validation_errors"])
    # A recipe made on different firmware is worth a word. Validation catches
    # everything structural, because steps name models rather than numbering
    # them, but Fractal revises voicings between releases and no read can see
    # that. Best effort: a rig that does not answer just means no note.
    try:
        rig_fw = get_fm9().firmware_label()
    except Exception:
        rig_fw = ""
    return {"summary": body.recipe.get("title") or body.recipe.get("name"),
            "actions": actions, "blocked": blocked,
            "assumes": body.recipe.get("assumes"),
            "firmware_note": recipebook.firmware_note(
                body.recipe.get("tested_firmware"), rig_fw),
            "ear_checklist": body.recipe.get("ear_checklist") or []}


@app.get("/api/share/status")
def api_share_status():
    """What is waiting to be handed over, and whether there is anywhere to
    hand it to. Both are normal states."""
    return {"endpoint": share.endpoint() or None,
            "pending": len(share.pending()),
            "entries": [{k: e[k] for k in
                         ("id", "kind", "queued", "attempts", "last_error")}
                        for e in share.pending()[:20]]}


@app.post("/api/share/sync")
def api_share_sync():
    """Try to flush the outbox. Safe to call as often as you like."""
    out = share.sync()
    share.forget_accepted()
    return out


class UseBody(BaseModel):
    name: str


@app.post("/api/share/used")
def api_share_used(body: UseBody):
    """A recipe actually reached hardware. Queued like everything else, so a
    gig with the laptop offline still counts once it is back."""
    share.queue("use", {"name": body.name, "id": uuid.uuid4().hex})
    return {"queued": True, "pending": len(share.pending())}


@app.post("/api/recipes/save")
def api_recipe_save(body: RecipeBody):
    """Keep a recipe of your own, and say how to pass it on."""
    try:
        path = recipebook.save_local(body.recipe)
    except OSError as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    # Queued only AFTER the file is on disk. By the time any network call is
    # attempted the work is already safe and already visible in the app's own
    # browser, which is what makes losing it impossible.
    share.queue("recipe", body.recipe)
    sent = share.sync()
    return {"saved": path.name, "dir": str(path.parent),
            # a prefilled NEW FILE in recipes/, not a new issue
            "pr_url": recipebook.pr_url(body.recipe),
            "share": sent}


@app.get("/api/profile")
def api_profile():
    """The profile currently loaded, if any."""
    return {"profile": _profile["loaded"]}


@app.post("/api/profile/export")
def api_profile_export():
    """Describe the loaded preset's SHAPE, for someone else to design against.

    Structure only, never values. A full parameter dump would be the preset
    itself, and many presets on a real unit came from paid packs. See
    docs/RECIPES.md: nothing paid is ever redistributed.
    """
    with _lock:
        try:
            fm9 = get_fm9()
            snap = snapshot(fm9)
            try:
                cells = fm9.read_grid() or []
                status = {b.effect_id: b for b in fm9.status_dump() or []}
                w = path_audit.walk(cells, status, reg)
                grid = {"rows": 0, "cols": 0, "cells": []}
                for c in cells:
                    if c.effect_id is None and not c.is_shunt:
                        continue
                    eid = w["resolved"].get((c.row, c.col)) if c.effect_id else None
                    fam = reg.family_of_effect_id(eid) if eid else None
                    grid["cells"].append({
                        "row": c.row, "col": c.col,
                        "shunt": bool(c.effect_id is None and c.is_shunt),
                        "family": fam[0] if fam else None,
                        "instance": fam[1] if fam else None,
                        "feeds": [r for r in range(8)
                                  if c.cable_in_mask & (1 << (r + 1))]})
                grid["rows"] = 1 + max((c["row"] for c in grid["cells"]), default=0)
                grid["cols"] = 1 + max((c["col"] for c in grid["cells"]), default=0)
            except Exception:
                grid = None
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
    return {"profile": rigprofile.build(snap, grid)}


class ProfileBody(BaseModel):
    profile: dict | None = None


@app.post("/api/profile/load")
def api_profile_load(body: ProfileBody):
    """Design against someone else's rig. Pass null to go back to your own."""
    if body.profile is None:
        _profile["loaded"] = None
        return {"profile": None}
    why = rigprofile.check(body.profile)
    if why:
        return JSONResponse({"error": why}, status_code=400)
    _profile["loaded"] = body.profile
    return {"profile": body.profile}


@app.get("/api/designs")
def api_designs():
    """Everything designed and not yet sent, newest first."""
    return {"designs": designs.listing(),
            "connected": _fm9 is not None}


@app.post("/api/designs")
def api_design_save(body: DesignBody):
    """Keep a validated plan until there is a device to send it to.

    Validation is re-run here rather than trusted from the browser: a design
    is only worth saving if it would actually run, and the browser is not the
    place that decides that.
    """
    actions = []
    for a in body.actions:
        errs, warns = validate_action(Action(**a))
        actions.append({**a, "validation_errors": errs,
                        "validation_warnings": warns})
    try:
        rec = designs.save({
            "name": body.name, "summary": body.summary, "author": body.author,
            "actions": actions, "preset": body.preset, "anchor": body.anchor,
            "offline": body.offline, "profile": body.profile,
            "backend": body.backend,
            "model": body.model,
        })
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"design": rec}


@app.delete("/api/designs/{design_id}")
def api_design_delete(design_id: str):
    try:
        return {"deleted": designs.delete(design_id)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/designs/{design_id}/recipe")
def api_design_recipe(design_id: str):
    """The shareable form: how to build the tone, never the tone file."""
    d = designs.load(design_id)
    if d is None:
        return JSONResponse({"error": "no such design"}, status_code=404)
    return {"recipe": designs.to_recipe(d)}


@app.post("/api/designs/{design_id}/check")
def api_design_check(design_id: str):
    """Has the rig moved since this was designed? Reads, never writes."""
    d = designs.load(design_id)
    if d is None:
        return JSONResponse({"error": "no such design"}, status_code=404)
    with _lock:
        try:
            snap = snapshot(get_fm9())
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
    return designs.check(d, (snap.get("preset") or {}).get("number"),
                         snap.get("values", {}))


@app.get("/api/gig")
def api_gig_state():
    return {"gig_mode": _gig_mode["on"]}


@app.get("/api/ai-settings")
def api_ai_settings_state():
    """The saved planner choice, plus what this host can actually run.

    Never returns the API key in any form: `hasKey` says whether one is
    stored and nothing more.
    """
    return {"settings": ai_settings.panel_state(),
            "backends": ai_settings.available_backends(),
            "defaults": {"cliproxy": ai_settings.CLIPROXY_DEFAULT_URL,
                         "localLlm": ai_settings.LOCAL_LLM_DEFAULT_URL}}


@app.get("/api/ai-settings/models")
def api_ai_models(backend: str = ""):
    """Model ids to offer for a backend, and where the list came from.

    Suggestions only: every model box stays typeable, because a list that
    cannot be overridden is worse than no list once it goes stale.
    """
    return ai_settings.list_models(backend)


@app.post("/api/ai-settings")
def api_ai_settings(body: dict):
    """Save the choice and make it effective for the next prompt.

    A blank or absent apiKey keeps whatever is stored; clearKey removes it.
    """
    if not _settings_lock.acquire(timeout=2):
        return JSONResponse(
            {"error": "a plan is in flight, so nothing was saved. Try again "
                      "once it finishes: changing the backend underneath a "
                      "running plan would send it half of each setting."},
            status_code=409)
    try:
        saved = ai_settings.save(body)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        _settings_lock.release()
    return {"settings": saved.public(),
            "backends": ai_settings.available_backends()}


@app.post("/api/apply")
def api_apply(body: ApplyBody):
    results = []
    if _gig_mode["on"]:
        blocked = [a.kind for a in body.actions if a.kind not in GIG_SAFE_KINDS]
        if blocked:
            return JSONResponse(
                {"error": f"GIG MODE is on: refusing {sorted(set(blocked))}. "
                          f"Only scene changes are allowed during a "
                          f"performance. POST /api/gig {{\"on\": false}} "
                          f"after the set."},
                status_code=423)
    with _lock:
        try:
            fm9 = get_fm9()
            if body.expected_preset is not None:
                current = fm9.current_preset()
                if current is None or current[0] != body.expected_preset:
                    return JSONResponse(
                        {"error": f"preset changed since planning (plan was for "
                                  f"{body.expected_preset}, unit is on "
                                  f"{current[0] if current else 'unknown'} "
                                  f"\"{current[1] if current else ''}\"). "
                                  f"Re-run the prompt against the current preset."},
                        status_code=409)
            # Snapshot before anything is written, so undo is always there
            # rather than something you had to remember to arm. It is silent
            # and costs about a quarter second, which is the whole reason it
            # can be automatic: reads of the loaded buffer are free, unlike
            # the scene sweep a health scan needs.
            #
            # Only for actions that actually write. A scene change is the
            # rig's own control surface and undoing it means pressing the
            # other scene, and storing is guarded by its own confirmation.
            if any(a.kind not in ("set_scene", "store") for a in body.actions):
                try:
                    _take("undo")
                except Exception as e:
                    # A snapshot that fails must not block the edit. Say so,
                    # rather than leaving an UNDO button that quietly refers
                    # to some older state than the user assumes.
                    _snaps["undo"] = None
                    results.append({"action": {"kind": "snapshot"}, "ok": False,
                                    "detail": f"could not snapshot for undo: {e}"})
            for a in body.actions:
                errs, warns = validate_action(a)
                if errs:
                    results.append({"action": a.model_dump(), "ok": False,
                                    "detail": "validation: " + "; ".join(errs)})
                    continue
                try:
                    res = run_action(fm9, a)
                except Exception as e:
                    res = {"ok": False, "detail": str(e)}
                if warns:
                    res["detail"] = (res.get("detail", "") + " | " + "; ".join(warns)).strip(" |")
                results.append({"action": a.model_dump(), **res})
                if not res.get("ok") and a.kind == "add_block":
                    # later actions in the plan target the block that failed
                    # to land; running them would set params and bind pedals
                    # on a block that is not on the grid (hardware-observed
                    # on 2026-08-20, preset 143: dangling modifier binding).
                    # Only say so when there is something to skip: a one-action
                    # plan used to be told its remaining actions were skipped,
                    # which is a false sentence sitting under a true refusal.
                    remaining = body.actions[body.actions.index(a) + 1:]
                    if remaining:
                        results.append({"action": None, "ok": False,
                                        "detail": f"remaining actions skipped "
                                                  f"({len(remaining)}): "
                                                  f"add_block failed"})
                    break
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
    return {"results": results}


def main():
    # a choice made in the UI has to survive a restart, and the planner reads
    # its configuration from the environment, so push the saved one there
    ai_settings.apply_to_env()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8909)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""FM9 natural-language tone controller - local web server.

Run:  .venv/bin/python server.py   then open http://127.0.0.1:8909

Safety contract: edit-buffer only. No store/save command is implemented;
nothing is ever written to a preset slot on the unit.
"""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from fm9.device import FM9, FM9NotFound
from fm9.registry import Registry
from fm9 import planner

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="FM9 Tone Control")

reg = Registry()
_lock = threading.Lock()
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
}


def get_fm9() -> FM9:
    global _fm9
    if _fm9 is None:
        _fm9 = FM9(reg)
    return _fm9


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
    lines.append("\nAmp models selectable via set_type (block=amp). One per line as "
                 "`type_name = the real-world amp it models`; use the name to the "
                 "LEFT of the '=' as type_name, verbatim:")
    lines.extend(reg.amp_description(o) for o in reg.amp_roster)
    lines.append("\nDrive models selectable via set_type (block=drive):")
    lines.append(", ".join(str(v) for v in reg.drive_roster.values()))
    lines.append("\nReverb types selectable via set_type (block=reverb):")
    lines.append(", ".join(str(v) for v in reg.reverb_roster.values()))
    return "\n".join(lines)


PARAM_REFERENCE = param_reference()


def snapshot(fm9: FM9) -> dict:
    preset = fm9.current_preset()
    scene = fm9.scene_name()
    blocks = fm9.status_dump() or []
    out_blocks = []
    values = {}
    seen_fams = set()
    for b in blocks:
        fam = reg.family_of_effect_id(b.effect_id)
        if not fam:
            continue
        fname, inst = fam
        label = f"{FRIENDLY.get(fname, fname)} {inst}"
        out_blocks.append({"family": fname, "instance": inst, "label": label,
                           "bypassed": b.bypassed, "channel": "ABCD"[b.channel]})
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
                for pid in INTEREST[fname]:
                    s = reg.spec(fname, pid, inst)
                    idx = base + pid
                    if s.dmin is not None and idx < len(vals):
                        from fm9.protocol import normalized_to_display
                        values[f"{s.name}"] = round(
                            normalized_to_display(vals[idx] / 65534, s.dmin, s.dmax, s.scale), 2)
    return {
        "connected": True,
        "preset": {"number": preset[0], "name": preset[1]} if preset else None,
        "scene": {"number": scene[0], "name": scene[1]} if scene else None,
        "blocks": out_blocks,
        "values": values,
    }


def state_text(snap: dict) -> str:
    p, s = snap.get("preset"), snap.get("scene")
    lines = []
    if p:
        lines.append(f"Preset {p['number']}: \"{p['name']}\"")
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
    type_name: str | None = None
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
    matches = [(int(o), str(l)) for o, l in roster.items()
               if needle in str(l).lower()]
    if matches:
        return min(matches, key=lambda m: len(m[1]))
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
    with _lock:
        try:
            snap = snapshot(get_fm9())
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
    try:
        result = planner.plan(body.prompt, state_text(snap), PARAM_REFERENCE)
        result["device"] = {"preset": snap["preset"], "scene": snap["scene"]}
        return result
    except Exception as e:
        return JSONResponse({"error": f"planner failed: {e}"}, status_code=502)


def run_action(fm9: FM9, a: Action) -> dict:
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


@app.post("/api/apply")
def api_apply(body: ApplyBody):
    results = []
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
            for a in body.actions:
                try:
                    res = run_action(fm9, a)
                except Exception as e:
                    res = {"ok": False, "detail": str(e)}
                results.append({"action": a.model_dump(), **res})
        except FM9NotFound:
            drop_fm9()
            return JSONResponse({"error": "FM9 not connected"}, status_code=503)
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8909)

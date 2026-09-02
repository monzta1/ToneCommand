"""Is this preset actually correct, or is a scene silently dead?

The question no other FM9 tool answers. FM9-Edit edits presets; it does not
reason about them, so it will let you save a preset whose scene 4 makes no
sound and tell you nothing. The audits that catch that have existed here for
weeks as command-line scripts, which means nobody outside this repo has ever
run one. This module is those checks, callable against the connection the
server already holds, so they can reach a screen.

WHAT IT COSTS
-------------
A scan is AUDIBLE. It walks the preset through all eight scenes to read each
one, so the rig makes noise for a few seconds. That is unavoidable: the FM9
reports the loaded scene's state and nothing else, so the only way to know
whether scene 4 is alive is to be standing in scene 4.

This is exactly the mistake that nearly shipped in `shared_scenes()`, which
would have cycled the rig every five seconds on the state poll. So: a scan is
never automatic, never on a timer, and always something the owner asked for.
The scene it started from is restored when it finishes.

WHAT IT CHECKS
--------------
alive     Reuses signal_path.scene_alive, which walks the real cable grid from
          Input to Output. This is the check that distinguishes "the write
          landed" from "the scene makes sound", written after five different
          silent-scene classes each passed write-level verification.

clone     Two scenes that are the same scene twice. Preset 151 scene 4 was a
          byte-identical copy of scene 3 and every audit passed it, because a
          duplicate is not broken by any rule anyone had written down. Moncy
          found it by ear. It is cheap to detect and worth detecting: a wasted
          scene is a footswitch that does nothing on stage.

levels    Amp level per scene, flagged against the conventions file: a scene
          more than hot_db above the reference, or a spread wider than
          spread_db across the preset. Never summed into a fake loudness
          number, because perceived loudness is an ears question. This only
          makes outliers visible on paper.

WHY THE CLONE CHECK NEEDS NO EXTRA READS
----------------------------------------
FM9 parameters live on the CHANNEL, not on the scene. What a scene stores is
which blocks are bypassed and which channel each one is on; everything else
follows from the channel. So two scenes with an identical set of
(block, bypassed, channel) triples are not merely similar, they are the same
scene, necessarily and without reading a single parameter.

That is the same fact the UI's blast-radius warning is built on, used in the
other direction.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.conventions import load as _load_conventions   # noqa: E402
from fm9.signal_path import scene_alive

#: Let the unit land on the scene before reading it. path_audit uses the same
#: figure, arrived at on hardware; reading sooner returns the previous scene.
SETTLE = 0.3

#: Loudness is not one number. The amp block has a level in dB and the volume
#: block has a gain on a 0-10 scale, and which one carries a preset's staircase
#: depends on how it was built: on 151 the amp level is flat across all eight
#: scenes while the volume gain climbs 7.0 to 9.0, so reading only the amp
#: would have reported "levels are even" about a deliberate staircase. Both are
#: read and both are shown, side by side and never summed, exactly as
#: tools/level_report.py has always done. The flags follow the convention as
#: written, which is stated in dB and therefore about the amp.


def _blank(name: str | None) -> bool:
    """A scene the owner never named is not a scene, it is a spare slot."""
    return not name or name.strip() in ("", "-")


def _fingerprint(status) -> tuple:
    """What this scene actually stores, and therefore what makes it itself."""
    return tuple(sorted((b.effect_id, bool(b.bypassed), int(b.channel))
                        for b in status))


#: A read can simply not come back during a fast sweep. Observed on preset
#: 151 scene 4: one blank volume gain in a scan whose other seven scenes read
#: fine, and three re-reads of that exact scene returned the value every time.
READ_TRIES = 3


def _read(fm9, reg, status_by_eid, spec, eid):
    """One parameter on the channel this scene selected.

    Returns (value, why). The `why` matters as much as the value, because
    there are two different reasons for a blank and only one of them is a fact
    about the preset:

        bypassed   the block is switched out, so it contributes no level.
                   Reporting its gain would be a number about nothing.
        absent     no such block in this preset.
        unread     the read did not come back. NOT a fact about anything, and
                   the one case that must never be drawn as an empty cell,
                   because an empty cell reads as "this scene has no volume
                   block" and that is a false statement about the rig.
    """
    blk = status_by_eid.get(eid)
    if blk is None:
        return None, "absent"
    if blk.bypassed:
        return None, "bypassed"
    if spec is None or spec.dmin is None:
        return None, "absent"
    from fm9.protocol import normalized_to_display
    for attempt in range(READ_TRIES):
        wire = fm9.get_param_wire(spec, channel=blk.channel)
        if wire is not None:
            return round(normalized_to_display(
                wire / 65534, spec.dmin, spec.dmax, spec.scale), 2), "ok"
        time.sleep(0.08 * (attempt + 1))
    return None, "unread"


def _levels(fm9, reg, status) -> dict:
    """Amp level in dB and volume gain on 0-10, side by side, never summed."""
    by_eid = {b.effect_id: b for b in status}
    out = {"amp_db": None, "vol": None, "unread": []}
    for key, spec_fn, eid_fn in (
        ("amp_db", lambda: reg.find_param("DISTORT", "Level"),
         lambda: reg.effect_id("DISTORT")),
        ("vol", lambda: reg.spec("VOLUME", 0), lambda: reg.effect_id("VOLUME")),
    ):
        try:
            val, why = _read(fm9, reg, by_eid, spec_fn(), eid_fn())
        except Exception:
            val, why = None, "absent"
        out[key] = val
        if why == "unread":
            out["unread"].append(key)
    return out


def scan(fm9, reg, read_levels: bool = True, on_scene=None) -> dict:
    """Walk every named scene of the LOADED preset and report on it.

    AUDIBLE, and slow enough to be felt: eight scene changes plus a read each.
    Only ever call this because someone asked for it.

    `on_scene(n, name)` is called as each scene is entered, so a watcher can
    say which scene the rig is standing on instead of a bare "scanning...".
    A callback that raises is ignored: progress is a courtesy, the scan is
    the point.

    The scene that was loaded on entry is restored on the way out, including
    when a read raises, so a failed scan does not leave the rig somewhere the
    owner did not put it.
    """
    conv = _load_conventions()
    hot_db = conv.get("hot_db")
    spread_db = conv.get("spread_db")

    preset = fm9.current_preset()
    started_on = fm9.scene_name()
    started_on = started_on[0] if started_on else 1

    cells = fm9.read_grid() or []
    scenes: list[dict] = []
    try:
        for n in range(1, 9):
            got = fm9.scene_name(n)
            name = got[1] if got else None
            if _blank(name):
                continue
            if on_scene is not None:
                try:
                    on_scene(n, name)
                except Exception:
                    pass
            fm9.set_scene(n)
            time.sleep(SETTLE)
            status = fm9.status_dump() or []
            alive, why = scene_alive(cells, {x.effect_id: x for x in status}, reg)
            scenes.append({
                "number": n,
                "name": name,
                "alive": bool(alive),
                # `why` names the hop that broke the path, which is the whole
                # value of the check: "DEAD" alone sends you hunting.
                "why": "" if alive else why,
                **(_levels(fm9, reg, status) if read_levels
                   else {"amp_db": None, "vol": None, "unread": []}),
                "_print": _fingerprint(status),
            })
    finally:
        fm9.set_scene(started_on)
        time.sleep(SETTLE)

    findings = _cross_scene(scenes, hot_db, spread_db)
    for s in scenes:
        s.pop("_print", None)
    return {
        "preset": {"number": preset[0], "name": preset[1]} if preset else None,
        "scenes": scenes,
        "findings": findings,
        # The honest bottom rung. Every other check here is a machine reading
        # a wire; none of them can tell you the tone is GOOD.
        "ears": "pending",
    }


def _cross_scene(scenes: list[dict], hot_db, spread_db) -> list[dict]:
    """The checks that need more than one scene to be visible at all.

    Each finding carries a `fix` describing what could be done about it, in
    one of two shapes:

      actions  we know the exact change, so we say it in the action vocabulary
               and nothing has to be invented. Levels are arithmetic.
      prompt   the repair needs taste rather than arithmetic, so it is handed
               to the planner as a precise, grounded sentence.

    A fix is never applied here. It is a PROPOSAL, and it lands in the same
    plan-and-confirm path as anything else, which is what keeps the blast
    radius warning, validation, undo and the transmit gate in front of it.
    """
    out: list[dict] = []

    # --- the same scene twice ---
    # Grouped, not pairwise. Four identical scenes are one problem, and
    # reporting it as six findings buries the other checks under it.
    groups: dict[tuple, list[dict]] = {}
    for s in scenes:
        groups.setdefault(s["_print"], []).append(s)
    for members in groups.values():
        if len(members) < 2:
            continue
        nums = [m["number"] for m in members]
        named = ", ".join(f'{m["number"]} "{m["name"]}"' for m in members)
        out.append({
            "kind": "clone", "severity": "warn", "scenes": nums,
            "fix": {
                "how": "prompt",
                "label": f"Make scene {nums[-1]} its own sound",
                "prompt": (
                    f"Scenes {', '.join(str(n) for n in nums)} of this preset "
                    f"are identical: the same blocks, the same bypass states "
                    f"and the same channels, so they are one sound under "
                    f"{len(nums)} names. Scene {nums[-1]} is called "
                    f"\"{members[-1]['name']}\". Change scene {nums[-1]} so "
                    f"it earns that name and is audibly different from scene "
                    f"{nums[0]}, using bypass and channel changes on the "
                    f"blocks already in this preset. Do not add blocks."),
            },
            "detail": f"scenes {named} are identical: same blocks, same bypass "
                      f"states, same channels. Parameters live on the channel, "
                      f"so these are the same sound, and every footswitch past "
                      f"the first does nothing.",
        })

    # --- dead scenes ---
    for s in scenes:
        if not s["alive"]:
            out.append({
                "kind": "dead", "severity": "fail", "scenes": [s["number"]],
                "fix": {
                    "how": "prompt",
                    "label": f"Get scene {s['number']} making sound again",
                    "prompt": (
                        f"Scene {s['number']} of this preset makes no sound. "
                        f"Walking the grid from the Input block to the Output "
                        f"block finds no live path, and the reason is: "
                        f"{s['why']}. Re-engage whatever blocks are bypassed "
                        f"on that scene so signal reaches an engaged Output. "
                        f"Do not add blocks and do not rewire the grid."),
                },
                "detail": f"scene {s['number']} \"{s['name']}\" has no live "
                          f"signal path: {s['why']}",
            })

    # --- reads that did not come back ---
    missed = [(s["number"], s.get("unread") or []) for s in scenes
              if s.get("unread")]
    if missed:
        where = "; ".join(f"scene {n}: {', '.join(w)}" for n, w in missed)
        out.append({
            "kind": "incomplete", "severity": "warn",
            "fix": {"how": "rescan", "label": "Scan again"},
            "scenes": [n for n, _ in missed],
            "detail": f"some values did not read back after {READ_TRIES} tries "
                      f"({where}). Those cells are unknown, not empty, and the "
                      f"level checks below skip them. Scan again.",
        })

    # --- loudness outliers, reported as facts and never as a verdict ---
    levels = [(s["number"], s["amp_db"]) for s in scenes if s["amp_db"] is not None]
    if levels and hot_db is not None and spread_db is not None:
        vals = [v for _, v in levels]
        # Scene 3 is the reference by convention, the median if there is no 3.
        ref = next((v for n, v in levels if n == 3), None)
        if ref is None:
            ordered = sorted(vals)
            ref = ordered[len(ordered) // 2]
        for n, v in levels:
            if v - ref > hot_db:
                out.append({
                    "kind": "hot", "severity": "warn", "scenes": [n],
                    "detail": f"scene {n} amp level is {round(v - ref, 2)} dB "
                              f"above the reference ({ref} dB), past the "
                              f"{hot_db} dB the conventions allow",
                    # Arithmetic, not taste, so the exact change is stated
                    # rather than described to a language model. Two actions
                    # because amp level lives on the CHANNEL: you have to be
                    # standing on the scene before writing it, and the blast
                    # radius warning will then say which other scenes share
                    # that channel and are coming with it.
                    "fix": {
                        "how": "actions",
                        "label": f"Bring scene {n} down to {ref} dB",
                        "actions": [
                            {"kind": "set_scene", "value": n,
                             "reason": f"the level lives on scene {n}'s channel"},
                            {"kind": "set_param", "block": "DISTORT",
                             "instance": 1, "param": "DISTORT_LEVEL",
                             "value": ref,
                             "reason": f"{round(v - ref, 2)} dB above the "
                                       f"reference, past the {hot_db} dB "
                                       f"convention"},
                        ],
                    },
                })
        spread = max(vals) - min(vals)
        if spread > spread_db:
            out.append({
                "kind": "spread", "severity": "warn",
                # Deliberately no fix. A wide spread is often the point: the
                # scene 1-5 loudness staircase is a convention here, not a
                # fault, and offering to flatten it would be offering to undo
                # the thing the preset was built to do.
                "fix": None,
                "scenes": [n for n, _ in levels],
                "detail": f"amp level spans {round(spread, 2)} dB across the "
                          f"preset, wider than the {spread_db} dB convention",
            })
    return out

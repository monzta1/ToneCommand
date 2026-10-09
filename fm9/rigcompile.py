"""A rig graph, compiled to FM9 scenes (#228; Rig Reconstruction, #224).

Deterministic on purpose. What a build keeps, changes and leaves out is
decided here, before any model runs, so it can be stated to the player and
tested. The planner then chooses models and values for a chain this module
has already fixed.

Every original node and edge id ends up in `status` with exactly one state,
kept, changed or not_reproduced, and a reason. Nothing in a rig is dropped
without saying so.

Today's FM9 builds are one serial path (#16), so a rig that runs two amps
at once, or in stereo, is built as one mono path with that disclosed; in
faithful-routing mode it is refused instead of built as something it is not.
"""
from __future__ import annotations

from fm9 import riggraph

MODES = ("closest", "faithful", "simplified")
MAX_SCENES = 8

#: rig role -> the planner's block name. Roles with no block (the guitar, a
#: switcher, a controller, an interface) are not part of the audio chain.
ROLE_BLOCK = {"wah": "wah", "drive": "drive", "compressor": "comp",
              "modulation": "chorus", "delay": "delay", "reverb": "reverb",
              "pitch": "pitch", "volume": "volume", "preamp": "amp",
              "amp": "amp", "cab": "cab", "rack_fx": "delay"}
NO_BLOCK = {"instrument", "switcher", "controller", "interface"}


def _block_for(node: dict) -> str | None:
    role = node.get("role")
    if role == "modulation":
        label = node.get("label", "").lower()
        # stems, so an "MXR Phase 90" or a "Uni-Vibe-ish leslie" still lands
        for stem, block in (("phas", "phaser"), ("flang", "flanger"), ("trem", "tremolo"),
                            ("rotary", "rotary"), ("leslie", "rotary")):
            if stem in label:
                return block
        return "chorus"
    return ROLE_BLOCK.get(role)


def compile(graph: dict, mode: str = "closest", scenes: int | None = None) -> dict:
    if mode not in MODES:
        raise riggraph.RigGraphError(f"mode {mode!r} is not one of {', '.join(MODES)}")
    g = riggraph.load(graph)
    nodes = {n["id"]: n for n in g["nodes"]}
    node_status: dict[str, list] = {}
    edge_status: dict[str, list] = {}
    blockers: list[str] = []

    walked = riggraph.audio_paths(g)
    groups: dict = {}
    for p in walked["paths"]:
        groups.setdefault(p["route"], []).append(p["nodes"])
    # route order as the rig gives it; unrouted (None) first when present
    order = sorted(groups, key=lambda r: (r is not None, list(groups).index(r)))

    if mode == "simplified":
        dropped_groups = order[1:]
        order = order[:1]
    else:
        dropped_groups = []
    cap = MAX_SCENES if scenes is None else max(1, min(MAX_SCENES, int(scenes)))
    over_cap = order[cap:]
    order = order[:cap]

    built: list[dict] = []
    kept_pairs: set[tuple] = set()      # consecutive (from, to) on a built chain
    for route in order:
        paths = groups[route]
        chosen = paths[0]
        if len(paths) > 1:
            others = [x for p in paths[1:] for x in p if x not in chosen]
            what = ", ".join(nodes[x]["label"] for x in dict.fromkeys(others)) or "a second path"
            if mode == "faithful":
                blockers.append(
                    f"{'Route ' + route + ' runs' if route else 'This rig runs'} two signal paths at "
                    f"once ({what}); an FM9 build is one serial path until stereo and parallel "
                    f"builds land (#16).")
            for x in dict.fromkeys(others):
                node_status.setdefault(x, ["not_reproduced",
                                           "runs in parallel with the kept path; one serial path is built (#16)"])
        chain: list[dict] = []
        counts: dict[str, int] = {}
        prev_amp = None
        for nid in chosen:
            n = nodes[nid]
            if n["role"] in NO_BLOCK:
                node_status.setdefault(nid, ["changed", "not a block; it is you playing, or switching scenes"]
                                       if n["role"] != "instrument" else ["kept", "the input"])
                continue
            if n["role"] == "power_amp":
                if prev_amp is not None:
                    node_status.setdefault(nid, ["changed", f"part of the {prev_amp['label']} amp block's power section"])
                    continue
                node_status.setdefault(nid, ["changed", "built as the amp block, there being no preamp before it"])
                block = "amp"
            else:
                block = _block_for(n)
            if block is None:
                node_status.setdefault(nid, ["not_reproduced", f"no FM9 block stands in for the {n['label']}"])
                continue
            if mode == "simplified" and block in counts:
                node_status.setdefault(nid, ["not_reproduced", f"simplified: one {block} block kept"])
                continue
            counts[block] = counts.get(block, 0) + 1
            step = {"node": nid, "label": n["label"], "role": n["role"], "block": block,
                    "instance": counts[block]}
            chain.append(step)
            node_status.setdefault(nid, ["kept", f"{block} {counts[block]}"])
            if block == "amp":
                prev_amp = n
        for a, b in zip(chosen, chosen[1:]):
            kept_pairs.add((a, b))
        built.append({"n": len(built) + 1, "name": route or "Rig", "route": route, "chain": chain})

    for route in dropped_groups:
        for p in groups[route]:
            for x in p:
                node_status.setdefault(x, ["not_reproduced", f"simplified: only the first route is built"])
    for route in over_cap:
        for p in groups[route]:
            for x in p:
                node_status.setdefault(x, ["not_reproduced", f"more routes than scenes asked for ({cap})"])

    # edges: one state each
    # a stereo source with one side on the built chain: its other side is the
    # second half of a pair, built as the one mono path
    stereo_on_chain = {e["from"] for e in g["edges"]
                       if e["kind"] == "audio_stereo" and (e["from"], e["to"]) in kept_pairs}
    lr_seen: set[tuple] = set()
    for e in g["edges"]:
        on_chain = (e["from"], e["to"]) in kept_pairs
        if e["kind"] in ("control", "expression"):
            edge_status[e["id"]] = ["changed", "control, not audio: you switch scenes or ride the pedal yourself"]
        elif e["kind"] == "audio_stereo" and (((e["from"], e["to"]) in lr_seen)
                                              or (not on_chain and e["from"] in stereo_on_chain)):
            edge_status[e["id"]] = ["changed", "the second side of a stereo pair; built as one mono path (#16)"]
        elif e["kind"] in riggraph.AUDIO_KINDS and on_chain:
            if e["kind"] == "audio_stereo":
                lr_seen.add((e["from"], e["to"]))
                edge_status[e["id"]] = ["changed", "built mono; stereo builds come with #16"]
            else:
                edge_status[e["id"]] = ["kept", "in the built chain"]
        elif e["kind"] in riggraph.AUDIO_KINDS and any(e["from"] in c and e["to"] in c for c in walked["cycles"]):
            edge_status[e["id"]] = ["not_reproduced", "part of a loop that cannot be built"]
        elif e["kind"] in riggraph.AUDIO_KINDS:
            edge_status[e["id"]] = ["not_reproduced", "not on the built path"]
        else:
            edge_status[e["id"]] = ["not_reproduced", f"a {e['kind']} connection has no FM9 equivalent here"]
    # nodes never reached by any audio path (a lone controller, say)
    for nid, n in nodes.items():
        if nid not in node_status:
            if n["role"] in ("controller", "switcher"):
                node_status[nid] = ["changed", "control, not audio: you switch scenes yourself"]
            else:
                node_status[nid] = ["not_reproduced", "not connected to the signal path"]

    return {"mode": mode, "scenes": built,
            "status": {"nodes": node_status, "edges": edge_status},
            "blockers": blockers}


def summary(compiled: dict, graph: dict) -> dict:
    """kept / changed / not_reproduced as words for the report."""
    g = riggraph.normalize(graph)
    label = {n["id"]: n["label"] for n in g["nodes"]}
    edges = {e["id"]: e for e in g["edges"]}
    out = {"kept": [], "changed": [], "not_reproduced": []}
    for nid, (state, why) in compiled["status"]["nodes"].items():
        if state != "kept":
            out[state].append({"what": label.get(nid, nid), "why": why})
    for eid, (state, why) in compiled["status"]["edges"].items():
        if state != "kept":
            e = edges.get(eid, {})
            out[state].append({"what": f"{label.get(e.get('from'), '?')} -> {label.get(e.get('to'), '?')}",
                               "why": why})
    for sc in compiled["scenes"]:
        for step in sc["chain"]:
            out["kept"].append({"node": step["node"], "what": step["label"], "scene": sc["n"],
                                "block": step["block"], "instance": step["instance"]})
    return out


# --- the plan, read back against the rig ---------------------------------------

#: value-setting actions; a set_param can be credited to the source, the rest
#: are always ToneCommand's choice
VALUE_KINDS = ("set_param", "set_tempo", "set_type", "set_cab", "set_channel")


def _num(v) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _stated_match(action: dict, stated: list[str]) -> bool:
    """True when one stated item names this parameter AND this number."""
    if action.get("kind") != "set_param" or action.get("value") is None or not action.get("param"):
        return False
    import re
    words = [w for w in re.split(r"[_\s]+", str(action["param"]).lower()) if w]
    number = _num(action["value"])
    for item in stated or []:
        text = str(item).lower()
        if all(w in text for w in words) and re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", text):
            return True
    return False


def fidelity(compiled: dict, graph: dict, actions: list[dict], stated: list[str]) -> dict:
    """The report the player reads with the plan. Grounded in the plan's own
    validated actions: a piece of gear names a model only when a valid
    set_type or set_cab sits on its block and instance."""
    from fm9.registry import Registry, BLOCK_ALIASES
    words = summary(compiled, graph)

    def family(block):
        name = str(block or "").strip().lower()
        return BLOCK_ALIASES.get(name, name.upper())

    def instance(a):
        try:
            return int(a.get("instance") or 1)
        except (TypeError, ValueError):
            return 1

    kept = []
    for item in words["kept"]:
        fam = family(item["block"])
        idx = [i for i, a in enumerate(actions)
               if not a.get("validation_errors") and family(a.get("block")) == fam
               and instance(a) == item["instance"]]
        model = next((actions[i].get("type_name") or actions[i].get("cab_name")
                      for i in idx if actions[i].get("kind") in ("set_type", "set_cab")
                      and (actions[i].get("type_name") or actions[i].get("cab_name"))), None)
        try:
            eid = Registry().effect_id(fam, item["instance"])
        except (KeyError, ValueError):
            eid = None
        # Every name this block family answers to: send results echo the
        # action as planned (block and instance, no effect id), so the page
        # matches them on these (#228).
        names = sorted({k for k, v in BLOCK_ALIASES.items() if v == fam} | {fam.lower()})
        kept.append({**item, "model": model, "actions": idx, "effect_id": eid, "names": names})
    chosen = [i for i, a in enumerate(actions)
              if not a.get("validation_errors") and a.get("kind") in VALUE_KINDS
              and not _stated_match(a, stated)]
    return {"kept": kept, "changed": words["changed"], "not_reproduced": words["not_reproduced"],
            "chosen": {"count": len(chosen), "actions": chosen,
                       "stated_used": sum(1 for a in actions if not a.get("validation_errors")
                                          and _stated_match(a, stated))}}

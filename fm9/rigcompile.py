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
    # Faithful routing cannot build stereo either: a stereo pair on the built
    # chain is refused before planning, the same as two paths at once.
    if mode == "faithful" and stereo_on_chain:
        what = ", ".join(nodes[x]["label"] for x in sorted(stereo_on_chain))
        blockers.append(f"This rig runs in stereo from {what}; an FM9 build is one mono path "
                        f"until stereo and parallel builds land (#16).")
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
VALUE_KINDS = ("set_param", "set_tempo", "set_type", "set_cab", "set_channel",
               "set_device_param")


def _num(v) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _stated_match(action: dict, stated: list[str]) -> bool:
    """True when one stated item names this parameter AND this number."""
    if action.get("kind") not in ("set_param", "set_device_param") or action.get("value") is None \
            or not action.get("param"):
        return False
    import re
    words = [w for w in re.split(r"[_\s]+", str(action["param"]).lower()) if w]
    number = _num(action["value"])
    for item in stated or []:
        text = str(item).lower()
        # whole words and whole signed numbers: GAIN is not "again", 7 is
        # not 7.5, and 7 is not -7
        if all(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) for w in words) \
                and re.search(rf"(?<![\d.+\-\u2212]){re.escape(number)}(?!\d|\.\d)", text):
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

    # #230: on a device that names its parameters, a kept piece is the
    # parameters it became, and its model is the AMP voicing the plan chose
    steps = {s["node"]: s for sc in compiled["scenes"] for s in sc["chain"]}
    kept = []
    for item in words["kept"]:
        step = steps.get(item.get("node"), {})
        if step.get("params"):
            idx = [i for i, a in enumerate(actions)
                   if not a.get("validation_errors") and a.get("kind") == "set_device_param"
                   and str(a.get("param") or "").upper() in step["params"]]
            model = next((actions[i].get("type_name") for i in idx
                          if str(actions[i].get("param") or "").upper() == "AMP"
                          and actions[i].get("type_name")), None)
            kept.append({**item, "param": step["param"], "params": step["params"], "model": model,
                         "actions": idx, "effect_id": None, "names": []})
            continue
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


# --- #229: the rig against the loaded preset -------------------------------------

#: grid families that are the preset's own ends, not gear
_ENDS = {"INPUT", "OUTPUT"}


def _in_order(seq: list[int]) -> set[int]:
    """Indexes of one longest strictly increasing run in seq: the blocks that
    can stay where they are; everything else is the fewest moves."""
    if not seq:
        return set()
    best = [1] * len(seq)
    prev = [-1] * len(seq)
    for i in range(len(seq)):
        for j in range(i):
            if seq[j] < seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(len(seq)), key=lambda k: best[k])
    keep = set()
    while i != -1:
        keep.add(i)
        i = prev[i]
    return keep


def compare(compiled: dict, grid: dict, scene: int = 1) -> dict:
    """What differs between a compiled rig scene and the loaded scene's grid.

    Read-only by construction: it takes a grid reading (the cells /api/grid
    returns) and returns words. Gear is matched to blocks by family and order
    of appearance, so the rig's second drive is the second drive on the live
    path, left to right. Every rig block ends up matched or missing, and
    every live block matched or extra."""
    from fm9.registry import BLOCK_ALIASES
    scenes = compiled.get("scenes") or []
    sc = next((s for s in scenes if s["n"] == scene), scenes[0] if scenes else None)
    rig = list(sc["chain"]) if sc else []
    cells = grid.get("cells") or []
    live = sorted((c for c in cells if c.get("live") and c.get("effect_id") is not None
                   and c.get("family") and c["family"] not in _ENDS),
                  key=lambda c: (c["col"], c["row"]))

    def fam(step):
        return BLOCK_ALIASES.get(step["block"], step["block"].upper())

    pool: dict[str, list[int]] = {}
    for i, c in enumerate(live):
        pool.setdefault(c["family"], []).append(i)
    matches, missing, used = [], [], set()
    for step in rig:
        queue = pool.get(fam(step)) or []
        if queue:
            i = queue.pop(0)
            used.add(i)
            matches.append((step, live[i], i))
        else:
            missing.append({"what": step["label"], "block": step["block"],
                            "why": f"the rig has the {step['label']} ({step['block']}); "
                                   f"the loaded scene has no {step['block']} block on its signal path for it"})
    extra = [{"what": c["label"], "why": f"{c['label']} is on the loaded scene's path; the rig has nothing there"}
             for i, c in enumerate(live) if i not in used]
    keep = _in_order([i for _, _, i in matches])
    out_of_order = []
    for k, (step, c, _) in enumerate(matches):
        if k not in keep:
            before = matches[k - 1][0]["label"] if k else None
            out_of_order.append({"what": step["label"], "live": c["label"],
                                 "why": f"the {step['label']} is {c['label']}, which sits in a different "
                                        f"place on the preset" + (f"; the rig has it after the {before}" if before
                                                                    else "; the rig has it first")})
    routing = []
    # Forks and merges come from the cables (feeds), shunts included. A
    # serial path that steps from one row to another is still one path, so
    # rows alone never count as a split.
    path = {(c["row"], c["col"]): c for c in cells if c.get("live")}
    for (r, col), c in sorted(path.items(), key=lambda x: (x[0][1], x[0][0])):
        fed = [x for x in c.get("feeds") or [] if (x, col - 1) in path]
        if len(fed) > 1:
            routing.append({"what": f"merge at column {col + 1}",
                            "why": f"{len(fed)} paths join at column {col + 1} of the loaded scene; "
                                   f"the rig is one path"})
        outs = [x for (rr, cc), x in path.items() if cc == col + 1 and r in (x.get("feeds") or [])]
        if len(outs) > 1:
            routing.append({"what": f"split at column {col + 1}",
                            "why": f"the loaded scene's signal splits into {len(outs)} paths after "
                                   f"column {col + 1}; the rig is one path"})
    for step, c, _ in matches:
        if c.get("bypassed"):
            routing.append({"what": c["label"], "why": f"{c['label']} (the {step['label']}) is bypassed in this scene"})
    if grid.get("alive") is False:
        routing.append({"what": "path", "why": f"no signal reaches the output: {grid.get('why') or 'the path is broken'}"})
    for state in ("changed", "not_reproduced"):
        for nid, (st, why) in (compiled.get("status", {}).get("nodes") or {}).items():
            if st == state and "#16" in why:
                routing.append({"what": nid, "why": f"from the rig: {why}"})
    n = len(missing) + len(extra) + len(out_of_order) + len(routing)
    summary = ("The loaded scene already matches this rig." if n == 0 else
               f"{n} difference{'s' if n != 1 else ''} between this rig and the loaded scene.")
    return {"scene": sc["n"] if sc else None,
            "matches": [{"rig": s["label"], "block": s["block"], "live": c["label"]} for s, c, _ in matches],
            "missing": missing, "extra": extra, "out_of_order": out_of_order,
            "routing": routing, "summary": summary}


# --- #230: the same rig on a device that names its parameters --------------------

#: what a published parameter stands in for: the parameter, the rig roles it
#: takes (the first of them), and the parameters that come with it
PARAM_ROLES = {
    "AMP": {"roles": ("amp", "preamp"), "block": "amp",
            "with": ("AMP", "GAIN", "BASS", "MIDDLE", "TREBLE")},
    "AMBIENCE": {"roles": ("reverb",), "block": "reverb", "with": ("AMBIENCE",)},
}


def compile_for_params(graph: dict, params: list[dict], device: str,
                       mode: str = "closest") -> dict:
    """A rig evaluated against a device that declares named parameters (the
    IR-2), from what that device publishes and nothing else. Same shape and
    the same one-state-per-id accounting as compile(), plus `target`."""
    if mode not in MODES:
        raise riggraph.RigGraphError(f"mode {mode!r} is not one of {', '.join(MODES)}")
    g = riggraph.load(graph)
    nodes = {n["id"]: n for n in g["nodes"]}
    names = {p["name"] for p in params}
    amp_row = next((p for p in params if p["name"] == "AMP"), {})
    own_cab = bool(amp_row.get("option_cabs"))
    node_status: dict[str, list] = {}
    edge_status: dict[str, list] = {}
    blockers: list[str] = []

    walked = riggraph.audio_paths(g)
    groups: dict = {}
    for p in walked["paths"]:
        groups.setdefault(p["route"], []).append(p["nodes"])
    order = sorted(groups, key=lambda r: (r is not None, list(groups).index(r)))
    chosen = groups[order[0]][0] if order else []
    parallel = []
    if order:
        for p in groups[order[0]][1:]:
            parallel += [x for x in p if x not in chosen]
    for route in order[1:]:
        for p in groups[route]:
            for x in p:
                node_status.setdefault(x, ["not_reproduced", f"the {device} has no scenes; one route is built"])
    for x in dict.fromkeys(parallel):
        node_status.setdefault(x, ["not_reproduced",
                                   f"runs in parallel with the kept path; the {device} is one signal path"])

    chain: list[dict] = []
    taken: dict[str, dict] = {}            # parameter -> the step that took it
    lost: list[str] = []                   # audio gear the device cannot have
    for nid in chosen:
        n = nodes[nid]
        role = n["role"]
        if role in NO_BLOCK:
            node_status.setdefault(nid, ["kept", "the input"] if role == "instrument"
                                   else ["changed", "not a block; it is you playing, or switching"])
            continue
        if role == "power_amp":
            if "AMP" in taken:
                node_status.setdefault(nid, ["changed", f"part of the {taken['AMP']['label']} voicing"])
                continue
            role = "amp"
        if role == "cab":
            if "AMP" in names and own_cab:
                node_status.setdefault(nid, ["changed", f"the {device}'s amp voicing brings its own cab"])
            else:
                node_status.setdefault(nid, ["not_reproduced", f"the {device} has no cab block"])
                lost.append(n["label"])
            continue
        param = next((k for k, v in PARAM_ROLES.items() if k in names and role in v["roles"]), None)
        block = _block_for({**n, "role": role}) or role
        if param is None:
            node_status.setdefault(nid, ["not_reproduced", f"the {device} has no {block} block"])
            lost.append(n["label"])
            continue
        if param in taken:
            node_status.setdefault(nid, ["not_reproduced", f"the {device} has one {block}; the "
                                                           f"{taken[param]['label']} took it"])
            lost.append(n["label"])
            continue
        spec = PARAM_ROLES[param]
        step = {"node": nid, "label": n["label"], "role": n["role"], "block": spec["block"],
                "instance": 1, "param": param, "params": [p for p in spec["with"] if p in names]}
        taken[param] = step
        chain.append(step)
        node_status.setdefault(nid, ["kept", f"{param} on the {device}"])

    kept_pairs = set(zip(chosen, chosen[1:]))
    stereo = {e["from"] for e in g["edges"] if e["kind"] == "audio_stereo" and (e["from"], e["to"]) in kept_pairs}
    lr_seen: set[tuple] = set()
    for e in g["edges"]:
        on_chain = (e["from"], e["to"]) in kept_pairs
        if e["kind"] in ("control", "expression"):
            edge_status[e["id"]] = ["changed", "control, not audio: you ride the pedal yourself"]
        elif e["kind"] == "audio_stereo" and ((e["from"], e["to"]) in lr_seen
                                              or (not on_chain and e["from"] in stereo)):
            edge_status[e["id"]] = ["changed", f"the second side of a stereo pair; the {device} is mono"]
        elif e["kind"] in riggraph.AUDIO_KINDS and on_chain:
            if e["kind"] == "audio_stereo":
                lr_seen.add((e["from"], e["to"]))
                edge_status[e["id"]] = ["changed", f"built mono on the {device}"]
            else:
                edge_status[e["id"]] = ["kept", "in the built path"]
        elif e["kind"] in riggraph.AUDIO_KINDS and any(e["from"] in c and e["to"] in c for c in walked["cycles"]):
            edge_status[e["id"]] = ["not_reproduced", "part of a loop that cannot be built"]
        elif e["kind"] in riggraph.AUDIO_KINDS:
            edge_status[e["id"]] = ["not_reproduced", "not on the built path"]
        else:
            edge_status[e["id"]] = ["not_reproduced", f"a {e['kind']} connection has no equivalent here"]
    for nid, n in nodes.items():
        if nid not in node_status:
            node_status[nid] = (["changed", "control, not audio"] if n["role"] in ("controller", "switcher")
                                else ["not_reproduced", "not connected to the signal path"])

    if mode == "faithful":
        if lost:
            blockers.append(f"The {device} has no place for {', '.join(lost)}.")
        if parallel or stereo:
            blockers.append(f"This rig runs {'in stereo' if stereo else 'two paths at once'}; "
                            f"the {device} is one mono path.")
    return {"mode": mode, "target": device,
            "scenes": [{"n": 1, "name": device, "route": order[0] if order else None, "chain": chain}],
            "status": {"nodes": node_status, "edges": edge_status}, "blockers": blockers}

"""A rig, as a graph: what a reference shows, connected the way it shows it.

Rig Reconstruction (#224). A rig rundown, a video or (later) a picture is
read into this shape before anything is built, so the player can see what
was recognised, what was only inferred, and what the source never said.

The rules that make it honest:

- Edges are TYPED. A switcher's control line is never an audio cable: only
  audio, audio_mono, audio_stereo and send_return carry signal, and
  audio_paths() walks nothing else.
- Every node and edge carries PROVENANCE. observed: the source shows or
  states it. inferred: the reader concluded it. user_confirmed: the player
  said so. unresolved: nobody knows. A missing provenance is unresolved,
  never observed, so a reader that forgets to say cannot launder a guess.
- Switcher ALTERNATIVES carry a route label. A path takes at most one route,
  so two alternatives that merge and split again never combine into one
  chain that does not exist.
- Corrections are structured ops applied to a copy, all or nothing, with
  edges targeted by id (two parallel L/R cables share their endpoints).
"""
from __future__ import annotations

import copy

SCHEMA_VERSION = 1

#: "audio" carries sound but the source does not say mono or stereo;
#: "unknown" means it cannot be told whether the connection is audio at all.
#: Found by the first live extract: without "audio", an honest reader had to
#: call switcher cables unknown, and both routes fell out of the chain.
EDGE_KINDS = ("audio", "audio_mono", "audio_stereo", "send_return", "control",
              "expression", "other", "unknown")
AUDIO_KINDS = frozenset({"audio", "audio_mono", "audio_stereo", "send_return"})
PROVENANCE = ("observed", "inferred", "user_confirmed", "unresolved")
ROLES = ("instrument", "wah", "drive", "compressor", "modulation", "delay",
         "reverb", "pitch", "volume", "preamp", "amp", "power_amp", "cab",
         "switcher", "controller", "rack_fx", "interface", "other")
CHANNELS = ("L", "R")


class RigGraphError(ValueError):
    """A graph or an edit that cannot be accepted, said in words."""


def normalize(graph: dict) -> dict:
    """A copy with defaults filled in: missing provenance is unresolved,
    edges without an id get e1, e2, ... (never reusing an id in use)."""
    g = copy.deepcopy(graph) if isinstance(graph, dict) else {}
    g.setdefault("schema_version", SCHEMA_VERSION)
    g["nodes"] = [dict(n) for n in g.get("nodes") or [] if isinstance(n, dict)]
    g["edges"] = [dict(e) for e in g.get("edges") or [] if isinstance(e, dict)]
    g["unknowns"] = [str(u) for u in g.get("unknowns") or [] if str(u).strip()]
    for n in g["nodes"]:
        n["id"] = str(n.get("id") or "").strip()
        n["label"] = str(n.get("label") or n["id"]).strip()
        n.setdefault("role", "other")
        n["provenance"] = n.get("provenance") or "unresolved"
    used = {str(e.get("id")) for e in g["edges"] if e.get("id")}
    k = 0
    for e in g["edges"]:
        if not e.get("id"):
            k += 1
            while f"e{k}" in used:
                k += 1
            e["id"] = f"e{k}"
            used.add(e["id"])
        e["id"] = str(e["id"])
        e.setdefault("kind", "unknown")
        e["provenance"] = e.get("provenance") or "unresolved"
    return g


def validate(graph: dict) -> list[str]:
    """Every problem with a NORMALIZED graph, in words. Empty means valid."""
    problems: list[str] = []
    if graph.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version {graph.get('schema_version')!r} is not "
                        f"one this version reads ({SCHEMA_VERSION})")
    ids: set[str] = set()
    for n in graph.get("nodes", []):
        if not n["id"]:
            problems.append("a node has no id")
        elif n["id"] in ids:
            problems.append(f"node id {n['id']!r} is used twice")
        ids.add(n["id"])
        if n["role"] not in ROLES:
            problems.append(f"node {n['id']!r} has role {n['role']!r}, not one of {', '.join(ROLES)}")
        if n["provenance"] not in PROVENANCE:
            problems.append(f"node {n['id']!r} has provenance {n['provenance']!r}")
    eids: set[str] = set()
    for e in graph.get("edges", []):
        if e["id"] in eids:
            problems.append(f"edge id {e['id']!r} is used twice")
        eids.add(e["id"])
        for end in ("from", "to"):
            if e.get(end) not in ids:
                problems.append(f"edge {e['id']!r} {end} {e.get(end)!r} is not a node")
        if e["kind"] not in EDGE_KINDS:
            problems.append(f"edge {e['id']!r} has kind {e['kind']!r}, not one of {', '.join(EDGE_KINDS)}")
        if e["provenance"] not in PROVENANCE:
            problems.append(f"edge {e['id']!r} has provenance {e['provenance']!r}")
        if e.get("channel") is not None:
            if e["kind"] != "audio_stereo":
                problems.append(f"edge {e['id']!r} has a channel but is not audio_stereo")
            elif e["channel"] not in CHANNELS:
                problems.append(f"edge {e['id']!r} channel {e['channel']!r} is not L or R")
        if e.get("route") is not None and not str(e["route"]).strip():
            problems.append(f"edge {e['id']!r} has an empty route")
    return problems


def _shape_problems(graph: dict) -> list[str]:
    """What normalize would otherwise drop or choke on: wrong containers,
    members that are not objects, ids and endpoints that are not text."""
    problems = []
    for key in ("nodes", "edges", "unknowns"):
        if key in graph and graph[key] is not None and not isinstance(graph[key], list):
            problems.append(f"{key} is not a list")
    for i, x in enumerate(graph.get("nodes") or [] if isinstance(graph.get("nodes"), list) else []):
        if not isinstance(x, dict):
            problems.append(f"node {i + 1} is not an object")
        elif not isinstance(x.get("id"), str):
            problems.append(f"node {i + 1} has no text id")
    for i, x in enumerate(graph.get("edges") or [] if isinstance(graph.get("edges"), list) else []):
        if not isinstance(x, dict):
            problems.append(f"edge {i + 1} is not an object")
            continue
        for end in ("from", "to"):
            if not isinstance(x.get(end), str):
                problems.append(f"edge {i + 1} {end} is not a node id")
        if x.get("kind") is not None and not isinstance(x.get("kind"), str):
            problems.append(f"edge {i + 1} kind is not text")
    return problems


def load(graph: dict) -> dict:
    """Normalize and validate, or raise RigGraphError with every problem.
    Malformed input is refused, never quietly emptied."""
    if not isinstance(graph, dict):
        raise RigGraphError("the rig is not an object")
    shape = _shape_problems(graph)
    if shape:
        raise RigGraphError("; ".join(shape))
    g = normalize(graph)
    problems = validate(g)
    if problems:
        raise RigGraphError("; ".join(problems))
    return g


def audio_paths(graph: dict) -> dict:
    """{'paths': [{'route': str|None, 'nodes': [ids]}], 'cycles': [[ids]]}.

    Audio edges only: a control or expression edge is never followed. A path
    takes at most one route label, so switcher alternatives never combine.
    A cycle is reported, not looped."""
    g = normalize(graph)
    nodes = [n["id"] for n in g["nodes"]]
    out_edges: dict[str, list[dict]] = {n: [] for n in nodes}
    has_in: set[str] = set()
    for e in g["edges"]:
        if e["kind"] in AUDIO_KINDS and e.get("from") in out_edges and e.get("to") in out_edges:
            out_edges[e["from"]].append(e)
            has_in.add(e["to"])
    audio_nodes = {e["from"] for es in out_edges.values() for e in es} | has_in
    sources = [n for n in nodes if n in audio_nodes and n not in has_in]
    paths: list[dict] = []
    cycles: list[list[str]] = []
    seen_paths: set[tuple] = set()

    def walk(node: str, trail: list[str], route):
        nexts = [e for e in out_edges[node]
                 if e.get("route") is None or route is None or e.get("route") == route]
        extended = False
        for e in nexts:
            nxt = e["to"]
            if nxt in trail:
                cyc = trail[trail.index(nxt):] + [nxt]
                if cyc not in cycles:
                    cycles.append(cyc)
                continue
            extended = True
            walk(nxt, trail + [nxt], e.get("route") if e.get("route") is not None else route)
        # A path ends where nothing new follows: a sink, or a node whose only
        # way on loops back (the loop is reported, the path still counts).
        if not extended:
            key = (route, tuple(trail))
            if key not in seen_paths:
                seen_paths.add(key)
                paths.append({"route": route, "nodes": list(trail)})

    for s in sources:
        walk(s, [s], None)
    # A part of the rig that is only a loop has no source. Every such part
    # is walked from its first node, so each loop is reported, not dropped.
    reached = {x for p in paths for x in p["nodes"]} | {x for c in cycles for x in c}
    for nid in nodes:
        if nid in audio_nodes and nid not in reached:
            walk(nid, [nid], None)
            reached |= {x for p in paths for x in p["nodes"]} | {x for c in cycles for x in c}
    return {"paths": paths, "cycles": cycles}


def _label(g: dict, nid: str) -> str:
    n = next((n for n in g["nodes"] if n["id"] == nid), None)
    return n["label"] if n else nid


def explain(graph: dict) -> list[str]:
    """The rig in plain lines a guitarist reads top to bottom."""
    g = normalize(graph)
    lines: list[str] = []
    walked = audio_paths(g)
    routes = {p["route"] for p in walked["paths"] if p["route"]}
    for p in walked["paths"]:
        chain = " -> ".join(_label(g, n) for n in p["nodes"])
        lead = f"Route {p['route']}: " if p["route"] else ("Signal: " if not routes else "Common: ")
        lines.append(lead + chain)
    for cyc in walked["cycles"]:
        lines.append("Unresolved loop: " + " -> ".join(_label(g, n) for n in cyc))
    for e in g["edges"]:
        if e["kind"] in ("control", "expression"):
            what = "controls" if e["kind"] == "control" else "is an expression pedal for"
            lines.append(f"Control: {_label(g, e['from'])} {what} {_label(g, e['to'])} (not in the audio path)")
    stereo = [e for e in g["edges"] if e["kind"] == "audio_stereo"]
    if stereo:
        pairs = sorted({f"{_label(g, e['from'])} -> {_label(g, e['to'])}" for e in stereo})
        lines.append("Stereo: " + "; ".join(pairs))
    inferred = [n["label"] for n in g["nodes"] if n["provenance"] == "inferred"] + \
               [f"{_label(g, e['from'])} -> {_label(g, e['to'])}" for e in g["edges"] if e["provenance"] == "inferred"]
    if inferred:
        lines.append("Inferred, not shown in the source: " + "; ".join(inferred))
    unresolved = [n["label"] for n in g["nodes"] if n["provenance"] == "unresolved"] + \
                 [f"{_label(g, e['from'])} -> {_label(g, e['to'])}" for e in g["edges"]
                  if e["provenance"] == "unresolved" or e["kind"] == "unknown"]
    if unresolved:
        lines.append("Unclear: " + "; ".join(unresolved))
    for u in g["unknowns"]:
        lines.append("Not stated: " + u)
    return lines


# --- corrections ------------------------------------------------------------

_EDGE_FIELDS = ("kind", "channel", "route")


def apply_ops(graph: dict, ops: list) -> tuple[dict, list[str]]:
    """Apply structured edits to a COPY, in order, all or nothing.

    Ops: set_node {id, label?, role?}; add_edge {from, to, kind, channel?,
    route?}; set_edge {id, kind?, channel?, route?}; remove_edge {id}.
    Touched items become user_confirmed. Returns (new graph, what changed in
    words); raises RigGraphError on the first bad op or an invalid result,
    and the caller's graph is never modified."""
    g = load(graph)
    changed: list[str] = []
    if not isinstance(ops, list) or not ops:
        raise RigGraphError("no edits were understood")
    for i, op in enumerate(ops, 1):
        if not isinstance(op, dict):
            raise RigGraphError(f"edit {i} is not an object")
        kind = op.get("op")
        if kind == "set_node":
            n = next((n for n in g["nodes"] if n["id"] == op.get("id")), None)
            if n is None:
                raise RigGraphError(f"edit {i}: there is no node {op.get('id')!r}")
            if "role" in op and op["role"] not in ROLES:
                raise RigGraphError(f"edit {i}: {op['role']!r} is not a role")
            if "label" in op and not (isinstance(op["label"], str) and op["label"].strip()):
                raise RigGraphError(f"edit {i}: a node needs a name")
            for f in ("label", "role"):
                if f in op:
                    n[f] = op[f]
            n["provenance"] = "user_confirmed"
            changed.append(f"{n['label']} updated")
        elif kind == "add_edge":
            ids = {x["id"] for x in g["nodes"]}
            for end in ("from", "to"):
                if op.get(end) not in ids:
                    raise RigGraphError(f"edit {i}: there is no node {op.get(end)!r}")
            if op.get("kind") not in EDGE_KINDS:
                raise RigGraphError(f"edit {i}: {op.get('kind')!r} is not a kind of connection")
            e = {k: op[k] for k in ("from", "to", "kind", "channel", "route") if op.get(k) is not None}
            e["provenance"] = "user_confirmed"
            g["edges"].append(e)
            g = normalize(g)
            changed.append(f"connected {_label(g, e.get('from'))} -> {_label(g, e.get('to'))} ({e.get('kind')})")
        elif kind == "set_edge":
            e = next((e for e in g["edges"] if e["id"] == op.get("id")), None)
            if e is None:
                raise RigGraphError(f"edit {i}: there is no connection {op.get('id')!r}")
            if "kind" in op and op["kind"] not in EDGE_KINDS:
                raise RigGraphError(f"edit {i}: {op['kind']!r} is not a kind of connection")
            for f in _EDGE_FIELDS:
                if f in op:
                    if op[f] is None:
                        e.pop(f, None)       # only channel and route can be cleared
                    else:
                        e[f] = op[f]
            e["provenance"] = "user_confirmed"
            changed.append(f"{_label(g, e['from'])} -> {_label(g, e['to'])} is now {e['kind']}"
                           + (f" ({e['channel']})" if e.get("channel") else ""))
        elif kind == "remove_edge":
            e = next((e for e in g["edges"] if e["id"] == op.get("id")), None)
            if e is None:
                raise RigGraphError(f"edit {i}: there is no connection {op.get('id')!r}")
            g["edges"].remove(e)
            changed.append(f"removed {_label(g, e['from'])} -> {_label(g, e['to'])}")
        else:
            raise RigGraphError(f"edit {i}: {kind!r} is not an edit this understands")
    problems = validate(normalize(g))
    if problems:
        raise RigGraphError("that would leave the rig invalid: " + "; ".join(problems))
    return normalize(g), changed

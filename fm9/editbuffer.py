"""Undo, and A/B: the two things that make a tone tool safe to play with.

Every plugin a guitarist has ever used has A/B compare. The FM9 does not, and
until now neither did this. That absence shapes behaviour: a change you cannot
take back is a change you think twice about, so the tool got used timidly, for
edits people were already sure of. The interesting prompts are the ones you
are NOT sure of.

WHAT A SNAPSHOT IS
------------------
A read of the whole edit buffer: every block's bypass state, selected channel,
and complete parameter dump across all its channels. On the connected FM9 that
is fourteen bulk reads and about a quarter of a second, and it is SILENT. No
scene changes, no writes, nothing audible. That is what makes it affordable to
take one automatically before every transmit, which is what makes undo always
available rather than something you had to remember to arm.

Contrast with fm9/health.py, where reading a scene means standing in it. The
difference is worth internalising: reads of the loaded state are free, reads
that require changing the loaded state are not.

WHAT A RESTORE IS
-----------------
A diff, not a replay. Comparing two snapshots gives the handful of parameters
that actually differ, and only those are written back. Writing all 3000 values
in the buffer would take minutes, would put thousands of messages on the wire,
and would touch parameters nothing had changed, which is a large blast radius
for an operation whose entire purpose is to be safe.

Each write goes through the device's verified path and is read back. A restore
that could not put something back says so and names it, because "undone" is a
claim about the rig, not about our intentions.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
Nothing here writes to a preset slot. Snapshots live in memory for the life of
the server process and are lost on restart, which is correct: an undo history
that outlives the session would be offering to revert a rig it has not looked
at since. The edit buffer is the scope, exactly as everywhere else in this
tool.

It also refuses to restore into a different preset than it captured. The block
layout, the channel assignments and the parameter meanings are all
preset-specific, so a snapshot applied to the wrong preset is not an undo, it
is a corruption with a reassuring name.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Change:
    """One parameter that differs between two snapshots."""
    effect_id: int
    family: str
    instance: int
    channel: int          # which channel the value lives on
    param_id: int
    label: str
    frm: float | None     # display units, for saying what will happen
    to: float | None
    #: The exact values. Restores write these, never the display numbers: a
    #: cab slot is an ordinal stored raw in the wire, so a display round trip
    #: turned cab 105 into cab 1 and an undo loaded the wrong cabinet.
    frm_wire: int = 0
    to_wire: int = 0


@dataclass
class Restore:
    """What a restore actually managed to do."""
    applied: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    #: Params the device read back at its own value even after a retry, because
    #: it normalizes them in the target's context (a cab cut slope when the cut
    #: is off, say). Not a failure of the copy: the device chose to keep them.
    normalized: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def _stride(values: list[int], channels: int) -> int:
    """Parameter block length for one channel.

    bulk_read returns every channel's values concatenated, so index
    `channel * stride + param_id` addresses one parameter on one channel.
    """
    return len(values) // channels if channels > 1 else len(values)


def capture(fm9, reg) -> dict:
    """Read the whole edit buffer. Silent, and cheap enough to do often."""
    preset = fm9.current_preset()
    scene = fm9.scene_name()
    blocks = []
    for b in fm9.status_dump() or []:
        fam = reg.family_of_effect_id(b.effect_id)
        if not fam:
            continue
        values = fm9.bulk_read(b.effect_id)
        blocks.append({
            "effect_id": b.effect_id,
            "family": fam[0],
            "instance": fam[1],
            "bypassed": bool(b.bypassed),
            "channel": int(b.channel),
            "channels": max(1, fm9._channels.get(b.effect_id, 1)),
            "values": values or [],
        })
    return {
        "preset": preset[0] if preset else None,
        "preset_name": preset[1] if preset else None,
        "scene": scene[0] if scene else None,
        "blocks": blocks,
    }


def _display(reg, family, instance, param_id, wire):
    """(display value, spec). The display half may be None; the spec must not.

    An uncalibrated parameter has no number worth showing a human, but it is
    still perfectly restorable, because a restore writes the raw wire value.
    Returning no spec for those would have made them silently unrestorable
    while the summary looked complete.
    """
    try:
        spec = reg.spec(family, param_id, instance)
    except Exception:
        return None, None
    if spec is None or spec.dmin is None:
        return None, spec
    from fm9.protocol import normalized_to_display
    return round(normalized_to_display(
        wire / 65534, spec.dmin, spec.dmax, spec.scale), 2), spec


def diff(reg, frm: dict, to: dict) -> dict:
    """What changed between two snapshots.

    Returns parameter changes plus bypass and channel changes, which are
    stored per scene rather than per channel and so are listed separately.
    """
    params: list[Change] = []
    switches: list[str] = []
    by_eid = {b["effect_id"]: b for b in to["blocks"]}
    for a in frm["blocks"]:
        b = by_eid.get(a["effect_id"])
        if b is None:
            continue
        if a["bypassed"] != b["bypassed"]:
            switches.append(f"{a['family']} {a['instance']}: "
                            f"{'bypassed' if b['bypassed'] else 'engaged'} "
                            f"-> {'bypassed' if a['bypassed'] else 'engaged'}")
        if a["channel"] != b["channel"]:
            switches.append(f"{a['family']} {a['instance']}: channel "
                            f"{'ABCD'[b['channel']]} -> {'ABCD'[a['channel']]}")
        av, bv = a["values"], b["values"]
        if not av or len(av) != len(bv):
            continue
        chans = a["channels"]
        stride = _stride(av, chans)
        for i, (x, y) in enumerate(zip(av, bv)):
            if x == y:
                continue
            ch, pid = (i // stride, i % stride) if stride else (0, i)
            old, spec = _display(reg, a["family"], a["instance"], pid, x)
            new, _ = _display(reg, a["family"], a["instance"], pid, y)
            params.append(Change(
                effect_id=a["effect_id"], family=a["family"],
                instance=a["instance"], channel=ch, param_id=pid,
                label=(spec.label if spec is not None and spec.label
                       else f"param {pid}"),
                frm=old, to=new, frm_wire=x, to_wire=y))
    return {"params": params, "switches": switches}


def restore(fm9, reg, snap: dict) -> Restore:
    """Put the edit buffer back the way the snapshot found it.

    Writes only what differs. Raises if the loaded preset is not the one the
    snapshot came from, because applying it anywhere else is not an undo.
    """
    now = capture(fm9, reg)
    if snap.get("preset") != now.get("preset"):
        raise ValueError(
            f"snapshot is of preset {snap.get('preset')} but "
            f"{now.get('preset')} is loaded; refusing to restore across presets")

    out = Restore()
    d = diff(reg, snap, now)
    by_eid = {b["effect_id"]: b for b in now["blocks"]}
    # Track channel positions rather than re-reading them between writes. The
    # device applies writes asynchronously and a read fired inside that window
    # returns the PRE-write state, which the simulator models faithfully. So a
    # status dump taken right after set_channel would report where the block
    # used to be, and we would move it back to the wrong place.
    where = {eid: b["channel"] for eid, b in by_eid.items()}

    # Parameters first, grouped by block so a block whose values live on a
    # non-active channel is switched there once rather than once per value.
    from itertools import groupby
    changes = sorted(d["params"], key=lambda c: (c.effect_id, c.channel))
    for (eid, ch), group in groupby(changes, key=lambda c: (c.effect_id, c.channel)):
        group = list(group)
        if where.get(eid) != ch:
            fm9.set_channel(eid, ch)
            where[eid] = ch
        for c in group:
            try:
                spec = reg.spec(c.family, c.param_id, c.instance)
            except Exception:
                spec = None
            if spec is None:
                # Nothing to address the parameter with. Saying nothing here
                # would let a restore report success over a value it never
                # touched.
                out.failed.append(f"{c.family} {c.instance} {c.label}: "
                                  f"not in the registry, left as it is")
                continue
            # The exact wire value, not the display number. A calibrated
            # parameter round trips either way; an ordinal does not.
            res = fm9.set_param_wire(spec, c.frm_wire)
            if getattr(res, "ok", False):
                shown = c.frm if c.frm is not None else c.frm_wire
                out.applied.append(f"{c.family} {c.instance} {c.label} -> {shown}")
            else:
                out.failed.append(f"{c.family} {c.instance} {c.label}: "
                                  f"{getattr(res, 'detail', 'write not verified')}")

    # Then bypass and channel, which are what the scene itself stores. Channel
    # goes last for each block so the parameter writes above land where they
    # were read from before the block is moved back.
    for a in snap["blocks"]:
        b = by_eid.get(a["effect_id"])
        if b is None:
            continue
        if a["bypassed"] != b["bypassed"]:
            fm9.set_bypass(a["effect_id"], a["bypassed"])
            out.applied.append(f"{a['family']} {a['instance']}: "
                               f"{'bypassed' if a['bypassed'] else 'engaged'}")
        if where.get(a["effect_id"]) != a["channel"]:
            fm9.set_channel(a["effect_id"], a["channel"])
            where[a["effect_id"]] = a["channel"]
            out.applied.append(f"{a['family']} {a['instance']}: "
                               f"channel {'ABCD'[a['channel']]}")
    return out


def transplant(fm9, reg, source_snap: dict, families) -> Restore:
    """Copy the given effect families (e.g. {"DELAY", "REVERB"}) from a snapshot
    of ANOTHER preset onto the current edit buffer.

    This is the deliberate cross-preset copy behind "make the delay like that
    tone's": unlike restore it does NOT refuse a preset mismatch, since copying
    across presets is the whole point. It writes the source's exact wire values
    and bypass state for the named blocks onto the matching blocks here. A block
    the current preset does not have is reported, not invented, and the signal
    chain ORDER is left alone; only each block's settings are copied.
    """
    fams = {str(f).upper() for f in families}
    now = capture(fm9, reg)
    now_by = {b["effect_id"]: b for b in now["blocks"]}
    out = Restore()

    # diff(source, now): each Change carries the SOURCE value in frm_wire, so
    # writing frm_wire makes this buffer match the source. Keep only the named
    # families, and only where a matching block exists here to write onto.
    d = diff(reg, source_snap, now)
    changes = [c for c in d["params"]
               if c.family in fams and c.effect_id in now_by]
    where = {eid: b["channel"] for eid, b in now_by.items()}
    from itertools import groupby
    changes.sort(key=lambda c: (c.effect_id, c.channel))
    for (eid, ch), group in groupby(changes, key=lambda c: (c.effect_id, c.channel)):
        group = list(group)
        if where.get(eid) != ch:
            fm9.set_channel(eid, ch)
            where[eid] = ch
        for c in group:
            try:
                spec = reg.spec(c.family, c.param_id, c.instance)
            except Exception:
                spec = None
            if spec is None:
                out.failed.append(f"{c.family} {c.instance} {c.label}: "
                                  f"not in the registry, left as it is")
                continue
            res = fm9.set_param_wire(spec, c.frm_wire)
            if not getattr(res, "ok", False):
                # A settle-window read can miss a write that took; try once more
                # past it before judging. What survives a retry is the device
                # holding its own value, not a flaky write.
                import time as _t
                _t.sleep(0.1)
                res = fm9.set_param_wire(spec, c.frm_wire)
            if getattr(res, "ok", False):
                shown = c.frm if c.frm is not None else c.frm_wire
                out.applied.append(f"{c.family} {c.instance} {c.label} -> {shown}")
            else:
                out.normalized.append(
                    f"{c.family} {c.instance} {c.label}: device kept its own "
                    f"value ({getattr(res, 'detail', 'read-back mismatch')})")

    # Match the source's bypass for each copied block, so a delay the source
    # runs engaged comes across engaged.
    for sb in source_snap["blocks"]:
        if sb["family"] not in fams:
            continue
        tb = now_by.get(sb["effect_id"])
        if tb is None:
            out.failed.append(f"{sb['family']} {sb['instance']}: not present in "
                              "the current preset, so there is nothing to copy "
                              "it onto (add the block first)")
            continue
        if sb["bypassed"] != tb["bypassed"]:
            fm9.set_bypass(sb["effect_id"], sb["bypassed"])
            out.applied.append(f"{sb['family']} {sb['instance']}: "
                               f"{'bypassed' if sb['bypassed'] else 'engaged'}")
    return out


def _scene_state(fm9, eids):
    """Per scene 1-8, {effect_id: (channel, bypassed)} for the given blocks. A
    scene sweep (audible); returns to the scene it started on."""
    here = fm9.scene_name()
    active = here[0] if here else 1
    out = {}
    try:
        for sc in range(1, 9):
            fm9.set_scene(sc)
            out[sc] = {b.effect_id: (int(b.channel), bool(b.bypassed))
                       for b in (fm9.status_dump() or []) if b.effect_id in eids}
    finally:
        fm9.set_scene(active)
    return out


def read_scene_state(fm9, reg, families):
    """Read the CURRENTLY LOADED preset's per-scene channel/bypass and its
    all-channel param values for the named families. The caller loads the
    source preset first: editbuffer never switches presets itself, that stays
    in the orchestration layer as everywhere here. Returns (scene_state, vals)
    to hand to transplant_by_scene."""
    fams = {str(f).upper() for f in families}
    eids = set()
    for f in fams:
        try:
            eids.add(reg.effect_id(f, 1))
        except Exception:
            pass
    scene_state = _scene_state(fm9, eids)
    snap = capture(fm9, reg)
    vals = {b["effect_id"]: (b["values"], b["channels"])
            for b in snap["blocks"] if b["effect_id"] in eids}
    return scene_state, vals


def transplant_by_scene(fm9, reg, src_scene_state, src_vals) -> Restore:
    """Scene-aware copy onto the CURRENTLY LOADED target: what an effect did on
    the SOURCE's scene N lands on the TARGET's scene N, on whatever channel each
    maps that scene to.

    The channel-faithful transplant() is scene-blind: two presets map scenes to
    channels differently, so a channel-for-channel copy puts an effect on the
    wrong scene (#48). The caller reads the source with read_scene_state, loads
    the target, and calls this; it sweeps the TARGET's scenes and, for each,
    writes the source's per-scene params and bypass onto the target's per-scene
    channel. Sweeps the loaded target (audible), leaves it on the scene it
    started on, and never switches presets.
    """
    out = Restore()
    eids = set(src_vals)
    tgt_state = _scene_state(fm9, eids)
    src_state = src_scene_state

    here = fm9.scene_name()
    active = here[0] if here else 1
    for sc in range(1, 9):
        for eid in eids:
            if eid not in src_state.get(sc, {}) or eid not in tgt_state.get(sc, {}):
                continue
            src_ch, src_byp = src_state[sc][eid]
            tgt_ch, _ = tgt_state[sc][eid]
            vals, chans = src_vals.get(eid, (None, None))
            if not vals:
                continue
            stride = _stride(vals, chans)
            src_params = vals[src_ch * stride:(src_ch + 1) * stride]
            fam = reg.family_of_effect_id(eid)
            if not fam:
                continue
            family, inst = fam
            fm9.set_scene(sc)
            fm9.set_channel(eid, tgt_ch)
            for pid, wire in enumerate(src_params):
                try:
                    spec = reg.spec(family, pid, inst)
                except Exception:
                    spec = None
                if spec is None:
                    continue
                res = fm9.set_param_wire(spec, wire)
                if not getattr(res, "ok", False):
                    import time as _t
                    _t.sleep(0.1)
                    res = fm9.set_param_wire(spec, wire)
                if getattr(res, "ok", False):
                    out.applied.append(f"scene {sc} {family} {inst} param {pid}")
                else:
                    out.normalized.append(f"scene {sc} {family} {inst} param {pid}: "
                                          "device kept its own value")
            fm9.set_bypass(eid, src_byp)
            out.applied.append(f"scene {sc} {family} {inst}: "
                               f"{'bypassed' if src_byp else 'engaged'}")
    fm9.set_scene(active)
    return out


def summarise(d: dict, limit: int = 6) -> str:
    """One line saying what a restore would do, for a button that needs to be
    honest about its blast radius before it is pressed."""
    bits = [f"{c.family} {c.instance} {c.label} {c.to} -> {c.frm}"
            for c in d["params"][:limit]]
    bits += d["switches"][:max(0, limit - len(bits))]
    total = len(d["params"]) + len(d["switches"])
    if not total:
        return "nothing to undo: the buffer matches the snapshot"
    more = total - len(bits)
    return "; ".join(bits) + (f"; and {more} more" if more > 0 else "")

"""Pre-ship tone review: the deterministic half of the rulebook.

config/tone_rules.md is the spec the planner READS; this is the check that runs
on the RESULT, so the hard rules hold whether or not the planner followed the
prose. It is the code form of the rulebook's rule 14 self-check, aimed at the
failures that shipped in real builds (2026-09-04): cleans cut quiet, cleans with
no wet effects, and leads that do not out-saturate the rhythm so they sound
clean.

Deliberately pure and source-agnostic. It takes a per-scene summary - role plus
the few numbers a check needs - and returns findings. The summary can be built
from a plan's actions before sending (summary_from_plan) or read off the hardware
after applying; the checker does not care which, which is what makes it testable
without an FM9.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

#: Numeric floors per role, so "generous mix" is arithmetic rather than taste.
#: See config/tone_targets.json for why each number is what it is.
TARGETS_PATH = Path(__file__).resolve().parent.parent / "config" / "tone_targets.json"


def targets() -> dict:
    """The numeric policy, or an empty one if it is missing or unreadable.

    Absent targets mean the depth checks simply do not run, exactly as before
    they existed. A missing policy file must never take a build down.
    """
    try:
        return json.loads(TARGETS_PATH.read_text())
    except (OSError, ValueError):
        return {}


@dataclass
class Scene:
    """The little that a role check needs to know about one scene."""
    n: int
    name: str = ""
    role: str | None = None            # clean | rhythm | lead | None
    amp_gain: float | None = None      # DISTORT_DRIVE
    amp_level: float | None = None     # DISTORT_LEVEL
    scene_level: float | None = None   # OUTPUT_SCENEn
    effects: set[str] = field(default_factory=set)  # engaged families: DELAY, REVERB, ...
    boosted: bool = False              # a drive/boost engaged in front
    #: family -> mix/depth percent, when the plan sets one. Engagement alone was
    #: never enough: issue #50 shipped a "lush" clean with reverb at 12 percent,
    #: which passed an is-it-on check and was nearly dry.
    fx_mix: dict = field(default_factory=dict)
    boost_gain: float | None = None    # FUZZ_DRIVE, to catch a boost dialled
                                       # BELOW the rhythm it is meant to push
    #: block -> channel (0-3) and block -> bypassed, as the PLAN sets them.
    #: FM9 parameters live on the CHANNEL, not the scene, so what a scene
    #: actually stores is which blocks are bypassed and which channel each one
    #: is on. That makes these two the whole identity of a scene, which is why
    #: health.py can spot a duplicate after apply without reading a single
    #: parameter. Issue #51: the plan-time review threw them away, so a scene
    #: configured purely by set_channel was invisible here.
    channels: dict = field(default_factory=dict)
    bypass: dict = field(default_factory=dict)

    def shape(self) -> tuple:
        """What this scene stores, and therefore what makes it itself.

        The plan-time twin of health._fingerprint. Empty when the plan says
        nothing structural about the scene, which is not the same as two
        scenes matching, and callers must not treat it as such.
        """
        return tuple(sorted(
            (b, bool(self.bypass.get(b)), self.channels.get(b))
            for b in set(self.channels) | set(self.bypass)))


@dataclass
class Finding:
    scene: int
    rule: str
    severity: str                       # "fail" (violates a hard rule) | "warn"
    message: str


def infer_role(name: str) -> str | None:
    """A scene's role from its name. None when it cannot be told, so a check is
    skipped rather than guessed."""
    n = (name or "").lower()
    if any(w in n for w in ("lead", "solo")):
        return "lead"
    if "clean" in n:
        return "clean"
    if any(w in n for w in ("rhythm", "crunch", "chug", "rhy")):
        return "rhythm"
    return None


def clones(scenes: list[Scene]) -> list[Finding]:
    """Rule 15: two scenes the plan makes structurally identical.

    Issue #51. A clone is a footswitch that does nothing on stage. health.py
    already catches it AFTER apply, from the same fact: FM9 parameters live on
    the CHANNEL, not the scene, so a scene's whole identity is which blocks are
    bypassed and which channel each one is on. Observed 2026-09-05 on a fresh
    80s build, the plan-time review passed clean and the post-apply scan then
    found scenes 4 and 8 identical, and after that 1 and 7.

    WHAT THIS CAN AND CANNOT CONCLUDE. A plan is a delta, so this sees only
    what the plan states, never the state a scene inherits. The finding is
    therefore worded as a fact about the PLAN, which is always true, rather
    than a prediction about the preset, which would not be. On a from-scratch
    build the two coincide, because a new preset's scenes all start identical,
    and that is exactly the case this was written for.

    A scene the plan says nothing structural about has an empty shape. Empty
    shapes are excluded rather than grouped: "the plan does not touch these
    two" is not evidence that they are the same, and treating it as a match
    would fire on every delta plan that renames a couple of scenes.
    """
    out: list[Finding] = []
    groups: dict[tuple, list[Scene]] = {}
    for s in scenes:
        shape = s.shape()
        if shape:
            groups.setdefault(shape, []).append(s)
    for members in groups.values():
        # Grouped, not pairwise, the same way health.py reports it: four
        # identical scenes are one problem, not six findings burying the rest.
        if len(members) < 2:
            continue
        nums = ", ".join(str(m.n) for m in members)
        for m in members[1:]:
            out.append(Finding(
                m.n, "15", "warn",
                f"scenes {nums} get the same blocks, bypass states and "
                f"channels from this plan; parameters live on the channel, so "
                f"nothing here makes scene {m.n} a different sound from scene "
                f"{members[0].n}, and its footswitch would do nothing"))
    return out


def review(scenes: list[Scene]) -> list[Finding]:
    """Run the deterministic role checks and return what failed, worst first.

    The rhythm scenes are the reference the others are judged against (rule 4:
    rhythm is the loudness reference; rule 10: a lead out-saturates the rhythm).
    """
    out: list[Finding] = list(clones(scenes))

    def avg(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    rhythm_gain = avg([s.amp_gain for s in scenes if s.role == "rhythm"])
    rhythm_level = avg([s.amp_level for s in scenes if s.role == "rhythm"])
    rhythm_boost = avg([s.boost_gain for s in scenes if s.role == "rhythm"])

    for s in scenes:
        fx = s.effects or set()
        if s.role == "clean":
            # rule 8: a clean is always wet - delay AND reverb at minimum
            missing = [e for e in ("DELAY", "REVERB") if e not in fx]
            if missing:
                out.append(Finding(s.n, "8", "fail",
                    f"clean scene has no {' or '.join(m.lower() for m in missing)}; "
                    "a big/80s clean needs delay + reverb"))
            # rule 8 / rule 4: a clean must not sit under its own rhythm.
            #
            # Judged RELATIONALLY, against this preset's own gain staging.
            # An absolute floor here used to fail every professional clean
            # (issue #65): AustinBuddy's sit at a median of -8.11 dB, which an
            # "at or below -4 is cut quiet" rule rejects outright. The absolute
            # value carries no information because DISTORT_LEVEL is an output
            # trim, and a harder-driven scene reads quieter by it.
            #
            # The relation does carry information, and separates the two cases
            # cleanly. The build that shipped wrong had a clean 6 dB BELOW its
            # rhythm; the professional presets put the clean roughly 1.5 dB
            # ABOVE theirs. Same absolute level, opposite verdicts.
            if s.amp_level is not None and rhythm_level is not None \
                    and s.amp_level < rhythm_level - 2:
                out.append(Finding(s.n, "8", "fail",
                    f"clean sits {rhythm_level - s.amp_level:.0f} dB below the "
                    "rhythm; a clean amp makes little output, so its level "
                    "belongs at or above the rhythm's, not under it"))
        elif s.role == "lead":
            # rule 10: audibly MORE saturated than the rhythm, not a hair more.
            # The rulebook's own example calls gain 7.8 over a 6.8 rhythm (+1.0)
            # too little for a lead, so the bar is a clear margin, ~+1.5.
            if s.amp_gain is not None and rhythm_gain is not None \
                    and s.amp_gain < rhythm_gain + 1.5:
                # A warning, not a failure. The tendency is real but not a law:
                # 5 of 13 professional presets miss this margin and two run the
                # lead BELOW the rhythm outright (issue #65), so blocking on it
                # rejects work that gigs.
                out.append(Finding(s.n, "10", "warn",
                    f"lead gain {s.amp_gain:g} is not clearly above the rhythm "
                    f"({rhythm_gain:g}); usually a lead out-saturates the "
                    "rhythm, though professional presets do vary"))
            # rule 4 hard cap: a lead more than ~4 dB over the rhythm
            if s.amp_level is not None and rhythm_level is not None \
                    and s.amp_level > rhythm_level + 4:
                out.append(Finding(s.n, "4", "warn",
                    f"lead sits {s.amp_level - rhythm_level:.0f} dB over the rhythm; "
                    "the cap is about +4, trim its level"))

    # Issue #50: an attempt to add absolute parameter floors here was tested
    # against 104 scenes of professionally voiced presets and refuted. It
    # raised 196 failures against gig-ready work, because DISTORT_LEVEL is an
    # output trim rather than loudness and a harder-driven scene reads quieter
    # by it. config/tone_targets.json records the measurements. The relational
    # lead-versus-rhythm idea already exists as rule 10 above, so nothing from
    # that attempt survives here.

    # whole-build: nothing inaudibly quiet (rule 4)
    for s in scenes:
        if s.amp_level is not None and s.amp_level <= -12:
            out.append(Finding(s.n, "4", "warn",
                f"amp level {s.amp_level:g} dB is very low; check it is not inaudible"))

    order = {"fail": 0, "warn": 1}
    out.sort(key=lambda f: (order.get(f.severity, 2), f.scene))
    return out


# Effect families that count as "engaged wet/boost" when their block is on.
_WET = {"DELAY", "REVERB", "CHORUS", "FLANGER", "PHASER", "MULTITAP"}
_BOOST = {"FUZZ", "DRIVE"}


def summary_from_plan(actions: list[dict], reg=None) -> list[Scene]:
    """Best-effort per-scene summary from a plan's actions, for a check BEFORE
    anything is sent. A plan is a delta, so params it does not set are unknown
    (None) and their checks are simply skipped; the hardware-read summary after
    apply is the authoritative one. Actions are attributed to the scene active
    when they run (set_scene switches it), which is how a fresh build writes.
    """
    scenes: dict[int, Scene] = {}

    def scn(n: int) -> Scene:
        return scenes.setdefault(n, Scene(n=n))

    cur = None
    for a in actions:
        kind = a.get("kind")
        if kind == "set_scene":
            v = a.get("value")
            cur = int(v) if v is not None else cur
            continue
        if kind == "rename_scene":
            v = a.get("value")
            if v is not None:
                s = scn(int(v))
                s.name = a.get("type_name") or s.name
                s.role = infer_role(s.name)
            continue
        block = (a.get("block") or "").lower()
        if kind == "set_param" and cur is not None:
            p = (a.get("param") or "").upper()
            val = a.get("value")
            if p == "DISTORT_DRIVE":
                scn(cur).amp_gain = val
            elif p == "DISTORT_LEVEL":
                scn(cur).amp_level = val
            elif p == "FUZZ_DRIVE":
                scn(cur).boost_gain = val
            elif p.endswith("_MIX") or p.endswith("_DEPTH"):
                fam = p.rsplit("_", 1)[0]
                # Depth is what makes an effect audible. A plan that engages
                # reverb and leaves it at 12 percent has not made a lush clean.
                if val is not None:
                    scn(cur).fx_mix[fam] = val
            elif p.startswith("OUTPUT_SCENE"):
                tail = p.replace("OUTPUT_SCENE", "")
                if tail.isdigit():
                    scn(int(tail)).scene_level = val
        elif kind == "set_bypass" and cur is not None:
            # Record the structural fact FIRST, for both directions. Only
            # engagement used to be kept, so a scene that differs from another
            # solely by what it BYPASSES read as identical to it.
            scn(cur).bypass[block] = bool(a.get("bypassed"))
            if a.get("bypassed") is False:
                fam = block.upper()
                # normalise a couple of friendly names
                fam = {"AMP": "DISTORT", "DRIVE": "FUZZ"}.get(fam, fam)
                if fam in _WET:
                    scn(cur).effects.add(fam)
                if fam in _BOOST:
                    scn(cur).boosted = True
        elif kind == "set_channel" and cur is not None:
            # The action that was dropped entirely. A scene voiced purely by
            # pointing blocks at already-voiced channels sets no parameters,
            # so it created no Scene at all and every check skipped it.
            v = a.get("value")
            if v is not None:
                scn(cur).channels[block] = int(v)

    # fill roles for any scene named but not yet role'd
    for s in scenes.values():
        if s.role is None and s.name:
            s.role = infer_role(s.name)
    return [scenes[k] for k in sorted(scenes)]


def coverage(scenes: list[Scene]) -> dict:
    """What could actually be checked, so an empty result cannot pose as a pass.

    Issue #54: a plan is a delta, so any parameter it does not set is unknown
    and its check is skipped. That made one green result mean three different
    things at once: nothing was wrong, nothing could be checked, or the scene
    roles could not be inferred. The player could not tell which, and the
    dangerous one looked exactly like the safe one.

    Status is the honest summary of the whole review:
      verified        at least one check ran and had the facts it needed
      unknown         nothing could be checked
      not_applicable  there are no scenes to check
    """
    checks = {
        "role": lambda s: s.role is not None,
        "gain": lambda s: s.amp_gain is not None,
        "level": lambda s: s.amp_level is not None,
        "scene_level": lambda s: s.scene_level is not None,
        "effects": lambda s: bool(s.effects),
    }
    observed, missing = {}, {}
    for name, has in checks.items():
        seen = [s.n for s in scenes if has(s)]
        observed[name] = seen
        absent = [s.n for s in scenes if not has(s)]
        if absent:
            missing[name] = absent

    roles = [s.n for s in scenes if s.role]
    ran = sum(1 for name in checks if observed[name])
    # A role on its own is not a check, it is the precondition for one. Counting
    # it as coverage let a scene with a known role and no values at all report
    # "verified", which is precisely the overstatement this function exists to
    # prevent. At least one VALUE must have been observed.
    value_checks = [n for n in checks if n != "role" and observed[n]]
    if not scenes:
        status = "not_applicable"
    elif not roles or not value_checks:
        # No role means no role check can run, whatever else is known; no value
        # means there was nothing to judge that role against.
        status = "unknown"
    else:
        status = "verified"
    return {
        "status": status,
        "scenes": [s.n for s in scenes],
        "scenes_checked": roles,
        "roles_unknown": [s.n for s in scenes if not s.role],
        "checks_run": ran,
        "checks_possible": len(checks),
        "observed": observed,
        "missing": missing,
        "why": ("no scenes in this plan" if not scenes else
                "no scene role could be inferred, so no role check could run"
                if not roles else
                "the scene roles are known but no parameter value was, so "
                "there was nothing to judge them against"
                if not value_checks else
                f"{ran} of {len(checks)} checks had the facts they needed"),
    }


def findings_as_dicts(findings: list[Finding]) -> list[dict]:
    return [{"scene": f.scene, "rule": f.rule, "severity": f.severity,
             "message": f.message} for f in findings]

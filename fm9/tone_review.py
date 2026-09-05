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

from dataclasses import dataclass, field


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


def review(scenes: list[Scene]) -> list[Finding]:
    """Run the deterministic role checks and return what failed, worst first.

    The rhythm scenes are the reference the others are judged against (rule 4:
    rhythm is the loudness reference; rule 10: a lead out-saturates the rhythm).
    """
    out: list[Finding] = []

    def avg(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    rhythm_gain = avg([s.amp_gain for s in scenes if s.role == "rhythm"])
    rhythm_level = avg([s.amp_level for s in scenes if s.role == "rhythm"])

    for s in scenes:
        fx = s.effects or set()
        if s.role == "clean":
            # rule 8: a clean is always wet - delay AND reverb at minimum
            missing = [e for e in ("DELAY", "REVERB") if e not in fx]
            if missing:
                out.append(Finding(s.n, "8", "fail",
                    f"clean scene has no {' or '.join(m.lower() for m in missing)}; "
                    "a big/80s clean needs delay + reverb"))
            # rule 8 / rule 4: cleans go up near 0, never cut quiet
            if s.amp_level is not None:
                if s.amp_level <= -4:
                    out.append(Finding(s.n, "8", "fail",
                        f"clean amp level {s.amp_level:g} dB is cut quiet; a clean "
                        "amp makes little output, so its level goes up near 0"))
                elif rhythm_level is not None and s.amp_level < rhythm_level - 2:
                    out.append(Finding(s.n, "4", "warn",
                        f"clean sits {rhythm_level - s.amp_level:.0f} dB below the "
                        "rhythm; cleans should match the rhythm, not sit under it"))
        elif s.role == "lead":
            # rule 10: audibly MORE saturated than the rhythm, not a hair more.
            # The rulebook's own example calls gain 7.8 over a 6.8 rhythm (+1.0)
            # too little for a lead, so the bar is a clear margin, ~+1.5.
            if s.amp_gain is not None and rhythm_gain is not None \
                    and s.amp_gain < rhythm_gain + 1.5:
                out.append(Finding(s.n, "10", "fail",
                    f"lead gain {s.amp_gain:g} is not clearly above the rhythm "
                    f"({rhythm_gain:g}); a lead must out-saturate the rhythm or it "
                    "reads as clean/crunch"))
            # rule 4 hard cap: a lead more than ~4 dB over the rhythm
            if s.amp_level is not None and rhythm_level is not None \
                    and s.amp_level > rhythm_level + 4:
                out.append(Finding(s.n, "4", "warn",
                    f"lead sits {s.amp_level - rhythm_level:.0f} dB over the rhythm; "
                    "the cap is about +4, trim its level"))

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
            elif p.startswith("OUTPUT_SCENE"):
                tail = p.replace("OUTPUT_SCENE", "")
                if tail.isdigit():
                    scn(int(tail)).scene_level = val
        elif kind == "set_bypass" and cur is not None and a.get("bypassed") is False:
            fam = block.upper()
            # normalise a couple of friendly names
            fam = {"AMP": "DISTORT", "DRIVE": "FUZZ"}.get(fam, fam)
            if fam in _WET:
                scn(cur).effects.add(fam)
            if fam in _BOOST:
                scn(cur).boosted = True

    # fill roles for any scene named but not yet role'd
    for s in scenes.values():
        if s.role is None and s.name:
            s.role = infer_role(s.name)
    return [scenes[k] for k in sorted(scenes)]


def findings_as_dicts(findings: list[Finding]) -> list[dict]:
    return [{"scene": f.scene, "rule": f.rule, "severity": f.severity,
             "message": f.message} for f in findings]

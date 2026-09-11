#!/usr/bin/env python3
"""Replay a tone recipe: validate, then optionally apply. See docs/RECIPES.md.

    python tools/replay_recipe.py recipes/x.json           # dry-run
    python tools/replay_recipe.py recipes/x.json --apply   # edit buffer only
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fm9 import nam_captures  # noqa: E402
from fm9 import recipes as recipebook  # noqa: E402

FORBIDDEN = {"store"}

def main(path: str, apply: bool) -> int:
    rec = json.loads(Path(path).read_text())
    assert rec.get("recipe_version") == 1, "unknown recipe version"
    steps = recipebook.steps_of(rec)
    bad = [a for a in steps if a.get("kind") in FORBIDDEN]
    if bad:
        print("REFUSED: recipes may not contain store actions"); return 2
    # A tone_target citation is checked here, before anything below opens a
    # device or simulator: an invented citation is refused as a bad recipe,
    # not as a failed action against hardware.
    tone_target = rec.get("tone_target")
    if tone_target is not None:
        problem = nam_captures.validate_tone_target(tone_target)
        if problem:
            print(f"REFUSED: {problem}"); return 2
    print(f"recipe: {rec.get('title', rec['name'])}")
    for s in rec.get("sources", []):
        print(f"  source: {s}")
    if tone_target is not None:
        print(f"  tone target: {nam_captures.describe(tone_target['capture_id'])}")
        print("    on an A2-capable device this capture IS the tone; "
              "the steps below are this FM9's grounded approximation")
    import server
    from server import Action, validate_action, run_action
    if os.environ.get("TONECOMMAND_SIM") == "1":
        from fm9.sim import SimFM9
        dev = SimFM9(server.reg)
    else:
        from fm9.device import FM9
        dev = FM9(server.reg)
    server._fm9 = dev
    dev.status_dump()
    print(f"device: {dev.current_preset()}")
    actions = [Action(**a) for a in steps]
    problems = []
    for i, a in enumerate(actions):
        errs, warns = validate_action(a)
        for e in errs:
            problems.append(f"action {i} ({a.kind}): {e}")
        for w in warns:
            print(f"  note on action {i} ({a.kind}): {w}")
    if problems:
        print("VALIDATION FAILED:")
        for pr in problems:
            print(" ", pr)
        return 1
    print(f"validated: {len(actions)} actions clean")
    if not apply:
        print("dry-run complete; use --apply to execute (edit buffer only)")
        return 0
    for i, a in enumerate(actions):
        res = run_action(dev, a)
        ok = res.get("ok", True)
        print(f"  [{i}] {a.kind} {a.param or a.block or ''}: "
              f"{'ok' if ok else 'FAILED: ' + str(res.get('detail'))}")
        if not ok:
            print("stopped at first failure; nothing was stored")
            return 1
    und = sorted(getattr(getattr(dev, "sim_core", None), "undecoded", []) or [])
    for u in und:
        print("  !!", u)
    print("\nEAR CHECKLIST (a human confirms tone, not a read-back):")
    for item in rec.get("ear_checklist", []):
        print(f"  [ ] {item}")
    print("\napplied to the edit buffer only; storing is your decision "
          "at the unit or via your own tooling")
    return 0

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(main(args[0], "--apply" in sys.argv))

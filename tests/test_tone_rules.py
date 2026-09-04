"""The tone-building rulebook is the single source of truth for how a good FM9
tone is built, and the planner must read it on every build. It exists because
the tool broke each of these rules once (the Marco Sfogli experiment): scene
blindness, wrong effect order, inaudible levels."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "config" / "tone_rules.md"


def test_the_rulebook_ships():
    assert RULES.exists(), "config/tone_rules.md must ship with the tool"
    text = RULES.read_text()
    # the rules that came from real failures must be stated
    for rule in ("Delay goes BEFORE reverb",
                 "Scenes are roles",
                 "never ship an inaudible",
                 "align by ROLE",
                 "delay only on leads"):
        assert rule in text, rule


def test_the_planner_reads_the_rulebook_on_every_build():
    from fm9 import planner
    assert planner._TONE_RULES, "planner did not load the rulebook"
    # the rules are in the system prompt the model actually receives
    for rule in ("Delay goes BEFORE reverb", "Scenes are roles",
                 "never ship an inaudible"):
        assert rule in planner.SYSTEM, rule

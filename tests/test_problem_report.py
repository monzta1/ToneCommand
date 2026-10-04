"""#201: a report a maintainer can act on, and a key that can never travel.

A user hit "The AI helper is busy right now" on every request and sent the
conversation transcript, which was all he could send. It carried no operating
system, no version, no backend, no model and not the actual error, so nobody
could diagnose it, including him. The underlying cause was a misclassified
error message that said congestion when there was none.

This is the other half of that fix: the report carries what is needed, and
the player reads every word of it before anything leaves the machine.
"""
from pathlib import Path

import pytest

from fm9 import diagnostics

UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"


# --- the thing that must never happen --------------------------------------

@pytest.mark.parametrize("secret,label", [
    ("AIzaSyD9fK3mQ1vXn7bR2tLpW4eY8uZ0cH6jA5s", "a Google key"),
    ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "an Anthropic key"),
    ("sk-abcdefghijklmnopqrstuvwxyz012345", "an OpenAI-style key"),
    ("ghp_abcdefghijklmnopqrstuvwxyz0123", "a GitHub token"),
    ("github_pat_11ABCDEFG0abcdefghijklmnop", "a fine-grained PAT"),
])
def test_a_credential_never_survives_the_scrub(secret, label):
    """A shared report is the one that leaves the machine. The Google pattern
    is here because the report that prompted this feature came from a Gemini
    user, and `AIza...` matched none of the original four patterns."""
    out = diagnostics.scrub_text(f"request failed with key={secret} on attempt 1")
    assert secret not in out, f"{label} survived the scrub"
    assert diagnostics.REDACTED in out


def test_a_bearer_header_never_survives():
    out = diagnostics.scrub_text("Authorization: Bearer abcdef0123456789xyz")
    assert "abcdef0123456789xyz" not in out


def test_the_home_directory_is_masked_but_the_path_shape_survives():
    """A username is a real name on a public issue. The shape is what
    diagnoses the problem; whose machine it is never does."""
    out = diagnostics.scrub_text(f"config at {Path.home()}/.tonecommand/ai.json")
    assert str(Path.home()) not in out
    assert "~/.tonecommand/ai.json" in out


def test_a_model_name_is_kept_because_it_is_the_diagnosis():
    """The NAME is the answer; the key is the credential. Conflating them
    either leaks a secret or throws away the useful part."""
    out = diagnostics.scrub_text("planner: gemini, model gemini-2.5-pro")
    assert "gemini-2.5-pro" in out


# --- what a maintainer needs ----------------------------------------------

def test_the_environment_answers_the_questions_always_asked():
    lines = "\n".join(diagnostics.environment())
    for label in ("ToneCommand:", "OS:", "Python:", "Install:", "Planner:",
                  "Device:"):
        assert label in lines, f"{label} missing from the report"


def test_the_environment_never_raises_on_a_broken_install(monkeypatch):
    """A report from a half-broken install is the one that matters most."""
    monkeypatch.setattr(diagnostics, "_planner_line",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    lines = "\n".join(diagnostics.environment())
    assert "could not be read" in lines
    assert "OS:" in lines, "one bad lookup must not take the report down"


def test_the_report_carries_the_environment_and_the_players_words(tmp_path):
    pkg = diagnostics.package_for_sharing(
        path=tmp_path / "none.jsonl",
        note="tried the Van Halen example, got this every time")
    assert "**What happened**" in pkg["body"]
    assert "tried the Van Halen example" in pkg["body"]
    assert "**Environment**" in pkg["body"]
    assert "OS:" in pkg["body"]


def test_the_title_uses_the_players_own_words(tmp_path):
    """An issue list full of "Diagnostics report (all, 10 entries)" is
    unreadable."""
    pkg = diagnostics.package_for_sharing(path=tmp_path / "none.jsonl",
                                          note="every request fails")
    assert pkg["title"] == "Problem report: every request fails"


def test_without_a_note_the_title_still_says_something(tmp_path):
    pkg = diagnostics.package_for_sharing(path=tmp_path / "none.jsonl")
    assert pkg["title"].startswith("Problem report")


def test_the_package_makes_no_network_call(tmp_path, monkeypatch):
    """The whole privacy model rests on this: building a report sends
    nothing, and the only thing that leaves the machine is the player opening
    the URL themselves."""
    import urllib.request
    def forbidden(*a, **k):
        raise AssertionError("package_for_sharing made a network call")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    pkg = diagnostics.package_for_sharing(path=tmp_path / "none.jsonl")
    assert pkg["url"].startswith("https://github.com/")


# --- the offer, on every error --------------------------------------------

def test_every_error_note_offers_to_report_itself():
    """Not only the ones we think we cannot explain. The error that prompted
    this said "busy", which sounded self-explanatory and was wrong."""
    ui = UI.read_text(encoding="utf-8")
    assert "function chatNote(text, isError)" in ui
    assert "reportbtn" in ui
    assert "chatNote(plainPlanError(e.message), true)" in ui
    assert "chatNote(`Nothing was sent. ${plain}`, true)" in ui


def test_the_panel_says_nothing_is_sent_from_it():
    ui = UI.read_text(encoding="utf-8")
    assert "Nothing is sent from here" in ui


def test_the_panel_shows_the_whole_body_not_a_summary():
    """The preview is what makes "nothing hidden" true rather than
    decorative."""
    ui = UI.read_text(encoding="utf-8")
    assert "reportbody" in ui and "esc(pkg.body)" in ui


def test_there_is_no_duplicate_search_from_the_app():
    """It would need a network call, which would cost the property that
    makes this safe to put on every error. Triage is not a player's job."""
    ui = UI.read_text(encoding="utf-8")
    start = ui.index("async function openReport()")
    body = ui[start:ui.index("\n}", start)]
    assert "search" not in body.lower()
    assert body.count("fetch(") <= 2, "only builds the report, twice at most"

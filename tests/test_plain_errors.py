"""The player-facing error messages must not lie about the cause.

A user with a free Gemini key reported "The AI helper is busy right now" on
every request. He was not busy or rate limited. The classifier matched
`rate` with no word boundary, and Gemini's API method is literally
`generateContent`, so every Gemini failure, including a bad key and an
unavailable model, was reported as congestion. The real reason went to the
diagnostic log and never reached him, and the suggested remedy ("give it a
moment") was advice that could never work.
"""
import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"


def _js_regex(func: str, line_contains: str) -> re.Pattern:
    """Lift a literal regex out of the page so the test checks the SHIPPED
    pattern rather than a copy of it that can drift."""
    src = UI.read_text(encoding="utf-8")
    start = src.index(f"function {func}(")
    body = src[start:src.index("\n}", start)]
    for line in body.splitlines():
        if line_contains in line and "/.test(m)" in line:
            pat = line[line.index("(/") + 2:line.rindex("/.test(m)")]
            return re.compile(pat.replace("\\b", r"\b"))
    raise AssertionError(f"no regex line containing {line_contains!r} in {func}")


BUSY = _js_regex("plainPlanError", "429")


@pytest.mark.parametrize("msg", [
    "generateContent returned 400",
    "Gemini: could not generate a plan",
    "models/gemini-2.5-pro:generateContent failed",
    "could not generate",
    "the request was moderated",
])
def test_an_error_that_merely_contains_rate_is_not_congestion(msg):
    """`generate` contains `rate`. So do moderate, operate and accurate."""
    assert not BUSY.search(msg.lower()), (
        f"{msg!r} would be reported to the player as 'busy, try again', which "
        "is both wrong and un-actionable")


@pytest.mark.parametrize("msg", [
    "HTTP 429 rate limit exceeded",
    "RESOURCE_EXHAUSTED: quota exceeded",
    "the model is overloaded",
    "too many requests",
    "server busy",
    "rate_limit_exceeded",
])
def test_real_congestion_is_still_recognised(msg):
    assert BUSY.search(msg.lower()), f"{msg!r} is congestion and should say so"

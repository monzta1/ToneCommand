"""ui/index.html's script must actually parse.

WHY THIS EXISTS. On 2026-09-19 a commit pasted `runAxeChange` inside
`runArtistInstall`'s `finally` block, leaving that block and its function
unclosed. The result was not a subtle bug: the browser threw
`SyntaxError: Unexpected end of input` at the closing </script>, so NOTHING
in the page ran. No polling, no link indicator, no buttons. The page still
rendered, because HTML and CSS are unaffected by a dead script, so it looked
fine in a screenshot and in the diff. It shipped in 1.5.3 and survived ten
days and twelve releases, and a user reported it as "I can open it but cannot
interact with anything".

Every existing test read the file as text or drove the server. None of them
parsed the script, which is why a whole-file syntax error was invisible to a
green suite. This test closes exactly that gap, and it is cheap.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"


def page_script() -> str:
    """The contents of the page's one <script> block."""
    s = UI.read_text(encoding="utf-8")
    start = s.index(">", s.index("<script")) + 1
    return s[start:s.rindex("</script>")]


def test_the_page_has_exactly_one_script_block():
    """The extraction above assumes it. If a second one is ever added, this
    test fails rather than silently checking only part of the page."""
    s = UI.read_text(encoding="utf-8")
    assert s.count("<script") == 1 and s.count("</script>") == 1


def test_the_page_script_parses(tmp_path):
    """Run the real thing: node's parser, not a brace-counting heuristic that
    would trip over a regex literal and cry wolf."""
    node = shutil.which("node")
    if node is None:
        # Never skip silently on CI: a guard that quietly does not run is
        # worse than no guard, because the suite still reports green.
        if os.environ.get("CI"):
            pytest.fail("node is required on CI to syntax-check the UI script")
        pytest.skip("node not installed; install it to run the UI syntax check")

    js = tmp_path / "page.js"
    js.write_text(page_script(), encoding="utf-8")
    r = subprocess.run([node, "--check", str(js)],
                       capture_output=True, text=True)
    assert r.returncode == 0, (
        "ui/index.html's script does not parse, so the whole page is dead in "
        "a browser:\n" + (r.stderr or r.stdout))


def test_node_is_available_wherever_this_suite_gates_a_merge():
    """The syntax check above is only a guard if it actually runs. GitHub's
    ubuntu and windows runners both ship node, so on CI its absence is a
    broken environment rather than an excuse to skip.

    A brace-counting fallback was written for machines without node and then
    deleted: it reported an imbalance in a file node parses cleanly, because
    telling a regex literal from a division sign needs a real tokenizer. A
    guard that cries wolf gets muted, and a muted guard is how the original
    bug survived ten days.
    """
    if os.environ.get("CI"):
        assert shutil.which("node"), "CI must provide node"

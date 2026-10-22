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
from html.parser import HTMLParser
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inline = []
        self.external = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            source = dict(attrs).get("src")
            if source:
                self.external.append(source)
            else:
                self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.inline.append("".join(self.current))
            self.current = None


def page_scripts():
    parser = Scripts()
    parser.feed(UI.read_text(encoding="utf-8"))
    return parser


def page_script() -> str:
    """Extract the application script without including local language assets."""
    scripts = page_scripts()
    assert len(scripts.inline) == 1
    return scripts.inline[0]


def test_the_page_has_one_application_script_and_local_language_assets():
    scripts = page_scripts()
    assert len(scripts.inline) == 1
    assert scripts.external == ["/language/i18next.min.js", "/language/tc-language.js"]


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

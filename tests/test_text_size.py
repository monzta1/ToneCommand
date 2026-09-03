"""Type sized for reading, and a control for when that is still not enough.

Moncy: "the font size is very small, for my aging eyes its hard to see". He
was right, and the numbers said so plainly. The scale ran from 8.7px to
15.75px on a 15px root, so body text was 12px and hints were 11px. That is
workable on a large screen at arm's length and hard work everywhere else.

Two changes, because one would not have been enough. The scale is bigger, and
the small end grew by more than the large end since that is where the strain
was. And how big text needs to be is a fact about the reader and their screen
rather than something a stylesheet can know, so there is a control.
"""
import re
from pathlib import Path

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]
STYLE = UI.split("<style>")[1].split("</style>")[0]


def test_the_root_is_not_a_quiet_reduction_of_everything():
    """15px silently shrinks every size below what the browser and every other
    site assume. 16 is the default for a reason."""
    root = STYLE.split(":root {")[1].split("}")[0]
    m = re.search(r"font-size: (\d+)px", root)
    assert m and int(m.group(1)) >= 16


# The tokens live in their own :root block, so these read the whole
# stylesheet rather than one block: splitting on the first ":root {" found the
# colours and missed the scale entirely.
def _rem(name):
    return float(re.search(rf"--fs-{name}:\s*calc\(([\d.]+)rem", STYLE).group(1))


def _root_px():
    return int(re.search(r"font-size: (\d+)px", STYLE).group(1))


def test_body_text_is_at_least_sixteen_pixels():
    assert _rem("body") * _root_px() >= 16


def test_the_smallest_step_is_still_legible():
    """A badge nobody can read is decoration, not information."""
    assert _rem("badge") * _root_px() >= 11


def test_the_small_end_grew_by_more_than_the_large_end():
    """That is where the strain was. Before: badge 0.58, lead 1.05, a ratio of
    1.81. Compressing the scale lets the smallest text catch up."""
    assert _rem("lead") / _rem("badge") < 1.81


def test_every_size_on_the_page_answers_to_the_control():
    """A raw rem left behind means the page looks half adjusted when someone
    scales it up, which is worse than not offering the control."""
    raw = re.findall(r"font-size: ([0-9.]+)rem(?!\s*\*)", STYLE)
    assert not raw, f"these bypass --ui-scale: {raw}"


def test_the_control_is_under_settings_and_clamped():
    """In Settings > Appearance now, per the control-surface spec, and
    neither end can make the page unusable."""
    assert 'id="tsup"' in UI and 'id="tsdown"' in UI
    appearance = UI.split('data-label="APPEARANCE"')[1].split("</div>\n    </div>")[0]
    assert 'class="textsize"' in appearance
    assert re.search(r"TS_MIN\s*=\s*0\.\d+", SCRIPT)
    assert re.search(r"TS_MAX\s*=\s*1\.\d+", SCRIPT)
    fn = SCRIPT.split("function textScale")[1].split("\n}")[0]
    assert "Math.min(TS_MAX" in fn and "Math.max(TS_MIN" in fn


def test_the_choice_is_remembered():
    """Setting it again on every visit would make it a nuisance rather than a
    setting."""
    assert "localStorage.setItem('tc-ui-scale'" in SCRIPT
    assert "localStorage.getItem('tc-ui-scale')" in SCRIPT


def test_a_browser_that_refuses_storage_still_renders():
    """Private windows and locked down browsers throw on localStorage rather
    than returning null."""
    assert SCRIPT.count("try { localStorage.setItem('tc-ui-scale'") == 1
    restore = SCRIPT.split("localStorage.getItem('tc-ui-scale')")[1][:200]
    assert "catch" in restore

"""The audition list must sit above the manual inspector.

The inspector is a fixed, full-width panel with its own stacking level. The
amp and cab audition list opens from a button inside it and is itself fixed
(so a long name cannot widen the panel mid-filter). With the list below the
inspector in z-order it rendered behind the sliders: the button appeared to
do nothing, on exactly the screen whose whole point is auditioning by
typing. Found by a screenshot, 2026-09-08. This pins the order.
"""
import re
from pathlib import Path

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


def _z(selector: str) -> int:
    """The largest z-index declared in any rule block for this selector."""
    zs = []
    for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", UI):
        for z in re.findall(r"z-index:\s*(\d+)", m.group(1)):
            zs.append(int(z))
    assert zs, f"no z-index declared for {selector}"
    return max(zs)


def test_the_audition_popover_stacks_above_the_inspector():
    assert _z("#audpop") > _z("#inspector")

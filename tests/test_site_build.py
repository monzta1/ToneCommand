"""The header logo on tonecommand.com read as a mini icon.

The sticky header's brand logo was 40x40, the only persistently-visible logo
on the site (the 220x220 splash is once-per-session and fades; the favicon
is browser chrome). Bumped to 64x64 so it reads as a real logo.

Source-inspection, not a rendered build: site/build.py's own network calls
(GitHub release lookup, Shopify product fetch) make a full build slow and
flaky to assert against for a one-line markup change, and this repo already
uses inspect.getsource-style checks for exactly this reason (see
docs/TEST-REPORT-2026-09-07.md).
"""
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


def test_header_logo_is_64px():
    source = (SITE_DIR / "build.py").read_text()
    assert 'class="brand" href="/"><img src="{img_url(\'logo.png\')}" alt="" width="64" height="64">' in source
    assert 'class="brand" href="/"><img src="{img_url(\'logo.png\')}" alt="" width="40" height="40">' not in source


def test_no_em_dash_in_touched_site_files():
    for rel in ("build.py", "theme.css"):
        text = (SITE_DIR / rel).read_text()
        assert "—" not in text, f"em dash in site/{rel}"

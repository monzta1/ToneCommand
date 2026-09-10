"""The logo on tonecommand.com read as too small, twice.

Round 1: the sticky header's brand logo was 40x40, the only persistently-
visible logo on the site. Bumped to 64x64 -- shipped, verified live, and
still called "too small". Round 2: rather than keep inflating a nav icon
(which has to share a sticky header with nav links), the fix moved to where
"much much larger, central" actually reads well -- the full-screen splash
shown once per browser session before the page fades in. The old static
152px ".mark" pulse above the hero is gone; the splash (520x520, clamp
280px-42vw-520px) is now the one dramatic logo moment.

Source-inspection, not a rendered build: site/build.py's own network calls
(GitHub release lookup, Shopify product fetch) make a full build slow and
flaky to assert against for a markup change, and this repo already uses
inspect.getsource-style checks for exactly this reason (see
docs/TEST-REPORT-2026-09-07.md).
"""
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


def test_header_logo_is_64px():
    source = (SITE_DIR / "build.py").read_text()
    assert 'class="brand" href="/"><img src="{img_url(\'logo.png\')}" alt="" width="64" height="64">' in source
    assert 'class="brand" href="/"><img src="{img_url(\'logo.png\')}" alt="" width="40" height="40">' not in source


def test_splash_logo_is_520px():
    build_source = (SITE_DIR / "build.py").read_text()
    assert 'id="splash" aria-hidden="true"><img src="{img_url(\'logo.png\')}" alt="" width="520" height="520"' in build_source

    css_source = (SITE_DIR / "theme.css").read_text()
    assert "#splash img {" in css_source
    assert "clamp(280px, 42vw, 520px)" in css_source

    assert ".mark img" not in css_source, "the old static hero mark should be fully replaced, not left dead"


def test_splash_reduced_motion_and_no_js_fallback():
    css_source = (SITE_DIR / "theme.css").read_text()

    # The base #splash rule fires the fade-out purely from CSS, unconditioned
    # on any class -- a visitor with JS disabled still gets the splash hidden
    # after 1.65s, not stuck staring at it forever.
    assert "#splash {\n  position: fixed; inset: 0; z-index: 200; display: flex; align-items: center;\n  justify-content: center; background: var(--bg);\n  animation: splash-out 0.5s 1.15s forwards;\n}" in css_source

    # prefers-reduced-motion suppresses the splash outright (opacity/visibility
    # set directly, not merely disabling the animation), so a user who asked
    # for less motion is never blocked by it even for an instant.
    assert (
        "@media (prefers-reduced-motion: reduce) {\n"
        "  #splash { animation: none; opacity: 0; visibility: hidden; pointer-events: none; }\n"
        "}"
    ) in css_source


def test_splash_skip_on_interaction_is_wired():
    css_source = (SITE_DIR / "theme.css").read_text()
    assert "#splash.skip, #splash.skip img { animation: none !important; }" in css_source
    assert "#splash.skip { opacity: 0 !important; visibility: hidden !important; pointer-events: none !important; }" in css_source

    fx_source = (SITE_DIR / "fx.js").read_text()
    assert "function splashSkip()" in fx_source
    assert "splash.className = 'skip';" in fx_source
    assert "document.addEventListener('pointerdown', go" in fx_source
    assert "document.addEventListener('keydown', go" in fx_source
    assert "splashSkip();" in fx_source, "splashSkip must actually be called from start()"


def test_no_em_dash_in_touched_site_files():
    for rel in ("build.py", "theme.css", "fx.js"):
        text = (SITE_DIR / rel).read_text()
        assert "—" not in text, f"em dash in site/{rel}"

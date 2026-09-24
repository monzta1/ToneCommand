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
    source = (SITE_DIR / "build.py").read_text(encoding="utf-8")
    assert 'class="brand" href="/"><img src="{img_url(\'logo.png\')}" alt="" width="64" height="64">' in source
    assert 'class="brand" href="/"><img src="{img_url(\'logo.png\')}" alt="" width="40" height="40">' not in source


def test_splash_logo_is_520px():
    build_source = (SITE_DIR / "build.py").read_text(encoding="utf-8")
    assert 'id="splash" aria-hidden="true"><img src="{img_url(\'logo.png\')}" alt="" width="520" height="520"' in build_source

    css_source = (SITE_DIR / "theme.css").read_text(encoding="utf-8")
    assert "#splash img {" in css_source
    assert "clamp(280px, 42vw, 520px)" in css_source

    assert ".mark img" not in css_source, "the old static hero mark should be fully replaced, not left dead"


def test_splash_reduced_motion_and_no_js_fallback():
    css_source = (SITE_DIR / "theme.css").read_text(encoding="utf-8")

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
    css_source = (SITE_DIR / "theme.css").read_text(encoding="utf-8")
    assert "#splash.skip, #splash.skip img { animation: none !important; }" in css_source
    assert "#splash.skip { opacity: 0 !important; visibility: hidden !important; pointer-events: none !important; }" in css_source

    fx_source = (SITE_DIR / "fx.js").read_text(encoding="utf-8")
    assert "function splashSkip()" in fx_source
    assert "splash.className = 'skip';" in fx_source
    assert "document.addEventListener('pointerdown', go" in fx_source
    assert "document.addEventListener('keydown', go" in fx_source
    assert "splashSkip();" in fx_source, "splashSkip must actually be called from start()"


def test_no_em_dash_in_touched_site_files():
    em_dash = chr(0x2014)          # spelled, so this file is not a hit itself
    for rel in ("build.py", "theme.css", "fx.js"):
        text = (SITE_DIR / rel).read_text(encoding="utf-8")
        assert em_dash not in text, f"em dash in site/{rel}"


# --- every link the site writes has to land somewhere real (#184) ---

def test_every_doc_page_with_a_short_url_is_routed_there():
    """DOC_PAGE_PATHS gives a doc its own short URL; ROUTES turns a
    `docs/NAME.md` cross-link into that URL. A page in the first and not the
    second renders as a repo blob link with the `docs/` prefix already
    stripped, which is a 404 and bypasses the page: exactly what shipped for
    docs/WINDOWS.md before this test existed.
    """
    import sys

    sys.path.insert(0, str(SITE_DIR))
    import build

    for slug, source, *_ in build.DOC_PAGES:
        if slug not in build.DOC_PAGE_PATHS:
            continue
        name = Path(source).name
        assert build.ROUTES.get(name) == build.DOC_PAGE_PATHS[slug], (
            f"{name} is published at {build.DOC_PAGE_PATHS[slug]} but ROUTES sends "
            f"links to {build.ROUTES.get(name)!r}; add "
            f'"{name}": "{build.DOC_PAGE_PATHS[slug]}" to ROUTES'
        )


def test_no_rendered_link_points_at_a_repo_path_that_does_not_exist(tmp_path, monkeypatch):
    """The fallback in rewrite_link sends anything unrouted to a blob URL on
    main. If the path is wrong the link 404s on a page nobody rebuilds by
    hand, so check every blob link a build produced against the tree.

    The build runs here, into a temporary directory: site/dist is gitignored
    and CI never builds the site, so a test that read an existing site/dist
    would skip in the one place that gates a merge.
    """
    import re
    import sys

    sys.path.insert(0, str(SITE_DIR))
    import build

    dist = tmp_path / "dist"
    monkeypatch.setattr(build, "DIST", dist)
    monkeypatch.setattr(sys, "argv", ["build.py", "--offline"])
    assert build.main() == 0

    pages = list(dist.rglob("*.html"))
    assert pages, "the build wrote no pages"
    root = SITE_DIR.parent
    blob = re.compile(r"https://github\.com/monzta1/ToneCommand/blob/main/([^\"#?]+)")
    missing = set()
    for page in pages:
        for target in blob.findall(page.read_text(encoding="utf-8")):
            if not (root / target).exists():
                missing.add(f"{page.relative_to(dist)} -> {target}")
    assert not missing, "links to repository paths that do not exist:\n" + "\n".join(sorted(missing))

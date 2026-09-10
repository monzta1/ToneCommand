"""Build tonecommand.com from what the repository already says.

The site is generated, not written: every page is the README, a doc, the
changelog, a recipe, or a screenshot the repository already ships, rendered
under one theme. Nothing on the site exists only on the site, so the site can
never contradict the repo and there is nothing to keep in sync by hand.

    .venv/bin/python site/build.py            # writes site/dist/
    .venv/bin/python site/build.py --offline  # skip the GitHub release lookup

Deploy: npx wrangler pages deploy site/dist --project-name tonecommand
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DIST = SITE / "dist"
DOCS = ROOT / "docs"
IMG = DOCS / "img"

SITE_URL = "https://tonecommand.com"
REPO = "monzta1/ToneCommand"
REPO_URL = f"https://github.com/{REPO}"
SLACK_URL = ("https://join.slack.com/t/tonecommand/shared_invite/"
             "zt-47oosli5y-GMHa93bbD4Qf76X4s1Crfg")
COFFEE_URL = "https://buymeacoffee.com/shieldbearer"
SHOP_URL = "https://shop.shieldbearerusa.com"
TEE_URL = f"{SHOP_URL}/products/tonecommand-emblem-tee"
JERSEY_URL = f"{SHOP_URL}/products/tonecommand-performance-jersey"
TAGLINE = "OLD SOUL. NEW MACHINE. HUMANS IN COMMAND."

# Product images for the merch cards come from the shop's own product pages
# (Shopify exposes them as JSON). Filled in by load_merch(); empty means the
# cards render without a picture rather than with a wrong one.
MERCH: dict[str, dict] = {}
MERCH_HTML = ""


def load_merch(offline: bool) -> None:
    if offline:
        return
    for key, url in (("tee", TEE_URL), ("jersey", JERSEY_URL)):
        try:
            req = urllib.request.Request(url + ".json", headers={"User-Agent": "tonecommand.com build"})
            with urllib.request.urlopen(req, timeout=10) as r:
                prod = json.load(r)["product"]
            img = (prod.get("images") or [{}])[0].get("src", "")
            price = (prod.get("variants") or [{}])[0].get("price", "")
            MERCH[key] = {"title": prod.get("title", ""), "image": img, "price": price}
        except Exception as e:  # noqa: BLE001
            print(f"merch lookup failed for {key}: {e}", file=sys.stderr)


def merch_card(key: str) -> str:
    m = MERCH.get(key)
    if not m or not m.get("image"):
        return '<span class="merchimg placeholder"></span>'
    alt = html.escape(m.get("title") or key)
    price = f'<span class="merchprice">${html.escape(str(m["price"]))}</span>' if m.get("price") else ""
    return f'<span class="merchimg"><img src="{html.escape(m["image"])}" alt="{alt}" loading="lazy"></span>{price}'


# Documentation pages, in the order the docs index lists them. The one-line
# descriptions are the README's own documentation table, verbatim.
DOC_PAGES = [
    ("setup", DOCS / "SETUP.md", "Install and setup",
     "Install, video extras, testing, compatibility matrix"),
    ("ai-backends", DOCS / "AI-BACKENDS.md", "Bring your own AI",
     "ChatGPT, Gemini, Grok, DeepSeek, Kimi, subscriptions, local models"),
    ("interface", DOCS / "INTERFACE.md", "The interface",
     "Every panel, with screenshots"),
    ("recipes", DOCS / "RECIPES.md", "Tone recipes",
     "What a recipe is, the format, and how to replay one"),
    ("architecture", ROOT / "ARCHITECTURE.md", "Architecture",
     "The adapter contract and the safety layer"),
    ("protocol", DOCS / "PROTOCOL.md", "FM9 editor protocol",
     "The living protocol record, evidence per claim"),
    ("protocol-contributions", DOCS / "PROTOCOL-CONTRIBUTIONS.md",
     "Protocol contributions",
     "Original decodes offered back to the community"),
    ("hardware-validation", DOCS / "HARDWARE-VALIDATION.md",
     "Hardware validation report",
     "The FM9 editor-protocol feasibility report"),
    ("credits", DOCS / "CREDITS.md", "Credits and prior work",
     "Prior work and contributors"),
    ("third-party-notices", ROOT / "THIRD_PARTY_NOTICES.md",
     "Third-party notices",
     "Upstream copyrights for vendored and derived content"),
    ("changelog", ROOT / "CHANGELOG.md", "Changelog",
     "Every release, cause alongside fix"),
]

# Where a repository-relative link lands on the site. Keys are the path as it
# appears in the markdown once "../" and "docs/" are stripped.
ROUTES = {
    "README.md": "/",
    "SETUP.md": "/install/",
    "AI-BACKENDS.md": "/docs/ai-backends/",
    "INTERFACE.md": "/docs/interface/",
    "RECIPES.md": "/docs/recipes/",
    "ARCHITECTURE.md": "/docs/architecture/",
    "PROTOCOL.md": "/docs/protocol/",
    "PROTOCOL-CONTRIBUTIONS.md": "/docs/protocol-contributions/",
    "HARDWARE-VALIDATION.md": "/docs/hardware-validation/",
    "CREDITS.md": "/docs/credits/",
    "THIRD_PARTY_NOTICES.md": "/docs/third-party-notices/",
    "CHANGELOG.md": "/docs/changelog/",
}

def img_url(name: str) -> str:
    """/img/<name> with a content hash, so a re-taken screenshot that keeps
    its filename is never served stale by a browser or edge cache."""
    f = IMG / name
    if not f.exists():
        return f"/img/{name}"
    import hashlib
    h = hashlib.sha256(f.read_bytes()).hexdigest()[:10]
    return f"/img/{name}?v={h}"


# Screenshots that are real captures of the running tool. The mock-up in the
# same folder is deliberately not here: the README's promise is that nothing
# shown is a mock-up.
SCREENSHOTS = [
    "ui-full.png", "audition-amp.png", "audition-cab.png", "graphic-eq.png",
    "pedal-and-bypass.png", "blast-radius.png", "health-scan.png",
]

NAV = [
    ("/", "Home"),
    ("/install/", "Install"),
    ("/docs/", "Docs"),
    ("/screenshots/", "Screenshots"),
    ("/recipes/", "Recipes"),
    ("/download/", "Download"),
    ("/support/", "Support"),
]


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

def rewrite_link(target: str) -> str:
    """Map a link as written in the repo to where it lives on the site."""
    if re.match(r"^(https?:|mailto:|#)", target):
        return target
    path, _, frag = target.partition("#")
    frag = f"#{frag}" if frag else ""
    clean = path
    while clean.startswith("../"):
        clean = clean[3:]
    if clean.startswith("./"):
        clean = clean[2:]
    if clean.startswith("docs/"):
        clean = clean[5:]
    if clean.startswith("img/"):
        return img_url(clean[4:]) + frag
    if clean in ROUTES:
        return f"{ROUTES[clean]}{frag}"
    if clean.startswith("recipes/") and clean.endswith(".json"):
        return f"/recipes/{clean[8:]}"
    # Anything else (source files, tools, tests) is a file in the repository.
    return f"{REPO_URL}/blob/main/{clean}{frag}"


_LINK_RE = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
_HTML_ATTR_RE = re.compile(r'((?:href|src)=")([^"]+)(")')
_MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.S)


def rewrite_links(md: str) -> str:
    md = _LINK_RE.sub(lambda m: m.group(1) + rewrite_link(m.group(2)) + m.group(3), md)
    md = _HTML_ATTR_RE.sub(lambda m: m.group(1) + rewrite_link(m.group(2)) + m.group(3), md)
    return md


def render_md(md: str) -> tuple[str, bool]:
    """Markdown to HTML. Returns (html, page_uses_mermaid)."""
    uses_mermaid = bool(_MERMAID_RE.search(md))
    md = _MERMAID_RE.sub(
        lambda m: '<pre class="mermaid">\n' + html.escape(m.group(1)) + "</pre>\n", md)
    md = rewrite_links(md)
    md = loosen_lists(md)
    converter = markdown.Markdown(extensions=[
        "fenced_code", "tables", "toc", "sane_lists", "codehilite",
    ], extension_configs={
        "toc": {"permalink": False},
        "codehilite": {"guess_lang": False, "css_class": "hl", "noclasses": False},
    })
    return mark_videos(converter.convert(md)), uses_mermaid


_VIDEO_RE = re.compile(
    r'<a href="(https://(?:youtu\.be/|www\.youtube\.com/watch)[^"]*)">(\s*<img[^>]*>\s*)</a>')
_PLAY = ('<span class="play" aria-hidden="true"><svg viewBox="0 0 68 48" width="68" height="48">'
         '<path d="M66.5 7.7c-.8-2.9-3-5.2-5.9-6C55.4 0 34 0 34 0S12.6 0 7.4 1.7c-2.9.8-5.1 3.1-5.9 6C0 13 0 24 0 24s0 11 1.5 16.3c.8 2.9 3 5.2 5.9 6C12.6 48 34 48 34 48s21.4 0 26.6-1.7c2.9-.8 5.1-3.1 5.9-6C68 35 68 24 68 24s0-11-1.5-16.3z" fill="#f00"/>'
         '<path d="M45 24 27 14v20z" fill="#fff"/></svg></span>')


def mark_videos(page_html: str) -> str:
    """A YouTube link wrapping a thumbnail gets a play button over the image.

    A thumbnail alone reads as a picture; the button is what tells a visitor
    it is a video. The link text and target are untouched.
    """
    return _VIDEO_RE.sub(
        lambda m: f'<a class="video" href="{m.group(1)}" rel="noopener" '
                  f'aria-label="Watch on YouTube">{m.group(2).strip()}{_PLAY}'
                  f'<span class="video-label">Watch on YouTube</span></a>',
        page_html)


_LIST_START = re.compile(r"^(?:[-*+] |\d+\. )")


def loosen_lists(md: str) -> str:
    """Insert the blank line python-markdown needs before a list.

    GitHub renders a list that starts right under a paragraph; python-markdown
    folds it into the paragraph. Only a top-level list item whose previous
    line is unindented prose gets the blank line, so nested items and wrapped
    continuations are untouched.
    """
    out: list[str] = []
    in_fence = False
    prev = ""
    for line in md.splitlines(keepends=True):
        if line.startswith("```"):
            in_fence = not in_fence
        prev_stripped = prev.lstrip()
        prose_above = (prev.strip() and not prev[0].isspace()
                       and not _LIST_START.match(prev) and not prev.startswith("```"))
        quote_above = prev_stripped.startswith(">")
        if not in_fence and _LIST_START.match(line) and (prose_above or quote_above):
            out.append("\n")
        out.append(line)
        prev = line
    return "".join(_break_quote_runs(out))


def _break_quote_runs(lines: list[str]) -> list[str]:
    """Consecutive '> *"..."*' example prompts stay one per line.

    Markdown joins consecutive quote lines into one paragraph, which reads as
    one run-on quotation. A trailing hard break after each closed quote keeps
    them as the separate examples they are. Wrapped prose inside a blockquote
    does not end with the closing quote marker, so it is left alone.
    """
    out: list[str] = []
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        body = line.rstrip("\n")
        if (body.lstrip().startswith(">") and body.rstrip().endswith('"*')
                and nxt.lstrip().startswith(">")):
            line = body.rstrip() + "  \n"
        out.append(line)
    return out


def split_sections(md: str) -> dict[str, str]:
    """Split a markdown document on its '## ' headings.

    Returns {heading: body} with the preamble under ''. Fenced code blocks are
    respected so a '## ' inside a code sample does not start a section.
    """
    sections: dict[str, str] = {}
    current = ""
    buf: list[str] = []
    in_fence = False
    for line in md.splitlines(keepends=True):
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            sections[current] = "".join(buf)
            current = line[3:].strip()
            buf = []
            continue
        buf.append(line)
    sections[current] = "".join(buf)
    return sections


def demote_headings(md: str) -> str:
    """Turn '# Title' documents into page bodies: h1 becomes the page title."""
    out = []
    in_fence = False
    for line in md.splitlines(keepends=True):
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("# ") and not out:
            continue  # the document title; the page chrome carries it
        out.append(line)
    return "".join(out)


def first_title(md: str) -> str | None:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


# --------------------------------------------------------------------------
# Page chrome
# --------------------------------------------------------------------------

def load_theme() -> str:
    return (SITE / "theme.css").read_text()


def page(*, title: str, description: str, body: str, path: str,
         version: str, mermaid: bool = False, wide: bool = False) -> str:
    full_title = "ToneCommand" if path == "/" else f"{title} | ToneCommand"
    nav = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if _active(path, href) else ""}>{label}</a>'
        for href, label in NAV
    )
    mermaid_tag = (
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/11.4.1/mermaid.min.js"></script>\n'
        '<script>mermaid.initialize({startOnLoad:true,theme:"dark",'
        'themeVariables:{primaryColor:"#16211f",primaryTextColor:"#d8dde5",'
        'primaryBorderColor:"#2fe6ff",lineColor:"#6ea8fe",fontFamily:"inherit"}});</script>'
        if mermaid else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="{SITE_URL}{path}">
<link rel="icon" type="image/png" href="/img/logo.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ToneCommand">
<meta property="og:title" content="{html.escape(full_title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:image" content="{SITE_URL}/img/social-preview.png">
<meta property="og:url" content="{SITE_URL}{path}">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/theme.css">
<script src="/fx.js" defer></script>
</head>
<body>
<header class="top">
  <a class="brand" href="/"><img src="{img_url('logo.png')}" alt="" width="64" height="64"><span>ToneCommand</span></a>
  <nav class="nav">{nav}</nav>
  <a class="gh" href="{REPO_URL}" rel="noopener">GitHub</a>
</header>
<main class="{'wide' if wide else ''}">
{body}
</main>
<footer class="foot">
  <p class="tagline">{TAGLINE}</p>
  <p>ToneCommand {html.escape(version)}. Free, Apache-2.0. Not affiliated with or endorsed by Fractal Audio Systems. Uses a reverse-engineered protocol; may break with firmware updates. Back up your presets. Use at your own risk.</p>
  <p><a href="/install/">Install</a> · <a href="/docs/">Docs</a> · <a href="/recipes/">Recipes</a> · <a href="{SLACK_URL}" rel="noopener">Slack</a> · <a href="{REPO_URL}/issues" rel="noopener">Issues</a> · <a href="{TEE_URL}" rel="noopener">Tee</a> · <a href="{JERSEY_URL}" rel="noopener">Jersey</a> · <a href="{SHOP_URL}" rel="noopener">Shop</a> · <a href="{REPO_URL}" rel="noopener">Source on GitHub</a></p>
</footer>
{mermaid_tag}
</body>
</html>
"""


def _active(path: str, href: str) -> bool:
    if href == "/":
        return path == "/"
    return path.startswith(href)


def write(path: str, content: str) -> None:
    out = DIST / path.strip("/") / "index.html" if path != "/" else DIST / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def latest_release(offline: bool) -> dict:
    """The latest GitHub release, or the packaged version if unreachable.

    The site says which one it is: a version pulled from pyproject is labelled
    as such rather than dressed up as a release.
    """
    fallback = {"tag": None, "version": pyproject_version(), "date": None,
                "notes": "", "url": f"{REPO_URL}/releases/latest", "source": "pyproject"}
    if offline:
        return fallback
    try:
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "tonecommand.com build"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:  # lifts the shared unauthenticated rate limit on CI runners
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases/latest", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            json.JSONDecodeError, ValueError) as e:
        print(f"release lookup failed, using pyproject version: {e}", file=sys.stderr)
        return fallback
    tag = data["tag_name"]
    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "date": data.get("published_at", "")[:10],
        "notes": data.get("body") or "",
        "url": data["html_url"],
        "zip": f"{REPO_URL}/archive/refs/tags/{tag}.zip",
        "source": "github",
    }


def pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else "unknown"


def load_recipes() -> list[dict]:
    out = []
    for f in sorted((ROOT / "recipes").glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            print(f"skipping {f.name}: {e}", file=sys.stderr)
            continue
        data["_file"] = f
        out.append(data)
    return out


def screenshot_captions() -> dict[str, str]:
    """Captions are the alt texts the docs already give each image."""
    caps: dict[str, str] = {}
    for src in (DOCS / "INTERFACE.md", ROOT / "README.md"):
        for m in re.finditer(r"!\[([^\]]*)\]\((?:docs/)?img/([^)]+)\)", src.read_text()):
            caps.setdefault(m.group(2), m.group(1))
    return caps


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

_BOLD_GROUP = re.compile(r"^\*\*(.+?)\*\*\s*$", re.M)
_QUOTED = re.compile(r'"([^"\n]{12,90})"')


def bold_groups(md: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a README section on its '**Title**' lines.

    Returns (intro, [(title, body)]). The Features and What-you-can-say
    sections are written this way: a bold line, then the bullets under it.
    """
    parts = _BOLD_GROUP.split(md)
    intro = parts[0]
    groups = [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    return intro, groups


def typed_prompts(md: str) -> list[str]:
    """The real requests quoted in the README, for the hero command bar."""
    seen: list[str] = []
    for q in _QUOTED.findall(md):
        q = q.strip()
        if "http" in q or "<" in q or q in seen:
            continue
        seen.append(q)
    return seen[:10]


def build_home(readme: str, release: dict) -> None:
    sec = split_sections(readme)
    pre = sec[""]
    paras = [p.strip() for p in re.split(r"\n\s*\n", pre) if p.strip()]
    lead = next((p for p in paras if p.startswith("**Talk")), "")
    lead = lead.replace("**Talk to your FM9. It builds the tone.** ", "", 1)
    lead_html, _ = render_md(lead)
    prompts = typed_prompts(sec.get("What you can say", "") + sec.get("Features", ""))
    caps = screenshot_captions()

    hero = f"""
<div class="mark">
  <img src="{img_url('logo.png')}" alt="ToneCommand" width="152" height="152" fetchpriority="high">
</div>
<section class="hero2">
  <div class="hero-copy">
    <p class="kicker">{TAGLINE}</p>
    <h1>Talk to your FM9.<br><span class="glow">It builds the tone.</span></h1>
    <div class="lead">{lead_html}</div>
    <div class="cmdbar" data-prompts='{html.escape(json.dumps(prompts), quote=True)}' aria-label="Examples of what you can type">
      <span class="cmdlabel">COMMAND</span>
      <span class="typed"></span><span class="caret" aria-hidden="true"></span>
      <span class="cmdsend">SEND</span>
    </div>
    <p class="cta">
      <a class="btn primary sweep" href="/install/">Install ToneCommand</a>
      <a class="btn" href="#watch-it-happen">Watch it happen</a>
      <a class="btn" href="/recipes/">Browse recipes</a>
    </p>
    <p class="version">Free and open source, Apache-2.0 · macOS, Windows and Linux · current release <a href="/download/">{html.escape(release['version'])}</a></p>
  </div>
  <figure class="hero-panel">
    <img src="{img_url('ui-full.png')}" alt="{html.escape(caps.get('ui-full.png', 'The ToneCommand interface'))}" width="2000" height="1299" fetchpriority="high">
    <figcaption>Live from a connected FM9. Nothing on this page is a mock-up.</figcaption>
  </figure>
</section>
<section class="stats reveal">
  <div><strong>331</strong><span>amps, searchable by the real gear they model</span></div>
  <div><strong>2,237</strong><span>cabs, by name and by what the cab actually is</span></div>
  <div><strong>8</strong><span>scenes per preset, named on your footswitches</span></div>
  <div><strong>Every write</strong><span>verified by reading the unit back</span></div>
  <div><strong>Your AI</strong><span>ChatGPT, Gemini, Grok, DeepSeek, Kimi, local, or the Claude CLI</span></div>
</section>
"""

    def section(num: str, name: str, body_html: str, extra_class: str = "") -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return (f'<section id="{slug}" class="block reveal {extra_class}">'
                f'<p class="kicker">{num} · {html.escape(name.upper())}</p>'
                f'<h2>{html.escape(name)}</h2>{body_html}</section>\n')

    out = []
    uses_mermaid = False

    # 01 watch
    watch_html, _ = render_md(sec.get("Watch it happen", ""))
    out.append(section("01", "Watch it happen", watch_html))

    # 02 features, as cards
    intro, groups = bold_groups(sec.get("Features", ""))
    intro_html, _ = render_md(intro)
    cards = ""
    for i, (title, body) in enumerate(groups):
        body_html, _ = render_md(body)
        cards += (f'<article class="feature reveal" style="--i:{i}"><h3>{html.escape(title)}</h3>{body_html}</article>')
    out.append(section("02", "Features", intro_html + f'<div class="features">{cards}</div>'))

    # 03 humans in command, as a statement
    hic_html, _ = render_md(sec.get("Humans in command", ""))
    out.append(section("03", "Humans in command", hic_html, "statement"))

    # 04 what you can say, as prompt chips
    intro, groups = bold_groups(sec.get("What you can say", ""))
    intro_html, _ = render_md(intro)
    chips = ""
    for title, body in groups:
        items = [ln.strip()[2:] for ln in body.splitlines() if ln.strip().startswith("- ")]
        # bullets wrap onto continuation lines in the README; rejoin them
        joined: list[str] = []
        for ln in body.splitlines():
            if ln.startswith("- "):
                joined.append(ln[2:].strip())
            elif ln.startswith("  ") and joined:
                joined[-1] += " " + ln.strip()
        items = joined or items
        lis = "".join(f"<li>{render_md(it)[0].replace('<p>', '').replace('</p>', '')}</li>" for it in items)
        chips += f'<div class="saygroup"><h3>{html.escape(title)}</h3><ul class="chips">{lis}</ul></div>'
    out.append(section("04", "What you can say", intro_html + f'<div class="say">{chips}</div>'))

    # 05 the interface: the real screenshots as cards, then the README's tour
    ui_md = sec.get("The interface", "")
    ui_md = re.sub(r"^!\[[^\]]*\]\([^)]*\)\s*$", "", ui_md, flags=re.M)  # the hero already shows it
    ui_html, _ = render_md(ui_md)
    shots = "".join(
        f'<figure class="shot reveal" style="--i:{i}"><a href="/screenshots/"><img src="{img_url(n)}" alt="{html.escape(caps.get(n, n))}" loading="lazy"></a>'
        f'<figcaption>{html.escape(caps.get(n, n))}</figcaption></figure>'
        for i, n in enumerate(x for x in SCREENSHOTS if x != "ui-full.png" and (IMG / x).exists()))
    out.append(section("05", "The interface", f'<div class="shots">{shots}</div>' + ui_html))

    # 06 how it works, 07 safety
    how_html, m = render_md(sec.get("How it works", "")); uses_mermaid |= m
    out.append(section("06", "How it works", how_html))
    safe_html, _ = render_md(sec.get("Safety", ""))
    out.append(section("07", "Safety", safe_html))

    # 08 support: the README's own words, with the merch as direct links
    support_html, _ = render_md(sec.get("Support", ""))
    merch = MERCH_HTML if MERCH_HTML else ""
    out.append(section("08", "Support", support_html + f"""
<div class="merchgrid">
  <a class="merchcard" href="{TEE_URL}" rel="noopener">{merch_card('tee')}<span class="merchname">ToneCommand emblem tee</span><span class="merchcta">See it in the shop</span></a>
  <a class="merchcard" href="{JERSEY_URL}" rel="noopener">{merch_card('jersey')}<span class="merchname">ToneCommand performance jersey</span><span class="merchcta">See it in the shop</span></a>
</div>
<p><a class="btn" href="{COFFEE_URL}" rel="noopener">Buy the maintainer a coffee</a> <a class="btn" href="{SHOP_URL}" rel="noopener">The whole Shieldbearer shop</a></p>
"""))

    # install
    install_short, _ = render_md(sec.get("Install", ""))
    out.append(f"""
<section id="install" class="block reveal">
  <p class="kicker">09 · INSTALL</p>
  <h2>Install</h2>
  {install_short}
  <p><a class="btn primary sweep" href="/install/">The full install guide</a></p>
</section>
""")
    body = hero + '<div class="home prose">' + "".join(out) + "</div>"
    write("/", page(title="ToneCommand", path="/", version=release["version"],
                    description="Natural-language tone control for the Fractal FM9 over USB MIDI. Describe the tone; review the exact changes; verified on real hardware.",
                    body=body, mermaid=uses_mermaid, wide=True))


def build_docs(release: dict) -> None:
    items = "".join(
        f'<li><a href="/docs/{slug}/"><strong>{html.escape(title)}</strong></a><span>{html.escape(desc)}</span></li>'
        if slug != "setup" else
        f'<li><a href="/install/"><strong>{html.escape(title)}</strong></a><span>{html.escape(desc)}</span></li>'
        for slug, _, title, desc in DOC_PAGES
    )
    body = f"""
<article class="prose">
<h1>Documentation</h1>
<p>Every page here is the same document that ships in the repository, rendered for reading. The source of each is one click away on GitHub.</p>
<ul class="doclist">{items}</ul>
</article>
"""
    write("/docs/", page(title="Documentation", path="/docs/", version=release["version"],
                         description="ToneCommand documentation: install, AI backends, the interface, recipes, architecture, protocol, credits and changelog.",
                         body=body))
    for slug, src, title, desc in DOC_PAGES:
        md = src.read_text()
        doc_title = first_title(md) or title
        body_html, mermaid = render_md(demote_headings(md))
        rel = src.relative_to(ROOT)
        path = "/install/" if slug == "setup" else f"/docs/{slug}/"
        head = ""
        body = f"""
<article class="prose">
<p class="crumbs"><a href="/docs/">Docs</a></p>
<h1>{html.escape(doc_title)}</h1>
{head}
{body_html}
<p class="srcnote">Source: <a href="{REPO_URL}/blob/main/{rel}" rel="noopener">{rel}</a> in the repository.</p>
</article>
"""
        write(path, page(title=doc_title, path=path, version=release["version"],
                         description=desc, body=body, mermaid=mermaid,
                         wide=slug in ("protocol", "changelog")))


def build_screenshots(release: dict) -> None:
    caps = screenshot_captions()
    figs = "".join(
        f'<figure><a href="{img_url(name)}"><img src="{img_url(name)}" alt="{html.escape(caps.get(name, name))}" loading="lazy"></a>'
        f'<figcaption>{html.escape(caps.get(name, name))}</figcaption></figure>'
        for name in SCREENSHOTS if (IMG / name).exists()
    )
    body = f"""
<article class="prose">
<h1>Screenshots</h1>
<p>Everything below is live from a connected FM9. Nothing on this page is a mock-up. The full tour of every panel is in <a href="/docs/interface/">The interface</a>.</p>
</article>
<section class="gallery">{figs}</section>
"""
    write("/screenshots/", page(title="Screenshots", path="/screenshots/", version=release["version"],
                                description="ToneCommand screenshots, every one captured live from a connected Fractal FM9.",
                                body=body, wide=True))


def build_recipes(recipes: list[dict], release: dict) -> None:
    cards = ""
    for r in recipes:
        name = r.get("name", r["_file"].stem)
        steps = r.get("steps") or r.get("actions") or []
        cards += f"""
<li class="card">
  <h2><a href="/recipes/{html.escape(name)}/">{html.escape(r.get('title', name))}</a></h2>
  <p>{html.escape(r.get('summary', ''))}</p>
  <p class="meta">{html.escape(str(r.get('device', '')))} · {len(steps)} steps · by {html.escape(str(r.get('author', 'unknown')))}</p>
</li>"""
    count = len(recipes)
    body = f"""
<article class="prose">
<h1>Tone recipes</h1>
<p>A recipe is <em>how</em> to build a tone, not the tone file itself: a named, cited, replayable list of ToneCommand actions. You share the knowledge; everyone replays it on their own unit against their own base preset. Nothing paid is ever redistributed. <a href="/docs/recipes/">How recipes work</a>.</p>
<p>{count} shared so far. To share yours, press <strong>SHARE RECIPE</strong> in the app.</p>
</article>
<ul class="cards">{cards}</ul>
"""
    write("/recipes/", page(title="Tone recipes", path="/recipes/", version=release["version"],
                            description="Shared ToneCommand recipes: replayable, cited tone builds for the Fractal FM9.",
                            body=body))
    index = []
    for r in recipes:
        name = r.get("name", r["_file"].stem)
        steps = r.get("steps") or r.get("actions") or []
        rows = ""
        for s in steps:
            kind = s.get("kind", "")
            parts = []
            if "block" in s:
                parts.append(f"{s['block']} {s.get('instance', '')}".strip())
            for k in ("param", "type_name", "value", "scene", "name", "source", "target"):
                if k in s and not (k == "value" and "block" not in s and kind == "set_scene"):
                    parts.append(f"{k}={s[k]}")
            if kind == "set_scene" and "value" in s:
                parts.append(f"scene {s['value']}")
            target = ", ".join(parts)
            rows += (f"<tr><td><code>{html.escape(kind)}</code></td>"
                     f"<td>{html.escape(target)}</td>"
                     f"<td>{html.escape(str(s.get('reason', '')))}</td></tr>")
        sources = "".join(f"<li>{html.escape(str(x))}</li>" for x in r.get("sources", []))
        ears = "".join(f"<li>{html.escape(str(x))}</li>" for x in r.get("ear_checklist", []))
        extra = ""
        if sources:
            extra += f"<h2>Sources</h2><ul>{sources}</ul>"
        if r.get("assumes"):
            extra += f"<h2>Assumes</h2><p>{html.escape(str(r['assumes']))}</p>"
        if ears:
            extra += f"<h2>Ear checklist</h2><ul>{ears}</ul>"
        body = f"""
<article class="prose">
<p class="crumbs"><a href="/recipes/">Recipes</a></p>
<h1>{html.escape(r.get('title', name))}</h1>
<p class="meta">{html.escape(str(r.get('device', '')))} · by {html.escape(str(r.get('author', 'unknown')))}{' · tested on firmware ' + html.escape(str(r['tested_firmware'])) if r.get('tested_firmware') else ''}</p>
<p>{html.escape(r.get('summary', ''))}</p>
<p><a class="btn primary" href="/recipes/{html.escape(name)}.json" download>Download recipe JSON</a></p>
<p>In the app, open <strong>LIBRARY</strong> in the footer to replay it, or from a terminal:</p>
<pre><code>python tools/replay_recipe.py recipes/{html.escape(name)}.json            # dry-run: validate only
python tools/replay_recipe.py recipes/{html.escape(name)}.json --apply    # edit buffer</code></pre>
<h2>Steps</h2>
<div class="tablewrap"><table><thead><tr><th>Action</th><th>Target</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>
{extra}
</article>
"""
        write(f"/recipes/{name}/", page(title=r.get("title", name), path=f"/recipes/{name}/",
                                        version=release["version"],
                                        description=r.get("summary", "A ToneCommand recipe."),
                                        body=body, wide=True))
        shutil.copy(r["_file"], DIST / "recipes" / f"{name}.json")
        public = {k: v for k, v in r.items() if not k.startswith("_")}
        index.append({"name": name, "title": r.get("title", name), "device": r.get("device"),
                      "author": r.get("author"), "summary": r.get("summary", ""),
                      "steps": len(steps), "url": f"{SITE_URL}/recipes/{name}.json"})
    (DIST / "recipes" / "index.json").write_text(json.dumps(index, indent=1))


def build_download(release: dict) -> None:
    notes_html, _ = render_md(release["notes"]) if release["notes"] else ("", False)
    if release["source"] == "github":
        head = f"""
<p class="meta">Released {html.escape(release['date'] or '')} · <a href="{release['url']}" rel="noopener">release notes on GitHub</a></p>
<p><a class="btn primary" href="{release['zip']}">Download ToneCommand {html.escape(release['version'])} (zip)</a>
<a class="btn" href="{REPO_URL}/releases" rel="noopener">All releases</a></p>
"""
    else:
        head = f"""
<p class="meta">Version from the packaged source; the release list was not reachable when this page was built.</p>
<p><a class="btn primary" href="{REPO_URL}/releases/latest" rel="noopener">Latest release on GitHub</a></p>
"""
    body = f"""
<article class="prose">
<h1>Download ToneCommand {html.escape(release['version'])}</h1>
{head}
<p>The zip is the source tree at that release. Unzip it and follow the <a href="/install/">install guide</a> for your system: macOS, Windows and Linux are all supported. Already installed? The app updates itself from the gear menu.</p>
<h2>What is new</h2>
{notes_html or '<p>See the <a href="/docs/changelog/">changelog</a>.</p>'}
<p><a href="/docs/changelog/">Every release, cause alongside fix, in the changelog.</a></p>
</article>
"""
    write("/download/", page(title="Download", path="/download/", version=release["version"],
                             description=f"Download ToneCommand {release['version']} for macOS, Windows and Linux.",
                             body=body))


def build_support(readme: str, release: dict) -> None:
    sec = split_sections(readme)
    community, _ = render_md(sec.get("Community", ""))
    support, _ = render_md(sec.get("Support", ""))
    disclaimer, _ = render_md(sec.get("Disclaimer and license", ""))
    body = f"""
<article class="prose">
<h1>Support and community</h1>
<h2>Community</h2>
{community}
<p><a class="btn primary" href="{SLACK_URL}" rel="noopener">Join the ToneCommand Slack</a></p>
<h2>Something broke?</h2>
<p>The <a href="/install/#if-something-goes-wrong">install guide</a> covers the common failures. For anything else, open an issue and paste what the app said: <a href="{REPO_URL}/issues" rel="noopener">{REPO_URL}/issues</a>.</p>
<h2>Support the project</h2>
{support}
<div class="merch">
  <a class="btn" href="{COFFEE_URL}" rel="noopener">Buy the maintainer a coffee</a>
  <a class="btn" href="{TEE_URL}" rel="noopener">ToneCommand emblem tee</a>
  <a class="btn" href="{JERSEY_URL}" rel="noopener">ToneCommand performance jersey</a>
  <a class="btn" href="{SHOP_URL}" rel="noopener">The whole Shieldbearer shop</a>
</div>
<h2>Disclaimer and license</h2>
{disclaimer}
</article>
"""
    write("/support/", page(title="Support", path="/support/", version=release["version"],
                            description="ToneCommand community Slack, issues, merch and how to support the project.",
                            body=body))


def build_static(recipes: list[dict]) -> None:
    (DIST / "img").mkdir(parents=True, exist_ok=True)
    for f in IMG.glob("*.png"):
        if f.name == "ui-redesign-review-mockup.png":
            continue
        shutil.copy(f, DIST / "img" / f.name)
    shutil.copy(SITE / "theme.css", DIST / "theme.css")
    shutil.copy(SITE / "fx.js", DIST / "fx.js")
    (DIST / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "/img/*\n  Cache-Control: public, max-age=86400\n"
        "/recipes/*.json\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n"
        "/recipes/index.json\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=300\n")
    (DIST / "_redirects").write_text(
        "/readme /  301\n/setup /install/ 301\n/changelog /docs/changelog/ 301\n"
        "/github https://github.com/monzta1/ToneCommand 302\n"
        "/slack " + SLACK_URL + " 302\n"
        "/shop https://shop.shieldbearerusa.com 302\n"
        "/releases https://github.com/monzta1/ToneCommand/releases 302\n"
        "/issues https://github.com/monzta1/ToneCommand/issues 302\n")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    urls = [href for href, _ in NAV] + [f"/docs/{s}/" for s, *_ in DOC_PAGES if s != "setup"]
    urls += [f"/recipes/{r.get('name', r['_file'].stem)}/" for r in recipes]
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{SITE_URL}{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    (DIST / "404.html").write_text(page(
        title="Not found", path="/404", version="", description="Page not found.",
        body='<article class="prose"><h1>Not found</h1><p>That page is not here. Try the <a href="/">home page</a> or the <a href="/docs/">docs</a>.</p></article>'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip the GitHub release lookup")
    args = ap.parse_args()
    started = time.time()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    readme = (ROOT / "README.md").read_text()
    release = latest_release(args.offline)
    load_merch(args.offline)
    recipes = load_recipes()
    build_static(recipes)
    build_home(readme, release)
    build_docs(release)
    build_screenshots(release)
    build_recipes(recipes, release)
    build_download(release)
    build_support(readme, release)
    pages = sum(1 for _ in DIST.rglob("index.html"))
    print(f"built {pages} pages for ToneCommand {release['version']} "
          f"({release['source']}) in {time.time() - started:.1f}s -> {DIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

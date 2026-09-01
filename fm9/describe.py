"""Build a tone from a description: a video, a forum post, or pasted text.

The point is to save the player the work. They paste a link to somebody's
"here's my worship rig" video or a long forum post, and get a plan against
their own FM9 instead of watching forty minutes and typing settings out.

WHY THIS IS TWO PASSES AND NOT ONE

Feeding a source straight to the planner does not work, and the failure is not
subtle: a 326 word forum post produced no reply within 180 seconds, on a
backend that answers a short prompt in eight. Splitting it is what makes this
feature possible at all.

    read + extract   about 20s   a noisy source becomes a compact spec
    build            about 220s  the spec becomes validated actions

The extract pass also does the honesty work, and it has to happen before the
builder sees anything. It separates what the source ACTUALLY STATED from what
it only gestured at, so the plan can show the player which numbers came from
the source and which this tool chose. Without that split the two are
indistinguishable by the time they reach the confirm panel, and a guess wearing
a source's authority is exactly what this project refuses to ship.

WHAT THIS FEATURE CLAIMS

Ballpark, not clone. A source rarely states everything, sources contradict
themselves, and a description of a tone is not the tone. The wording
everywhere, in code and in the UI, is an interpretation to review and tweak.

SAFETY

This is an INPUT METHOD. It produces the same action list `/api/plan`
produces, goes through the same `validate_action`, lands in the same confirm
panel, and is transmitted by the same gate. It adds no write path of its own.
`store` is refused outright: a build assembled out of somebody else's video has
no business overwriting a preset slot.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from fm9 import planner

#: This path is slow by nature and a stock 180s timeout fails a legitimate
#: build. Measured: a four scene rig took 226s to produce 73 actions, and a
#: bigger one will take longer. Sized with headroom rather than tuned to the
#: one example that was measured.
DEFAULT_TIMEOUT = 900


def timeout_s() -> int:
    raw = os.environ.get("TONECOMMAND_DESCRIBE_TIMEOUT", "").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_TIMEOUT


#: `store` is deliberately absent. Everything else the planner may propose is
#: fine here; overwriting a preset slot on the strength of a stranger's video
#: is not, and refusing it in the source text is cheaper than catching it later.
FORBIDDEN_KINDS = {"store"}

MAX_SOURCE = 200_000       # a long transcript, not a whole book
YOUTUBE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)"
                     r"([A-Za-z0-9_-]{11})")


class SourceError(RuntimeError):
    """A source that could not be read, with something useful to say."""


def looks_like_url(text: str) -> bool:
    t = (text or "").strip()
    return t.startswith(("http://", "https://")) and " " not in t.split("\n")[0]


#: A YouTube watch page is about 1.3MB and the description sits two thirds of
#: the way through it. Capping the FETCH at MAX_SOURCE truncated the page
#: before the part worth reading, which looked exactly like "this video has no
#: description". The cap belongs on the text kept, not on the bytes read.
MAX_FETCH = 3_000_000


def _get(url: str, timeout: int = 25, cap: int = MAX_FETCH) -> str:
    req = urllib.request.Request(url, headers={
        # Some sites serve a stub or a consent wall to anything that does not
        # look like a browser, and a stub is worse than an error: it extracts
        # to "no tone information" and blames the source.
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(cap)
    return raw.decode("utf-8", "replace")


def _strip_html(html: str) -> str:
    """Readable text out of a page, without pulling in a parser dependency."""
    html = re.sub(r"(?is)<(script|style|nav|footer|header|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&quot;", '"').replace("&#39;", "'")
                .replace("&lt;", "<").replace("&gt;", ">"))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def youtube_id(url: str) -> str | None:
    m = YOUTUBE.search(url or "")
    return m.group(1) if m else None


def read_youtube(url: str) -> dict:
    """Description first, captions if the platform will part with them.

    The description is the reliable half and, usefully, often the better half:
    creators list gear and settings there in a tidy block, where the spoken
    version is scattered through forty minutes of talking.

    Captions are attempted and usually refused (see _fetch_transcript). That
    is a note on the result rather than a failure, because a description alone
    is frequently enough to build from, and the note tells the player how to
    get the transcript themselves in two clicks.
    """
    vid = youtube_id(url)
    if not vid:
        raise SourceError("that does not look like a YouTube video link")
    notes, parts = [], []

    title = description = ""
    page = ""
    try:
        page = _get(f"https://www.youtube.com/watch?v={vid}")
        m = re.search(r'"shortDescription":"(.*?)","', page, re.S)
        if m:
            description = json.loads(f'"{m.group(1)}"')
        t = re.search(r'"title":"([^"]{3,160})"', page)
        if t:
            title = json.loads(f'"{t.group(1)}"')
    except (urllib.error.URLError, OSError, ValueError) as exc:
        notes.append(f"could not read the video page ({exc})")

    if description:
        parts.append(f"VIDEO DESCRIPTION:\n{description}")
    else:
        notes.append("this video has no description text")

    try:
        text = _fetch_transcript(page)
        if text:
            parts.append(f"SPOKEN TRANSCRIPT:\n{text}")
        else:
            # Accurate about whose limitation this is. "No captions" would be a
            # false statement about most videos, and it points the player at
            # the wrong problem.
            notes.append(
                "only the description was read: YouTube will not serve this "
                "video's captions to anything but a browser. For the spoken "
                "detail, open the video, click the three dots then Show "
                "transcript, copy it, and paste it here instead.")
    except SourceError as exc:
        notes.append(str(exc))

    if not parts:
        raise SourceError(
            "nothing readable came back from that video: no description and no "
            "captions. Paste the relevant text instead and it will work the "
            "same way.")
    return {"text": "\n\n".join(parts), "title": title, "notes": notes,
            "kind": "youtube", "url": url}


def _fetch_transcript(page: str) -> str:
    """Captions from the track list embedded in the watch page.

    Verified against a real video on 2026-09-01, and the honest state of it is
    that this rarely returns anything.

    The bare timedtext endpoint answers an unsigned request with zero bytes.
    The signed baseUrls carried in the page's own captionTracks do too, in
    every format tried (bare, fmt=json3, fmt=srv3), on a video whose captions
    are plainly there in a browser. YouTube now gates caption fetching behind
    signals a server-side request does not carry.

    It is kept because it costs one request off a page already fetched, it
    works where a track is served, and it will start working again if that
    changes. What it must never do is imply the video had no captions when the
    truth is that we could not get them, so the caller says which.
    """
    if not page:
        return ""
    m = re.search(r'"captionTracks":(\[.*?\])', page, re.S)
    if not m:
        return ""
    try:
        tracks = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return ""
    # English if it is there, otherwise whatever the creator published: a
    # gear list in Spanish still names the same pedals.
    pick = next((t for t in tracks
                 if str(t.get("languageCode", "")).startswith("en")), None)
    pick = pick or (tracks[0] if tracks else None)
    if not pick or not pick.get("baseUrl"):
        return ""
    try:
        raw = _get(pick["baseUrl"])
    except (urllib.error.URLError, OSError) as exc:
        raise SourceError(f"could not fetch this video's captions ({exc})")
    lines = re.findall(r"(?s)<text[^>]*>(.*?)</text>", raw)
    if not lines:
        lines = re.findall(r'"utf8":"(.*?)"', raw)
    text = " ".join(_strip_html(x) for x in lines)
    return re.sub(r"\s+", " ", text).strip()


def read_page(url: str) -> dict:
    try:
        html = _get(url)
    except (urllib.error.URLError, OSError) as exc:
        raise SourceError(
            f"could not fetch that page ({exc}). Open it, copy the part that "
            f"describes the tone, and paste it here instead.")
    text = _strip_html(html)
    if len(text.split()) < 40:
        raise SourceError(
            "that page returned almost no readable text, which usually means "
            "it needs a login or renders in the browser. Paste the text "
            "instead.")
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if m:
        title = _strip_html(m.group(1))[:200]
    return {"text": text[:MAX_SOURCE], "title": title, "notes": [],
            "kind": "page", "url": url}


def read_source(raw: str) -> dict:
    """A URL or pasted text becomes source text, or an error worth reading."""
    raw = (raw or "").strip()
    if not raw:
        raise SourceError("paste a link or some text describing the tone")
    if looks_like_url(raw):
        return read_youtube(raw) if youtube_id(raw) else read_page(raw)
    if len(raw.split()) < 12:
        raise SourceError(
            "that is too short to build from. Paste a link, or enough text to "
            "describe the sound you are after.")
    return {"text": raw[:MAX_SOURCE], "title": "", "notes": [],
            "kind": "text", "url": None}


EXTRACT_TASK = """You are reading a source a guitarist pasted in: a forum post, a
video transcript, or a description. It may be long and mostly irrelevant.

Extract ONLY the tone information. Ignore intros, sponsor reads, tangents,
merch plugs, and anything not about gear or settings.

Return JSON and nothing else, exactly this shape:

{
  "found": true,
  "summary": "one plain sentence a guitarist would say, describing the whole rig",
  "scenes": [
    {"n": 1, "name": "short label", "describes": "one sentence on what this scene is"}
  ],
  "stated": ["each specific setting the source ACTUALLY states, close to its own words"],
  "vague": ["each tone instruction that is directional rather than numeric"],
  "quotes": [{"about": "what this supports", "text": "the sentence from the source", "at": "timestamp if the source has one, else null"}]
}

If the source states no tone information at all, return
{"found": false, "why": "one sentence saying what the source is instead"}.

Rules:
- "stated" is ONLY what the source says. Never add a setting it did not give.
- Do not resolve gear to model names. "a Tube Screamer" stays "a Tube Screamer".
- If there are no scenes described, return a single scene.
- Keep it compact. This is handed to a builder next.

SOURCE:
"""


def extract(source_text: str) -> dict:
    """Turn a noisy source into a compact spec, with stated and vague split.

    Runs on the configured planner backend, because it is the same kind of
    work: read text, return structured JSON. It does NOT go through
    planner.plan, which exists to produce device actions and would be the
    wrong shape for this.
    """
    cli = planner.find_claude_cli()
    if not cli:
        raise SourceError(
            "reading a source needs a planner backend. Install the claude CLI "
            "or configure one in AI settings.")
    try:
        proc = subprocess.run(
            [cli, "-p", EXTRACT_TASK + source_text, "--output-format", "json",
             "--model", planner.cli_model()],
            capture_output=True, text=True, timeout=timeout_s(), cwd="/tmp",
            env={**planner.cli_env(planner.CLAUDE_ENV_KEYS),
                 "CLAUDE_CODE_ENTRYPOINT": "fm9-tone"})
    except subprocess.TimeoutExpired:
        raise SourceError(f"reading that source took longer than "
                          f"{timeout_s()}s. Try a shorter extract of it.")
    if proc.returncode != 0:
        raise SourceError(f"the reader failed: {(proc.stderr or '').strip()[:200]}")
    try:
        body = json.loads(proc.stdout).get("result") or ""
        spec = json.loads(body[body.index("{"):body.rindex("}") + 1])
    except (json.JSONDecodeError, ValueError):
        raise SourceError("could not read a tone description out of that source")
    if not isinstance(spec, dict):
        raise SourceError("the reader returned something unusable")
    spec.setdefault("found", False)
    for key in ("scenes", "stated", "vague", "quotes"):
        if not isinstance(spec.get(key), list):
            spec[key] = []
    return spec


def brief_from(spec: dict) -> str:
    """The spec, as ONE instruction in prose.

    This shape is load-bearing and it is not a style preference. Handed the
    same content as labelled lists, the model refused it outright:

        "This message seems to contain two pasted, unrelated pieces of content
         rather than a direct instruction to me"

    and returned prose instead of a plan, which surfaces as an unreadable
    output error several layers away. The planner prompt already carries a
    system message, a device state block and a parameter reference, so a fourth
    block of labelled text reads as another pasted document rather than as the
    request. Written as sentences it works every time.

    So: do not "tidy" this into bullet points.
    """
    scenes = spec.get("scenes") or []
    parts = []
    if scenes:
        parts.append(f"Build this rig across {len(scenes)} "
                     f"{'scene' if len(scenes) == 1 else 'scenes'}: "
                     f"{spec.get('summary') or 'a tone described by a player'}")
        for s in scenes:
            label = str(s.get("name") or f"scene {s.get('n')}").lower()
            parts.append(f"Scene {s.get('n')} is the {label}: {s.get('describes')}")
    else:
        parts.append(f"Build this rig: {spec.get('summary') or ''}")

    stated = [x for x in spec.get("stated") or [] if str(x).strip()]
    if stated:
        parts.append("Use these settings exactly where they are given: "
                     + "; ".join(str(x).rstrip(".") for x in stated) + ".")
    vague = [x for x in spec.get("vague") or [] if str(x).strip()]
    if vague:
        parts.append("Choose sensible values for these, which the source "
                     "described only loosely: "
                     + "; ".join(str(x).rstrip(".") for x in vague) + ".")
    parts.append("Do not store to any preset slot.")
    return " ".join(parts)

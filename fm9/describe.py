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
import pathlib
import re
import shutil
import subprocess
import tempfile
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


#: Whisper is the fallback, not the default: subtitles are free and instant
#: where they exist. Measured on this machine, CPU int8, no GPU involved:
#:
#:     base    14.7x realtime   a 40 minute video in about 2.7 minutes
#:     small    5.4x realtime   the same video in about 7.4 minutes
#:
#: `base` mishears gear names, and that matters less than it looks: the
#: extraction pass repairs "match less DC 30" from context, and the grounding
#: layer refuses a name it cannot resolve rather than guessing at it. Speed
#: wins, because the build after this already takes minutes. Set
#: TONECOMMAND_WHISPER_MODEL to small or medium to trade it back.
WHISPER_MODEL = "base"

#: Past this, transcribing is a worse deal than asking for a paste. Two hours
#: of stream is eight minutes of CPU before the build even starts.
WHISPER_MAX_SECONDS = 5400


def whisper_model_name() -> str:
    return os.environ.get("TONECOMMAND_WHISPER_MODEL", "").strip() or WHISPER_MODEL


def read_youtube(url: str) -> dict:
    """Everything the video will give us, cheapest source first.

    The order is the whole design:

        1. metadata    always. The description is where players put their gear
                       list, in a tidy block, and it costs one request.
        2. subtitles   usually. Free, instant, and exact where the creator
                       published them or YouTube auto-generated them.
        3. whisper     rarely. Downloads the audio and transcribes it locally,
                       which takes minutes but always works.

    An earlier version scraped the watch page with regexes and asked the bare
    timedtext endpoint for captions. Both broke: the page truncated before the
    description, and YouTube answers unsigned caption requests with zero bytes
    however the URL is signed. yt-dlp handles all of it and keeps handling it
    when YouTube changes, which it will.
    """
    vid = youtube_id(url)
    if not vid:
        raise SourceError("that does not look like a YouTube video link")
    try:
        import yt_dlp
    except ImportError:
        raise SourceError(
            "reading YouTube links needs yt-dlp (pip install yt-dlp). Open the "
            "video, use Show transcript, and paste the text instead.")

    notes, parts = [], []
    workdir = tempfile.mkdtemp(prefix="tonecommand-src-")
    try:
        info = _yt_info(yt_dlp, url, workdir)
        title = info.get("title") or ""
        duration = info.get("duration") or 0

        description = (info.get("description") or "").strip()
        if description:
            parts.append(f"VIDEO DESCRIPTION:\n{description}")
        else:
            notes.append("this video has no description text")

        subs = _subtitle_text(workdir)
        if subs:
            parts.append(f"SPOKEN TRANSCRIPT:\n{subs}")
        else:
            spoken, note = _whisper_transcript(yt_dlp, url, workdir, duration)
            if spoken:
                parts.append(f"SPOKEN TRANSCRIPT (transcribed here):\n{spoken}")
            if note:
                notes.append(note)
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError(f"could not read that video ({exc})")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if not parts:
        raise SourceError(
            "nothing readable came back from that video: no description, no "
            "captions, and no transcript. Paste the relevant text instead.")
    return {"text": "\n\n".join(parts)[:MAX_SOURCE], "title": title,
            "notes": notes, "kind": "youtube", "url": url}


def _yt_info(yt_dlp, url: str, workdir: str) -> dict:
    """Metadata, and subtitles written alongside it in one pass."""
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "noprogress": True, "consoletitle": False,
        "writesubtitles": True, "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"], "subtitlesformat": "vtt",
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as y:
        return y.extract_info(url, download=True)


def _subtitle_text(workdir: str) -> str:
    """VTT on disk becomes plain prose.

    Cues, timestamps and the WEBVTT header all go. Auto-generated captions
    also repeat each line as they roll, so consecutive duplicates are dropped:
    left in, a forty minute video arrives as eighty minutes of text saying
    everything twice.
    """
    files = [f for f in os.listdir(workdir) if f.endswith(".vtt")]
    if not files:
        return ""
    raw = pathlib.Path(workdir, sorted(files)[0]).read_text(
        encoding="utf-8", errors="replace")
    out, last = [], None
    for line in raw.splitlines():
        line = line.strip()
        if (not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or "-->" in line or line.isdigit()):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and line != last:
            out.append(line)
            last = line
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def whisper_ready() -> tuple[bool, str]:
    """Whether transcribing can happen at all, and what is missing if not.

    Called before the slow path starts so the UI can say "this will take a few
    minutes and download a model the first time" rather than going quiet.
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False, "faster-whisper is not installed"
    if not shutil.which("ffmpeg"):
        return False, "ffmpeg is not installed"
    import pathlib as _pl
    cached = list((_pl.Path.home() / ".cache/huggingface/hub").glob(
        f"models--*whisper-{whisper_model_name()}"))
    if not cached:
        return True, ("first run will download the whisper model, about 150MB")
    return True, ""


def _whisper_transcript(yt_dlp, url: str, workdir: str,
                        duration: int) -> tuple[str, str]:
    """Download the audio and transcribe it locally. The last resort.

    Returns (text, note). A note without text is the reason there is none, and
    it is always something the player can act on.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return "", ("this video has no captions and faster-whisper is not "
                    "installed, so only the description was read. Either pip "
                    "install faster-whisper, or open the video, use Show "
                    "transcript, and paste the text here.")
    # ffmpeg is a SYSTEM dependency and pip cannot install it, so a clone that
    # ran `pip install -e ".[video]"` and stopped there still fails here. It
    # fails inside a yt-dlp postprocessor too, which surfaces as something
    # about "ffprobe/ffmpeg not found" buried in a download error. Checked up
    # front so the message names the actual missing thing.
    if not shutil.which("ffmpeg"):
        return "", ("this video has no captions, and transcribing needs ffmpeg, "
                    "which is not installed. Install it (brew install ffmpeg, "
                    "or apt install ffmpeg), or open the video, use Show "
                    "transcript, and paste the text here.")
    if duration and duration > WHISPER_MAX_SECONDS:
        return "", (f"this video has no captions and runs "
                    f"{duration // 60} minutes, which is too long to "
                    f"transcribe here. Paste the part that describes the tone "
                    f"instead.")
    audio = os.path.join(workdir, "audio.mp3")
    opts = {"quiet": True, "no_warnings": True, "noprogress": True,
            "format": "bestaudio/best",
            "outtmpl": os.path.join(workdir, "audio.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": "64"}]}
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])
    except Exception as exc:
        return "", f"could not download this video's audio to transcribe ({exc})"
    if not os.path.exists(audio):
        return "", "could not extract audio from this video to transcribe"
    try:
        # First run downloads the model, about 150MB for base, with no output
        # of its own. Silence for two minutes on a fresh clone reads as a
        # hang, so the caller is told before it starts rather than after.
        model = WhisperModel(whisper_model_name(), device="cpu",
                             compute_type="int8")
        # NO vad_filter. It silently returned zero segments for a whole video
        # here, which reads as "this video has no speech" and is a far worse
        # failure than transcribing a few seconds of music.
        segments, _ = model.transcribe(audio, language="en")
        text = " ".join(seg.text.strip() for seg in segments)
    except Exception as exc:
        return "", f"could not transcribe this video's audio ({exc})"
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "", "transcribing this video produced no speech"
    return text, ""


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

"""Building a tone from a video, a page, or pasted text.

The point is to remove work: paste a link to somebody's "here's my worship
rig" video and get a plan for YOUR FM9, instead of watching forty minutes and
typing settings out.

This is an INPUT METHOD and nothing more. It produces the same action list
/api/plan produces, gets the same validation, lands in the same confirm panel,
and is transmitted by the same gate. These tests exist mostly to prove that
sentence stays true, because a new entry point is exactly where a safety
pipeline gets quietly bypassed.
"""
import inspect
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import describe, planner
from fm9.sim import SimFM9

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


# --- the new entry point cannot skip a single gate -------------------------

def test_it_runs_the_same_validation_as_every_other_plan():
    """Not a lighter version, and not a copy that can drift: the same
    validate_action, called the same way."""
    src = inspect.getsource(server.api_describe_build)
    assert "validate_action(Action(**a))" in src
    assert 'a["validation_errors"] = errs' in src
    assert 'a["validation_warnings"] = warns' in src


def test_it_cannot_transmit(client):
    """It proposes. The confirm panel and /api/apply are unchanged and are
    still the only way anything reaches hardware."""
    src = inspect.getsource(server.api_describe_build)
    for forbidden in ("run_action", "/api/apply", "fm9.set_", "store_preset"):
        assert forbidden not in src, forbidden


def test_a_build_from_someone_elses_source_may_not_store(client, monkeypatch):
    """The one destructive action in the product. Asked for in the brief AND
    dropped from the result, because asking a model not to do something is not
    the same as it not happening."""
    assert describe.FORBIDDEN_KINDS == {"store"}
    assert "Do not store to any preset slot." in describe.brief_from(
        {"summary": "x", "scenes": [], "stated": [], "vague": []})

    monkeypatch.setattr(planner, "plan", lambda *a, **k: {
        "summary": "s", "actions": [
            {"kind": "set_param", "block": "amp", "instance": 1,
             "param": "DISTORT_MID", "value": 6},
            {"kind": "store", "block": "PRESET", "instance": 1, "value": 12}]})
    r = client.post("/api/describe/build", json={"spec": {"summary": "s"}}).json()
    kinds = [a["kind"] for a in r["actions"]]
    assert "store" not in kinds
    assert r["dropped"] == ["store"]


def test_the_store_whitelist_is_untouched_by_this_path():
    """It is enforced in device.store_preset, which this path never reaches."""
    src = inspect.getsource(server.api_describe_build)
    assert "get_store_slots" not in src


def test_the_longer_timeout_is_restored_and_scoped_to_the_lock():
    """Raised for this path only. Left raised, a later /api/plan would inherit
    a fifteen minute timeout; raised outside the lock, a concurrent plan would
    have its own restored out from under it."""
    src = inspect.getsource(server.api_describe_build)
    lock_at = src.index("with _settings_lock:")
    set_at = src.index('_os.environ["PLANNER_TIMEOUT"]')
    assert lock_at < set_at, "the timeout must be raised inside the lock"
    assert "finally:" in src
    assert '_os.environ.pop("PLANNER_TIMEOUT", None)' in src


def test_the_timeout_has_real_headroom():
    """A four scene build measured 226s, which the stock 180s refuses. Sized
    for bigger builds rather than tuned to the one that was measured."""
    assert describe.timeout_s() >= 600
    assert describe.timeout_s() > planner.timeout_s()


# --- the two pass shape, which is not a preference -------------------------

def test_reading_and_building_are_separate_endpoints():
    """A raw source handed straight to the planner produced no reply within
    180s, on a backend that answers a short prompt in eight. The split is what
    makes the feature work at all, and it is also what makes the wait legible."""
    routes = {r.path for r in server.app.routes if getattr(r, "methods", None)}
    assert "/api/describe/read" in routes
    assert "/api/describe/build" in routes


def test_the_brief_is_prose_and_says_why():
    """Handed the same content as labelled lists, the model refused it:
    "two pasted, unrelated pieces of content rather than a direct instruction".
    This is the fix, and the comment is there so nobody tidies it back."""
    spec = {"summary": "a clean and a lead",
            "scenes": [{"n": 1, "name": "Clean", "describes": "chimey"},
                       {"n": 2, "name": "Lead", "describes": "pushed"}],
            "stated": ["gain 4", "treble 6"], "vague": ["crank it"]}
    brief = describe.brief_from(spec)
    assert brief.startswith("Build this rig across 2 scenes:")
    assert "\n" not in brief, "newlines make it read as a pasted document"
    assert "- " not in brief, "bullets are what the model refused"
    assert "gain 4; treble 6." in brief
    doc = inspect.getdoc(describe.brief_from)
    assert "unrelated pieces of content" in doc
    assert "do not" in doc.lower()


# --- honesty: what the source said versus what this chose ------------------

def test_the_split_survives_to_the_confirm_panel(client, monkeypatch):
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": []})
    spec = {"summary": "a rig", "stated": ["gain 4"], "vague": ["crank it"],
            "quotes": [{"about": "gain", "text": "gain around 4", "at": "3:20"}],
            "source": {"kind": "youtube", "url": "u", "title": "t", "notes": []}}
    r = client.post("/api/describe/build", json={"spec": spec}).json()
    assert r["from_source"]["stated"] == ["gain 4"]
    assert r["from_source"]["vague"] == ["crank it"]
    assert r["from_source"]["quotes"][0]["at"] == "3:20"


def test_the_browser_keeps_them_visually_apart():
    fn = SCRIPT.split("function srcSplitHtml(from)")[1].split("\n}\n")[0]
    assert "The source specified these" in fn
    assert "These were vague, so this is my choice" in fn
    assert 'class="said"' in fn and 'class="guessed"' in fn


def test_the_copy_calls_it_an_interpretation_not_a_copy():
    assert "This is my interpretation of what" in SCRIPT
    assert "gets you in the ballpark: review and tweak" in SCRIPT
    assert "An interpretation to review and\n      tweak, not a copy" in UI


def test_the_framing_comes_before_the_summary():
    """A multi-scene summary runs to hundreds of words. Provenance read at the
    end of that is provenance nobody read."""
    assert "$('plansummary').before(note);" in SCRIPT
    assert "$('plansummary').after(note);" not in SCRIPT


def test_the_source_note_does_not_outlive_its_plan():
    """Plan extras are per plan. Left behind, the next plan would carry the
    previous source's provenance, which is worse than carrying none."""
    assert "const prevSrc = $('plansrc'); if (prevSrc) prevSrc.remove();" in SCRIPT


# --- progress, because the build really does take minutes ------------------

def test_the_wait_has_a_shape():
    """Four minutes of an apparently hung UI is a broken experience even when
    it is working."""
    assert "const SRC_STEPS" in SCRIPT
    fn = SCRIPT.split("function srcProgress(active, note)")[1].split("\n}\n")[0]
    assert "box.hidden = false" in fn
    steps = SCRIPT.split("const SRC_STEPS = [")[1].split("];")[0]
    for label in ("Reading the source", "Working out what tone it describes",
                  "Building it against your rig"):
        assert label in steps


def test_it_says_what_it_found_before_the_slow_part():
    """The whole reason for two calls: the player learns the source was
    understood in about twenty seconds, rather than after four minutes."""
    fn = SCRIPT.split("async function analyzeSource()")[1].split("\n}\n")[0]
    assert fn.index("srcProgress('build', note)") < fn.index("/api/describe/build")
    assert "settings stated in the source" in fn


# --- reading sources ------------------------------------------------------

@pytest.mark.parametrize("url,vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://example.com/forum/thread/1", None),
])
def test_youtube_links_are_recognised(url, vid):
    assert describe.youtube_id(url) == vid


def test_pasted_text_needs_to_say_something():
    with pytest.raises(describe.SourceError, match="too short"):
        describe.read_source("nice tone")
    with pytest.raises(describe.SourceError, match="paste a link"):
        describe.read_source("   ")


def test_pasted_text_is_used_as_is():
    got = describe.read_source("Scene one is a Matchless clean with the gain "
                               "around four and a large hall reverb at 25%")
    assert got["kind"] == "text" and got["url"] is None


def test_a_source_with_no_tone_information_is_not_fabricated(client, monkeypatch):
    """The refusal that matters. A video that never states a setting must not
    produce a confident tone."""
    monkeypatch.setattr(describe, "read_source",
                        lambda raw: {"text": "x" * 100, "title": "", "notes": [],
                                     "kind": "text", "url": None})
    monkeypatch.setattr(describe, "extract",
                        lambda text: {"found": False, "why": "this is a live "
                                      "performance with no gear discussion"})
    r = client.post("/api/describe/read", json={"source": "a" * 100})
    assert r.status_code == 422
    assert "no gear discussion" in r.json()["error"]


def test_a_source_that_cannot_be_read_says_so_plainly(client, monkeypatch):
    """Never fail silently, and always leave a way forward."""
    monkeypatch.setattr(describe, "read_source", lambda raw: (_ for _ in ()).throw(
        describe.SourceError("could not fetch that page (403). Open it, copy "
                             "the part that describes the tone, and paste it "
                             "here instead.")))
    r = client.post("/api/describe/read", json={"source": "https://x.example/a"})
    assert r.status_code == 400
    assert "paste it here instead" in r.json()["error"]


def test_the_description_is_the_half_that_actually_works():
    """Verified against a real video: the description comes back, the captions
    do not. YouTube gates caption fetching behind signals a server-side
    request does not carry, and the signed baseUrls in the page's own
    captionTracks return zero bytes in every format tried.

    Creators list gear in the description in a tidy block anyway, where the
    spoken version is scattered through forty minutes, so a description alone
    is frequently enough to build from.
    """
    src = inspect.getsource(describe.read_youtube)
    assert "VIDEO DESCRIPTION" in src and "SPOKEN TRANSCRIPT" in src


def test_captions_are_tried_before_transcribing():
    """Subtitles are free and instant where they exist. Whisper downloads
    audio and burns CPU for minutes, so it is the fallback and not the
    default."""
    src = inspect.getsource(describe.read_youtube)
    assert src.index("_subtitle_text") < src.index("_whisper_transcript")


def test_when_whisper_cannot_run_the_note_says_what_to_do():
    """Never a dead end. Every reason there is no transcript comes with the
    two click alternative that always works."""
    src = inspect.getsource(describe._whisper_transcript)
    assert "faster-whisper is not" in src
    assert "Show" in src and "transcript" in src
    assert "too long to" in src


def test_a_transcript_this_tool_produced_is_labelled_as_such():
    """The extractor should know it is reading machine heard speech rather
    than the creator's own captions, because gear names come out of it
    mangled."""
    src = inspect.getsource(describe.read_youtube)
    assert "SPOKEN TRANSCRIPT (transcribed here)" in src


def test_the_vad_filter_stays_off_and_says_why():
    """It silently returned zero segments for an entire video here, which
    reads as "this video has no speech" and is a far worse failure than
    transcribing a few seconds of music."""
    src = inspect.getsource(describe._whisper_transcript)
    assert "vad_filter" not in src.replace("# NO vad_filter", "")
    assert "NO vad_filter" in src


def test_auto_caption_duplicates_are_dropped():
    """Auto-generated captions repeat each line as they roll. Left in, a forty
    minute video arrives as eighty minutes of text saying everything twice."""
    src = inspect.getsource(describe._subtitle_text)
    assert "line != last" in src


def test_the_whisper_model_is_configurable_with_a_documented_default():
    """base is 14.7x realtime here and small is 5.4x. base mishears gear
    names, which matters less than it looks because the extraction pass
    repairs them from context and grounding refuses what it cannot resolve."""
    assert describe.whisper_model_name() == "base"
    import os
    os.environ["TONECOMMAND_WHISPER_MODEL"] = "small"
    try:
        assert describe.whisper_model_name() == "small"
    finally:
        os.environ.pop("TONECOMMAND_WHISPER_MODEL")


def test_there_is_a_length_past_which_transcribing_is_the_wrong_trade():
    assert 1800 <= describe.WHISPER_MAX_SECONDS <= 10800


def test_the_extractor_is_told_not_to_invent_settings():
    assert '"stated" is ONLY what the source says' in describe.EXTRACT_TASK
    assert "Never add a setting it did not give" in describe.EXTRACT_TASK
    assert "Do not resolve gear to model names" in describe.EXTRACT_TASK


# --- what a fresh clone gets ----------------------------------------------

def test_the_base_install_can_still_use_the_field():
    """Pasted text and page URLs need nothing beyond the base package. Only
    YouTube needs the extras, so the feature must not present itself as
    all-or-nothing."""
    got = describe.read_source("Scene one is a Matchless clean with the gain "
                               "at four and a large hall reverb at 25 percent")
    assert got["kind"] == "text"


def test_the_video_dependencies_are_an_optional_extra():
    """Declared, not required. CI installs only [dev] and the whole suite
    passes, which is the proof."""
    toml = (ROOT / "pyproject.toml").read_text()
    assert "video = [" in toml
    assert "yt-dlp" in toml and "faster-whisper" in toml
    deps = toml.split("dependencies = [")[1].split("]")[0]
    assert "yt-dlp" not in deps and "faster-whisper" not in deps


def test_ffmpeg_is_checked_by_name_rather_than_failing_inside_yt_dlp():
    """pip cannot install it, so a clone that ran the extra and stopped there
    still fails. Inside a yt-dlp postprocessor it surfaces as something about
    ffprobe buried in a download error."""
    src = inspect.getsource(describe._whisper_transcript)
    assert 'shutil.which("ffmpeg")' in src
    assert "brew install ffmpeg" in src
    ffmpeg_at = src.index('shutil.which("ffmpeg")')
    download_at = src.index("y.download")
    assert ffmpeg_at < download_at, "check before spending the download"


def test_the_machine_says_what_it_can_read_before_anything_is_pasted():
    """Better than a four minute wait ending in a missing dependency."""
    routes = {r.path for r in server.app.routes if getattr(r, "methods", None)}
    assert "/api/describe/ready" in routes
    ok, why = describe.whisper_ready()
    assert isinstance(ok, bool) and isinstance(why, str)
    assert "$('srchint').innerHTML +=" in SCRIPT
    assert "Pasting text or a page link works either way" in SCRIPT


def test_the_readme_documents_the_system_dependency():
    """ffmpeg cannot be declared in pyproject, so the README is the only place
    a cloner can learn about it."""
    readme = (ROOT / "README.md").read_text()
    assert 'pip install -e ".[video]"' in readme
    assert "brew install ffmpeg" in readme
    assert "pip cannot install it" in readme


# --- and how it scales ----------------------------------------------------

def test_long_sources_are_handled_by_compression_not_patience():
    """The point that makes hour-long walkthroughs viable: the expensive build
    pass never sees the transcript. Measured on a 5,286 word walkthrough, the
    brief came out at 282 words with all twelve tone statements kept and the
    sponsor read dropped."""
    spec = {"summary": "a rig", "scenes": [{"n": 1, "name": "Clean",
            "describes": "chimey"}], "stated": ["gain 4"] * 30, "vague": []}
    brief = describe.brief_from(spec)
    assert len(brief.split()) < 400, "the brief must stay small whatever came in"


def test_there_is_a_ceiling_on_what_will_be_read():
    """A source has to end somewhere, and silently truncating mid sentence is
    better than a request that never returns."""
    assert describe.MAX_SOURCE >= 100_000
    huge = "word " * 200_000
    got = describe.read_source(huge)
    assert len(got["text"]) <= describe.MAX_SOURCE

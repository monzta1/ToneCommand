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
    validate_action, called the same way. The body moved into
    _describe_build_for so the streaming twin cannot drift from the blocking
    one, which is the same one-body-two-deliveries rule /api/plan follows."""
    src = inspect.getsource(server._describe_build_for)
    assert "validate_action(Action(**a))" in src
    assert 'a["validation_errors"] = errs' in src
    assert 'a["validation_warnings"] = warns' in src
    for endpoint in (server.api_describe_build,
                     server.api_describe_build_stream):
        assert "_describe_build_for(" in inspect.getsource(endpoint), \
            endpoint.__name__


def _code_only(src: str) -> str:
    """`src` with its comments removed, everything else byte for byte."""
    import io
    import tokenize
    out, prev = [], (1, 0)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.start[0] != prev[0]:
            prev = (tok.start[0], 0)
        if tok.type != tokenize.COMMENT:
            out.append(" " * max(0, tok.start[1] - prev[1]) + tok.string)
        prev = tok.end
    return "".join(out)

def test_it_cannot_transmit(client):
    """It proposes. The confirm panel and /api/apply are unchanged and are
    still the only way anything reaches hardware."""
    # Comments stripped first. A scan of raw text calls a comment EXPLAINING
    # that this path cannot reach run_action a violation, which pushes the
    # next person to delete the comment rather than keep the guard honest.
    # Strings are left intact, because "/api/apply" would only ever appear as
    # one.
    src = _code_only(inspect.getsource(server.api_describe_build))
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
    have its own restored out from under it. The lock is taken through
    _hold_settings now, so waiting behind a previous request is said instead
    of suffered, and released in a finally."""
    src = inspect.getsource(server._describe_build_for)
    lock_at = src.index("_hold_settings(")
    set_at = src.index('_os.environ["PLANNER_TIMEOUT"]')
    release_at = src.index("_settings_lock.release()")
    assert lock_at < set_at < release_at, \
        "the timeout must be raised inside the held lock"
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
    # Whitespace-insensitive: the copy is wrapped for readability and its
    # indentation moved when the panel was folded into a <details>. Pinning
    # the line breaks pins the layout, which is not the claim being made.
    assert "An interpretation to review and tweak, not a copy" in \
        " ".join(UI.split())


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
    understood in about twenty seconds, rather than after four minutes.

    The slow half now sits behind the questions, in runBuild, so the gap is
    wider still: reading, then what was found, then the questions, and only
    then the wait.
    """
    fn = SCRIPT.split("async function analyzeSource()")[1].split("\n}\n")[0]
    assert "srcProgress('found', note)" in fn
    assert "settings stated in the source" in fn
    assert "/api/describe/build" not in fn
    build = SCRIPT.split("async function runBuild(spec, note)")[1].split("\n}\n")[0]
    assert build.index("srcProgress('build', note)") < build.index(
        "/api/describe/build")


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


# --- asking, rather than going ahead --------------------------------------

def test_the_scene_count_is_the_owners_call_not_the_sources():
    """A rig tour describes four scenes because the player in it runs four.
    Somebody who wants one lead sound should get one, and building the wrong
    shape and calling it an interpretation is not the same as asking."""
    spec = {"summary": "a clean and a lead", "stated": [], "vague": [],
            "scenes": [{"n": 1, "name": "Clean", "describes": "chimey"},
                       {"n": 2, "name": "Lead", "describes": "pushed"},
                       {"n": 3, "name": "Ambient", "describes": "washy"}]}
    assert "across 3 scenes" in describe.brief_from(spec)
    one = describe.brief_from(spec, scenes=1)
    assert "SINGLE scene" in one and "do not set up any other scene" in one
    assert "Scene 2" not in one and "Scene 3" not in one


def test_a_name_reaches_the_builder_and_names_the_scenes_too():
    """Scene names were inherited from the preset underneath and nobody was
    told, so a Petrucci build shipped with scenes called Cron-chay."""
    b = describe.brief_from({"summary": "x", "scenes": [], "stated": [],
                             "vague": []}, name="Lukather Lead")
    assert "Name the preset 'Lukather Lead'" in b
    assert "name each scene you set up after what it is for" in b


def test_the_build_endpoint_takes_the_answers(client, monkeypatch):
    captured = {}

    def fake(prompt, *a, **k):
        captured["p"] = prompt
        return {"summary": "s", "actions": []}

    monkeypatch.setattr(planner, "plan", fake)
    client.post("/api/describe/build",
                json={"spec": {"summary": "a rig", "scenes": [{"n": 1, "name": "Clean"}]},
                      "scenes": 1, "name": "My Tone"})
    assert "SINGLE scene" in captured["p"]
    assert "My Tone" in captured["p"]


# --- and saying what it will NOT touch ------------------------------------

def test_the_plan_names_what_it_leaves_alone(client, monkeypatch):
    """The failure this exists to stop. A store writes the whole edit buffer
    rather than the changes, so a build that touched three blocks of thirteen
    was saved under a name claiming the whole rig, with the cabinet, which
    shapes the sound as much as the head does, coming from the preset
    underneath.
    """
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": [
        {"kind": "set_param", "block": "amp", "instance": 1,
         "param": "DISTORT_MID", "value": 6}]})
    r = client.post("/api/describe/build", json={"spec": {"summary": "x"}}).json()
    assert "Cab 1" in r["inherits"], r["inherits"]
    assert not any(x.startswith("Amp") for x in r["inherits"]), \
        "a block the build changed is not inherited"


def test_the_browser_shows_that_before_the_transmit_button():
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "function inheritsHtml(plan)" in ui
    fn = ui.split("function inheritsHtml(plan)")[1].split("\n}\n")[0]
    assert "keeps whatever" in fn and "If you save this" in fn
    assert ui.count("inheritsHtml(plan)") >= 2, "computed but never rendered"


def test_the_questions_come_between_reading_and_building():
    ui = (ROOT / "ui" / "index.html").read_text()
    script = ui.split("<script>")[1]
    fn = script.split("async function analyzeSource()")[1].split("\n}\n")[0]
    assert "askAboutBuild(spec, note)" in fn
    assert "/api/describe/build" not in fn, "building must wait for the answers"
    ask = script.split("function askAboutBuild(spec, note)")[1].split("\n}\n")[0]
    assert "Scenes to build" in ask and "Name it" in ask
    assert "Building on top of" in ask


def test_the_suggested_name_does_not_trail_off():
    """"A Matchless clean into" is worse than no suggestion: it reads as a
    mistake and invites being accepted unread."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function suggestName(spec)")[1].split("\n}\n")[0]
    assert "stop.test(words[0])" in fn, "no leading article"
    assert "stop.test(out[out.length - 1])" in fn, "no trailing preposition"


# --- and naming what it stores --------------------------------------------

def test_the_name_you_gave_is_applied_not_merely_requested(client, monkeypatch):
    """Asking the planner to rename is not the same as renaming. The buffer
    keeps the loaded preset's name until something changes it, and a store
    writes that name into flash where it becomes the only label anyone has."""
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": [
        {"kind": "set_param", "block": "amp", "instance": 1,
         "param": "DISTORT_MID", "value": 6}]})
    r = client.post("/api/describe/build",
                    json={"spec": {"summary": "x"}, "name": "Lukather Lead"}).json()
    first = r["actions"][0]
    assert first["kind"] == "rename_preset"
    assert first["type_name"] == "Lukather Lead"
    assert not first["validation_errors"], first["validation_errors"]


def test_it_does_not_fight_the_planner_over_the_name(client, monkeypatch):
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": [
        {"kind": "rename_preset", "block": "PRESET", "instance": 1,
         "type_name": "Its Own Idea"}]})
    r = client.post("/api/describe/build",
                    json={"spec": {"summary": "x"}, "name": "Mine"}).json()
    assert len([a for a in r["actions"] if a["kind"] == "rename_preset"]) == 1


def test_no_name_means_no_rename(client, monkeypatch):
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": []})
    for body in ({"spec": {"summary": "x"}}, {"spec": {"summary": "x"}, "name": "  "}):
        r = client.post("/api/describe/build", json=body).json()
        assert not any(a["kind"] == "rename_preset" for a in r["actions"])


def test_a_long_name_survives_the_fm9ai_prefix(client, monkeypatch):
    """run_action prepends "FM9AI-" and truncates at 32, so a name accepted
    here can still arrive at the device cut in half."""
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {"summary": "s", "actions": []})
    r = client.post("/api/describe/build",
                    json={"spec": {"summary": "x"},
                          "name": "A" * 60}).json()
    name = r["actions"][0]["type_name"]
    assert len(("FM9AI-" + name)) <= 32, name


def test_saving_says_the_name_it_saves_under():
    """It said which slot it would overwrite but never what the preset would
    be called afterwards, which is how a Petrucci build went into flash under
    the previous preset's name."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function saveToSlot")[1].split("\n}\n")[0]
    assert "It will be saved under the name" in fn
    assert "lastState.preset" in fn
    assert "cancel and rename it first" in fn


# --- the wait has a shape now ----------------------------------------------
#
# This path measured 226 seconds for a four scene build and used to show a
# static "Building it against your rig..." the whole way: the exact
# frozen-spinner failure /api/plan/stream was built to end, rebuilt behind a
# different button. These prove the streaming twins actually stream.

def test_the_build_stream_counts_and_delivers(client, monkeypatch):
    monkeypatch.setattr(planner, "plan_stream", lambda *a, **k: iter([
        ("count", {"n": 1, "kind": "set_param"}),
        ("done", {"summary": "s", "actions": []})]))
    with client.stream("POST", "/api/describe/build/stream",
                       json={"spec": {"summary": "x"}}) as r:
        body = "".join(r.iter_text())
    assert "event: count" in body
    assert '"n": 1' in body
    assert "event: plan" in body


def test_the_read_stream_narrates_its_stages(client, monkeypatch):
    def fake_read(raw, on_stage=None):
        on_stage("fetch", "fetching the page")
        return {"text": "enough words to pass " * 10, "title": "t",
                "notes": [], "kind": "text", "url": None}

    monkeypatch.setattr(describe, "read_source", fake_read)
    monkeypatch.setattr(describe, "extract",
                        lambda text, cancel=None: {
                            "found": True, "summary": "s", "scenes": [],
                            "stated": [], "vague": [], "quotes": []})
    with client.stream("POST", "/api/describe/read/stream",
                       json={"source": "https://x.example/a"}) as r:
        body = "".join(r.iter_text())
    assert "event: stage" in body
    assert "fetching the page" in body
    # the extract stage is announced by the endpoint itself
    assert "working out what tone it describes" in body
    assert "event: spec" in body


def test_a_source_the_reader_refuses_streams_a_readable_error(client, monkeypatch):
    monkeypatch.setattr(describe, "read_source",
                        lambda raw, on_stage=None: (_ for _ in ()).throw(
                            describe.SourceError("nothing readable there")))
    with client.stream("POST", "/api/describe/read/stream",
                       json={"source": "https://x.example/a"}) as r:
        body = "".join(r.iter_text())
    assert "event: error" in body
    assert "nothing readable there" in body


def test_the_ui_build_goes_through_the_stream(client):
    build = SCRIPT.split("async function runBuild(spec, note)")[1].split("\n}\n")[0]
    assert "/api/describe/build/stream" in build
    assert "srcWork" in build, "the sticky working strip must light"
    read = SCRIPT.split("async function analyzeSource()")[1].split("\n}\n")[0]
    assert "/api/describe/read/stream" in read

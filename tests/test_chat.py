"""Talking a tone through before planning it.

A tone is an opinion, and the first sentence somebody types is rarely the one
they mean. "Warmer" from a player chasing a Dumble and "warmer" from one
chasing a Vox are different edits.

The property that matters most here is a negative one: conversation adds NO
path to the hardware. It produces a better sentence, and that sentence goes
through the same planner, validator and confirm gate as one typed straight in.
"""
import inspect
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import planner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", None, raising=False)
    return TestClient(server.app)


def _reply(**over):
    base = {"reply": "Is it woolly on the lows, or spiky up top?",
            "ready": False, "request": ""}
    base.update(over)
    return base


# --- it cannot reach the rig ----------------------------------------------

def test_conversation_has_no_path_to_hardware():
    src = inspect.getsource(planner.converse)
    for forbidden in ("run_action", "apply", "set_param", "store", "fm9."):
        assert forbidden not in src, forbidden


def test_the_endpoint_only_talks(client, monkeypatch):
    monkeypatch.setattr(planner, "converse", lambda *a, **k: _reply())
    d = client.post("/api/chat", json={"messages": [
        {"role": "user", "content": "warmer"}]}).json()
    assert "actions" not in d, "conversation must never carry actions"


def test_the_chat_schema_cannot_express_an_action():
    assert set(planner.CHAT_SCHEMA["properties"]) == {
        "reply", "ready", "request", "name"}
    assert planner.CHAT_SCHEMA["additionalProperties"] is False


# --- it is grounded in the actual rig -------------------------------------

def test_it_gets_the_same_device_state_the_planner_does(client, monkeypatch):
    seen = {}

    def fake(messages, state, ref):
        seen["state"] = state
        seen["ref"] = ref
        return _reply()

    monkeypatch.setattr(planner, "converse", fake)
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert seen["ref"] is server.PARAM_REFERENCE
    assert isinstance(seen["state"], str) and seen["state"]


# --- the conversation itself ----------------------------------------------

def test_both_sides_reach_the_model(monkeypatch):
    seen = {}

    def fake_ask(prompt, state, ref, **kw):
        seen["prompt"] = prompt
        seen["kw"] = kw
        return _reply(), "cli", "m", []

    monkeypatch.setattr(planner, "_ask_backends", fake_ask)
    planner.converse([{"role": "user", "content": "warmer"},
                      {"role": "assistant", "content": "warmer how?"},
                      {"role": "user", "content": "like a Dumble"}], "state", "ref")
    assert "Guitarist: warmer" in seen["prompt"]
    assert "You: warmer how?" in seen["prompt"]
    assert "Guitarist: like a Dumble" in seen["prompt"]
    assert seen["kw"]["schema"] is planner.CHAT_SCHEMA


def test_a_long_argument_does_not_grow_without_bound(monkeypatch):
    seen = {}
    monkeypatch.setattr(planner, "_ask_backends",
                        lambda p, s, r, **k: (seen.update(p=p), (_reply(), "cli", "m", []))[1])
    planner.converse([{"role": "user", "content": f"m{i}"} for i in range(90)],
                     "state", "ref")
    assert seen["p"].count("Guitarist:") <= 24


def test_an_empty_conversation_is_refused(client):
    assert client.post("/api/chat", json={"messages": []}).status_code == 400


def test_a_reply_with_nothing_in_it_is_a_failure(monkeypatch):
    monkeypatch.setattr(planner, "_ask_backends",
                        lambda *a, **k: (_reply(reply="   "), "cli", "m", []))
    with pytest.raises(RuntimeError, match="nothing to say"):
        planner.converse([{"role": "user", "content": "hi"}], "s", "r")


def test_ready_carries_the_agreed_sentence(monkeypatch):
    monkeypatch.setattr(planner, "_ask_backends", lambda *a, **k: (
        _reply(ready=True, request="Add focused mids to the JP-2C."),
        "cli", "m", []))
    out = planner.converse([{"role": "user", "content": "hi"}], "s", "r")
    assert out["ready"] is True
    assert out["request"] == "Add focused mids to the JP-2C."


# --- one loop, not two ----------------------------------------------------

def test_planning_and_talking_share_the_fallthrough():
    """Two copies of the backend loop drift, and the failure taxonomy is the
    part that would drift silently."""
    assert "_ask_backends(" in inspect.getsource(planner.plan)
    assert "_ask_backends(" in inspect.getsource(planner.converse)


def test_validation_still_runs_inside_the_retry_loop():
    """A reply can parse as JSON and still be shaped wrongly enough to raise
    ({"actions": 42} is valid JSON and a truthy non-iterable). That is a
    backend failing, not a reason to abandon the remaining candidates."""
    src = inspect.getsource(planner._ask_backends)
    body = src.split("try:")[1].split("except BackendFailure")[0]
    assert "validate(raw)" in body


def test_a_backend_that_returns_a_non_object_falls_through(monkeypatch):
    calls = []

    def bad(*a, **k):
        calls.append("bad")
        return ["not an object"], "m"

    def good(*a, **k):
        calls.append("good")
        return _reply(), "m"

    monkeypatch.setattr(planner, "candidates", lambda: ["cli", "api"])
    monkeypatch.setattr(planner, "_RUNNERS", {"cli": bad, "api": good})
    out = planner.converse([{"role": "user", "content": "hi"}], "s", "r")
    assert calls == ["bad", "good"]
    assert out["backend"] == "api"


# --- the browser ----------------------------------------------------------

def test_there_is_one_action_in_the_prompt_row():
    """Two buttons meant choosing, before typing a word, whether your own
    request was clear enough to skip the conversation. Nobody knows that
    about their own request."""
    ui = (ROOT / "ui" / "index.html").read_text()
    row = ui.split('<div class="promptrow">')[1].split("</div>")[0]
    assert row.count("<button") == 1
    assert 'id="engage">SEND<' in row
    assert "TALK IT OVER" not in ui


def test_send_and_enter_both_talk():
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "$('engage').onclick = talk;" in ui
    fn = ui.split("$('prompt').addEventListener('keydown'")[1].split("});")[0]
    assert "talk();" in fn


def test_building_takes_the_sentence_rather_than_the_input_box():
    """Pasting a long agreed sentence into a one-line box showed the reader
    the middle of their own request, scrolled sideways, and nothing else."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "$('cbuild').onclick = () => engage(chatRequest, chatName);" in ui
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "$('prompt').value" not in fn, "building must not touch the input"
    assert "/api/plan" in fn, "and it still goes through the ordinary planner"


def test_a_planner_question_lands_in_the_conversation_not_in_red():
    """The planner has always been able to ask (PLAN_SCHEMA.clarification).
    The UI printed the question as an error and hid the panel, leaving it
    nowhere to be answered. The conversation is where a question belongs."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "chatLog.push({role: 'assistant', content: plan.clarification})" in fn
    assert "needs clarification" not in fn, "no longer logged as an error"


def test_the_examples_step_aside_once_a_conversation_starts():
    """They teach the vocabulary to somebody staring at an empty panel. Once
    there is an exchange to read they are clutter under it. They now live
    INSIDE the empty state, so they leave with it rather than needing their
    own rule to remember."""
    ui = (ROOT / "ui" / "index.html").read_text()
    empty = ui.split('id="cempty"')[1].split("</div>\n      <div")[0]
    assert 'id="egs"' in empty
    assert "$('cempty').hidden = !!chatLog.length;" in ui


def test_a_working_button_keeps_its_word():
    """A spinner INSTEAD of the label leaves an unexplained circle where a
    button used to be, and the screenshot had two of them side by side."""
    ui = (ROOT / "ui" / "index.html").read_text()
    for label in ("SENDING", "BUILDING"):
        assert f"◍</span> {label}" in ui


def test_a_failed_turn_does_not_leave_a_dangling_question():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function talk()")[1].split("\n}\n")[0]
    assert "chatLog.pop();" in fn


# --- a conversation is work, and work should not evaporate ----------------

def test_the_conversation_outlives_a_reload():
    """Losing four turns to a refresh is the kind of small betrayal that
    stops people using a thing they otherwise liked."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "const CHAT_KEY = 'tonecommand.chat.v1';" in ui
    assert "function saveChat()" in ui and "function loadChat()" in ui
    # restored on load, not merely written
    tail = ui.split("$('prompt').addEventListener('keydown'")[1]
    assert "loadChat();" in tail and "renderChat();" in tail


def test_storage_is_never_trusted():
    """An older version of this page, or a half-written entry, must not take
    the panel down with it."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function loadChat()")[1].split("\n}\n")[0]
    assert "Array.isArray(d.log)" in fn
    assert "['user', 'assistant', 'note'].includes(m.role)" in fn
    assert "catch (e)" in fn


def test_every_storage_call_can_fail_without_a_message():
    """A private window throws on localStorage. That is not worth an error."""
    ui = (ROOT / "ui" / "index.html").read_text()
    for fn_name in ("function saveChat()", "function loadChat()"):
        fn = ui.split(fn_name)[1].split("\n}\n")[0]
        assert "try {" in fn and "catch" in fn, fn_name


def test_clearing_leaves_nothing_behind():
    ui = (ROOT / "ui" / "index.html").read_text()
    save = ui.split("function saveChat()")[1].split("\n}\n")[0]
    assert "if (!chatLog.length) { localStorage.removeItem(CHAT_KEY); return; }" in save


def test_clear_asks_before_deleting_real_work():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("$('cclear').onclick")[1].split("\n  };")[0]
    assert "window.confirm" in fn
    assert "chatLog.length > 1" in fn, "do not nag over a single line"


# --- the box people actually type into ------------------------------------

def test_the_prompt_is_a_textarea_that_grows():
    """People describe tones in sentences. A one-line box shows them the
    middle of their own thought."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert '<textarea id="prompt"' in ui
    assert "function growPrompt()" in ui


def test_an_emptied_box_returns_to_one_line():
    """Collapsed to zero, an EMPTY textarea reported 62px against a 31.2px
    line, so emptying a grown box left it permanently double height. Every
    other size measures correctly."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function growPrompt()")[1].split("\n}\n")[0]
    assert "if (!t.value) { t.style.height = ''; return; }" in fn


def test_enter_sends_and_shift_enter_writes_a_line():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("$('prompt').addEventListener('keydown'")[1].split("});")[0]
    assert "e.shiftKey" in fn and "e.preventDefault();" in fn
    assert "Enter sends, Shift+Enter for a new line" in ui, \
        "a box that grows implies Enter breaks a line; say which it is"


# --- and the small things that make it feel finished ----------------------

def test_it_says_it_is_thinking_where_you_are_looking():
    """A spinner on a button at the far side of the panel is not an answer to
    "did that send?" when your eyes are on the last thing said."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "chatBusy && !chatBuilding" in ui, \
        "a build has its own banner; the grey line is for a conversation turn"
    assert "waitLine()" in ui


def test_only_one_turn_at_a_time():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function talk()")[1].split("\n}\n")[0]
    assert "if (chatBusy) return;" in fn


def test_a_failed_turn_gives_the_words_back():
    """Dropping the turn silently made somebody retype a sentence they had
    already written. That is the wrong party paying for a failed request."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function talk()")[1].split("\n}\n")[0]
    assert "$('prompt').value = said;" in fn


def test_reading_back_is_not_interrupted_by_a_new_message():
    """Yanking somebody to the bottom while they are reading something
    further up is worse than making them scroll."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function renderChat()")[1].split("\n}\n")[0]
    assert "wasAtBottom" in fn
    assert fn.index("const wasAtBottom") < fn.index("feed.innerHTML ="), \
        "measure before the rewrite, or scrollTop means nothing"


# --- shaped like a conversation, not like a form --------------------------
#
# The input sat at the TOP with suggestions and two paragraphs of explanation
# stacked underneath, and a SECOND text box with its own button below that. So
# the first thing on screen was chrome, and it read as a form.

def test_the_transcript_comes_before_the_box_you_type_into():
    ui = (ROOT / "ui" / "index.html").read_text()
    panel = ui.split('data-label="COMMAND"')[1].split('data-label="PROPOSED')[0]
    assert panel.index('id="chat"') < panel.index('class="composer"')
    assert panel.index('class="composer"') < panel.index('id="prompt"')


def test_the_transcript_area_does_not_come_and_go():
    """It is the shape of the panel, not something that appears once you have
    used it. Only its contents swap."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert '<div id="chat">' in ui, "no longer hidden when empty"
    fn = ui.split("function renderChat()")[1].split("\n}\n")[0]
    assert "$('cempty').hidden = !!chatLog.length;" in fn


def test_the_empty_state_asks_and_suggests_in_the_middle():
    """Most people's first sight of this panel. A question and six real
    requests beat any amount of describing what the box accepts."""
    ui = (ROOT / "ui" / "index.html").read_text()
    empty = ui.split('id="cempty"')[1].split("</div>\n      <div")[0]
    assert "What do you want it to sound like?" in empty
    assert 'id="egs"' in empty, "the suggestions belong in the empty state"
    css = ui.split(".cempty {")[1].split("}")[0]
    assert "align-items: center" in css and "justify-content: center" in css


def test_the_second_text_box_is_folded_away():
    """Two text boxes and two buttons stacked in one panel is a form. Building
    from a video is real and rare, so it is one line until wanted."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert '<details class="srcfold">' in ui
    fold = ui.split('<details class="srcfold">')[1].split("</details>")[0]
    assert 'id="srcinput"' in fold and 'id="analyze"' in fold
    assert "<summary>" in fold


def test_the_explaining_shrank_to_one_line():
    ui = (ROOT / "ui" / "index.html").read_text()
    hint = ui.split('class="hint composerhint">')[1].split("</div>")[0]
    assert len(hint) < 130, "the composer hint is a line, not a paragraph"
    assert "Enter sends" in hint and "until you confirm" in hint


# --- saying what it is doing ----------------------------------------------
#
# Somebody asked for a build after a long conversation and got no sign it was
# working, finished, or transmitting. The plan renders in a panel below the
# fold while the reader is still looking at the conversation, so "done" and
# "nothing happened" looked identical.

def test_building_says_so_where_the_reader_is_looking():
    """It used to be a static string, which is how a 283-second build read as
    a dead button. It is a counting line now, via the same waitLine the
    conversation uses."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "chatBuilding = true;" in fn
    assert "setInterval(renderChat, 1000)" in fn
    wait = ui.split("function waitLine()")[1].split("\n}\n")[0]
    assert "working out the changes..." in wait
    assert "takes a few minutes" in wait


def test_a_finished_plan_announces_itself_and_scrolls_into_view():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "Proposed ${n} change" in fn
    assert "Nothing has been " in fn and "press TRANSMIT" in fn
    assert "$('planbox').scrollIntoView" in fn


def test_a_plan_with_no_actions_still_says_something():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "That produced no changes to make." in fn


def test_a_failed_build_is_not_silence():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "I could not build that:" in fn


def test_transmitting_reports_into_the_conversation_too():
    """It reported itself only into the LOG, which is two panels further down
    the page from where somebody five turns into a conversation is looking."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function apply()")[1].split("\n}\n")[0]
    assert "chatWorking = 'sending to the FM9...'" in fn
    assert "Sent ${good} change" in fn
    assert "Nothing was sent:" in fn


def test_the_count_is_what_landed_not_what_was_asked_for():
    """A partial failure that reports "sent" is worse than no report."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function apply()")[1].split("\n}\n")[0]
    assert "acted.filter(r => r.ok).length" in fn
    assert "did not apply" in fn


def test_a_note_is_never_fed_back_to_the_model():
    """"I proposed 3 changes" is our bookkeeping. Sending it back as though
    the model had said it would have it answering its own status notes."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function talk()")[1].split("\n}\n")[0]
    assert "m.role === 'user' || m.role === 'assistant'" in fn
    assert "chatLog.push({role: 'note'" in ui


def test_notes_look_different_from_what_either_party_said():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function renderChat()")[1].split("\n}\n")[0]
    assert "m.role === 'note'" in fn
    assert 'class="cnote"' in fn
    assert "#chat .cnote {" in ui


def test_the_working_line_is_always_cleared():
    """A spinner that outlives its request is a hang that never resolves."""
    ui = (ROOT / "ui" / "index.html").read_text()
    for name in ("async function engage(prompt, name)", "async function apply()"):
        fn = ui.split(name)[1].split("\n}\n")[0]
        tail = fn.split("finally {")[-1]
        assert "chatWorking = ''" in tail, name


# --- streaming, and telling slow apart from stuck -------------------------
#
# Measured before building any of this: stripping the 8,600-token parameter
# reference did NOT make replies faster (2.7s with, 3.5s without: the proxy
# caches the prefix), and a smaller model was SLOWER (5-7s). The prompt was
# never the problem. Staring at an unchanging spinner for 3 to 8 seconds was.

def test_the_reply_field_comes_first_so_it_can_be_read_early():
    """Waiting for the closing brace before showing anything means watching a
    spinner for the whole reply, which is what streaming exists to stop."""
    assert list(planner.CHAT_SCHEMA["properties"])[0] == "reply"


@pytest.mark.parametrize("obj", [
    {"reply": "Hello there", "ready": False, "request": ""},
    {"reply": 'He said "warmer" and \\ then left', "ready": True, "request": "x"},
    {"reply": "line one\nline two\ttabbed", "ready": False, "request": ""},
    {"reply": "unicode: é done", "ready": True, "request": "y"},
    {"reply": "", "ready": False, "request": "z"},
])
@pytest.mark.parametrize("size", [1, 2, 3, 7, 40, 10_000])
def test_the_reply_survives_any_chunk_boundary(obj, size):
    """A network splits wherever it likes, including inside an escape."""
    raw = json.dumps(obj)
    s = planner.ReplyStreamer()
    got = "".join(s.feed(raw[i:i + size]) for i in range(0, len(raw), size))
    assert got == obj["reply"]


def test_the_streamer_stops_at_the_end_of_the_reply():
    s = planner.ReplyStreamer()
    s.feed(json.dumps({"reply": "done", "ready": True, "request": "later"}))
    assert s.finished
    assert s.feed('{"reply": "more"}') == "", "nothing after the closing quote"


def test_the_streamer_is_not_fooled_by_earlier_fields():
    s = planner.ReplyStreamer()
    assert s.feed('{"ready": true, "request": "no", "reply": "yes"}') == "yes"


def test_a_backend_that_cannot_stream_still_answers(monkeypatch):
    """Streaming must not become a feature only some configurations have."""
    monkeypatch.setattr(planner, "_openai_base_url", lambda: "")
    monkeypatch.setattr(planner, "converse",
                        lambda *a, **k: {"reply": "hi", "ready": False,
                                         "request": "", "backend": "cli",
                                         "model": "m", "attempts": []})
    out = list(planner.converse_stream([{"role": "user", "content": "x"}], "s", "r"))
    assert out == [("done", {"reply": "hi", "ready": False, "request": "",
                             "backend": "cli", "model": "m", "attempts": []})]


def test_the_stream_endpoint_exists_beside_the_plain_one(client):
    """The non-streaming route stays: a browser that cannot hold a stream
    open, or a backend that cannot stream, still gets an answer."""
    paths = {r.path for r in server.app.routes}
    assert "/api/chat" in paths and "/api/chat/stream" in paths
    assert client.post("/api/chat/stream", json={"messages": []}).status_code == 400


def test_both_chat_paths_describe_the_same_rig():
    """Two ways to build the context is two rigs to disagree about."""
    src = inspect.getsource(server.api_chat_stream)
    assert "_chat_context()" in src
    assert "_chat_context()" in inspect.getsource(server.api_chat)


def test_the_stream_pings_while_it_is_quiet():
    """The only thing that separates "still thinking" from "the connection
    died". No amount of spinner animation answers that."""
    src = inspect.getsource(server.api_chat_stream)
    assert "event: ping" in src
    assert "out.get(timeout=3)" in src


def test_the_browser_tells_slow_apart_from_stuck():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function waitLine()")[1].split("\n}\n")[0]
    assert "It may be stuck" in fn, "no answer at all has to say so"
    assert "Longer than usual" in fn, "slow is not the same as broken"
    assert "writing..." in fn
    assert "chatAlive" in fn, "stuck is judged on pings, not on words"


def test_the_wait_counts_seconds_out_loud():
    """A spinner says "working" for as long as it is on screen and never
    distinguishes four seconds from four minutes."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "setInterval(renderChat, 1000)" in ui
    fn = ui.split("function waitLine()")[1].split("\n}\n")[0]
    assert "secs" in fn


def test_a_wait_can_be_left():
    """A wedged backend used to mean reloading the page, which until recently
    also lost the conversation."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "chatAbort = new AbortController()" in ui
    assert "signal: chatAbort.signal" in ui
    assert "chatAbort.abort()" in ui
    fn = ui.split("async function talk()")[1].split("\n}\n")[0]
    assert "e.name === 'AbortError'" in fn, "stopping is not an error"


def test_a_stream_that_ends_early_is_a_failure_not_a_reply():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function talk()")[1].split("\n}\n")[0]
    assert "if (!landed) throw" in fn


def test_which_model_answered_is_on_the_reply_it_produced():
    """It was returned on every turn and thrown away, so "who am I talking
    to" had no answer anywhere on the page."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "model: d.model || ''" in ui
    fn = ui.split("function renderChat()")[1].split("\n}\n")[0]
    assert "m.model ? `<i>${esc(m.model)}</i>`" in fn


# --- naming what gets built -----------------------------------------------
#
# Ask for a Marco Sfogli tone and the preset kept whatever name was already on
# it. A store writes the buffer's CURRENT name, and that name is the only
# label anybody has afterwards.

def test_the_conversation_decides_the_name():
    """Picking it needs the judgement to tell a player from an amp model. A
    first attempt with capitalised-word runs named a Sfogli build "Fender
    Twin", and saw nothing at all in "i want a marco sfogli style lead",
    which is how people actually type."""
    assert "name" in planner.CHAT_SCHEMA["properties"]
    assert "Marco Sfogli" in planner.CHAT_SYSTEM
    assert "never the amp you chose to get there" in planner.CHAT_SYSTEM
    assert "Leave `name` EMPTY" in planner.CHAT_SYSTEM


def test_the_heuristic_that_did_not_work_is_gone():
    assert not hasattr(planner, "name_from_request")


def test_reply_is_still_first_so_streaming_survives_the_new_field():
    assert list(planner.CHAT_SCHEMA["properties"])[0] == "reply"
    assert '"name": string' in planner.chat_shape_line()


def test_applying_the_name_is_code_not_a_request(client, monkeypatch):
    """A model that is merely asked to emit a rename will sometimes not."""
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {
        "summary": "s", "clarification": None,
        "actions": [{"kind": "set_param", "block": "amp", "instance": 1,
                     "param": "DISTORT_MID", "value": 6, "reason": "x"}]})
    r = client.post("/api/plan", json={"prompt": "a sfogli lead",
                                       "name": "Marco Sfogli"}).json()
    first = r["actions"][0]
    assert first["kind"] == "rename_preset"
    assert first["type_name"] == "Marco Sfogli"
    assert not first["validation_errors"]


def test_an_adjustment_is_never_renamed(client, monkeypatch):
    """That is the same preset with a change. Renaming it would be wrong."""
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {
        "summary": "s", "clarification": None,
        "actions": [{"kind": "set_param", "block": "amp", "instance": 1,
                     "param": "DISTORT_MID", "value": 6, "reason": "x"}]})
    for body in ({"prompt": "more presence"},
                 {"prompt": "more presence", "name": ""},
                 {"prompt": "more presence", "name": "   "}):
        r = client.post("/api/plan", json=body).json()
        assert not any(a["kind"] == "rename_preset" for a in r["actions"]), body


def test_a_planner_that_named_it_itself_is_left_alone(client, monkeypatch):
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {
        "summary": "s", "clarification": None,
        "actions": [{"kind": "rename_preset", "block": "PRESET", "instance": 1,
                     "type_name": "Sfogli Singing Lead", "reason": "x"}]})
    r = client.post("/api/plan", json={"prompt": "x", "name": "Marco Sfogli"}).json()
    renames = [a for a in r["actions"] if a["kind"] == "rename_preset"]
    assert len(renames) == 1
    assert renames[0]["type_name"] == "Sfogli Singing Lead"


def test_a_long_name_still_fits_after_the_prefix(client, monkeypatch):
    """run_action prepends "FM9AI-" and truncates at 32."""
    monkeypatch.setattr(planner, "plan", lambda *a, **k: {
        "summary": "s", "clarification": None, "actions": []})
    r = client.post("/api/plan", json={"prompt": "x", "name": "N" * 60}).json()
    assert len("FM9AI-" + r["actions"][0]["type_name"]) <= 32


def test_the_browser_says_what_it_will_be_called_before_you_build():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function renderChat()")[1].split("\n}\n")[0]
    assert "FM9AI-${esc(chatName)}" in fn
    assert "$('cbuild').onclick = () => engage(chatRequest, chatName);" in ui


def test_the_name_survives_a_reload_with_the_rest():
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "name: chatName" in ui
    load = ui.split("function loadChat()")[1].split("\n}\n")[0]
    assert "chatName = typeof d.name === 'string'" in load


# --- a five-minute build that looks like a dead button --------------------
#
# Measured: a four-scene Van Halen request took 283 seconds and produced 71
# actions. It was not stuck. The panel said "working out the changes..." and
# kept saying it, unchanged, for five minutes, so the only reasonable reading
# was that BUILD THIS did nothing.

def test_planning_has_a_heartbeat_too(client):
    paths = {r.path for r in server.app.routes}
    assert "/api/plan" in paths and "/api/plan/stream" in paths
    src = inspect.getsource(server.api_plan_stream)
    assert "event: ping" in src
    assert "out.get(timeout=3)" in src


def test_one_body_two_deliveries():
    """A second copy of the profile precedence, the validation loop, the
    splice consequences and the blast-radius maths is exactly the duplication
    that goes subtly wrong on one path only."""
    assert "_plan_for(body)" in inspect.getsource(server.api_plan)
    assert "_plan_for(body, on_count=" in inspect.getsource(server.api_plan_stream)


def test_the_shared_body_returns_data_not_http():
    """One of its two callers writes server-sent events, where a
    JSONResponse is not serialisable."""
    src = inspect.getsource(server._plan_for)
    assert "JSONResponse" not in src


def test_a_planner_failure_still_reaches_the_old_route_as_502(client, monkeypatch):
    monkeypatch.setattr(planner, "plan",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope")))
    r = client.post("/api/plan", json={"prompt": "x"})
    assert r.status_code == 502
    assert "nope" in r.json()["error"]


def test_a_long_build_can_be_left():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "chatAbort = new AbortController()" in fn
    assert "signal: chatAbort.signal" in fn
    assert "e.name === 'AbortError'" in fn
    assert "Stopped. Nothing was built and nothing was sent." in fn


def test_stopping_a_build_leaves_nothing_running():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    tail = fn.split("finally {")[-1]
    for cleared in ("clearInterval(tick)", "chatBusy = false",
                    "chatBuilding = false", "chatAbort = null"):
        assert cleared in tail, cleared


def test_the_button_is_not_touched_after_it_is_gone():
    """renderChat rewrites the transcript, so the BUILD THIS element the
    handler started with is detached by the time it finishes."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "document.body.contains(b)" in fn


# --- BUILDING, and a number that is actually measured ---------------------

def test_actions_are_counted_from_the_text_not_guessed():
    """Every action carries exactly one `"kind"`, so occurrences of it are
    actions written so far. A percentage invented from elapsed time would be
    a guess dressed as information, and would still read 40% at the end."""
    assert planner._ACTION_MARK == '"kind"'


def test_the_carry_is_one_short_of_the_marker():
    """Carrying eight characters of a six-character marker left a complete
    match in the next window too, and every action was counted twice: five
    reported as ten."""
    src = inspect.getsource(planner.plan_stream)
    assert "tail = window[-(len(_ACTION_MARK) - 1):]" in src


def test_a_split_marker_is_still_counted(monkeypatch):
    """A chunk boundary inside `"kind"` must not lose an action."""
    pieces = ['{"actions":[{"ki', 'nd":"set_param"},{"kin', 'd":"set_scene"}]}']
    seen, tail = 0, ""
    for piece in pieces:
        window = tail + piece
        seen += window.count(planner._ACTION_MARK)
        tail = window[-(len(planner._ACTION_MARK) - 1):]
    assert seen == 2


def test_a_backend_that_cannot_stream_still_plans(monkeypatch):
    monkeypatch.setattr(planner, "_openai_base_url", lambda: "")
    monkeypatch.setattr(planner, "plan",
                        lambda *a, **k: {"summary": "s", "actions": [],
                                         "clarification": None})
    out = list(planner.plan_stream("x", "s", "r"))
    assert [k for k, _ in out] == ["done"]


def test_counting_is_a_courtesy_and_the_plan_is_the_point(monkeypatch):
    """A count that fails must not take the plan down with it."""
    monkeypatch.setattr(planner, "plan_stream", lambda *a, **k: iter([
        ("count", 1), ("done", {"summary": "s", "actions": []})]))

    def explode(_n):
        raise RuntimeError("the browser went away")

    out = server._plan_counting("x", "ctx", explode)
    assert out == {"summary": "s", "actions": []}


def test_nobody_watching_means_the_ordinary_call(monkeypatch):
    called = {}
    monkeypatch.setattr(planner, "plan",
                        lambda *a, **k: called.setdefault("plain", True) or {})
    monkeypatch.setattr(planner, "plan_stream",
                        lambda *a, **k: called.setdefault("stream", True) or iter([]))
    server._plan_counting("x", "ctx", None)
    assert called == {"plain": True}


def test_the_build_gets_a_banner_not_a_line_of_grey_text():
    """A build runs for minutes. A line in the same weight as everything else
    is exactly what got read as "nothing is happening"."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function renderChat()")[1].split("\n}\n")[0]
    assert 'class="cbuilding"' in fn
    assert 'class="cblink">BUILDING' in fn
    assert "change${chatCount === 1 ? '' : 's'} written" in fn
    assert "#chat .cblink {" in ui and "@keyframes cbpulse" in ui


def test_the_bar_does_not_pretend_to_know_how_far_along_it_is():
    """There is no total, so there is no percentage. A bar filling against a
    guessed total is a lie with a progress bar drawn on it."""
    ui = (ROOT / "ui" / "index.html").read_text()
    bar = ui.split("#chat .cbbar i {")[1].split("}")[0]
    assert "animation: cbslide" in bar
    assert "%" not in ui.split("function buildNote()")[1].split("\n}\n")[0]


def test_the_banner_says_when_it_has_stopped_hearing_anything():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function buildNote()")[1].split("\n}\n")[0]
    assert "It may be stuck" in fn
    assert "chatAlive" in fn
    assert "takes a few minutes" in fn


def test_the_count_resets_between_builds():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt, name)")[1].split("\n}\n")[0]
    assert "chatCount = 0;" in fn


# --- TRANSMIT saying something -------------------------------------------
#
# Reported as: "i hit transmit, i got no progress, nothing - not sure if it
# wrote". The button greyed out, nothing moved, and 1.5 seconds later the
# whole panel hid itself, taking the per-action ticks with it.

def test_transmitting_reports_each_change_as_it_lands():
    """Unlike planning, this is a real loop over real actions, so the
    progress is not an estimate: it is which change of how many has actually
    been written."""
    src = inspect.getsource(server._apply_for)
    assert "on_step" in src
    assert '"done": len(' in src and '"total": len(body.actions)' in src


def test_a_progress_callback_cannot_break_the_transmit():
    src = inspect.getsource(server._apply_for)
    step = src.split("if on_step is not None:")[1].split("if not res.get")[0]
    assert "except Exception:" in step


def test_both_apply_paths_share_one_loop():
    assert "_apply_for(body)" in inspect.getsource(server.api_apply)
    assert "_apply_for(body, on_step=" in inspect.getsource(server.api_apply_stream)


def test_the_stream_route_exists_beside_the_plain_one():
    paths = {r.path for r in server.app.routes}
    assert "/api/apply" in paths and "/api/apply/stream" in paths


def test_the_button_counts_where_the_finger_was():
    """The transcript is two panels up and the log two panels down. Somebody
    who has just pressed TRANSMIT is looking at TRANSMIT."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function apply()")[1].split("\n}\n")[0]
    assert "SENDING ${n}/${total}" in fn
    assert "Sending ${d.done} of ${d.total}" in fn


def test_the_outcome_stays_until_it_is_dismissed():
    """It used to hide the panel 1.5s after finishing, throwing away the
    ticks and crosses on the cards, the only place the outcome was visible."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function apply()")[1].split("\n}\n")[0]
    assert "setTimeout(() => { $('planbox').style.display = 'none'" not in fn
    assert "planResult(" in fn
    res = ui.split("function planResult(html, how)")[1].split("\n}\n")[0]
    assert "DISMISS" in res


def test_the_outcome_says_what_landed_and_what_did_not():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function apply()")[1].split("\n}\n")[0]
    assert "did not apply" in fn
    assert "UNDO puts it back" in fn
    assert "Nothing was sent." in fn


def test_the_button_gets_its_own_label_back():
    ui = (ROOT / "ui" / "index.html").read_text()
    assert 'id="apply">TRANSMIT TO FM9<' in ui
    fn = ui.split("async function apply()")[1].split("\n}\n")[0]
    assert "'TRANSMIT TO FM9'" in fn, "restoring a shorter label renames the button"

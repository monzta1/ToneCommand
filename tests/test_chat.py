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
    assert set(planner.CHAT_SCHEMA["properties"]) == {"reply", "ready", "request"}
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
    assert "$('cbuild').onclick = () => engage(chatRequest);" in ui
    fn = ui.split("async function engage(prompt)")[1].split("\n}\n")[0]
    assert "$('prompt').value" not in fn, "building must not touch the input"
    assert "/api/plan" in fn, "and it still goes through the ordinary planner"


def test_a_planner_question_lands_in_the_conversation_not_in_red():
    """The planner has always been able to ask (PLAN_SCHEMA.clarification).
    The UI printed the question as an error and hid the panel, leaving it
    nowhere to be answered. The conversation is where a question belongs."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt)")[1].split("\n}\n")[0]
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
    assert "chatBusy ? `<div class=\"cthinking\">${waitLine()}</div>`" in ui


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
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt)")[1].split("\n}\n")[0]
    assert "chatWorking = 'working out the changes...'" in fn


def test_a_finished_plan_announces_itself_and_scrolls_into_view():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt)")[1].split("\n}\n")[0]
    assert "Proposed ${n} change" in fn
    assert "Nothing has been " in fn and "press TRANSMIT" in fn
    assert "$('planbox').scrollIntoView" in fn


def test_a_plan_with_no_actions_still_says_something():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt)")[1].split("\n}\n")[0]
    assert "That produced no changes to make." in fn


def test_a_failed_build_is_not_silence():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function engage(prompt)")[1].split("\n}\n")[0]
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
    for name in ("async function engage(prompt)", "async function apply()"):
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

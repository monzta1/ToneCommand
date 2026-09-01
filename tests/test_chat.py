"""Talking a tone through before planning it.

A tone is an opinion, and the first sentence somebody types is rarely the one
they mean. "Warmer" from a player chasing a Dumble and "warmer" from one
chasing a Vox are different edits.

The property that matters most here is a negative one: conversation adds NO
path to the hardware. It produces a better sentence, and that sentence goes
through the same planner, validator and confirm gate as one typed straight in.
"""
import inspect
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
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "$('egs').hidden = !!chatLog.length;" in ui


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
    assert "m.role === 'user' || m.role === 'assistant'" in fn
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
    assert "Enter sends, Shift+Enter starts a new line" in ui, \
        "a box that grows implies Enter breaks a line; say which it is"


# --- and the small things that make it feel finished ----------------------

def test_it_says_it_is_thinking_where_you_are_looking():
    """A spinner on a button at the far side of the panel is not an answer to
    "did that send?" when your eyes are on the last thing said."""
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "chatBusy ? '<div class=\"cthinking\">thinking...</div>' : ''" in ui


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
    assert fn.index("const wasAtBottom") < fn.index("box.innerHTML ="), \
        "measure before the rewrite, or scrollTop means nothing"

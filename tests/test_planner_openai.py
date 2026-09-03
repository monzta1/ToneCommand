"""The OpenAI-compatible backend, against a stub server on loopback.

No proxy, no subscription, no outbound network: a threaded http.server stands
in for CLIProxyAPI (or a local LLM), so every failure class below is
reproducible in CI.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from fm9 import planner

PLAN = {"summary": "more gain", "actions": [
    {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE",
     "value": 6.0, "reason": "asked for gain"}]}


class Stub:
    """One canned reply, plus a record of what the backend actually sent."""

    def __init__(self, status=200, body=None, raw=None):
        self.status, self.body, self.raw = status, body, raw
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", 0))
                outer.requests.append({
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": json.loads(self.rfile.read(length) or b"{}"),
                })
                payload = (outer.raw if outer.raw is not None
                           else json.dumps(outer.body).encode())
                self.send_response(outer.status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def reply(content, model="stub-model"):
    return {"model": model, "choices": [{"message": {"content": content}}]}


def ask(monkeypatch, url, **env):
    monkeypatch.setenv("PLANNER_BASE_URL", url)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return planner._plan_via_openai("more gain", "STATE", "REFERENCE")


def test_a_plan_comes_back_with_the_model_the_server_reported(monkeypatch):
    with Stub(body=reply(json.dumps(PLAN))) as stub:
        got, model = ask(monkeypatch, stub.url)
    assert got["actions"][0]["param"] == "DISTORT_DRIVE"
    assert model == "stub-model"


def test_it_posts_chat_completions_with_the_real_prompt(monkeypatch):
    with Stub(body=reply(json.dumps(PLAN))) as stub:
        ask(monkeypatch, stub.url, PLANNER_MODEL="llama3.3")
        sent = stub.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["body"]["model"] == "llama3.3"
    system, user = sent["body"]["messages"]
    assert planner.JSON_ONLY in system["content"]
    assert "REFERENCE" in user["content"] and "STATE" in user["content"]
    assert "more gain" in user["content"]


def test_the_api_key_is_optional_by_design(monkeypatch):
    """An OAuth router authenticates upstream and often wants no key."""
    monkeypatch.delenv("PLANNER_API_KEY", raising=False)
    with Stub(body=reply(json.dumps(PLAN))) as stub:
        ask(monkeypatch, stub.url)
        assert "authorization" not in {k.lower() for k in stub.requests[0]["headers"]}
    with Stub(body=reply(json.dumps(PLAN))) as stub:
        ask(monkeypatch, stub.url, PLANNER_API_KEY="sk-local")
        headers = {k.lower(): v for k, v in stub.requests[0]["headers"].items()}
        assert headers["authorization"] == "Bearer sk-local"


def test_json_buried_in_prose_is_still_extracted(monkeypatch):
    with Stub(body=reply(f"Sure thing!\n```json\n{json.dumps(PLAN)}\n```")) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["summary"] == "more gain"


def test_content_as_a_list_of_parts(monkeypatch):
    body = {"choices": [{"message": {"content": [
        {"text": json.dumps(PLAN)[:20]}, {"text": json.dumps(PLAN)[20:]}]}}]}
    with Stub(body=body) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["actions"][0]["value"] == 6.0


def test_reasoning_content_is_used_when_content_is_empty(monkeypatch):
    """Local reasoning models spend the budget there and leave content blank."""
    body = {"choices": [{"message": {"content": "",
                                     "reasoning_content": json.dumps(PLAN)}}]}
    with Stub(body=body) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["summary"] == "more gain"


# --- failure classes ---

def test_no_base_url_is_unavailable(monkeypatch):
    monkeypatch.setenv("PLANNER_BASE_URL", "")
    with pytest.raises(planner.BackendFailure) as err:
        planner._plan_via_openai("p", "s", "r")
    assert err.value.failure_class == "unavailable"


def test_a_refusal_reports_status_and_body(monkeypatch):
    with Stub(status=502, raw=b'{"error":"upstream oauth expired"}') as stub:
        with pytest.raises(planner.BackendFailure) as err:
            ask(monkeypatch, stub.url)
    assert err.value.failure_class == "http_status"
    assert "502" in err.value.detail and "oauth expired" in err.value.detail


def test_a_non_json_body_is_unreadable_output(monkeypatch):
    with Stub(raw=b"<html>gateway</html>") as stub:
        with pytest.raises(planner.BackendFailure) as err:
            ask(monkeypatch, stub.url)
    assert err.value.failure_class == "unreadable_output"


def test_prose_with_no_json_object_is_unreadable_output(monkeypatch):
    with Stub(body=reply("I would rather not.")) as stub:
        with pytest.raises(planner.BackendFailure) as err:
            ask(monkeypatch, stub.url)
    assert err.value.failure_class == "unreadable_output"


def test_an_empty_reply_says_what_to_change(monkeypatch):
    with Stub(body={"choices": [{"message": {"content": ""}}]}) as stub:
        with pytest.raises(planner.BackendFailure) as err:
            ask(monkeypatch, stub.url)
    assert err.value.failure_class == "empty_output"
    assert "PLANNER_MAX_TOKENS" in err.value.detail


def test_a_configured_but_dead_router_fails_fast_and_names_itself(monkeypatch):
    """The concern raised on #20: a router that is not running must not hang."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead = f"http://127.0.0.1:{sock.getsockname()[1]}/v1"
    sock.close()
    with pytest.raises(planner.BackendFailure) as err:
        ask(monkeypatch, dead)
    assert err.value.failure_class == "transport"
    assert err.value.target == dead


# --- what real local models actually emit ---

def test_two_json_objects_take_the_last_plan_shaped_one(monkeypatch):
    """A reasoning model drafts an object and then emits its final answer.
    Slicing first-brace-to-last-brace spans both and dies with
    "Extra data: line 2 column 1" - observed against LM Studio, 2026-08-25."""
    draft = json.dumps({"summary": "draft", "actions": []})
    final = json.dumps({"summary": "final", "actions": [
        {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE",
         "value": 5.4}]})
    with Stub(body=reply(f"{draft}\n{final}")) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["summary"] == "final"
    assert got["actions"][0]["value"] == 5.4


def test_thinking_out_loud_with_braces_before_the_answer(monkeypatch):
    body = reply('Let me consider {maybe: 1} and settle on\n'
                 + json.dumps({"summary": "ok", "actions": []}))
    with Stub(body=body) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["summary"] == "ok"


def test_braces_inside_strings_do_not_confuse_the_scan(monkeypatch):
    payload = {"summary": "mind the { and } here", "actions": []}
    with Stub(body=reply(json.dumps(payload))) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["summary"] == "mind the { and } here"


def test_a_reply_with_only_unparseable_braces_is_still_refused(monkeypatch):
    with Stub(body=reply("{not: valid json at all")) as stub:
        with pytest.raises(planner.BackendFailure) as err:
            ask(monkeypatch, stub.url)
    assert err.value.failure_class == "unreadable_output"


def test_an_abandoned_draft_does_not_take_the_answer_with_it(monkeypatch):
    """The other thing reasoning models do: start an object, give up part
    way, and restart. Raised on #21. A brace counter never recovers - the
    unclosed "{" pins the depth above zero and the unterminated quote eats
    the rest of the input, so the valid answer sitting right there is lost.
    """
    body = reply('Let me draft this.\n'
                 '{"summary": "wait, I need the amp first\n'
                 'Actually, starting over:\n'
                 + json.dumps({"summary": "final", "actions": []}))
    with Stub(body=body) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["summary"] == "final"


def test_an_unbalanced_opening_brace_in_prose_is_survivable(monkeypatch):
    """The milder version of the same fault: a model writing code aloud."""
    body = reply('Thinking: if (gain > 5) { back it off\n'
                 + json.dumps({"summary": "backed off", "actions": []}))
    with Stub(body=body) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["summary"] == "backed off"


def test_nested_action_objects_are_not_candidates_of_their_own(monkeypatch):
    """Trying every brace would offer each action as a candidate too. The
    scan resumes past what it consumed, so the outer object still wins even
    when it carries no summary."""
    payload = {"actions": [
        {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE",
         "value": 7.0}]}
    with Stub(body=reply(json.dumps(payload))) as stub:
        got, _ = ask(monkeypatch, stub.url)
    assert got["actions"][0]["value"] == 7.0


def test_the_last_object_wins_when_none_of_them_are_plan_shaped():
    """No plan-shaped object anywhere still prefers the final one, since
    that is the answer even when it is the wrong answer."""
    got = planner._extract_json('{"a": 1}\nno wait\n{"b": 2}')
    assert got == {"b": 2}


def test_bare_actions_are_gathered_into_a_plan():
    """Gemini 3.5 Flash answered an 8-scene build with the ACTIONS
    THEMSELVES, one JSON object per action and no {summary, actions}
    envelope. The extractor kept only the last object and called it an
    empty plan, so the owner watched a big build come back as nothing
    (2026-09-02). Action-shaped output is believed and enveloped; it all
    still passes through _validate and validate_action afterwards."""
    text = ('{"kind": "set_param", "block": "AMP", "instance": 1, '
            '"param": "TONE_BASS", "value": 4.4}\n'
            '{"kind": "rename_scene", "block": "SCENE", "instance": 1, '
            '"value": 1, "type_name": "British Steel"}\n'
            '{"kind": "set_bypass", "block": "REVERB", "instance": 1, '
            '"bypassed": false}')
    got = planner._extract_json(text)
    assert [a["kind"] for a in got["actions"]] == \
        ["set_param", "rename_scene", "set_bypass"]


def test_one_bare_action_is_still_a_plan_of_one():
    got = planner._extract_json(
        '{"kind": "set_bypass", "block": "REVERB", "instance": 1, '
        '"bypassed": false, "reason": "Enable reverb"}')
    assert len(got["actions"]) == 1
    assert got["actions"][0]["kind"] == "set_bypass"


def test_failures_name_the_service_not_the_protocol():
    """"openai [http_status] 429" while planning with Gemini reads as the
    wrong company failing. The quota that ran out was Google's, and the
    error says so (asked by the owner, 2026-09-02)."""
    exc = planner.BackendFailure(
        "openai", "http_status", "429 quota exceeded",
        "https://generativelanguage.googleapis.com/v1beta/openai", "m")
    assert str(exc).startswith("Gemini [http_status] 429")
    # An unknown host still names ITSELF rather than the protocol.
    exc = planner.BackendFailure(
        "openai", "transport", "unreachable", "http://127.0.0.1:8317/v1", "m")
    assert str(exc).startswith("127.0.0.1 [transport]")
    # Other backends are their own name.
    exc = planner.BackendFailure("cli", "timeout", "no reply", None, None)
    assert str(exc).startswith("cli [timeout]")

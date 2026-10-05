"""The Grok CLI backend, against a fake binary.

Envelope fixtures are the real shape emitted by grok 1.0.5, captured from the
CLI: `text`, `stopReason`, `usage`, `total_cost_usd`, and the model id as a KEY
under `modelUsage` rather than a top-level field.
"""
import json
import os
import sys
import stat

import pytest

from fm9 import planner

PLAN = {"summary": "raise drive", "actions": [
    {"kind": "set_param", "block": "amp", "instance": 1,
     "param": "DISTORT_DRIVE", "value": 6.5, "bypassed": None,
     "type_name": None, "position": None, "reason": "asked for gain"}],
    "clarification": None}

REAL_ENVELOPE = {
    "text": json.dumps(PLAN),
    "stopReason": "end_turn",
    "sessionId": "01a0349e-48ca-7391-b765-b1ebf66b142d",
    "usage": {"input_tokens": 13417, "output_tokens": 631},
    "num_turns": 1,
    "total_cost_usd": 0.00565148,
    "modelUsage": {"grok-4.6-build": {"modelCalls": 1}},
}




def fake_grok(tmp_path, monkeypatch, stdout="", stderr="", code=0):
    """A stand-in binary that echoes canned output and records its argv."""
    argv_log = tmp_path / "argv.json"
    script = tmp_path / "grok"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, os\n"
        f"open({str(argv_log)!r}, 'w').write(json.dumps("
        "{'argv': sys.argv[1:], 'env': dict(os.environ)}))\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({code})\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(planner, "find_grok_cli", lambda: _executable(script, tmp_path))
    return argv_log


def _executable(script, tmp_path):
    """The fake as something the OS runs directly. Windows ignores shebangs,
    and a .cmd shim would put the prompt through cmd.exe, which rewrites the
    % < > | it contains, so there it becomes a real grok.exe: distlib's
    launcher with the script inside (the same mechanism as pip's console
    scripts), which hands argv over exactly as a native CLI receives it
    (#186)."""
    if sys.platform != "win32":
        return str(script)
    from pip._vendor.distlib.scripts import ScriptMaker
    src, out = tmp_path / "src", tmp_path / "bin"
    src.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    (src / "grok.py").write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
    maker = ScriptMaker(str(src), str(out), add_launchers=True)
    maker.executable = sys.executable
    made = maker.make("grok.py")
    return next(p for p in made if p.lower().endswith(".exe"))


def call():
    return planner._plan_via_grok_cli("more gain", "STATE", "REFERENCE")


def test_a_plan_comes_back_with_the_model_from_modelusage(tmp_path, monkeypatch):
    fake_grok(tmp_path, monkeypatch, stdout=json.dumps(REAL_ENVELOPE))
    got, model = call()
    assert got["actions"][0]["value"] == 6.5
    assert model == "grok-4.6-build", "grok 1.0.5 has no top-level model field"


def test_output_is_constrained_by_plan_schema(tmp_path, monkeypatch):
    """The Claude CLI path can only ask for JSON; this one binds it."""
    log = fake_grok(tmp_path, monkeypatch, stdout=json.dumps(REAL_ENVELOPE))
    call()
    argv = json.loads(log.read_text(encoding="utf-8"))["argv"]
    assert "--json-schema" in argv
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema == planner.PLAN_SCHEMA
    for flag in ("--verbatim", "--no-subagents", "--no-plan",
                 "--disable-web-search"):
        assert flag in argv, f"{flag} verified present on grok 1.0.5"


def test_the_subprocess_gets_only_grok_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-not-leak")
    monkeypatch.setenv("XAI_API_KEY", "xai-expected")
    log = fake_grok(tmp_path, monkeypatch, stdout=json.dumps(REAL_ENVELOPE))
    call()
    env = json.loads(log.read_text(encoding="utf-8"))["env"]
    assert env.get("XAI_API_KEY") == "xai-expected"
    assert "ANTHROPIC_API_KEY" not in env


def test_the_model_flag_is_passed_only_when_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("GROK_CLI_MODEL", raising=False)
    log = fake_grok(tmp_path, monkeypatch, stdout=json.dumps(REAL_ENVELOPE))
    call()
    assert "-m" not in json.loads(log.read_text(encoding="utf-8"))["argv"]
    monkeypatch.setenv("GROK_CLI_MODEL", "grok-4.6-build")
    log = fake_grok(tmp_path, monkeypatch, stdout=json.dumps(REAL_ENVELOPE))
    call()
    argv = json.loads(log.read_text(encoding="utf-8"))["argv"]
    assert argv[argv.index("-m") + 1] == "grok-4.6-build"


# --- failure classes ---

def test_a_missing_binary_is_unavailable(monkeypatch):
    monkeypatch.setattr(planner, "find_grok_cli", lambda: None)
    with pytest.raises(planner.BackendFailure) as err:
        call()
    assert err.value.failure_class == "unavailable"


def test_an_error_envelope_is_a_backend_error(tmp_path, monkeypatch):
    fake_grok(tmp_path, monkeypatch, stdout=json.dumps(
        {"type": "error", "message": "authentication required; run grok --oauth"}))
    with pytest.raises(planner.BackendFailure) as err:
        call()
    assert err.value.failure_class == "backend_error"
    assert "authentication required" in err.value.detail


def test_a_nonzero_exit_with_no_envelope_reports_stderr(tmp_path, monkeypatch):
    fake_grok(tmp_path, monkeypatch, stdout="", stderr="command not found: xai",
              code=127)
    with pytest.raises(planner.BackendFailure) as err:
        call()
    assert err.value.failure_class == "backend_error"
    assert "exit 127" in err.value.detail and "xai" in err.value.detail


def test_an_empty_text_field_names_the_stop_reason(tmp_path, monkeypatch):
    fake_grok(tmp_path, monkeypatch, stdout=json.dumps(
        {"text": "", "stopReason": "max_tokens",
         "modelUsage": {"grok-4.6-build": {}}}))
    with pytest.raises(planner.BackendFailure) as err:
        call()
    assert err.value.failure_class == "empty_output"
    assert "max_tokens" in err.value.detail


def test_garbage_on_stdout_is_unreadable_output(tmp_path, monkeypatch):
    fake_grok(tmp_path, monkeypatch, stdout="Grok Build TUI\nnot json at all")
    with pytest.raises(planner.BackendFailure) as err:
        call()
    assert err.value.failure_class == "unreadable_output"


def test_envelope_survives_preamble_around_the_json(tmp_path, monkeypatch):
    fake_grok(tmp_path, monkeypatch,
              stdout="warning: config deprecated\n" + json.dumps(REAL_ENVELOPE))
    got, model = call()
    assert got["summary"] == "raise drive" and model == "grok-4.6-build"


def test_text_that_is_not_a_plan_is_unreadable_output(tmp_path, monkeypatch):
    fake_grok(tmp_path, monkeypatch, stdout=json.dumps(
        {"text": "I would rather not.", "modelUsage": {"grok-4.6-build": {}}}))
    with pytest.raises(planner.BackendFailure) as err:
        call()
    assert err.value.failure_class == "unreadable_output"

"""#211: the CLI planner backends on Windows. The prompt rode on the command
line, about 50,000 characters, and Windows refuses a command line past
32,767 (WinError 206). The Claude CLI now reads the prompt from stdin; the
grok CLI, whose stdin is not verified, is refused in words before it starts.

The fake claude here is a real executable everywhere (on Windows a launcher
.exe, as tests/test_planner_grok.py builds), so the Windows CI run proves the
long prompt actually starts there."""
import json
import stat
import subprocess
import sys
import threading

import pytest

from fm9 import describe, planner

# > 32,767, not ASCII, and with a character outside the BMP (two UTF-16 units)
LONG = "a bright clean tone with sparkle, " * 1200 + "the end \u2192 caf\u00e9 \U0001F3B8"
assert len(LONG) > planner.WINDOWS_CMDLINE_MAX


def _executable(script, tmp_path):
    if sys.platform != "win32":
        return str(script)
    from pip._vendor.distlib.scripts import ScriptMaker
    src, out = tmp_path / "src", tmp_path / "bin"
    src.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    (src / "claude.py").write_text(script.read_text(encoding="utf-8"), encoding="utf-8")
    maker = ScriptMaker(str(src), str(out), add_launchers=True)
    maker.executable = sys.executable
    made = maker.make("claude.py")
    return next(p for p in made if p.lower().endswith(".exe"))


def fake_claude(tmp_path, monkeypatch, envelope):
    """Records argv and the stdin it was handed (read as UTF-8 bytes), then
    answers like the CLI: one JSON envelope, or a stream ending in one."""
    log = tmp_path / "seen.json"
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "data = sys.stdin.buffer.read().decode('utf-8')\n"
        f"open({str(log)!r}, 'w', encoding='utf-8').write(json.dumps({{'argv': sys.argv[1:], 'stdin': data}}))\n"
        f"env = {envelope!r}\n"
        "if 'stream-json' in sys.argv:\n"
        "    sys.stdout.write(json.dumps({'type': 'stream_event', 'event': {'type': 'content_block_delta',"
        " 'delta': {'type': 'text_delta', 'text': env['result']}}}) + '\\n')\n"
        "    sys.stdout.write(json.dumps(dict(env, type='result')) + '\\n')\n"
        "else:\n"
        "    sys.stdout.write(json.dumps(env))\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(planner, "find_claude_cli", lambda: _executable(script, tmp_path))
    return log


PLAN = {"summary": "s", "actions": []}
ENVELOPE = {"result": json.dumps(PLAN), "is_error": False, "modelUsage": {"claude-test": {}}}


def seen(log):
    return json.loads(log.read_text(encoding="utf-8"))


def test_plan_via_cli_sends_the_prompt_on_stdin(tmp_path, monkeypatch):
    log = fake_claude(tmp_path, monkeypatch, ENVELOPE)
    got, _ = planner._plan_via_cli(LONG, "STATE", "REFERENCE")
    assert got["summary"] == "s"
    s = seen(log)
    assert LONG in s["stdin"] and "STATE" in s["stdin"]
    assert all(LONG[:40] not in a for a in s["argv"])
    assert s["argv"][:3] == ["-p", "--output-format", "json"] and "--model" in s["argv"]


def test_streaming_cli_sends_the_prompt_on_stdin(tmp_path, monkeypatch):
    log = fake_claude(tmp_path, monkeypatch, ENVELOPE)
    pieces = []
    text, _ = planner._cli_stream_text(LONG, on_text=pieces.append)
    assert json.loads(text) == PLAN and pieces
    s = seen(log)
    assert s["stdin"] == LONG
    assert s["argv"][:3] == ["-p", "--output-format", "stream-json"]
    assert "--include-partial-messages" in s["argv"] and all(LONG[:40] not in a for a in s["argv"])


def test_source_reader_sends_the_prompt_on_stdin(tmp_path, monkeypatch):
    log = fake_claude(tmp_path, monkeypatch, {"result": "read it", "is_error": False})
    assert describe._ask(LONG) == "read it"
    s = seen(log)
    assert s["stdin"] == LONG and s["argv"][:3] == ["-p", "--output-format", "json"]


def test_picture_reader_keeps_its_confinement_flags(tmp_path, monkeypatch):
    log = fake_claude(tmp_path, monkeypatch, {"result": "a rig", "is_error": False})
    assert describe._ask("look at the picture", cwd=str(tmp_path), image="rig.png") == "a rig"
    argv = seen(log)["argv"]
    assert argv[argv.index("--restricted"):] == ["--restricted", "--tools", "Read", "--strict-mcp-config",
                                                  "--allowedTools", "Read(./rig.png)"]
    assert seen(log)["stdin"] == "look at the picture"


def test_source_reader_still_stops_on_cancel(tmp_path, monkeypatch):
    """stdin is handed over on the first poll only; later polls must not
    resend it (Popen.communicate refuses input after it has started)."""
    script = tmp_path / "claude"
    script.write_text("#!/usr/bin/env python3\nimport sys, time\nsys.stdin.read()\ntime.sleep(30)\n",
                      encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(planner, "find_claude_cli", lambda: _executable(script, tmp_path))
    cancel = threading.Event()
    threading.Timer(1.2, cancel.set).start()
    with pytest.raises(describe.SourceCancelled):
        describe._ask(LONG, cancel=cancel)


@pytest.mark.parametrize("platform,expect", [("win32", True), ("darwin", False), ("linux", False)])
def test_cmdline_limit_is_only_a_windows_limit(platform, expect):
    long_args = ["grok", "-p", LONG]
    assert bool(planner._cmdline_too_long(long_args, platform)) is expect
    assert planner._cmdline_too_long(["grok", "-p", "short"], "win32") == 0


def _fill(units):
    """grok -p <x...> whose command line is exactly `units` UTF-16 units,
    terminating NUL included."""
    return ["grok", "-p", "x" * (units - 1 - len("grok -p "))]


def test_cmdline_limit_boundary_counts_the_terminating_nul():
    assert planner._cmdline_too_long(_fill(32767), "win32") == 0          # exactly fits
    assert planner._cmdline_too_long(_fill(32768), "win32") == 32768      # one over


def test_cmdline_limit_counts_utf16_units_not_characters():
    fits = _fill(32767)
    # swap two x for one guitar: same units, one character fewer
    guitar = ["grok", "-p", fits[2][:-2] + "\U0001F3B8"]
    assert planner._cmdline_too_long(guitar, "win32") == 0
    over = ["grok", "-p", fits[2][:-1] + "\U0001F3B8"]                   # one character, two units
    assert len(subprocess.list2cmdline(over)) + 1 == 32767                # characters say it fits
    assert planner._cmdline_too_long(over, "win32") == 32768              # units say it does not


def test_grok_on_windows_is_refused_in_words_before_it_starts(monkeypatch):
    monkeypatch.setattr(planner, "find_grok_cli", lambda: "grok.exe")
    monkeypatch.setattr(planner, "_cmdline_too_long",
                        lambda args, platform=None: len(subprocess.list2cmdline(args)))
    def no_start(*a, **k):
        raise AssertionError("grok was started")
    monkeypatch.setattr(planner.subprocess, "run", no_start)
    with pytest.raises(planner.BackendFailure) as exc:
        planner._plan_via_grok_cli(LONG, "STATE", "REFERENCE")
    assert "[unavailable]" in str(exc.value)
    assert "more than Windows allows (32,767); choose another backend in AI settings" in str(exc.value)

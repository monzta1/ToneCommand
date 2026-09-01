"""Choosing the planner backend from the UI (issue #24).

The rules that most need tests are the key-handling ones: a key must never
reach the browser, a blank key must keep the stored one, and clearing takes
an explicit flag. Getting any of those wrong leaks a secret into a page or
silently discards one.
"""
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fm9 import ai_settings, planner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the settings file at a tmp path, and start from a clean env.

    apply_to_env() writes real environment variables, which is the whole
    point of it, so the managed names are snapshotted and put back. monkeypatch
    only restores what monkeypatch itself set, and a variable a test caused
    the module to set would otherwise follow it into the next test.
    """
    path = tmp_path / "ai_settings.json"
    monkeypatch.setenv("TONECOMMAND_AI_SETTINGS", str(path))
    before = {name: os.environ.get(name) for name in ai_settings._MANAGED}
    for name in ai_settings._MANAGED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ai_settings, "_APPLIED", {})
    yield path
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture
def client(store, monkeypatch):
    import server
    monkeypatch.setattr(server, "_fm9", None, raising=False)
    return TestClient(server.app)


# --- the key never travels ---

def test_the_public_projection_reports_only_that_a_key_exists(store):
    saved = ai_settings.save({"backend": "openai", "baseUrl": "http://h/v1",
                              "apiKey": "sk-secret"})
    pub = saved.public()
    assert pub["hasKey"] is True
    assert "sk-secret" not in json.dumps(pub)
    assert "apiKey" not in pub and "api_key" not in pub


def test_the_endpoint_never_returns_the_key(client):
    client.post("/api/ai-settings", json={"backend": "openai",
                                          "baseUrl": "http://h/v1",
                                          "apiKey": "sk-must-not-leak"})
    got = client.get("/api/ai-settings")
    assert "sk-must-not-leak" not in got.text
    assert got.json()["settings"]["hasKey"] is True


def test_a_blank_key_keeps_the_stored_one(store):
    ai_settings.save({"backend": "openai", "baseUrl": "http://h/v1",
                      "apiKey": "sk-keep"})
    assert ai_settings.save({"backend": "openai", "baseUrl": "http://new/v1"}) \
        .key_for() == "sk-keep"
    assert ai_settings.save({"backend": "openai", "baseUrl": "http://new/v1",
                             "apiKey": ""}).key_for() == "sk-keep"


def test_clearing_takes_an_explicit_flag(store):
    ai_settings.save({"backend": "openai", "baseUrl": "http://h/v1",
                      "apiKey": "sk-drop"})
    assert ai_settings.save({"backend": "openai", "baseUrl": "http://h/v1",
                             "clearKey": True}).key_for() == ""
    assert ai_settings.load().key_for() == ""


def test_the_stored_file_is_gitignored():
    from pathlib import Path
    ignore = (Path(__file__).resolve().parent.parent / ".gitignore").read_text()
    assert "ai_settings.json" in ignore, "the settings file holds an API key"


# --- precedence and persistence ---

def test_the_file_wins_over_the_environment(store, monkeypatch):
    monkeypatch.setenv("PLANNER_BACKEND", "cli")
    assert ai_settings.load().backend == "cli"
    ai_settings.save({"backend": "grok"})
    assert ai_settings.load().backend == "grok"


def test_the_environment_is_the_fallback_when_no_file_exists(store, monkeypatch):
    monkeypatch.setenv("PLANNER_BASE_URL", "http://from-env/v1")
    assert not store.exists()
    assert ai_settings.load().base_url == "http://from-env/v1"


def test_a_choice_survives_a_restart(store):
    ai_settings.save({"backend": "grok", "model": "grok-4.6-build"})
    reloaded = ai_settings.load()           # a fresh read, as a new process would
    assert (reloaded.backend, reloaded.model_for()) == ("grok", "grok-4.6-build")


def test_a_corrupt_file_does_not_break_startup(store, monkeypatch):
    store.write_text("{ this is not json")
    monkeypatch.setenv("PLANNER_BACKEND", "cli")
    assert ai_settings.load().backend == "cli"


# --- the choice reaches the planner without changing it ---

def test_saving_makes_the_choice_effective_for_the_next_prompt(store):
    ai_settings.save({"backend": "grok"})
    assert planner.candidates() == ["grok"], \
        "the planner reads its own configuration; saving must land there"


def test_apply_to_env_clears_what_is_no_longer_set(store, monkeypatch):
    ai_settings.save({"backend": "openai", "baseUrl": "http://h/v1"})
    assert planner._openai_base_url() == "http://h/v1"
    ai_settings.save({"backend": "cli"})
    assert planner._openai_base_url() == "", \
        "a base URL must not steer a backend that never reads it"


def test_an_unknown_backend_is_refused(store, client):
    with pytest.raises(ValueError, match="unknown backend"):
        ai_settings.save({"backend": "gpt9"})
    assert client.post("/api/ai-settings", json={"backend": "gpt9"}).status_code == 400


# --- only offer what the host can run ---

def test_unavailable_backends_are_reported_with_a_reason(store, monkeypatch):
    monkeypatch.setattr(planner, "find_grok_cli", lambda: None)
    monkeypatch.setattr(planner, "find_claude_cli", lambda: None)
    by_name = {b["backend"]: b for b in ai_settings.available_backends()}
    assert by_name["grok"]["available"] is False
    assert "grok binary" in by_name["grok"]["why"]
    assert by_name["cli"]["available"] is False


def test_availability_lists_auto_first_then_the_planner_order(store):
    """Auto is what a fresh install does, so it heads the list and is always
    available; the rest follow the planner's own candidate order."""
    order = [b["backend"] for b in ai_settings.available_backends()]
    assert order == [""] + list(planner.BACKENDS)
    assert ai_settings.available_backends()[0]["available"] is True


def test_a_backend_the_panel_can_configure_stays_selectable(store):
    """The closed loop @Triumph1701 found on #25: openai was disabled until a
    base URL existed, and Claude API until a key existed, but the boxes that
    set those only appear once the backend is selected. Disabled is reserved
    for what the panel cannot fix."""
    def entry(name):
        return [b for b in ai_settings.available_backends()
                if b["backend"] == name][0]
    for name in ("openai", "api"):
        assert entry(name)["available"] is True, name
        assert entry(name)["needs"], f"{name} should say what it still needs"
    ai_settings.save({"backend": "", "baseUrl": "http://127.0.0.1:8317/v1"})
    assert entry("openai")["needs"] == ""


# --- the UI surfaces which backend answered ---

def _ui() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


def test_the_ui_shows_the_answering_backend():
    ui = _ui()
    assert "planned by" in ui, "a plan must be attributable to the model behind it"
    assert "plan.backend" in ui and "plan.model" in ui


def test_no_em_dashes_in_the_ui_or_the_settings_module():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for rel in ("ui/index.html", "fm9/ai_settings.py"):
        assert "—" not in (root / rel).read_text(), f"em dash in {rel}"


# --- every control must map to a variable the chosen backend actually reads ---

def test_each_backend_declares_only_the_controls_it_honours(store):
    by_name = {b["backend"]: b for b in ai_settings.available_backends()}
    # every backend takes a model now that the Claude ones are configurable,
    # but only two of them take a key and only one takes a base URL
    assert by_name["cli"]["needsModel"] and not by_name["cli"]["needsKey"]
    assert not by_name["cli"]["needsBaseUrl"]
    assert by_name["api"]["needsKey"] and by_name["api"]["needsModel"]
    assert not by_name["api"]["needsBaseUrl"]
    assert by_name["grok"]["needsModel"] and not by_name["grok"]["needsKey"]
    assert by_name["openai"]["needsBaseUrl"] and by_name["openai"]["needsModel"]


def test_the_claude_models_land_in_the_variables_the_planner_reads(store):
    import os
    ai_settings.save({"backend": "cli", "model": "opus"})
    assert os.environ.get("CLAUDE_CLI_MODEL") == "opus"
    assert planner.cli_model() == "opus"
    ai_settings.save({"backend": "api", "model": "claude-sonnet-5",
                      "apiKey": "sk-ant-x"})
    assert planner.api_model() == "claude-sonnet-5"
    assert "CLAUDE_CLI_MODEL" not in os.environ, \
        "a model for one backend must not leak into another"


def test_model_suggestions_come_with_their_source(store):
    """A list that cannot be overridden is worse than no list once it goes
    stale, so these are suggestions and say where they came from."""
    cli = ai_settings.list_models("cli")
    assert "sonnet" in cli["models"] and "opus" in cli["models"]
    assert cli["source"]
    assert ai_settings.list_models("openai")["source"] == "set a base URL first"


def test_grok_model_suggestions_survive_a_missing_binary(store, monkeypatch):
    monkeypatch.setattr(planner, "find_grok_cli", lambda: None)
    got = ai_settings.list_models("grok")
    assert got["models"] == []
    assert "not on this machine" in got["source"]


def test_the_grok_model_lands_in_the_variable_grok_reads(store):
    """It reads GROK_CLI_MODEL, not PLANNER_MODEL, so a shared box would have
    done nothing at all."""
    import os
    ai_settings.save({"backend": "grok", "model": "grok-4.6-build"})
    assert os.environ.get("GROK_CLI_MODEL") == "grok-4.6-build"
    assert "PLANNER_MODEL" not in os.environ


def test_the_claude_api_key_lands_in_anthropic_api_key(store):
    """The Claude API path reads ANTHROPIC_API_KEY. Storing it as
    PLANNER_API_KEY left that backend permanently unselectable."""
    import os
    ai_settings.save({"backend": "api", "apiKey": "sk-ant-real"})
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-real"
    assert "PLANNER_API_KEY" not in os.environ
    assert planner._api_available() is True
    assert [b for b in ai_settings.available_backends()
            if b["backend"] == "api"][0]["available"] is True


def test_keys_are_stored_per_backend_not_shared(store):
    """An OpenAI router key must never quietly become an Anthropic one."""
    ai_settings.save({"backend": "openai", "baseUrl": "http://h/v1",
                      "apiKey": "sk-router"})
    ai_settings.save({"backend": "api", "apiKey": "sk-ant"})
    stored = ai_settings.load()
    assert stored.keys["openai"] == "sk-router"
    assert stored.keys["api"] == "sk-ant"


def test_a_stale_value_cannot_steer_a_backend_that_ignores_it(store):
    import os
    ai_settings.save({"backend": "openai", "baseUrl": "http://h/v1",
                      "model": "llama3.3"})
    ai_settings.save({"backend": "grok"})
    assert "PLANNER_BASE_URL" not in os.environ
    assert "PLANNER_MODEL" not in os.environ


def test_auto_mode_still_honours_a_configured_endpoint(store):
    """In auto the planner tries a configured router first (#21), so a base
    URL is meaningful there even with no backend pinned."""
    import os
    ai_settings.save({"backend": "", "baseUrl": "http://127.0.0.1:8317/v1"})
    assert os.environ.get("PLANNER_BASE_URL") == "http://127.0.0.1:8317/v1"
    assert planner.candidates()[0] == "openai"


def test_every_model_box_is_optional(store):
    """Each backend has a default model, so a blank box is always valid."""
    for entry in ai_settings.available_backends():
        assert entry["modelOptional"] is True


def test_the_key_field_states_the_whole_rule(store):
    """A key an OAuth router never wanted should not send anyone hunting, and
    a key the Claude API cannot run without must not read as optional. One
    label covers both rather than trusting a per-backend word."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    assert "model (optional)" in ui
    assert "API key (required for Claude API but optional for others)" in ui
    assert "keyOptional" not in ui, "that flag drove the old per-backend label"


def test_the_model_source_line_is_set_not_appended(store):
    """It used to append to the note, so switching backends a few times
    stacked "Models from ..." several deep in one line."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    assert "$('ainote').textContent +=" not in ui
    assert "aisrc" in ui, "the source line needs its own element"
    assert "$('aibackend').value !== backend) return;" in ui, \
        "a slow listing must not land under a different backend"


# --- outranking the environment is not erasing it (#25, finding 1) ---

def test_applying_a_choice_leaves_an_exported_key_alone(store, monkeypatch):
    """The one that defeated the feature: with ANTHROPIC_API_KEY exported and
    no file, server startup called apply_to_env() and the Claude API backend
    vanished from candidates() with nothing changed and nothing said."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
    before = planner.candidates()
    assert "api" in before
    ai_settings.apply_to_env()
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-from-shell"
    assert planner.candidates() == before


def test_an_exported_base_url_survives_a_save_that_does_not_mention_it(
        store, monkeypatch):
    """Same shape, and worse: PLANNER_BASE_URL was wiped and never persisted,
    so a router the user had configured by hand simply stopped being used."""
    monkeypatch.setenv("PLANNER_BASE_URL", "http://router.local/v1")
    ai_settings.save({"backend": "cli"})
    assert os.environ["PLANNER_BASE_URL"] == "http://router.local/v1"
    assert ai_settings.load().base_url == "http://router.local/v1"


def test_a_value_this_module_set_is_still_taken_back(store, monkeypatch):
    """Releasing must not become never letting go: the panel's own value has
    to disappear when the panel stops asking for it, or a stale model id
    steers a backend it was never meant for."""
    ai_settings.save({"backend": "grok", "model": "grok-4.6"})
    assert os.environ["GROK_CLI_MODEL"] == "grok-4.6"
    ai_settings.save({"backend": "cli", "model": ""})
    assert "GROK_CLI_MODEL" not in os.environ


def test_releasing_restores_what_the_panel_displaced(store, monkeypatch):
    """A panel value on top of an exported one, then the panel value goes: the
    user's own setting comes back rather than being collateral damage."""
    monkeypatch.setenv("GROK_CLI_MODEL", "grok-from-shell")
    ai_settings.save({"backend": "grok", "model": "grok-4.6"})
    assert os.environ["GROK_CLI_MODEL"] == "grok-4.6"
    ai_settings.save({"backend": "cli"})
    assert os.environ["GROK_CLI_MODEL"] == "grok-from-shell"


# --- the Claude API backend can be reached (#25, finding 2) ---

def test_claude_api_can_be_enabled_through_the_panel(client, store):
    """End to end through the endpoints the panel actually calls. It used to
    be unreachable: the option was disabled without a key, and the key box
    only appears once the option is selected."""
    entries = {b["backend"]: b for b in client.get("/api/ai-settings").json()["backends"]}
    assert entries["api"]["available"] is True
    assert entries["api"]["needsKey"] is True

    r = client.post("/api/ai-settings", json={"backend": "api",
                                              "apiKey": "sk-ant-typed"})
    assert r.status_code == 200
    assert r.json()["settings"] == {"backend": "api", "baseUrl": "",
                                    "model": "", "hasKey": True}
    assert planner.candidates() == ["api"]
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-typed"


def test_pinning_a_backend_that_cannot_run_is_refused_in_words(client, store):
    """Pinning disables fallthrough (#21), so an unconfigured pin buys a
    failed prompt later. Say so now instead."""
    r = client.post("/api/ai-settings", json={"backend": "api"})
    assert r.status_code == 400
    assert "Anthropic API key" in r.json()["error"]
    assert not store.exists(), "a refused save must not persist"

    r = client.post("/api/ai-settings", json={"backend": "openai",
                                              "baseUrl": ""})
    assert r.status_code == 400
    # Plain words on purpose: "base URL" named the field, "an address" names
    # the thing, and the panel offers the services that supply one.
    assert "needs an address" in r.json()["error"]


def test_a_key_in_dot_env_is_enough_to_pin_the_api_backend(store, monkeypatch):
    """The check is against what will be in effect, not against the file."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
    assert ai_settings.save({"backend": "api"}).backend == "api"


# --- only what the user typed gets written down (#25, finding 3) ---

def test_a_shell_key_is_never_copied_into_the_settings_file(store, monkeypatch):
    """Two problems in one: a secret the user chose to keep in their shell
    appears in a new file on disk unasked, and because the file outranks .env,
    rotating it there afterwards silently does nothing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
    ai_settings.save({"backend": "cli"})
    stored = json.loads(store.read_text())
    assert stored["keys"] == {}, stored
    assert "sk-ant-from-shell" not in store.read_text()


def test_rotating_a_key_in_the_environment_still_takes_effect(store, monkeypatch):
    """The consequence of the above, stated as the user would experience it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-first")
    ai_settings.save({"backend": "cli"})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-second")
    assert ai_settings.load().key_for("api") == "sk-second"


def test_an_env_model_is_not_pinned_into_the_file_either(store, monkeypatch):
    monkeypatch.setenv("GROK_CLI_MODEL", "grok-from-shell")
    ai_settings.save({"backend": "cli", "model": "opus"})
    stored = json.loads(store.read_text())
    assert stored["models"] == {"cli": "opus"}, stored


# --- model strings from an endpoint are not trusted markup (#25, findings 4, 5)

def test_the_answering_model_is_written_as_text_not_markup():
    ui = _ui()
    assert "by.textContent" in ui, "plan.model must not be inserted as HTML"
    assert "insertAdjacentHTML('afterend'" not in ui


def test_remote_model_ids_are_not_interpolated_into_an_attribute():
    ui = _ui()
    assert 'value="${m}"' not in ui, "an id with a quote breaks out of this"
    assert "opt.value = m" in ui


def test_plan_card_strings_are_escaped():
    """Every string on a card is model output, and the model can now be any
    endpoint the user configured."""
    ui = _ui()
    assert "esc(describe(a))" in ui
    assert "esc(a.reason" in ui


# --- listing models cannot hang the panel (#25, finding 6) ---

def test_listing_anthropic_models_is_bounded(store, monkeypatch):
    """The grok and endpoint listers time out at 20s and 10s. Without one here
    a hung network pins a threadpool worker for the SDK default plus retries,
    and the panel looks frozen rather than slow."""
    seen = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.models = self

        def list(self, **_):
            return type("L", (), {"data": [type("M", (), {"id": "claude-x"})()]})()

    monkeypatch.setitem(sys.modules, "anthropic",
                        type(sys)("anthropic"))
    sys.modules["anthropic"].Anthropic = FakeAnthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    out = ai_settings.list_models("api")
    assert out["models"] == ["claude-x"]
    assert seen.get("timeout"), "no timeout on the Anthropic client"
    assert seen["timeout"] <= 30
    assert seen.get("max_retries") is not None


# --- Auto is a choice, not the absence of one (#25 review) ---

def test_selecting_auto_clears_a_pin_from_the_environment(store, monkeypatch):
    """The defect that made the panel unable to honour its own setting: with
    PLANNER_BACKEND=grok exported and Auto selected, the file stored 'grok',
    the variable stayed 'grok', and candidates() stayed pinned."""
    monkeypatch.setenv("PLANNER_BACKEND", "grok")
    assert planner.candidates() == ["grok"]
    saved = ai_settings.save({"backend": ""})
    assert saved.backend == ""
    assert json.loads(store.read_text())["backend"] == ""
    assert planner.candidates() != ["grok"]


def test_selecting_auto_clears_a_pin_from_dot_env(store, isolated_env):
    """The harder half: .env is read on every lookup, so an unset variable is
    not enough. A present blank is what says "no pin" on that channel."""
    isolated_env.write_text("PLANNER_BACKEND=grok\n")
    assert planner.candidates() == ["grok"]
    ai_settings.save({"backend": ""})
    assert planner.candidates() != ["grok"]
    assert ai_settings.load().backend == ""


def test_auto_survives_a_reload_rather_than_snapping_back(store, monkeypatch):
    """GET used to report the env pin again, so the dropdown snapped back
    after a successful save."""
    monkeypatch.setenv("PLANNER_BACKEND", "grok")
    ai_settings.save({"backend": ""})
    assert ai_settings.load().backend == ""
    assert ai_settings.panel_state()["backend"] == ""


def test_never_having_chosen_still_defers_to_the_environment(store, monkeypatch):
    """Auto must win, but only when it was actually picked. A file with no
    backend key at all is not a vote for anything."""
    store.write_text(json.dumps({"baseUrl": "http://h/v1"}))
    monkeypatch.setenv("PLANNER_BACKEND", "grok")
    assert ai_settings.load().backend == "grok"
    ai_settings.apply_to_env()
    assert planner.candidates() == ["grok"]


# --- the boxes hold what is stored, not what the environment provides ---

def test_a_save_does_not_pin_a_base_url_that_came_from_the_environment(
        store, monkeypatch):
    """The panel prefilled the box from the merged view and posted it back, so
    opening the panel and clicking SAVE pinned a .env value in the file. The
    file outranks .env, so editing .env afterwards silently did nothing."""
    monkeypatch.setenv("PLANNER_BASE_URL", "http://from-env/v1")
    state = ai_settings.panel_state()
    assert state["baseUrl"] == "", "the box shows only what is stored"
    assert state["baseUrlFallback"] == "http://from-env/v1"

    ai_settings.save({"backend": "", "baseUrl": state["baseUrl"]})
    assert json.loads(store.read_text())["baseUrl"] == ""
    monkeypatch.setenv("PLANNER_BASE_URL", "http://rotated/v1")
    assert ai_settings.load().base_url == "http://rotated/v1"


def test_a_save_does_not_pin_a_model_that_came_from_the_environment(
        store, monkeypatch):
    monkeypatch.setenv("GROK_CLI_MODEL", "grok-from-env")
    entry = [b for b in ai_settings.available_backends()
             if b["backend"] == "grok"][0]
    assert entry["model"] == ""
    assert entry["modelFallback"] == "grok-from-env"

    ai_settings.save({"backend": "grok", "model": entry["model"]})
    assert "grok" not in json.loads(store.read_text())["models"]
    monkeypatch.setenv("GROK_CLI_MODEL", "grok-rotated")
    assert ai_settings.load().models["grok"] == "grok-rotated"


def test_the_panel_shows_the_environment_value_as_a_hint():
    ui = _ui()
    assert "baseUrlFallback" in ui and "modelFallback" in ui
    assert ".env says" in ui, "a blank box that works needs to say why"


def test_the_openai_default_does_not_overwrite_an_env_base_url():
    ui = _ui()
    assert "&& !aiEnvBaseUrl" in ui


# --- the file holds a key, so only its owner may read it ---

def test_the_settings_file_is_not_world_readable(store):
    """Path.write_text uses the process umask, commonly 0644. Patch from
    @Triumph1701 on #25."""
    import stat
    ai_settings.save({"backend": "cli"})
    mode = store.stat().st_mode
    assert not mode & stat.S_IROTH, "world-readable"
    assert not mode & stat.S_IRGRP, "group-readable"
    assert stat.S_IMODE(mode) == 0o600

    # a file predating the fix is tightened rather than left as found
    os.chmod(store, 0o644)
    ai_settings.save({"backend": "cli"})
    assert stat.S_IMODE(store.stat().st_mode) == 0o600


# --- the log line was the last raw sink for model output ---

def test_log_lines_are_escaped():
    ui = _ui()
    assert "esc(msg)" in ui, "clarifications and planner errors reach here"


# --- a save cannot land in the middle of a plan ---

def test_a_save_during_a_plan_is_refused_rather_than_torn(client, store):
    """candidates() has already chosen a backend by then, and the runner
    rereads the base URL and key, so a half-applied save sends the new key at
    the old URL."""
    import server
    server._settings_lock.acquire()
    try:
        r = client.post("/api/ai-settings", json={"backend": "cli"})
    finally:
        server._settings_lock.release()
    assert r.status_code == 409
    assert "plan is in flight" in r.json()["error"]
    assert not store.exists(), "a refused save must not persist"

    assert client.post("/api/ai-settings",
                       json={"backend": "cli"}).status_code == 200


# --- a short name for places with no room to explain ---

def test_every_backend_has_a_short_name_fit_for_a_pill():
    """The header button names the model that is about to read your prompt.

    The dropdown labels read like sentences because a dropdown has room for
    one. "auto (let the planner choose)" in a header pill truncates to
    "auto (let the plan...", which is worse than either form, so the short
    name is a real string rather than an ellipsis.
    """
    for b in ai_settings.available_backends():
        short = b["short"]
        assert short and "(" not in short, b["backend"]
        assert len(short) <= 16, f"{short!r} will not fit a header pill"


def test_the_short_names_live_beside_the_long_ones():
    """Both tables cover the same backends, so adding one cannot leave the
    button falling back to a raw key like 'openai'."""
    assert set(ai_settings.BACKEND_SHORT) == set(ai_settings.BACKEND_LABELS)


# --- naming the services, instead of naming the protocol ------------------
#
# "OpenAI-compatible endpoint" over an empty box is accurate and useless.
# Somebody who wants to use ChatGPT does not know ChatGPT speaks that
# protocol, and certainly does not know to type https://api.openai.com/v1.

def test_chatgpt_is_offered_by_name_with_its_address():
    by_name = {p["name"]: p for p in ai_settings.ENDPOINT_PRESETS}
    assert "ChatGPT" in by_name
    assert by_name["ChatGPT"]["url"] == "https://api.openai.com/v1"
    assert by_name["ChatGPT"]["key"] == "required"


def test_every_preset_is_complete_and_addressable():
    for p in ai_settings.ENDPOINT_PRESETS:
        assert set(p) == {"name", "url", "key", "help"}, p
        assert p["url"].startswith("http") and p["url"].endswith("/v1"), p
        assert p["key"] in ("required", "no"), p
        assert len(p["help"]) > 40, p          # a label is not an explanation


def test_no_preset_hardcodes_a_model_id():
    """Model ids are listed live from the endpoint's own /models. One frozen
    here is wrong the day the provider retires it, and wrong silently."""
    for p in ai_settings.ENDPOINT_PRESETS:
        assert "model" not in p, p


def test_the_paid_route_says_it_is_paid_and_separate_from_plus():
    """A ChatGPT Plus subscription does not carry API access. Finding that
    out from a 401 after pasting the wrong thing is a bad afternoon."""
    chatgpt = next(p for p in ai_settings.ENDPOINT_PRESETS
                   if p["name"] == "ChatGPT")
    assert "separate account" in chatgpt["help"]
    assert "bills per request" in chatgpt["help"]


def test_the_free_route_exists_and_is_named_for_what_it_saves():
    """Using a subscription already paid for is the frugal path, so it is
    named by its benefit rather than by the proxy's product name."""
    sub = next(p for p in ai_settings.ENDPOINT_PRESETS
               if p["url"] == ai_settings.CLIPROXY_DEFAULT_URL)
    assert "subscription" in sub["name"].lower()
    assert sub["key"] == "no"


def test_the_dropdown_entry_no_longer_names_only_a_protocol():
    label = ai_settings.BACKEND_LABELS["openai"]
    assert "ChatGPT" in label
    assert "OpenAI-compatible" not in label, "a protocol name is not a service"


def test_the_browser_is_given_the_presets(client):
    d = client.get("/api/ai-settings").json()
    assert [p["name"] for p in d["endpoints"]] == \
        [p["name"] for p in ai_settings.ENDPOINT_PRESETS]


def test_the_still_needed_line_does_not_repeat_the_note():
    """It read "Still needed: an address: pick one of the services above, or
    type your own." directly after a sentence saying exactly that."""
    need = ai_settings.missing_setup("openai", ai_settings.AiSettings())
    assert need == "an address"
    assert need not in ai_settings.BACKEND_NOTES["openai"]


def test_the_note_points_the_right_way_up():
    """The chips sit above the note, so "below" sends the reader past it."""
    note = ai_settings.BACKEND_NOTES["openai"]
    assert "above" in note and "below" not in note


# --- filling the model box, not merely offering a list --------------------
#
# Blank is not a safe default on a hosted service: with no model the planner
# sends "local", and ChatGPT answers a 404 for a model nobody typed. So
# "optional" was a lie on exactly the route this panel now recommends.

def test_the_catalogue_is_not_the_menu():
    """A /models listing is everything the account can reach, most of which
    cannot write a tone plan."""
    kept = ai_settings.usable_models([
        "gpt-5", "text-embedding-3-small", "whisper-1", "dall-e-3", "tts-1",
        "omni-moderation-latest", "gpt-4o-realtime-preview", "gpt-image-1",
        "codex-mini-latest"])
    assert kept == ["gpt-5"]


def test_legacy_completion_models_are_dropped():
    """They answer, so nothing filters them by shape, and they cannot follow
    the plan schema. babbage-002 sorting first would have been auto-filled."""
    assert ai_settings.usable_models(
        ["babbage-002", "davinci-002", "gpt-3.5-turbo-instruct", "gpt-4o"]
    ) == ["gpt-4o"]


def test_the_undated_alias_is_offered_before_the_snapshot():
    """The box is FILLED with the first entry, and a listing arrives in no
    order at all, so first has to mean best rather than whatever came back.
    The undated alias keeps working after a snapshot is retired."""
    got = ai_settings.usable_models(["gpt-4o-2024-08-06", "gpt-5"])
    assert got[0] == "gpt-5"


def test_a_local_servers_own_names_survive():
    """The filter must not be an allowlist: a model on someone's laptop is
    named whatever they named it."""
    names = ["llama-3.3-70b", "qwen2.5-coder-32b", "mistral-nemo"]
    assert ai_settings.usable_models(names) == names


def test_models_can_be_listed_against_an_address_not_yet_saved(store, monkeypatch):
    """Picking a service and being handed an empty model box is the same dead
    end the address box used to be, one field further down."""
    seen = {}

    def fake(base_url=""):
        seen["base"] = base_url
        return ["gpt-5"], "stub"

    monkeypatch.setattr(ai_settings, "_endpoint_models", fake)
    out = ai_settings.list_models("openai", "https://api.openai.com/v1")
    assert seen["base"] == "https://api.openai.com/v1"
    assert out["models"] == ["gpt-5"]


def test_the_endpoint_passes_the_typed_address_through(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(ai_settings, "list_models",
                        lambda b, u="": seen.update(backend=b, url=u) or
                        {"backend": b, "models": [], "source": ""})
    client.get("/api/ai-settings/models?backend=openai&base_url=http%3A%2F%2Fx%2Fv1")
    assert seen == {"backend": "openai", "url": "http://x/v1"}


def test_the_browser_fills_the_box_but_never_overwrites_a_choice():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function loadAiModels(backend)")[1].split("\n}\n")[0]
    assert "!$('aimodel').value.trim()" in fn, "must only fill an empty box"
    assert "$('aimodel').value = models[0]" in fn
    # and the listing must be asked against what is typed
    assert "base_url=${encodeURIComponent(typedUrl)}" in fn


def test_a_stale_listing_cannot_land_on_a_fresh_one():
    """Changing backend then address fires two listings, and a slow first
    reply landed after a fast second and overwrote a correct list with "no
    model list yet". Both carried the same backend, so guarding on that
    alone did not catch it."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function loadAiModels(backend)")[1].split("\n}\n")[0]
    assert "const seq = ++aiModelsSeq;" in fn
    assert "seq !== aiModelsSeq" in fn


def test_the_key_box_stops_contradicting_the_service_above_it():
    """"optional for others" sat directly under "A key is required.", and
    "model (optional)" is plainly false on a hosted service where blank
    sends "local" and earns a 404 for a model nobody typed."""
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("function renderAiPresets()")[1].split("\n}\n")[0]
    assert "API key, required for this service" in fn
    assert "no key needed for this service" in fn
    assert "fills itself in once you save a key" in fn
    # a stored key must still say so rather than demand another
    assert "dataset.stored === '1'" in fn
    # and it must not paste a chip's phrase into a sentence: "no key needed
    # for A subscription you already pay for" is not English
    assert "${current.name} key" not in fn


# --- a saved setting is not a working one ---------------------------------

def test_saving_warns_when_nothing_is_listening(client, store):
    """Choosing the subscription route without the router running saved
    cleanly and then failed at the next prompt. _check_runnable only asked
    whether an address was FILLED IN, never whether anything answered it."""
    r = client.post("/api/ai-settings",
                    json={"backend": "openai",
                          "baseUrl": "http://127.0.0.1:9/v1"})
    assert r.status_code == 200, "a warning, never a refusal"
    assert "nothing is answering" in r.json()["warning"]


def test_a_reachable_endpoint_warns_about_nothing(client, store, monkeypatch):
    monkeypatch.setattr(ai_settings, "endpoint_reachable", lambda u: "")
    r = client.post("/api/ai-settings",
                    json={"backend": "openai", "baseUrl": "http://x/v1"})
    assert r.json()["warning"] == ""


def test_an_http_error_is_a_running_service(monkeypatch):
    """401 without a key means it answered. Treating that as unreachable
    would cry wolf on every correctly configured hosted endpoint."""
    import urllib.error
    import urllib.request

    def boom(*a, **k):
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert ai_settings.endpoint_reachable("https://api.openai.com/v1") == ""


def test_the_warning_reaches_the_log_not_just_the_response():
    ui = (ROOT / "ui" / "index.html").read_text()
    fn = ui.split("async function saveAiSettings(extra)")[1].split("\n}\n")[0]
    assert "if (d.warning) log(d.warning, 'warn');" in fn

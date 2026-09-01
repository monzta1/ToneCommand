"""What a stranger is allowed to write into the repository.

With auto-publish on, /submit is an unauthenticated endpoint that commits a
file into a public repo. Moncy's position, and it is the right one: that is
fine as long as what lands is genuinely an FM9 recipe and nothing else.

The filename was never the risk. `name` is `[a-z0-9-]` only, so the path is
always `recipes/<name>.json`: no traversal, nothing outside that folder. The
CONTENT was the risk, and it was unbounded: the original check validated the
envelope and never looked inside a step, while publish() writes the whole body
verbatim, so any invented top-level key was preserved into the repository.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKER = (ROOT / "service" / "worker.js").read_text()

HARNESS = r"""
import { readFileSync } from "fs";
const src = readFileSync(process.argv[2], "utf8");
const mod = src.slice(src.indexOf("const RECIPE_KEYS"), src.indexOf("export default"));
const readRecipe = new Function(mod + "\nreturn readRecipe;")();
const body = JSON.parse(readFileSync(process.argv[3], "utf8"));
const why = readRecipe(body);
console.log(why === null ? "ACCEPTED" : "REJECTED: " + why);
"""


def _check(tmp_path, body) -> str:
    """Run the worker's OWN validator, not a Python re-implementation of it.

    A second copy of a rule is a second thing to get wrong, and this rule
    decides what a stranger may write into the repository.
    """
    if not hasattr(_check, "harness"):
        h = tmp_path.parent / "harness.mjs"
        h.write_text(HARNESS)
        _check.harness = h
    payload = tmp_path / "body.json"
    payload.write_text(json.dumps(body))
    out = subprocess.run(["node", str(_check.harness), str(ROOT / "service/worker.js"),
                          str(payload)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


OK = {"recipe_version": 1, "name": "good-tone", "title": "A tone",
      "author": "someone", "steps": [{"kind": "set_scene", "value": 1}]}


def test_a_real_recipe_is_accepted(tmp_path):
    assert _check(tmp_path, OK) == "ACCEPTED"


def test_the_repositorys_own_recipes_still_validate(tmp_path):
    """Tightening a validator that rejects the existing catalogue is not a
    tightening, it is a break."""
    files = list((ROOT / "recipes").glob("*.json"))
    assert files, "no recipes to check"
    for f in files:
        assert _check(tmp_path, json.loads(f.read_text())) == "ACCEPTED", f.name


@pytest.mark.parametrize("label,body", [
    ("path traversal", {**OK, "name": "../../.github/workflows/evil"}),
    ("a slash in the name", {**OK, "name": "a/b"}),
    ("an invented top level key", {**OK, "notes": "x" * 60000}),
    ("steps that are not objects", {**OK, "steps": [1, 2, 3]}),
    ("a step with no kind", {**OK, "steps": [{"block": "amp"}]}),
    ("an unknown step kind", {**OK, "steps": [{"kind": "rm -rf"}]}),
    ("an invented key inside a step", {**OK, "steps": [{"kind": "set_scene", "evil": "x"}]}),
    ("a 60KB title", {**OK, "title": "x" * 60000}),
    ("a body that is a list", [1, 2, 3]),
    ("a future recipe_version", {**OK, "recipe_version": 2}),
])
def test_what_must_be_refused(tmp_path, label, body):
    assert _check(tmp_path, body).startswith("REJECTED"), label


def test_a_shared_recipe_may_not_store_to_a_slot(tmp_path):
    """`store` is the one action that writes to flash. A recipe from a
    stranger has no business overwriting one of the owner's presets, and while
    the app would still gate it behind the store whitelist and a confirmation,
    a shared recipe should not be asking in the first place."""
    out = _check(tmp_path, {**OK, "steps": [{"kind": "store", "value": 12}]})
    assert "may not store" in out


def test_markup_in_text_is_data_not_a_hole(tmp_path):
    """Accepted on purpose. The browser escapes every recipe field it draws
    (`esc(r.title)`), so text stays text. Refusing it would be theatre that
    also rejects a legitimate tone called "<12dB cut>"."""
    assert _check(tmp_path, {**OK, "title": "<script>alert(1)</script>"}) == "ACCEPTED"
    ui = (ROOT / "ui" / "index.html").read_text()
    row = ui.split("$('rlist').innerHTML = list.map")[1].split("}).join")[0]
    for field in ("r.title || r.name", "r.author", "r.assumes"):
        assert f"esc({field})" in row, field


def test_the_action_kinds_match_the_planners(tmp_path):
    """Two lists that must agree and cannot import each other need something
    that fails when they drift."""
    from fm9.planner import ACTION_KINDS as _kinds
    ACTION_KINDS = set(_kinds)
    block = WORKER.split("const ACTION_KINDS = new Set([")[1].split("]);")[0]
    worker_kinds = set(re.findall(r'"(\w+)"', block))
    # store is deliberately absent from the worker's set, and only store
    assert ACTION_KINDS - worker_kinds == {"store"}, ACTION_KINDS - worker_kinds
    assert worker_kinds - ACTION_KINDS == set()


def test_publishing_refuses_to_overwrite():
    """Not moderation, integrity: without it anyone could POST a recipe named
    after a curated tone and silently replace it."""
    fn = WORKER.split("async function publish(env, recipe)")[1].split("\n}\n")[0]
    assert "already exists" in fn
    assert "existing.status === 200" in fn


def test_the_path_written_is_always_inside_recipes():
    fn = WORKER.split("async function publish(env, recipe)")[1].split("\n}\n")[0]
    assert 'const path = `recipes/${recipe.name}.json`' in fn


def test_auto_publish_is_a_setting_and_defaults_to_off():
    """Off is the safe default for anyone else who deploys this."""
    sub = WORKER.split('url.pathname === "/submit"')[1].split('url.pathname ===')[0]
    assert 'env.AUTO_PUBLISH !== "true"' in sub
    toml = (ROOT / "service" / "wrangler.toml").read_text()
    assert "AUTO_PUBLISH" in toml


def test_every_submission_is_recorded_whatever_happens_next():
    """The row is the audit trail, and with auto-publish on it is the only
    record of who sent what and when."""
    sub = WORKER.split('url.pathname === "/submit"')[1].split("if (env.AUTO_PUBLISH")[0]
    assert "INSERT OR IGNORE INTO submissions" in sub


# --- a recipe from a different firmware ------------------------------------

def test_a_recipe_names_models_it_does_not_number_them():
    """This is the whole reason a recipe is portable across firmware.

    A step says `type_name: "Brit 800 2204 High"` and resolves through the
    LOADING rig's own roster. Ordinals move between releases as Fractal adds
    models, so a recipe carrying ordinal 250 would silently load whatever now
    sits at 250. Carrying the name means it either finds the right model or
    finds nothing.
    """
    for f in (ROOT / "recipes").glob("*.json"):
        body = json.loads(f.read_text())
        for step in (body.get("actions") or body.get("steps")):
            if step.get("kind") == "set_type":
                assert isinstance(step.get("type_name"), str), f.name
                assert "ordinal" not in step, f.name


def test_a_model_this_rig_does_not_have_is_refused_not_guessed():
    """The failure mode that matters. A recipe from newer firmware naming a
    model that does not exist here must not become its neighbour."""
    import server
    errs, _ = server.validate_action(server.Action(
        kind="set_type", block="amp", instance=1,
        type_name="Some Amp From Firmware 15"))
    assert any("unknown model name" in e for e in errs)


def test_the_firmware_gap_is_surfaced():
    """Validation catches everything structural. It cannot catch a revoiced
    model, and `tested_firmware` was being recorded and never shown."""
    from fm9 import recipes
    note = recipes.firmware_note("13.00", "12.00")
    assert "13.00" in note and "12.00" in note
    assert "sound different" in note
    assert "Trust your ears" in note


def test_no_note_when_there_is_nothing_to_say():
    from fm9 import recipes
    assert recipes.firmware_note("12.00", "12.00") == ""
    assert recipes.firmware_note("", "12.00") == ""
    assert recipes.firmware_note("13.00", "") == ""


def test_the_note_reaches_the_plan_and_the_browser():
    src = (ROOT / "server.py").read_text()
    fn = src.split("def api_recipe_plan(")[1].split("\n@app")[0]
    assert "firmware_note" in fn
    # a rig that does not answer must not break planning a recipe
    assert "except Exception:" in fn
    ui = (ROOT / "ui" / "index.html").read_text()
    assert "d.firmware_note" in ui


def test_the_firmware_label_is_written_the_way_fractal_writes_it():
    """12.00, not 12.0: that is how the unit shows it and how the recipes in
    this repository record it, and a mismatch in format would make every
    comparison a false positive."""
    from fm9.registry import Registry
    from fm9.sim import SimFM9
    with SimFM9(Registry()) as dev:
        assert re.fullmatch(r"\d+\.\d\d", dev.firmware_label())

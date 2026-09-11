"""The nam_captures grounding sidecar and the recipe tone_target it grounds
(#18, items 1 and 2). Facts-only citation: a recipe may point at a real
TONE3000 A2 capture, and the AI never invents one.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fm9 import nam_captures  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "build_nam_captures", ROOT / "tools" / "build_nam_captures.py")
build_nam_captures = importlib.util.module_from_spec(_spec)
sys.modules["build_nam_captures"] = build_nam_captures
_spec.loader.exec_module(build_nam_captures)

REAL_CAPTURE_ID = 57410  # "Mesa Boogie - Mark V [18dBu]", on file in the sidecar
FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "tone3000_search_response.json").read_text())


# --- c1: an ungrounded citation is refused before any device connects -----

def _run_replay(recipe_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, TONECOMMAND_SIM="1")
    return subprocess.run(
        [sys.executable, "tools/replay_recipe.py", str(recipe_path)],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=120)


def test_replay_rejects_ungrounded_tone_target_before_device_connect(tmp_path):
    rec = json.loads(
        (ROOT / "recipes" / "mesa-mark-v-a2-reference.json").read_text())
    rec["tone_target"]["capture_id"] = 123456  # well-formed id, not on file
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(rec))

    r = _run_replay(path)

    assert r.returncode == 2, r.stdout + r.stderr
    assert "REFUSED" in r.stdout
    assert "123456" in r.stdout
    # Proof the rejection happened before the device layer ran at all: the
    # dry-run only prints "device:" after status_dump() on a connected sim.
    assert "device:" not in r.stdout


def test_replay_accepts_grounded_tone_target():
    r = _run_replay(ROOT / "recipes" / "mesa-mark-v-a2-reference.json")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "tone target:" in r.stdout
    assert "Mesa Boogie - Mark V" in r.stdout
    assert "tone3000.com/tones" in r.stdout
    assert "grounded approximation" in r.stdout
    assert "validated:" in r.stdout


# --- c4: provenance-tier logic, against a real recorded API response ------

def test_provenance_tier_logic():
    for raw in FIXTURE["data"]:
        assert build_nam_captures.provenance_tier(raw) == "author_stated"
    verified = {**FIXTURE["data"][0], "user": {**FIXTURE["data"][0]["user"],
                                                "is_verified": True}}
    assert (build_nam_captures.provenance_tier(verified)
            == "author_stated_verified_creator")


def test_shape_record_keeps_only_real_facts():
    raw = FIXTURE["data"][0]
    rec = build_nam_captures.shape_record(raw)
    assert rec["title"] == raw["title"]
    assert rec["gear_claimed"] == [m["name"] for m in raw["makes"]]
    assert rec["creator"] == raw["user"]["username"]
    assert rec["license"] == raw["license"] == "t3k"
    assert rec["url"] == raw["url"]
    assert rec["a2_models_count"] == raw["a2_models_count"]
    # No per-capture accuracy metric exists on TONE3000; nothing is invented
    # to fill that gap.
    assert "accuracy_metric" not in rec


def test_build_skips_captures_with_no_a2_model(monkeypatch):
    non_a2 = {**FIXTURE["data"][0], "id": 999, "a2_models_count": 0}
    monkeypatch.setattr(build_nam_captures, "api_search", lambda term, n: [non_a2])
    blob = build_nam_captures.build(["irrelevant term"], per_term=1)
    assert "999" not in blob["captures"]


# --- c2/on-disk sidecar: the seed itself, loaded through this module -------

def test_seed_sidecar_loads_and_contains_the_real_capture():
    captures = nam_captures.load()
    assert str(REAL_CAPTURE_ID) in captures
    rec = captures[str(REAL_CAPTURE_ID)]
    assert rec["title"] == "Mesa Boogie - Mark V [18dBu]"
    assert "Mesa Boogie Mark V" in rec["gear_claimed"]
    assert rec["provenance_tier"] in (
        "author_stated", "author_stated_verified_creator")


# --- validate_tone_target: the same rules replay_recipe.py relies on ------

GOOD = {"source": "TONE3000", "capture_id": REAL_CAPTURE_ID, "note": "x"}


def test_validate_tone_target_accepts_a_real_citation():
    assert nam_captures.validate_tone_target(GOOD) is None


@pytest.mark.parametrize("label,override", [
    ("wrong source", {"source": "ToneX"}),
    ("string capture_id", {"capture_id": "57410"}),
    ("zero capture_id", {"capture_id": 0}),
    ("negative capture_id", {"capture_id": -1}),
    ("absurd capture_id", {"capture_id": 999_999_999}),
    ("boolean capture_id", {"capture_id": True}),
    ("unknown capture id", {"capture_id": 424242}),
])
def test_validate_tone_target_rejects(label, override):
    bad = {**GOOD, **override}
    problem = nam_captures.validate_tone_target(bad)
    assert problem is not None, label


def test_validate_tone_target_rejects_unknown_subkey():
    assert nam_captures.validate_tone_target({**GOOD, "extra": "x"}) is not None


def test_validate_tone_target_rejects_non_object():
    assert nam_captures.validate_tone_target(["not", "an", "object"]) is not None


# --- c7: the secret key is never hardcoded in tracked source --------------

def test_secret_key_never_hardcoded():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = []
    for rel in tracked:
        if rel in (".env",):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if "t3k_cs_" in text:
            offenders.append(rel)
    assert offenders == []

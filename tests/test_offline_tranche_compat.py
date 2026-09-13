"""Focused compatibility proof for the paired offline IR tranche.

These tests cross the ToneCommand and IRCommand process boundary without
opening a network socket. They prove the new closed contract, the older-service
fallback, and the additive legacy route used by older ToneCommand builds.
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

import server
from fm9 import ir_service


ROOT = Path(__file__).resolve().parent.parent
IR_ROOT = ROOT.parent / "ir-command"
IR_PYTHON = IR_ROOT / ".venv" / "bin" / "python"
ASSET_A = "asset_" + "a" * 32
ASSET_B = "asset_" + "b" * 32


def _run_ircommand(script: str, payload: dict) -> dict:
    result = subprocess.run(
        [str(IR_PYTHON), "-c", textwrap.dedent(script)],
        cwd=IR_ROOT,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout)


PAIR_RECOVERY = r"""
import json
import sys

import service

request = service.validate_reject_request(json.loads(sys.stdin.read()))
candidate = {
    "asset_id": "asset_" + "b" * 32,
    "variant_id": "variant_" + "c" * 32,
    "display_name": "Paired factory V30",
    "source": {"kind": "factory", "bank_name": "FACTORY 1", "pack": None},
    "attributes": {"bank": 0, "slot": 10},
    "eligibility": {
        "media_identity": "allowed",
        "rights": "bundled_metadata",
        "target_rendering": "allowed",
        "delivery": "already_present",
    },
    "identity_confidence": "verified",
    "intent_fit": "partial",
    "load_tradeoff": "already present",
    "reasons": ["factory V30 fallback"],
    "unknowns": [],
}
service._catalog = lambda: (object(), {"status": "ready"})
service.cab_ux.recover = lambda *args, **kwargs: {
    "candidates": [candidate],
    "factory_fallback": candidate,
    "local_quality": "available",
}
print(json.dumps(service.reject_all_response(request)))
"""


LEGACY_RECOMMENDATION = r"""
import json
import sys
import tempfile
from pathlib import Path

import service

payload = json.loads(sys.stdin.read())
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    path = root / "legacy-owned.wav"
    path.write_bytes(b"legacy fixture bytes")

    class LegacyMatcher:
        library_root = str(root)
        measured = False

        def recommend(self, *args, **kwargs):
            return [{
                "name": "Legacy owned cab",
                "path": str(path),
                "format": "wav",
                "category": "cab-ir",
                "pack": "Owned pack",
                "match": 0.8,
                "why": ["v30"],
            }]

        def parse(self, value):
            return {"speaker": ["v30"], "unresolved": []}

    captured = {}
    service.matcher = lambda: LegacyMatcher()
    handler = object.__new__(service.Handler)
    handler.path = "/ir/recommend?need=mesa%20v30&target=fm9&k=3"
    handler._send = lambda value, status=200: captured.update(
        {"status": status, "body": value})
    service.Handler.do_GET(handler)
    print(json.dumps(captured))
"""


def _recovery_body(**changes) -> dict:
    value = {
        "target": "mesa 4x12 v30",
        "request": "make the lead smoother",
        "feedback": "too fizzy",
        "rejected_asset_ids": [ASSET_A],
        "whole_rig": False,
    }
    value.update(changes)
    return value


def test_new_commit_pair_uses_the_exact_path_free_recovery_contract(monkeypatch):
    def paired_post(path, body, timeout):
        assert path == "/v1/recommendations/reject-all"
        assert timeout == 3
        return 200, _run_ircommand(PAIR_RECOVERY, body)

    monkeypatch.setattr(ir_service, "enabled", lambda: True)
    monkeypatch.setattr(ir_service, "_post", paired_post)
    monkeypatch.setattr(
        server, "_factory_cab_fallback",
        lambda target, rejected_slots=(): (_ for _ in ()).throw(
            AssertionError("valid paired fallback was not recognized")),
    )
    monkeypatch.setattr(
        server, "get_fm9",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("compatibility recovery touched the FM9")),
    )

    response = TestClient(server.app).post(
        "/api/ir/recover", json=_recovery_body())
    body = response.json()

    assert response.status_code == 200 and body["ok"]
    assert body["hardware_written"] is False and body["keep_current"] is True
    assert [row["asset_id"] for row in body["candidates"]] == [ASSET_B]
    assert body["factory_fallback"]["slot"]["bank"] == 0
    assert body["factory_fallback"]["slot"]["ordinal"] == 10
    assert all(row.get("path") is None for row in body["candidates"])
    assert body["factory_fallback"].get("path") is None
    assert not any(prefix in json.dumps(body) for prefix in (
        "/Users/", "/private/", "C:\\", "file://"))


def test_older_ircommand_is_an_honest_nonwriting_keep_current_state(monkeypatch):
    monkeypatch.setattr(
        ir_service, "reject_all",
        lambda *args, **kwargs: {
            "available": False,
            "legacy": True,
            "why": "older IRCommand has no reject-all endpoint",
        },
    )
    monkeypatch.setattr(
        ir_service, "recommend",
        lambda *args, **kwargs: [
            {"name": "path-only legacy row", "path": "/private/owned/cab.wav"}
        ],
    )
    monkeypatch.setattr(
        server, "_factory_cab_fallback",
        lambda target, rejected_slots=(): {
            "asset_id": "local_factory_0_10",
            "name": "Verified local fallback",
            "path": None,
            "pack": "FM9 factory cab",
            "intent_fit": "unknown",
            "why": ["eligible local fallback"],
            "measured": None,
            "distance_from_current": None,
            "slot": {"bank": 0, "ordinal": 10, "label": "Factory 0:10"},
        },
    )
    monkeypatch.setattr(
        server, "get_fm9",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("older-service fallback touched the FM9")),
    )

    response = TestClient(server.app).post(
        "/api/ir/recover", json=_recovery_body())
    body = response.json()

    assert response.status_code == 200 and body["ok"]
    assert body["legacy"] and body["keep_current"]
    assert body["hardware_written"] is False and body["candidates"] == []
    assert body["factory_fallback"]["slot"]
    assert "/private/owned" not in json.dumps(body)


def test_older_tonecommand_legacy_get_contract_remains_additively_compatible(
        monkeypatch):
    legacy = _run_ircommand(LEGACY_RECOMMENDATION, {})
    assert legacy["status"] == 200
    assert set(legacy["body"]) >= {
        "need", "target", "measured", "results", "relative",
        "understood", "best_match",
    }
    row = legacy["body"]["results"][0]
    assert set(row) >= {"name", "path", "format", "category", "pack", "match", "why"}
    assert row["asset_id"].startswith("asset_")

    monkeypatch.setattr(ir_service, "enabled", lambda: True)
    monkeypatch.setattr(ir_service, "_get", lambda path, timeout=3: legacy["body"])
    detail = {}
    rows = ir_service.recommend("mesa v30", "fm9", 3, detail=detail)
    assert rows[0]["name"] == "Legacy owned cab"
    assert rows[0]["path"].endswith("legacy-owned.wav")
    assert rows[0]["asset_id"] == row["asset_id"]
    assert detail["target"] == "fm9"

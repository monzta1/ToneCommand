"""Issue #85: reject-all recovery stays advisory and never dead-ends."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import ir_service


ASSET_A = "asset_" + "a" * 32
ASSET_B = "asset_" + "b" * 32
ASSET_C = "asset_" + "c" * 32


def body(**changes):
    value = {"target": "4x12 v30 bright lead", "request": "make it sing",
             "feedback": "too fizzy", "rejected_asset_ids": [ASSET_A],
             "whole_rig": True}
    value.update(changes)
    return value


def advisory(asset_id=ASSET_B, name="Wider V30", *, factory=False):
    return {
        "asset_id": asset_id, "variant_id": "variant_" + "d" * 32,
        "display_name": name,
        "source": {"kind": "factory" if factory else "user",
                   "bank_name": "FACTORY 1" if factory else None,
                   "pack": None if factory else "Owned pack"},
        "attributes": ({"bank": 0, "slot": 10} if factory else {}),
        "eligibility": {"media_identity": "allowed",
                        "target_rendering": "allowed"},
        "identity_confidence": "inferred", "intent_fit": "partial",
        "load_tradeoff": "already present" if factory else "requires loading",
        "reasons": ["v30", "smoother"], "unknowns": [],
    }


def fallback():
    return {"asset_id": "local_factory_3_61", "name": "4x12 V30 (LEGACY)",
            "path": None, "pack": "FM9 factory cab", "intent_fit": "partial",
            "why": ["eligible factory fallback"], "measured": None,
            "distance_from_current": None,
            "slot": {"bank": 3, "ordinal": 61, "label": "4x12 V30"}}


def test_reject_all_proxy_is_bounded_path_free_and_never_touches_hardware(
        monkeypatch):
    seen = {}

    def reject_all(request, feedback, rejected, **options):
        seen.update(request=request, feedback=feedback, rejected=rejected,
                    options=options)
        return {"available": True, "response": {
            "schema_version": 1, "request_id": "r", "candidates": [
                advisory(ASSET_A, "must stay rejected"),
                advisory(ASSET_B), advisory(ASSET_C, "Factory", factory=True),
                advisory("asset_" + "e" * 32, "four"),
                advisory("asset_" + "f" * 32, "five"),
                advisory("asset_" + "1" * 32, "six"),
                advisory("asset_" + "2" * 32, "capped away")],
            "factory_fallback": {"status": "available", "candidate":
                                 advisory(ASSET_C, "Factory", factory=True)},
            "recovery": {"message": "wider set excludes the first pass"},
        }}

    monkeypatch.setattr(ir_service, "reject_all", reject_all)
    monkeypatch.setattr(server, "_factory_cab_fallback", lambda target: fallback())

    def hardware_forbidden(*_args, **_kwargs):
        raise AssertionError("reject-all recovery touched the FM9")

    monkeypatch.setattr(server, "get_fm9", hardware_forbidden)
    out = TestClient(server.app).post("/api/ir/recover", json=body()).json()

    assert out["ok"] and out["hardware_written"] is False
    assert seen == {"request": "4x12 v30 bright lead",
                    "feedback": "smoother less fizz",
                    "rejected": [ASSET_A],
                    "options": {"operation": "new_build", "max_candidates": 5}}
    assert [row["asset_id"] for row in out["candidates"]] == [
        ASSET_B, ASSET_C, "asset_" + "e" * 32, "asset_" + "f" * 32,
        "asset_" + "1" * 32]
    assert all(row["path"] is None for row in out["candidates"])
    assert out["factory_fallback"]["slot"] == {
        "bank": 0, "ordinal": 10, "label": server.cab_label(0, 10)}
    assert out["keep_current"] is True


def test_an_older_ircommand_degrades_to_keep_current_and_factory(monkeypatch):
    monkeypatch.setattr(ir_service, "reject_all", lambda *a, **k: {
        "available": False, "legacy": True,
        "why": "IRCommand is an older build without wider recovery"})
    monkeypatch.setattr(ir_service, "recommend", lambda *a, **k: [
        {"name": "legacy path-only row", "path": "/private/library/cab.wav"}])
    monkeypatch.setattr(server, "_factory_cab_fallback",
                        lambda target, rejected_slots=None: fallback())
    response = TestClient(server.app).post("/api/ir/recover", json=body())
    out = response.json()
    assert response.status_code == 200 and out["ok"]
    assert out["legacy"] is True and out["candidates"] == []
    assert out["keep_current"] is True and out["factory_fallback"]["slot"]
    assert "cannot exclude" in out["why"]
    assert "/private/library" not in str(out)


@pytest.mark.parametrize("remote", [
    pytest.param(advisory(ASSET_A, "Rejected factory", factory=True),
                 id="rejected"),
    pytest.param(advisory(ASSET_C, "Not actually factory", factory=False),
                 id="non-factory"),
    pytest.param(advisory(ASSET_C, "Unknown factory slot", factory=True)
                 | {"attributes": {"bank": 99, "slot": 999}},
                 id="invalid-slot"),
])
def test_unusable_remote_factory_fallback_cannot_shadow_local(
        monkeypatch, remote):
    local = fallback()
    monkeypatch.setattr(ir_service, "reject_all", lambda *a, **k: {
        "available": True, "response": {
            "schema_version": 1, "candidates": [],
            "factory_fallback": {"status": "available", "candidate": remote}}})
    monkeypatch.setattr(server, "_factory_cab_fallback",
                        lambda target, rejected_slots=None: local)
    out = TestClient(server.app).post("/api/ir/recover", json=body()).json()
    assert out["ok"]
    assert out["factory_fallback"] == local


def test_rejected_physical_factory_slot_cannot_reappear_under_local_id(
        monkeypatch):
    """Opaque remote id and local_factory_bank_slot name the same hardware."""
    target = "4x12 v30 bright lead"
    first = server._factory_cab_fallback(target)
    assert first and first["slot"]
    slot = first["slot"]
    key = f"{slot['bank']}:{slot['ordinal']}"
    remote = advisory(ASSET_C, "same slot, different id", factory=True)
    remote["attributes"] = {"bank": slot["bank"], "slot": slot["ordinal"]}
    seen = {}

    def reject_all(request, feedback, rejected, **options):
        seen.update(rejected=rejected, options=options)
        return {"available": True, "response": {
            "schema_version": 1, "candidates": [],
            "factory_fallback": {"status": "available", "candidate": remote}}}

    monkeypatch.setattr(ir_service, "reject_all", reject_all)
    out = TestClient(server.app).post("/api/ir/recover", json=body(
        rejected_factory_slots=[key])).json()
    assert out["ok"] and out["rejected_factory_slots"] == [key]
    assert seen["rejected"] == [ASSET_A]
    assert "rejected_factory_slots" not in seen["options"], \
        "physical identities crossed IRCommand's opaque-id boundary"
    replacement = out["factory_fallback"]
    assert replacement and replacement["slot"] != slot
    assert replacement["asset_id"] != first["asset_id"]


def test_rejected_physical_factory_slot_cannot_reappear_as_candidate(
        monkeypatch):
    """A new opaque id cannot disguise a factory slot already heard."""
    rejected_slot = "0:10"
    repeated = advisory(ASSET_B, "same slot, different id", factory=True)
    fresh = advisory(ASSET_C, "new slot", factory=True)
    fresh["attributes"] = {"bank": 0, "slot": 11}
    monkeypatch.setattr(ir_service, "reject_all", lambda *a, **k: {
        "available": True, "response": {
            "schema_version": 1, "candidates": [repeated, fresh]}})
    monkeypatch.setattr(server, "_factory_cab_fallback",
                        lambda target, rejected_slots=None: None)

    out = TestClient(server.app).post("/api/ir/recover", json=body(
        rejected_factory_slots=[rejected_slot])).json()

    assert [row["asset_id"] for row in out["candidates"]] == [ASSET_C]
    assert out["candidates"][0]["slot"]["ordinal"] == 11


def test_pathless_legacy_plan_can_still_enter_an_honest_recovery(monkeypatch):
    """No opaque ids means do not call the new contract with an invalid body."""
    monkeypatch.setattr(ir_service, "reject_all",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("zero rejected ids crossed to IRCommand")))
    monkeypatch.setattr(ir_service, "recommend", lambda *a, **k: [])
    monkeypatch.setattr(server, "_factory_cab_fallback",
                        lambda target, rejected_slots=None: fallback())
    out = TestClient(server.app).post(
        "/api/ir/recover", json=body(rejected_asset_ids=[])).json()
    assert out["ok"] and out["legacy"] and out["candidates"] == []
    assert out["keep_current"] and out["factory_fallback"]


def test_reject_all_never_calls_online_discovery_without_separate_consent(
        monkeypatch):
    monkeypatch.setattr(ir_service, "reject_all", lambda *a, **k: {
        "available": True, "response": {"schema_version": 1,
                                          "candidates": []}})
    assert not hasattr(ir_service, "gaps_online")
    monkeypatch.setattr(ir_service, "_get",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("reject-all called a legacy GET")))
    monkeypatch.setattr(server, "_factory_cab_fallback",
                        lambda target, rejected_slots=None: fallback())
    out = TestClient(server.app).post("/api/ir/recover", json=body()).json()
    assert out["ok"] and "online" not in out
    assert "TONE3000" not in str(out)


def test_invalid_feedback_and_rejected_ids_fail_before_service(monkeypatch):
    monkeypatch.setattr(ir_service, "reject_all",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("invalid input reached IRCommand")))
    client = TestClient(server.app)
    assert client.post("/api/ir/recover",
                       json=body(feedback="make it awesome")).status_code == 400
    assert client.post("/api/ir/recover",
                       json=body(rejected_asset_ids=["/tmp/cab.wav"])).status_code == 400
    assert client.post("/api/ir/recover", json=body(
        rejected_asset_ids=["asset_" + f"{n:032x}" for n in range(13)]
    )).status_code == 400
    assert client.post("/api/ir/recover", json=body(
        action="install", path="/tmp/cab.wav")).status_code == 422
    assert client.post("/api/ir/recover", json=body(
        rejected_factory_slots=["99:999"])).status_code == 400


def test_the_single_post_plan_set_carries_the_opaque_recovery_identity(
        monkeypatch):
    monkeypatch.setattr(ir_service, "enabled", lambda: True)

    def recommend(*_args, **kwargs):
        kwargs["detail"].update(understood=True)
        return [{"asset_id": ASSET_A, "name": "Owned V30",
                 "path": "/library/owned.wav", "pack": "Owned",
                 "match": .8, "why": ["v30"]}]

    monkeypatch.setattr(ir_service, "recommend", recommend)
    monkeypatch.setattr(server, "_factory_cab_fallback", lambda target: fallback())
    from fm9 import user_cabs
    monkeypatch.setattr(user_cabs, "slot_for_source", lambda path: None)
    out = server.cab_listening_set(
        {"cab_need": "4x12 v30", "request": "make it sing",
         "whole_rig": True}, {"state": "unresolved"})
    assert out["target"] == "4x12 v30" and out["request"] == "make it sing"
    assert out["candidates"][0]["asset_id"] == ASSET_A
    assert out["factory_fallback"]


def test_ircommand_reject_contract_uses_exact_versioned_shape(monkeypatch):
    seen = {}
    monkeypatch.setattr(ir_service, "enabled", lambda: True)

    def post(path, payload, timeout):
        seen.update(path=path, payload=payload, timeout=timeout)
        return 200, {"schema_version": 1, "candidates": []}

    monkeypatch.setattr(ir_service, "_post", post)
    out = ir_service.reject_all("mesa v30", "too boxy", [ASSET_A],
                                operation="new_build", max_candidates=3)
    assert out["available"]
    assert seen["path"] == "/v1/recommendations/reject-all"
    assert set(seen["payload"]) == {
        "schema_version", "request_id", "request_text", "operation",
        "target_profile", "source_policy", "max_candidates", "feedback",
        "rejected_asset_ids"}
    assert seen["payload"]["rejected_asset_ids"] == [ASSET_A]
    assert seen["timeout"] == 3


def test_ircommand_404_is_a_supported_older_service(monkeypatch):
    monkeypatch.setattr(ir_service, "enabled", lambda: True)
    monkeypatch.setattr(ir_service, "_post", lambda *a, **k: (404, {}))
    out = ir_service.reject_all("mesa", "too dark", [ASSET_A])
    assert out["available"] is False and out["legacy"] is True


def test_review_exposes_reject_feedback_and_only_revises_selections():
    ui = (Path(server.__file__).parent / "ui" / "index.html").read_text()
    assert "NONE OF THESE" in ui
    for label in ("too dark", "too bright", "too boxy", "too scooped",
                  "too fizzy", "too dull"):
        assert label in ui
    assert "/api/ir/recover" in ui
    assert "rejected.length > 12" in ui
    assert "rejectedFactorySlots.length > 12" in ui
    assert "rejected_factory_slots: rejectedFactorySlots" in ui
    assert "...(sel.factory_fallback ? [sel.factory_fallback] : [])" in ui
    assert "sel.factory_fallback = data.factory_fallback || null" in ui
    assert ui.count("sel.factory_fallback = null") >= 2
    exhausted = ui.split("if (rejected.length > 12", 1)[1].split(
        "sel.recovery_loading = true", 1)[0]
    unavailable = ui.split("} catch (error) {", 1)[1].split(
        "} finally {", 1)[0]
    assert "sel.factory_fallback = null" in exhausted
    assert "sel.factory_fallback = null" in unavailable
    assert "sel.rejected_asset_ids = rejected" in unavailable
    assert "sel.rejected_factory_slots = rejectedFactorySlots" in unavailable
    assert "sel.candidates = []" in unavailable
    assert ".slice(-12)" not in ui, "old rejections must never be discarded"
    assert "no rejected cab will be recycled" in ui
    keep = ui.split("function keepCurrentCab()", 1)[1].split(
        "const CAB_FEEDBACK", 1)[0]
    choose = ui.split("function useCab(", 1)[1].split(
        "function keepCurrentCab", 1)[0]
    assert "revisePlan();" in keep and "revisePlan();" in choose
    assert "fetch('/api/apply'" not in keep + choose
    assert ".filter(" in keep and ".push(" not in keep, \
        "Keep Current must remove, not add, a cab action"

"""Issue #60: a guided correction may not send without a recovery snapshot.

A manual edit is allowed through when snapshotting fails: the player asked for
it and can hear the result, so the honest move is to say undo is unavailable
and continue. A guided correction is different. There the system proposed the
change and a measurement is its only justification, so an unrecoverable write
is not a trade anyone agreed to.
"""
from __future__ import annotations

import pytest

import server


@pytest.fixture
def snapshot_always_fails(monkeypatch):
    def boom(_name):
        raise RuntimeError("device busy")
    monkeypatch.setattr(server, "_take", boom, raising=False)


def body(origin=None):
    return server.ApplyBody(
        actions=[server.Action(kind="set_param", block="cab",
                               param="CABINET_LEVEL", value=-3.0)],
        origin=origin)


def test_origin_defaults_to_a_manual_edit():
    assert body().origin is None
    assert (body().origin or "") not in server.GUIDED_ORIGINS


def test_guided_origins_are_recognised():
    for name in ("sound_check_correction", "guided_correction"):
        assert name in server.GUIDED_ORIGINS
    assert "player" not in server.GUIDED_ORIGINS


def test_a_guided_correction_is_refused_without_a_snapshot(
        snapshot_always_fails, monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False}, raising=False)
    out = server._apply_for(body("sound_check_correction"))
    assert out.get("refused") == "no_recovery_snapshot"
    assert any("may not send without a recovery snapshot" in
               (r.get("detail") or "") for r in out["results"])
    assert not any(r["action"].get("kind") == "set_param"
                   for r in out["results"]), "nothing may reach the device"


def test_a_manual_edit_still_proceeds_without_a_snapshot(
        snapshot_always_fails, monkeypatch):
    """Unchanged behaviour: the player is deliberately turning a knob."""
    monkeypatch.setattr(server, "_gig_mode", {"on": False}, raising=False)
    out = server._apply_for(body())
    assert out.get("refused") is None
    assert any("could not snapshot for undo" in (r.get("detail") or "")
               for r in out["results"])


def test_the_refusal_names_why_it_refused(snapshot_always_fails, monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False}, raising=False)
    out = server._apply_for(body("guided_correction"))
    detail = " ".join(r.get("detail") or "" for r in out["results"])
    assert "device busy" in detail, "the underlying cause must survive"

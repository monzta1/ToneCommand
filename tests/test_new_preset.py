"""One-tap New preset (issue #44): a blank rig on a free slot, ready to build,
without the Danger Zone. It reuses the starter-template lay, so this pins the
entry point: the endpoint lays the template, refuses cleanly when there is no
free slot, and is blocked in gig mode. The UI carries the button.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


def test_new_preset_lays_the_starter_template(client, monkeypatch):
    called = {}

    def fake_lay(fm9, reg, slot=None, **k):
        called["slot"] = slot
        return {"ok": True, "slot": 386, "slot_label": "387 (wire 386)",
                "alive": True}

    monkeypatch.setattr(server.starter_template, "lay", fake_lay)
    d = client.post("/api/new-preset", json={}).json()
    assert "slot" in called, "new-preset must lay the starter template"
    assert d["ok"] and d["slot_label"] == "387 (wire 386)"


def test_no_free_slot_is_a_clean_refusal_not_a_crash(client, monkeypatch):
    monkeypatch.setattr(server.starter_template, "lay",
                        lambda *a, **k: {"ok": False,
                                         "detail": "no empty presets to build on"})
    r = client.post("/api/new-preset", json={})
    assert r.status_code == 409
    assert "no empty" in r.json()["detail"]


def test_new_preset_is_blocked_in_gig_mode(client, monkeypatch):
    monkeypatch.setitem(server._gig_mode, "on", True)
    r = client.post("/api/new-preset", json={})
    assert r.status_code == 423
    monkeypatch.setitem(server._gig_mode, "on", False)


def test_the_ui_has_a_new_preset_button_on_the_main_surface():
    assert 'id="newpreset"' in UI
    assert "/api/new-preset" in UI


def test_new_preset_falls_back_to_the_buffer_on_a_full_unit(client, monkeypatch):
    """No free slot must not fail: NEW clears the loaded buffer (into_current)."""
    calls = []

    def fake_lay(fm9, reg, slot=None, into_current=False, **k):
        calls.append(into_current)
        if not into_current:
            return {"ok": False, "detail": "no empty presets to build on"}
        return {"ok": True, "slot": 42, "slot_label": "loaded buffer", "alive": True}

    monkeypatch.setattr(server.starter_template, "lay", fake_lay)
    d = client.post("/api/new-preset", json={}).json()
    assert calls == [False, True], "must retry into_current after no free slot"
    assert d["ok"] and d["slot_label"] == "loaded buffer"

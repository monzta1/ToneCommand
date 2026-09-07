"""The optional IRCommand bridge and its Settings toggle.

OFF by default (no env, no saved url, no network, ToneCommand unchanged). A URL
saved from Settings turns it on and persists; the env var pins it above the
saved value; a missing or broken service never raises.
"""
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import ir_service


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    # every test starts off and reads/writes an isolated config file
    monkeypatch.delenv("TONECOMMAND_IR_SERVICE", raising=False)
    monkeypatch.setattr(ir_service, "_config_path",
                        lambda: tmp_path / "ir_service.json")


def test_off_by_default():
    assert ir_service.enabled() is False
    assert ir_service.status() == {"enabled": False, "url": "", "pinned": False}
    assert ir_service.recommend("v30 sm57") is None


def test_status_endpoint_is_off_when_unset():
    d = TestClient(server.app).get("/api/ir/status").json()
    assert d == {"enabled": False, "url": "", "pinned": False}


def test_recommend_endpoint_off_returns_empty():
    d = TestClient(server.app).get("/api/ir/recommend?need=v30").json()
    assert d["enabled"] is False and d["results"] == []


def test_saving_a_url_turns_it_on_and_persists():
    ir_service.set_url("http://127.0.0.1:8770/")   # trailing slash
    assert ir_service.get_url() == "http://127.0.0.1:8770"
    assert ir_service.enabled() is True


def test_env_var_pins_above_the_saved_url(monkeypatch):
    ir_service.set_url("http://127.0.0.1:1")
    monkeypatch.setenv("TONECOMMAND_IR_SERVICE", "http://127.0.0.1:2")
    assert ir_service.get_url() == "http://127.0.0.1:2"
    assert ir_service.status()["pinned"] is True


def test_config_endpoint_sets_the_url():
    d = TestClient(server.app).post(
        "/api/ir/config", json={"url": "http://127.0.0.1:8770"}).json()
    assert d["enabled"] is True and d["url"] == "http://127.0.0.1:8770"


def test_config_endpoint_refused_when_env_pinned(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_IR_SERVICE", "http://127.0.0.1:2")
    r = TestClient(server.app).post("/api/ir/config", json={"url": "http://127.0.0.1:1"})
    assert r.status_code == 409


def test_a_broken_service_never_raises(monkeypatch):
    ir_service.set_url("http://127.0.0.1:9")

    def boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(ir_service.urllib.request, "urlopen", boom)
    assert ir_service.status()["reachable"] is False
    assert ir_service.recommend("v30") is None


def test_configured_and_reachable(monkeypatch):
    ir_service.set_url("http://127.0.0.1:8770")

    def fake_get(path, timeout=3):
        if path == "/health":
            return {"ok": True, "cabs": 1122}
        if path.startswith("/ir/recommend"):
            return {"results": [{"name": "Mesa Recto V30 SM57.wav",
                                 "path": "/p", "score": 1.0}]}
        return None
    monkeypatch.setattr(ir_service, "_get", fake_get)
    st = ir_service.status()
    assert st["enabled"] and st["reachable"] and st["cabs"] == 1122
    assert st["pinned"] is False
    recs = ir_service.recommend("tight modern mesa v30 sm57")
    assert recs and recs[0]["name"].startswith("Mesa Recto")
    d = TestClient(server.app).get("/api/ir/recommend?need=mesa+v30").json()
    assert d["enabled"] is True and d["results"][0]["path"] == "/p"

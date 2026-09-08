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
    # Every test starts off and reads/writes an isolated config file.
    # Discovery is stubbed out because it probes a real localhost port: with
    # IRCommand actually running on this machine these tests would pass or
    # fail depending on whether a service happened to be up, which is worse
    # than either answer. The discovery behaviour has its own tests below,
    # where the probe is stubbed in the other direction.
    monkeypatch.delenv("TONECOMMAND_IR_SERVICE", raising=False)
    monkeypatch.setattr(ir_service, "_config_path",
                        lambda: tmp_path / "ir_service.json")
    monkeypatch.setattr(ir_service, "discover", lambda: "")


def test_off_when_nothing_is_configured_and_nothing_is_running():
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


# --- discovery (2026-09-07) ---------------------------------------------
#
# The bridge was config-gated and OFF unless someone pasted
# http://127.0.0.1:8770 into Settings. Nobody had, so `ir_context()` returned
# "" on every build and the planner was never told the player owns 7,655
# analysed IRs. Reported as: a Steve Vai preset where no question was asked
# about the cab and nothing was said about how one was chosen.

def test_a_running_local_service_is_found_without_configuration(monkeypatch):
    monkeypatch.setattr(ir_service, "_found", {"url": None, "at": 0.0})
    monkeypatch.setattr(ir_service, "discover", lambda: "http://127.0.0.1:8770")
    assert ir_service.enabled() is True
    assert ir_service.base_url() == "http://127.0.0.1:8770"


def test_discovery_only_probes_loopback():
    """Not a validation that could be bypassed: the candidates are literal
    127.0.0.1 addresses, so discovery cannot reach another host at all."""
    # Read the module file, not the attribute: the autouse fixture replaces
    # `discover` with a stub, so getsource would inspect the lambda.
    from pathlib import Path as _P
    src = _P(ir_service.__file__).read_text()
    body = src.split("def discover(")[1].split("\ndef ")[0]
    assert "127.0.0.1" in body
    assert "://" not in body.replace("http://127.0.0.1", ""), \
        "discovery must not build a URL for any other host"
    for url in [f"http://127.0.0.1:{p}" for p in ir_service.DEFAULT_PORTS]:
        assert ir_service.check_url(url) == url


def test_a_configured_url_beats_discovery(monkeypatch, tmp_path):
    """Discovery is last, so it can never override a deliberate choice."""
    monkeypatch.setattr(ir_service, "discover",
                        lambda: "http://127.0.0.1:9999")
    ir_service.set_url("http://127.0.0.1:8770")
    assert ir_service.get_url() == "http://127.0.0.1:8770"


def test_an_explicit_off_is_respected_over_discovery(monkeypatch):
    """Saving an empty URL in Settings means OFF on purpose. Discovery must
    not quietly switch the feature back on."""
    monkeypatch.setattr(ir_service, "discover",
                        lambda: "http://127.0.0.1:8770")
    ir_service.set_url("")
    assert ir_service.get_url() == ""
    assert ir_service.enabled() is False


def test_discovery_never_raises_when_nothing_is_listening(monkeypatch):
    """A build must never wait on, or break because of, a missing service."""
    monkeypatch.setattr(ir_service, "_found", {"url": None, "at": 0.0})
    monkeypatch.setattr(ir_service, "DEFAULT_PORTS", (1,))   # nothing listens
    assert ir_service.discover() == ""

"""The blast-radius sweep is lazy, announced, and never behind a GET.

Found by the owner, from the floor: changing presets on the FM9 front panel
made the rig cycle through all eight scenes on its own. The page was asking
GET /api/shared on every preset change, and that GET did the audible sweep.
An audible action behind a GET breaks the same rule /api/health is a POST
for, so the sweep moved to POST /api/shared/sweep and runs only when a plan
actually needs the hints. These tests keep it there.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()

A_MAP = {"106": {"0": [1, 2], "1": [3]}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setattr(server, "_shared_cache", {"preset": None, "map": None})
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    return TestClient(server.app)


def test_the_get_never_sweeps(client, monkeypatch):
    """GET /api/shared is cache-only. The sweep walks the rig through all
    eight scenes audibly, and this GET used to run it on every front-panel
    preset change."""
    def boom(fm9):
        raise AssertionError("GET /api/shared ran the audible sweep")
    monkeypatch.setattr(server, "shared_scenes", boom)
    d = client.get("/api/shared").json()
    assert d["shared"] is None
    assert d["unswept"] is True


def test_the_post_sweeps_and_the_get_then_serves_cache(client, monkeypatch):
    calls = []
    monkeypatch.setattr(server, "shared_scenes",
                        lambda fm9: calls.append(1) or A_MAP)
    d = client.post("/api/shared/sweep").json()
    assert d["swept"] is True and d["shared"] == A_MAP
    d2 = client.get("/api/shared").json()
    assert d2["cached"] is True and d2["shared"] == A_MAP
    assert len(calls) == 1


def test_gig_mode_refuses_the_sweep_loudly(client, monkeypatch):
    """423 like /api/health, not a quiet null: the page tells the owner the
    hints are off rather than leaving them silently absent."""
    monkeypatch.setattr(server, "_gig_mode", {"on": True})
    monkeypatch.setattr(server, "shared_scenes",
                        lambda fm9: pytest.fail("swept in gig mode"))
    r = client.post("/api/shared/sweep")
    assert r.status_code == 423
    assert "GIG MODE" in r.json()["error"]


def test_a_channel_write_invalidates_the_cached_map(client):
    """The map is exactly "which scenes sit on which channel", so a
    set_channel that lands must not leave the cached copy claiming the old
    layout."""
    server._shared_cache["preset"], server._shared_cache["map"] = 0, A_MAP
    client.post("/api/apply", json={"actions": [
        {"kind": "add_block", "block": "amp", "instance": 1},
        {"kind": "set_channel", "block": "amp", "instance": 1, "value": 1},
    ]})
    assert server._shared_cache["map"] is None


def test_the_polls_loader_cannot_reach_the_sweep():
    """loadShared runs from the state poll on every preset change; the lazy
    path with the announcement is ensureShared. Only the lazy path may name
    the sweep endpoint."""
    m = re.search(r"async function loadShared[\s\S]*?\n}", UI)
    assert m, "loadShared missing from the UI"
    assert "/api/shared/sweep" not in m.group(0)
    assert "/api/shared/sweep" in UI, "the lazy sweep call is gone entirely"


def test_the_sweep_is_announced_before_it_is_heard():
    """The announcement must sit between ensureShared's opening and its POST,
    so the scene-stepping is explained before it starts, not after."""
    m = re.search(r"async function ensureShared[\s\S]*?/api/shared/sweep", UI)
    assert m, "ensureShared does not POST the sweep"
    assert "hear the rig step" in m.group(0)

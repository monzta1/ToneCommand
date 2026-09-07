"""Naming the player's own user-cab slots.

Factory cabs are catalogued so they resolve to a name; USER-bank cabs are the
player's own IRs and cannot be, which is why an installed IR displayed as a
bare "26".
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import registry, user_cabs


@pytest.fixture(autouse=True)
def isolated_map(tmp_path, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_USER_CABS", str(tmp_path / "user_cabs.json"))
    monkeypatch.setattr(user_cabs, "_cache", {}, raising=False)
    monkeypatch.setattr(user_cabs, "_stamp", None, raising=False)
    return tmp_path / "user_cabs.json"


def test_no_map_means_no_names(isolated_map):
    assert user_cabs.all_names() == {}
    assert user_cabs.name(2, 26) is None


def test_set_then_get(isolated_map):
    user_cabs.set_name(2, 26, "Soldano SLO30")
    assert user_cabs.name(2, 26) == "Soldano SLO30"
    assert json.loads(isolated_map.read_text())["2"]["26"] == "Soldano SLO30"


def test_empty_name_clears_the_slot(isolated_map):
    user_cabs.set_name(2, 26, "Soldano SLO30")
    user_cabs.set_name(2, 26, "")
    assert user_cabs.name(2, 26) is None


def test_a_corrupt_file_is_survivable(isolated_map):
    isolated_map.write_text("{not json")
    assert user_cabs.all_names() == {}, "a bad file must mean no names, not a crash"


def test_reread_after_change(isolated_map):
    user_cabs.set_name(2, 26, "First")
    assert user_cabs.name(2, 26) == "First"
    user_cabs.set_name(2, 26, "Second")
    assert user_cabs.name(2, 26) == "Second"


# --- the actual bug: cab_description showed a bare ordinal ----------------

def test_user_cab_resolves_to_its_name(isolated_map):
    reg = registry.Registry()
    assert reg.cab_description(26, 2) == "26", "no name yet, so the ordinal"
    user_cabs.set_name(2, 26, "Soldano SLO30 - Emil Rohbe")
    assert reg.cab_description(26, 2) == "Soldano SLO30 - Emil Rohbe"


def test_factory_cabs_are_unaffected(isolated_map):
    """The catalogue still wins for banks it knows; naming is only a fallback."""
    reg = registry.Registry()
    before = reg.cab_description(20, 3)
    user_cabs.set_name(3, 20, "should not be used")
    assert reg.cab_description(20, 3) == before
    assert "DOUBLE VERB" in before


def test_unknown_slot_still_degrades_to_the_ordinal(isolated_map):
    reg = registry.Registry()
    assert reg.cab_description(999, 9) == "999"


# --- the endpoints --------------------------------------------------------

def test_get_and_post_round_trip(isolated_map):
    c = TestClient(server.app)
    assert c.get("/api/user-cabs").json()["names"] == {}
    r = c.post("/api/user-cabs", json={"ordinal": 26, "name": "Soldano SLO30"})
    assert r.status_code == 200 and r.json()["ok"]
    assert r.json()["label"] == "Soldano SLO30"
    assert c.get("/api/user-cabs").json()["names"]["2"]["26"] == "Soldano SLO30"


def test_post_rejects_a_bad_ordinal(isolated_map):
    c = TestClient(server.app)
    assert c.post("/api/user-cabs", json={"ordinal": 99999,
                                          "name": "x"}).status_code == 400
    assert c.post("/api/user-cabs", json={"ordinal": "nope",
                                          "name": "x"}).status_code == 400

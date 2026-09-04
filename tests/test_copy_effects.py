"""Copy an effect from one preset onto another: "make the delay like that
tone's". The owner's insight from the Marco Sfogli experiment: lifting a whole
effect from a reference preset beats guessing its parameters from scratch.

editbuffer.transplant is restore without the same-preset guard, scoped to the
named families. It writes the source's exact wire values, reports a block the
target lacks rather than inventing it, and never touches families you did not
ask for.
"""
import copy

from fm9 import editbuffer
from fm9.registry import Registry
from fm9.sim import SimFM9


def _delay(snap):
    return next(b for b in snap["blocks"] if b["family"] == "DELAY")


def _reverb(snap):
    return next((b for b in snap["blocks"] if b["family"] == "REVERB"), None)


def test_a_named_effect_is_copied_wire_exact():
    reg = Registry()
    sim = SimFM9(reg)
    now = editbuffer.capture(sim, reg)
    src = copy.deepcopy(now)
    d = _delay(src)
    d["values"][0] = (d["values"][0] + 12345) % 65534   # a value to carry over

    res = editbuffer.transplant(sim, reg, src, {"DELAY"})
    assert res.ok, res.failed
    after = editbuffer.capture(sim, reg)
    assert _delay(after)["values"][0] == d["values"][0]


def test_only_the_named_families_are_touched():
    reg = Registry()
    sim = SimFM9(reg)
    now = editbuffer.capture(sim, reg)
    src = copy.deepcopy(now)
    # change BOTH a delay and (if present) a reverb value in the source
    _delay(src)["values"][0] = (_delay(src)["values"][0] + 1000) % 65534
    rv = _reverb(src)
    if rv:
        rv["values"][0] = (rv["values"][0] + 1000) % 65534

    editbuffer.transplant(sim, reg, src, {"DELAY"})   # reverb NOT requested
    after = editbuffer.capture(sim, reg)
    assert _delay(after)["values"][0] == _delay(src)["values"][0]
    if rv:
        # reverb was left as it was, not pulled from the source
        assert _reverb(after)["values"][0] == _reverb(now)["values"][0]


def test_a_block_the_target_lacks_is_reported_not_invented():
    reg = Registry()
    sim = SimFM9(reg)
    now = editbuffer.capture(sim, reg)
    src = copy.deepcopy(now)
    # a source block for a family the target does not have: forge a PITCH block
    src["blocks"].append({"effect_id": 134, "family": "PITCH", "instance": 1,
                          "bypassed": False, "channel": 0, "channels": 1,
                          "values": [1, 2, 3]})
    res = editbuffer.transplant(sim, reg, src, {"PITCH"})
    assert any("current preset" in f for f in res.failed)


def test_the_endpoint_exists_and_is_shaped_right():
    import server
    routes = {r.path for r in server.app.routes if getattr(r, "methods", None)}
    assert "/api/copy-effects" in routes


# --- compose: build a preset from parts of others ------------------------

def _client(monkeypatch):
    # monkeypatch.setenv, not os.environ, so the whitelist does not leak into
    # other tests that depend on a restricted TONECOMMAND_STORE_SLOTS.
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "0-511")
    import server
    from fm9.sim import SimFM9
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_preset_cache", {"slots": None})
    return server, TestClient(server.app)


def test_compose_clones_a_base_and_pulls_a_block_from_another(monkeypatch):
    server, c = _client(monkeypatch)
    fm9 = server._fm9
    reg = server.reg
    # give preset 6 a distinctive delay so the transplant has to do real work
    fm9.select_preset(6)
    snap6 = editbuffer.capture(fm9, reg)
    d6 = _delay(snap6)
    d6["values"][0] = (d6["values"][0] + 20000) % 65534
    editbuffer.transplant(fm9, reg, snap6, {"DELAY"})   # write it onto 6's buffer
    fm9.store_preset(6)
    want = d6["values"][0]

    # compose: clone 5 into 20, take the DELAY from 6
    r = c.post("/api/compose", json={"target": 20, "base": "5",
                                     "take": [{"source": "6", "blocks": ["DELAY"]}]})
    assert r.status_code == 200 and r.json()["ok"], r.json()

    # slot 20's delay must be 6's, not 5's
    fm9.select_preset(20)
    got = _delay(editbuffer.capture(fm9, reg))["values"][0]
    assert got == want


def test_compose_refuses_a_target_outside_the_whitelist(monkeypatch):
    import os
    server, c = _client(monkeypatch)          # this sets the whitelist to 0-511
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "100-110")  # so narrow it after
    r = c.post("/api/compose", json={"target": 20, "base": "5"})
    assert r.status_code == 403


# --- scene-aware copy (#48): sim can only cover that it runs and copies; the
#     per-scene REMAPPING needs hardware, because the sim does not model
#     per-scene channel assignment. ------------------------------------------

def test_transplant_by_scene_runs_and_copies(monkeypatch):
    """Sweeps both presets, copies the source's per-scene effect onto the
    target. The sim keeps every scene on channel 0, so this proves the sweep +
    copy mechanism, not the cross-channel remapping (hardware-only)."""
    server, c = _client(monkeypatch)
    fm9, reg = server._fm9, server.reg
    # give preset 6 a distinctive delay
    fm9.select_preset(6)
    snap6 = editbuffer.capture(fm9, reg)
    d6 = _delay(snap6)
    d6["values"][0] = (d6["values"][0] + 22222) % 65534
    editbuffer.transplant(fm9, reg, snap6, {"DELAY"})
    fm9.store_preset(6)
    want = d6["values"][0]

    res = editbuffer.transplant_by_scene(fm9, reg, 6, 5, {"DELAY"})
    assert res.applied, "scene-aware copy applied nothing"
    # it ends on the target's buffer with the edit; re-selecting would discard
    # it, so read the buffer directly.
    assert _delay(editbuffer.capture(fm9, reg))["values"][0] == want

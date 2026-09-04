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
    assert "/api/copy-effects/nl" in routes    # the natural-language front door


# --- natural-language front door: "copy the delay from that tone" ----------

def test_parse_copy_request_reads_source_and_effects():
    import server
    p = server.parse_copy_request(
        "copy the delay and reverb from the Periphery tone into ours")
    assert p["source"] == "Periphery"
    assert p["effects"] == ["DELAY", "REVERB"]
    assert p["scene_aware"] is True


def test_parse_copy_request_strips_a_destination_clause():
    import server
    p = server.parse_copy_request(
        "take the reverb and delay from Periphery Misha GoT and put it in ours")
    assert p["source"] == "Periphery Misha GoT"       # no "and put it in ours"
    assert p["effects"] == ["REVERB", "DELAY"]         # in the order spoken


def test_parse_copy_request_defaults_effects_when_unnamed():
    import server
    p = server.parse_copy_request("copy the effects from the Petrucci preset")
    assert p["source"] == "Petrucci"
    assert p["effects"] == ["DELAY", "REVERB"]
    assert p["defaulted"] is True


def test_parse_copy_request_maps_a_slot_word_to_a_number():
    import server
    p = server.parse_copy_request("pull the chorus from preset 6")
    assert p["source"] == "6"
    assert p["effects"] == ["CHORUS"]


def test_parse_copy_request_honours_a_plain_settings_copy():
    import server
    p = server.parse_copy_request(
        "copy just the settings of the delay from Periphery")
    assert p["scene_aware"] is False


def test_parse_copy_request_ignores_a_non_copy_sentence():
    import server
    assert server.parse_copy_request("make it sound like Periphery") is None
    assert server.parse_copy_request("build a djent rig") is None


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

    # the caller loads source, reads it, loads target, then applies (editbuffer
    # never switches presets itself)
    fm9.select_preset(6)
    src_state, src_vals = editbuffer.read_scene_state(fm9, reg, {"DELAY"})
    fm9.select_preset(5)
    res = editbuffer.transplant_by_scene(fm9, reg, src_state, src_vals)
    assert res.applied, "scene-aware copy applied nothing"
    # it ends on the target's buffer with the edit; re-selecting would discard
    # it, so read the buffer directly.
    assert _delay(editbuffer.capture(fm9, reg))["values"][0] == want


# --- scene-aware copy: the per-channel/per-scene decomposition (#48) --------
# The SimFM9 keeps every scene on channel 0, so it cannot catch the bug that
# hardware did: FM9 params are per CHANNEL, not per scene, so when several
# target scenes share a channel a naive per-scene write loop has each later
# scene clobber the earlier one (a two-scene copy came back 10/10). This fake
# models per-scene channel assignment and shared per-channel params, so the
# clobber is reproducible in CI. Guards the decomposition, not the wire.

class _Blk:
    def __init__(self, eid, channel, bypassed, chans):
        self.effect_id = eid
        self.channel = channel
        self.bypassed = bypassed
        self.channels_supported = chans


class _SceneAwareDev:
    """One block (DELAY, eid 70), 4 channels. Params live per channel and are
    shared by every scene sitting on that channel; scenes store their own
    channel + bypass. Exactly the model that made the clobber possible."""
    EID, CHANS = 70, 4

    def __init__(self, scene_chan):
        # scene_chan: {scene: channel} for scenes 1..8
        self.scene_chan = dict(scene_chan)
        self.scene_byp = {s: False for s in range(1, 9)}
        self.params = {ch: {} for ch in range(self.CHANS)}   # channel -> {pid: wire}
        self._cur = 1
        self._channels = {self.EID: self.CHANS}

    def scene_name(self):
        return (self._cur, f"SCENE {self._cur}")

    def set_scene(self, sc):
        self._cur = sc
        return sc

    def status_dump(self):
        ch = self.scene_chan[self._cur]
        return [_Blk(self.EID, ch, self.scene_byp[self._cur], self.CHANS)]

    def set_channel(self, eid, ch):
        self.scene_chan[self._cur] = ch
        return ch

    def set_bypass(self, eid, byp):
        self.scene_byp[self._cur] = byp
        return byp

    def set_param_wire(self, spec, wire):
        ch = self.scene_chan[self._cur]
        self.params[ch][spec.param_id] = wire
        class _R:
            ok = True
        return _R()

    def mix_on_scene(self, sc, pid=0):
        return self.params[self.scene_chan[sc]].get(pid)


def test_scene_aware_copy_does_not_clobber_shared_channels():
    reg = Registry()
    EID = 70
    # SOURCE map: scene1->A(0) mix 6553, scene2->B(1) mix 13107, scene3->A(0).
    # scene3 SHARES channel A with scene1, which is exactly what breaks a naive
    # per-scene loop on the target side.
    src_state = {1: {EID: (0, False)}, 2: {EID: (1, False)}, 3: {EID: (0, False)}}
    for s in range(4, 9):
        src_state[s] = {EID: (0, False)}
    # channel-major values, stride 1 (mix only): A=6553, B=13107, C=0, D=0
    src_vals = {EID: ([6553, 13107, 0, 0], 4)}

    # TARGET map: channels deliberately swapped and spread so several scenes
    # share channels differently from the source.
    tgt = _SceneAwareDev({1: 1, 2: 0, 3: 2, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0})

    res = editbuffer.transplant_by_scene(tgt, reg, src_state, src_vals)
    assert res.applied

    # Each target scene must sound like the SOURCE's same scene, and the
    # shared-channel scenes must not have overwritten each other.
    assert tgt.mix_on_scene(1) == 6553, "scene 1 wrong"
    assert tgt.mix_on_scene(2) == 13107, "scene 2 CLOBBERED (the #48 bug)"
    assert tgt.mix_on_scene(3) == 6553, "scene 3 wrong"

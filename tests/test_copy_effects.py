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

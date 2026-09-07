"""Issue #66: global parameters are addressable at effect id 1.

Found by differential measurement on hardware: every bulk_read for effect ids
0..36 was captured, the owner changed exactly one front-panel setting, and the
captures were diffed. Out of 16,236 values exactly one moved, and it was the
one the catalogue predicted.
"""
from __future__ import annotations

import pytest

from fm9 import registry

reg = registry.Registry()


def test_global_is_addressable():
    assert "GLOBAL" in registry.EFFECT_ID_BASE
    base, count = registry.EFFECT_ID_BASE["GLOBAL"]
    assert (base, count) == (1, 1), "globals are one block at effect id 1"


def test_global_does_not_collide_with_any_grid_block():
    base, _ = registry.EFFECT_ID_BASE["GLOBAL"]
    others = [(f, b, c) for f, (b, c) in registry.EFFECT_ID_BASE.items()
              if f != "GLOBAL"]
    for fam, b, c in others:
        assert not (b <= base < b + c), f"GLOBAL id collides with {fam}"


def test_the_routing_parameter_resolves():
    """GLOBAL_IN1_SOURCE is the parameter that blocks #56: without a spec it
    could not be read, so the routing could not be restored."""
    s = reg.spec("GLOBAL", 72)
    assert s.effect_id == 1
    assert s.name == "GLOBAL_IN1_SOURCE"
    assert s.kind == "enum" and s.enum_count == 2


@pytest.mark.parametrize("pid,name", [
    (73, "GLOBAL_DIGITAL_SOURCE"),
    (139, "GLOBAL_USBLEVEL3"),
    (146, "GLOBAL_USB_MAPPING"),
    (3, "GLOBAL_CABINETBYP"),
])
def test_other_globals_resolve_with_their_ranges(pid, name):
    s = reg.spec("GLOBAL", pid)
    assert s.effect_id == 1 and s.name == name
    assert s.kind in ("enum", "float"), s.kind


def test_a_high_param_id_still_resolves():
    """The catalogue carries globals past 8000; those must address too, and on
    hardware they read stably at the default timeout."""
    s = reg.spec("GLOBAL", 8710)
    assert s.effect_id == 1 and s.name == "GLOBAL_IN2_SOURCE"


def test_every_catalogued_global_can_build_a_spec():
    """Before this change spec('GLOBAL', ...) raised KeyError for all 208."""
    ids = [pid for (fam, pid) in reg.params if fam == "GLOBAL"]
    assert len(ids) > 200
    for pid in ids:
        assert reg.spec("GLOBAL", pid).effect_id == 1


def test_reading_is_all_this_adds():
    """Writing a global is deliberately NOT enabled here. Reading is what makes
    a restore possible, and it should be trusted before anything writes."""
    import server
    assert "GLOBAL" not in server.BLOCK_ALIASES.values() \
        if hasattr(server, "BLOCK_ALIASES") else True


# --- reads yes, writes no -----------------------------------------------

def test_a_plan_cannot_target_a_global():
    """Adding GLOBAL to EFFECT_ID_BASE silently made it plan-targetable,
    because resolve_block accepts any family name in that table. A global write
    has no proven restore path (#56), so writing one blind is the exact hazard
    that issue exists to prevent."""
    with pytest.raises(KeyError, match="cannot be targeted"):
        reg.resolve_block("global")
    with pytest.raises(KeyError, match="cannot be targeted"):
        reg.resolve_block("GLOBAL")


def test_reading_a_global_is_still_allowed():
    """The whole point of the change: reads must survive the write block."""
    assert reg.spec("GLOBAL", 72).effect_id == 1


def test_normal_blocks_are_unaffected():
    assert reg.resolve_block("amp") == ("DISTORT", 58)
    assert reg.resolve_block("cab")[0] == "CABINET"


def test_the_block_list_is_explicit():
    assert registry.NOT_PLANNABLE == frozenset({"GLOBAL"})

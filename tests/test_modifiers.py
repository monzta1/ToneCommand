"""What is driving this parameter, when it is not you.

Moncy's question was "is it autowah, or how do I know if there is a pedal
assigned?", and the FM9's answer is not a block type: there is no auto-wah
model. A wah is whatever its sweep parameter is attached to. Read the
attachment and the question answers itself.

The bigger reason this exists: a modifier TAKES THE PARAMETER OVER. The FM9
sources the value from the pedal, envelope or LFO, and whatever is stored on
the block stops being what you hear. So a slider drawn for a modified
parameter is a control that does nothing. You drag it, the number moves, the
verification passes, the sound does not change, and you conclude the tool is
broken.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import protocol as fp
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]
STYLE = UI.split("<style>")[1].split("</style>")[0]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    # Which slots this tool built from defaults is module state that outlives
    # a request on purpose, so a test that does not isolate it inherits the
    # previous test's slots and reads whatever it likes into them.
    monkeypatch.setattr(server, "_synthetic_slots", {"preset": None, "slots": set()})
    return TestClient(server.app)


def _bind(fm9, slot, eid, pid, source):
    """Write a modifier slot straight into the simulator's store."""
    with fm9:
        mod_eid = fp.mod_slot_eid(slot)
        vals = fm9.bulk_read(mod_eid)
        assert vals, "the simulator has no modifier slots"
        fm9.set_param_wire(_FakeSpec(mod_eid, fp.MOD_PID_TARGET_EFFECT), eid)
        fm9.set_param_wire(_FakeSpec(mod_eid, fp.MOD_PID_TARGET_PARAM), pid)
        fm9.set_param_wire(_FakeSpec(mod_eid, fp.MOD_PID_SOURCE), source)


class _FakeSpec:
    kind, scale, dmin, dmax = "enum", "linear", 0, 65534

    def __init__(self, eid, pid):
        self.effect_id, self.param_id, self.name = eid, pid, f"MOD{pid}"


# --- reading them ----------------------------------------------------------

def test_an_unbound_rig_reports_nothing_bound(client):
    assert server.read_modifiers(server._fm9) == {}


def test_a_bound_parameter_is_reported_by_name(client):
    fm9 = server._fm9
    _bind(fm9, 1, server.reg.effect_id("WAH"), 5, 11)
    with fm9:
        mods = server.read_modifiers(fm9)
    assert "WAH_CONTROL" in mods
    assert mods["WAH_CONTROL"]["slot"] == 1
    assert mods["WAH_CONTROL"]["source"] == 11


def test_the_two_expression_pedals_are_the_grounded_sources():
    """Both onboard pedals are grounded now: each is bound and read back on
    hardware (Pedal 1 decoded 2026-09-05). Every OTHER ordinal stays a bare
    number, because the display-name query returns NONE whatever the source
    (docs/PROTOCOL.md finding 5)."""
    assert server.MOD_SOURCES == {10: "Pedal 1", 11: "Pedal 2"}
    assert server.PEDAL_1_SOURCE == 10 and server.PEDAL_2_SOURCE == 11
    src = Path("server.py").read_text()
    # the bind resolves the source from the requested pedal, so the name table
    # and the write cannot drift apart, and no pedal is hardcoded into the bind
    assert "source = _pedal_source(a.pedal)" in src
    args = re.search(r"fm9\.bind_modifier\((.*?)\)", src, re.S).group(1)
    assert "source" in args and "PEDAL_2_SOURCE" not in args


def test_an_unknown_source_is_a_number_not_a_guess(client):
    """Naming an ordinal we have not verified would be inventing a fact about
    someone's rig. Observed live: Moncy's preset 1 has the wah sweep on source
    13, which is a real attachment whose identity we do not have."""
    fm9 = server._fm9
    _bind(fm9, 2, server.reg.effect_id("WAH"), 5, 13)
    with fm9:
        d = server.read_modifiers(fm9)["WAH_CONTROL"]
    assert d["source_name"] == "source #13"
    assert d["known"] is False


def test_an_empty_slot_is_not_a_binding_to_block_zero(client):
    """A never-used slot is all zeroes, and effect id 0 is not a block. Reading
    that as a binding would report thirty-one phantom modifiers."""
    with server._fm9 as fm9:
        assert server.read_modifiers(fm9) == {}


def test_the_state_carries_them(client):
    assert client.get("/api/state").json()["mods"] == {}


def test_they_are_read_every_poll_not_cached_against_the_preset():
    """A modifier can be added or removed from the front panel without the
    preset number changing, and a stale "nothing is bound here" is exactly the
    statement this exists to stop the page making."""
    src = Path("server.py").read_text()
    fn = src.split("def snapshot(")[1].split("\ndef ")[0]
    assert '"mods": _safe_modifiers(fm9)' in fn
    # _safe_modifiers is read_modifiers wrapped so a hiccup cannot drop the
    # link, not a cache: it still reads on every call
    wrapper = src.split("def _safe_modifiers(")[1].split("\n\n\n")[0]
    assert "return read_modifiers(fm9)" in wrapper


# --- the sweep is on the page at all --------------------------------------

def test_the_wah_sweep_is_surfaced():
    """It was not: WAH's whitelist was [6, 10], Level and Drive, so the one
    parameter that answers the pedal question was never drawn. Verified live
    on preset 1, where /api/state now returns WAH_CONTROL alongside the
    frequency limits that bound its sweep.

    The simulator has no wah, deliberately: three existing tests use that
    block as "one this preset does not have", and a fixture that quietly
    changes what those tests mean is worse than a gap here.
    """
    for pid in (5, 1, 2, 3):
        assert pid in server.INTEREST["WAH"], pid
    assert server.reg.spec("WAH", 5, 1).name == "WAH_CONTROL"


# --- what the browser does with it ----------------------------------------

def test_a_driven_parameter_is_not_draggable():
    fn = SCRIPT.split("function knobRow(key, m, value)")[1].split("\n}\n")[0]
    assert "if (mod) {" in fn and "disabled" in fn
    assert 'class="knob modded ro"' in fn
    # no data-key, so the write path cannot reach it even if it were enabled
    assert 'data-mod="${esc(key)}"' in fn


def test_the_row_says_what_is_driving_it():
    assert "function modBadge(key)" in SCRIPT
    fn = SCRIPT.split("function modBadge(key)")[1].split("\n}\n")[0]
    assert "d.source_name" in fn and "modifier slot ${d.slot}" in fn
    assert "will not change what you hear" in fn


def test_the_badge_is_drawn_and_distinguishes_named_from_numbered():
    assert re.search(r"^\s*\.modbadge \{", STYLE, re.M)
    assert re.search(r"^\s*\.modbadge\.unk \{", STYLE, re.M)
    assert re.search(r"^\s*\.knob\.modded input\[type=range\] \{", STYLE, re.M)


def test_the_map_is_refreshed_with_the_rest_of_the_state():
    render = SCRIPT.split("function renderParams")[1].split("\nfunction ")[0]
    assert "lastMods = s.mods || {};" in render


# --- putting a parameter under Pedal 2 ------------------------------------

def test_the_write_order_follows_the_verified_sequence():
    """Finding 17: the slot's own fields as continuous writes FIRST, then the
    target effect id, the target param id and the source as discrete writes,
    in that order. Verified across sixteen presets, two ear-confirmed.

    The code here did it the other way round: targets first, a partial curve
    after. That is the shape finding 16 describes, which reads healthy
    immediately, survives a store, and comes back with target and source
    zeroed once the preset reloads.
    """
    import inspect
    from fm9.device import FM9
    src = inspect.getsource(FM9.bind_modifier)
    fields = src.index("MOD_FIELD_PIDS")
    targets = src.index("MOD_PID_TARGET_EFFECT, target_effect_id")
    assert fields < targets, "curve fields must be written before the targets"
    order = [src.index(f"MOD_PID_{n}") for n in
             ("TARGET_EFFECT, target", "TARGET_PARAM, target", "SOURCE, source")]
    assert order == sorted(order), "target, param, source, in that order"
    assert "build_set_param_continuous" in src.split("MOD_FIELD_PIDS")[-1] \
        .split("MOD_PID_TARGET_EFFECT")[0]


def test_the_fields_stop_at_pid_fourteen():
    """"Rewriting fields beyond pid 14 corrupted a slot and triggered the
    load-time clear." A boundary, not a guess."""
    assert max(fp.MOD_FIELD_PIDS) == 14
    assert fp.MOD_PID_TARGET_EFFECT not in fp.MOD_FIELD_PIDS
    assert fp.MOD_PID_TARGET_PARAM not in fp.MOD_FIELD_PIDS


def test_the_unknown_fields_are_left_out_rather_than_zeroed():
    """Pids 7 and 10-12 have no default here because nobody knows what they
    mean, and a continuous write of 0.0 is the zeroed-GET (a read, not a
    write) so they could not be zeroed on purpose anyway. That gap IS finding
    12, which is why a donor beats defaults."""
    assert set(fp.MOD_DEFAULT_FIELDS) == {1, 2, 3, 4, 5, 6, 13, 14}
    for pid in (7, 10, 11, 12):
        assert pid in fp.MOD_FIELD_PIDS and pid not in fp.MOD_DEFAULT_FIELDS


def test_a_working_slot_is_cloned_when_the_preset_has_one():
    """Finding 12: bindings written from scratch come out reversed or dead,
    and the working practice is to clone a proven slot. Verified live on
    preset 506, where the bind reported "curve cloned from slot 2"."""
    import inspect
    src = inspect.getsource(server._bind_pedal)
    assert "find_donor_slot" in src and "donor=donor" in src


def test_the_donor_is_never_the_slot_being_written():
    import inspect
    assert "skip={slot} | synthetic" in inspect.getsource(server._bind_pedal)


def test_a_default_curve_cannot_launder_itself_into_a_clone(client):
    """Bind three parameters on a preset with no modifiers of its own. The
    first gets this project's linear default. Without this, the second would
    clone the first and report "curve cloned from slot 1" about a curve that
    is really the default, and the provenance would improve itself one slot at
    a time until the log claimed a pedigree nothing has.

    Found by binding three parameters at once on preset 506, where binds 2 and
    3 cloned slot 1: harmless there, because slot 1 had itself come from the
    device's slot 2, and wrong in general.
    """
    fm9 = server._fm9
    with fm9:
        details = []
        for blk, par in (("delay", "DELAY_MIX"), ("reverb", "REVERB_MIX"),
                         ("chorus", "CHORUS_MIX")):
            r = server._bind_pedal(fm9, server.Action(
                kind="bind_pedal", block=blk, instance=1, param=par))
            if r["ok"]:
                details.append(r["detail"])
    assert len(details) >= 2, details
    assert all("linear default" in d for d in details), details
    assert not any("cloned" in d for d in details), details


def test_a_freed_slot_stops_being_ours(client):
    """Unbinding hands the slot back. Remembering it as one of ours would
    shrink the donor pool forever."""
    fm9 = server._fm9
    a = dict(block="delay", instance=1, param="DELAY_MIX")
    with fm9:
        server._bind_pedal(fm9, server.Action(kind="bind_pedal", **a))
        assert server._synthetic_slots["slots"]
        server._unbind_pedal(fm9, server.Action(kind="unbind_pedal", **a))
        assert not server._synthetic_slots["slots"]


def test_the_memory_resets_with_the_preset():
    """Slot numbers mean nothing across presets."""
    server._synthetic_slots.update({"preset": 12, "slots": {3, 4}})
    assert server._synthetic_for(99) == set()
    assert server._synthetic_slots["preset"] == 99


def test_bind_pedal_targets_the_pedal_the_player_named(client):
    """Pedal 1 and Pedal 2 are both bindable now (issue #11). pedal=1 writes
    source 10 and reads it back; pedal defaults to 2."""
    fm9 = server._fm9
    with fm9:
        r1 = server._bind_pedal(fm9, server.Action(
            kind="bind_pedal", block="output", param="OUTPUT_LEVEL", pedal=1))
        assert r1["ok"] and "Pedal 1" in r1["detail"]
        r2 = server._bind_pedal(fm9, server.Action(
            kind="bind_pedal", block="delay", param="DELAY_MIX", pedal=2))
        assert r2["ok"] and "Pedal 2" in r2["detail"]
        mods = server.read_modifiers(fm9)
    assert mods["OUTPUT_LEVEL"]["source"] == server.PEDAL_1_SOURCE
    assert mods["DELAY_MIX"]["source"] == server.PEDAL_2_SOURCE


def test_pedal_defaults_to_two_when_unspecified(client):
    fm9 = server._fm9
    with fm9:
        r = server._bind_pedal(fm9, server.Action(
            kind="bind_pedal", block="reverb", param="REVERB_MIX"))
        assert r["ok"] and "Pedal 2" in r["detail"]


def test_many_parameters_can_share_pedal_two(client):
    """Each modifier slot is one target and one source, so nothing stops
    several slots naming the same pedal. Verified live on preset 506: reverb
    mix, delay mix and phaser mix on slots 1, 9 and 10 at once."""
    fm9 = server._fm9
    with fm9:
        for blk, par in (("delay", "DELAY_MIX"), ("reverb", "REVERB_MIX")):
            assert server._bind_pedal(fm9, server.Action(
                kind="bind_pedal", block=blk, instance=1, param=par))["ok"]
        driven = {k: v for k, v in server.read_modifiers(fm9).items()
                  if v["source"] == server.PEDAL_2_SOURCE}
    assert set(driven) == {"DELAY_MIX", "REVERB_MIX"}
    assert len({v["slot"] for v in driven.values()}) == 2, "one slot each"


def test_running_out_of_slots_says_what_to_do(client):
    """The slots are filled in the simulator's own store rather than over the
    wire. Thirty-two binds is ninety-six writes, each waiting out a settle
    window, and it cost 78 seconds: a fifth of the whole suite to check one
    sentence. What is under test is the refusal, not the protocol, and the
    protocol has its own tests.
    """
    fm9 = server._fm9
    eid = server.reg.effect_id("DELAY")
    slots = fm9.sim_core.st.buffer["modifiers"]
    for m in range(1, fp.MOD_SLOT_COUNT + 1):
        slots[m][fp.MOD_PID_TARGET_EFFECT] = eid
        slots[m][fp.MOD_PID_TARGET_PARAM] = 12
        slots[m][fp.MOD_PID_SOURCE] = 11
    with fm9:
        r = server._bind_pedal(fm9, server.Action(
            kind="bind_pedal", block="reverb", instance=1, param="REVERB_MIX"))
    assert not r["ok"]
    assert "remove a binding to free one" in r["detail"]


def test_the_reply_says_how_many_slots_are_left(client):
    with server._fm9 as fm9:
        r = server._bind_pedal(fm9, server.Action(
            kind="bind_pedal", block="delay", instance=1, param="DELAY_MIX"))
    assert f"of {fp.MOD_SLOT_COUNT} slots still free" in r["detail"]


def test_binding_never_claims_the_sweep_works(client):
    """Live modulation is invisible to every read the protocol offers, and a
    dead binding reads byte-identical to a live one. A field read-back proves
    the slot was written and nothing about whether the pedal moves anything."""
    fm9 = server._fm9
    with fm9:
        r = server._bind_pedal(fm9, server.Action(
            kind="bind_pedal", block="delay", instance=1, param="DELAY_MIX"))
    assert r["ok"] and r["unverifiable"] is True
    assert "SWEEP is unverified" in r["detail"]
    assert "verified by read-back" not in r["detail"]


def test_binding_twice_is_refused_rather_than_doubled(client):
    fm9 = server._fm9
    a = server.Action(kind="bind_pedal", block="delay", instance=1,
                      param="DELAY_MIX")
    with fm9:
        assert server._bind_pedal(fm9, a)["ok"]
        second = server._bind_pedal(fm9, a)
    assert not second["ok"] and "already on modifier slot" in second["detail"]


def test_a_selector_cannot_be_put_under_a_pedal():
    """Sweeping a list of names with a foot is not a thing."""
    errs, _ = server.validate_action(server.Action(
        kind="bind_pedal", block="reverb", instance=1, param="REVERB_TYPE"))
    assert any("selector" in e for e in errs)


def test_pedal_one_is_never_referenced():
    """Moncy's global volume. Not a default, not an option, not in the
    vocabulary."""
    assert server.PEDAL_2_SOURCE == 11
    assert server.MOD_SOURCES[server.PEDAL_2_SOURCE] == "Pedal 2"
    for path in ("server.py", "ui/index.html", "fm9/device.py"):
        text = Path(path).read_text().lower()
        assert "pedal 1" not in text or "never" in text or "global volume" in text


# --- and the way back ------------------------------------------------------

def test_unbinding_gives_the_parameter_back(client):
    fm9 = server._fm9
    a = dict(block="delay", instance=1, param="DELAY_MIX")
    with fm9:
        server._bind_pedal(fm9, server.Action(kind="bind_pedal", **a))
        assert "DELAY_MIX" in server.read_modifiers(fm9)
        r = server._unbind_pedal(fm9, server.Action(kind="unbind_pedal", **a))
        assert r["ok"], r["detail"]
        assert "DELAY_MIX" not in server.read_modifiers(fm9)


def test_unbinding_refuses_a_source_it_cannot_name(client):
    """An unrecognised source is one the owner set up on the FM9 itself.
    Silently deleting somebody's own routing from a page that cannot even say
    what it is would be the opposite of safe. Live case: Moncy's preset 1 had
    the wah sweep on source 13."""
    fm9 = server._fm9
    _bind(fm9, 1, server.reg.effect_id("DELAY"), 0, 13)  # pid 0 is DELAY_MIX
    with fm9:
        r = server._unbind_pedal(fm9, server.Action(
            kind="unbind_pedal", block="delay", instance=1, param="DELAY_MIX"))
    assert not r["ok"]
    assert "not this tool's to remove" in r["detail"]


def test_unbinding_something_unbound_says_so(client):
    with server._fm9 as fm9:
        r = server._unbind_pedal(fm9, server.Action(
            kind="unbind_pedal", block="delay", instance=1, param="DELAY_MIX"))
    assert not r["ok"] and "no modifier on it" in r["detail"]


def test_clearing_writes_what_the_device_itself_writes():
    """Zeroing target and source is how the FM9 clears a slot that fails its
    own load-time validation (finding 16), so it is the device's idea of an
    empty slot rather than ours."""
    import inspect
    from fm9.device import FM9
    src = inspect.getsource(FM9.clear_modifier)
    for pid in ("MOD_PID_TARGET_EFFECT", "MOD_PID_TARGET_PARAM", "MOD_PID_SOURCE"):
        assert pid in src
    assert "build_set_param_discrete(eid, pid, 0)" in src


def test_gig_mode_refuses_both(client):
    for kind in ("bind_pedal", "unbind_pedal"):
        assert kind not in server.GIG_SAFE_KINDS, kind


# --- what the browser offers ----------------------------------------------

def test_the_row_offers_a_pedal_button():
    assert "function pedalBtn(key, m)" in SCRIPT
    fn = SCRIPT.split("function pedalable(key, m)")[1].split("\n}\n")[0]
    assert "if (lastMods[key]) return false;" in fn, \
        "a driven parameter cannot be bound again"
    assert "m.unit === 'enum' || m.unit === 'unverified'" in fn
    assert "(m.max - m.min) > 0" in fn


def test_only_our_own_binding_offers_removal():
    fn = SCRIPT.split("function modBadge(key)")[1].split("\n}\n")[0]
    assert "if (!d.known) {" in fn
    unknown = fn.split("if (!d.known) {")[1].split("}")[0]
    assert "data-unbind" not in unknown, \
        "a source we cannot name is not ours to delete"
    assert "data-unbind" in fn


def test_both_directions_confirm_first():
    fn = SCRIPT.split("const bind = e.target.closest('button[data-bind]')")[1] \
        .split("\n}));")[0]
    assert "window.confirm(msg)" in fn


def test_the_dialog_does_not_let_undo_imply_it_is_covered():
    """UNDO snapshots parameters, bypass and channel. A modifier slot is none
    of those, so the button is the only way back and the dialog has to say so
    rather than leaving the UNDO button to imply otherwise."""
    fn = SCRIPT.split("const bind = e.target.closest('button[data-bind]')")[1] \
        .split("\n}));")[0]
    assert "UNDO does not cover this" in fn
    assert "reversed" in fn, "the ear-check warning belongs in the dialog too"


def test_it_goes_through_the_one_write_path():
    fn = SCRIPT.split("const bind = e.target.closest('button[data-bind]')")[1] \
        .split("\n}));")[0]
    assert "blockAction({kind: bind ? 'bind_pedal' : 'unbind_pedal'" in fn
    assert "fetch(" not in fn

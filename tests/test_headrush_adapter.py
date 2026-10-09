"""Issue #125: the HeadRush DeviceAdapter, proven against the committed
simulator through the real client. No hardware; every claim about the unit
comes from docs/HEADRUSH-HARDWARE-FINDINGS.md and is cited in the adapter.
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from devices.headrush import adapter as hr
from devices.headrush import registry as hr_registry
from devices.headrush import tapers as hr_tapers
from devices.headrush.adapter import DerivedDisplay
from devices.headrush.client import HeadrushClient
from devices.headrush.registry import NotMeasured
from devices.headrush.sim import HeadrushSim
from fm9.adapter import (Capabilities, ReadPath, SceneSlotState, Topology,
                         conformance)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "config" / "headrush_schema.json").read_text(encoding="utf-8"))


class RecordingOpener:
    """Counts what reaches the wire, and can misbehave on purpose."""
    def __init__(self, sim, *, revert=None, hide=None):
        self.sim = sim
        self.calls = []
        self.revert = revert or {}     # (path, name) -> value the unit reverts to
        self.hide = set(hide or ())    # object paths that 404 on read

    def __call__(self, url, method, body, headers, timeout):
        self.calls.append((method, url))
        out = self.sim.opener(url, method, body, headers, timeout)
        path = url.split("/api/v1", 1)[1]
        if method == "PUT" and path.startswith("/object-properties"):
            target = path[len("/object-properties"):]
            for (p, name), value in self.revert.items():
                if p == target and name in json.loads(body or b"{}"):
                    self.sim.set_properties(p, {name: value})
        if method == "GET" and path.startswith("/object-properties"):
            target = path[len("/object-properties"):]
            if target in self.hide:
                import urllib.error
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return out


@pytest.fixture
def reg():
    return hr_registry.load()


def make(reg, **kw):
    sim = HeadrushSim()
    opener = RecordingOpener(sim, **kw)
    client = HeadrushClient("sim.local", "127.0.0.1", opener=opener)
    adapter = hr.HeadrushAdapter(client, reg, sleep=lambda s: None)
    return sim, opener, adapter


# --- conformance and capabilities ---------------------------------------------

def test_the_adapter_conforms_with_no_problems(reg):
    _sim, _op, a = make(reg)
    assert conformance(hr.HeadrushAdapter) == []
    assert conformance(a) == []


def test_capabilities_are_the_measured_ones(reg):
    _sim, _op, a = make(reg)
    c = a.capabilities()
    assert c == Capabilities(
        read_path=ReadPath.DEVICE, observes_foreign_writes=True,
        reads_slot_names=True, reads_slot_state=False, verifies_writes=True,
        has_scenes=True, stores_presets=False, topology=Topology.SELECTED,
        has_modifiers=False, installs_files=False, can_rename=False,
        composable_scene_slots=True)
    assert c.can_verify


def test_contract_methods_with_no_headrush_meaning_say_so(reg):
    _sim, _op, a = make(reg)
    with pytest.raises(hr.NotSupported):
        a.set_channel(1, 0)
    with pytest.raises(hr.NotSupported):
        a.store_preset(3)
    spec = reg.resolve("Amp", "Bass")
    with pytest.raises(NotMeasured):
        a.set_param_display(spec, 75.0)
    with pytest.raises(NotMeasured):
        a.get_param_display(spec)


# --- topology, chain, scenes ----------------------------------------------

def test_topology_is_enumerated_named_and_chosen_by_index(reg):
    sim, _op, a = make(reg)
    assert len(a.topologies()) == 10 and a.topologies()[0] == "S"
    assert a.select_topology(3)["ok"] and a.current_topology() == 3 == sim.routing
    with pytest.raises(LookupError):
        a.select_topology(42)


def test_place_by_slot_and_reorder_by_swap(reg):
    sim, _op, a = make(reg)
    assert a.place_block(2, 19)["ok"] and sim.slot(2) == 19
    assert a.place_block(5, 3)["ok"] and sim.slot(5) == 3
    assert a.reorder_block(2, 5)["ok"]
    assert (sim.slot(2), sim.slot(5)) == (3, 19)
    assert a.place_block(2, 0)["ok"] and sim.slot(2) == 0
    with pytest.raises(ValueError):
        a.place_block(15, 19)


def test_scenes_are_tri_state_by_slot_name(reg):
    sim, _op, a = make(reg)
    assert a.scene_slots(1) == {}
    assert a.set_scene_slot(1, "Amp", SceneSlotState.ON)["ok"]
    assert a.set_scene_slot(1, "Delay", SceneSlotState.OFF)["ok"]
    assert a.scene_slots(1) == {"Amp": SceneSlotState.ON, "Delay": SceneSlotState.OFF}
    assert a.set_scene_slot(1, "Amp", SceneSlotState.NO_CHANGE)["ok"]
    assert a.scene_slots(1) == {"Amp": SceneSlotState.NO_CHANGE,
                                "Delay": SceneSlotState.OFF}


def test_set_scene_needs_scene_mode_and_reads_last_scene_back(reg):
    sim, _op, a = make(reg)
    r = a.set_scene(2)
    assert r["ok"] is False and "scene mode" in r["detail"]
    sim.set_properties(hr.FOOTSWITCH, {"ModeNew2": 2})
    sim.set_properties(hr.FOOTSWITCH, {"LastScene": 1})     # the unit's answer
    assert a.set_scene(2)["ok"]


def test_readback_scene_activation_goes_through_the_verified_write_path(reg):
    """Review round 1: SceneActive is a property write like any other, so it
    is read back through _write_verified and reported. Success, though, is
    the measured effect (LastScene, finding 4): whether SceneActive persists
    or is a pulse the unit clears is unmeasured, so a cleared flag with an
    engaged scene is reported as engaged, with the flag noted as undecoded."""
    sim, opener, a = make(reg, revert={(hr.FOOTSWITCH, "SceneActive2"): False})
    sim.set_properties(hr.FOOTSWITCH, {"ModeNew2": 2, "LastScene": 1})
    r = a.set_scene(2)
    assert r["ok"] is True and r["written"] is False and r["engaged"] is True
    assert "SceneActive2" in r["detail"] and any("latches" in u for u in a.undecoded)
    puts = [u for m, u in opener.calls if m == "PUT"]
    assert len(puts) == 1 and "FootSwitch" in puts[0], "one verified write"
    sim2, _op, a2 = make(reg)
    sim2.set_properties(hr.FOOTSWITCH, {"ModeNew2": 2})
    r = a2.set_scene(2)                       # written, but LastScene never moved
    assert r["ok"] is False and r["written"] is True and r["engaged"] is False


def test_bypass_writes_the_blocks_own_on_switch(reg):
    sim, _op, a = make(reg)
    a.place_block(1, 19)
    r = a.set_bypass(1, True)
    assert r["ok"] and sim.get_properties("/Evil/Engine/Patch/Neural_Amp_Modeler")["On"] is False


def test_status_and_rig_names(reg):
    sim, _op, a = make(reg)
    sim.set_properties(hr.RIGS, {"RigNames": ["Init Rig", "Gig"]})
    st = a.status_dump()
    assert st["rig"] == "Init Rig" and set(st["slots"]) == set(range(1, 15))
    assert a.current_preset() == (None, "Init Rig")
    assert a.slot_name(1) == "Gig" and a.is_slot_empty(7)
    assert a.scan_slots(0, 1) == [(0, "Init Rig"), (1, "Gig")]


# --- readback: every write is verified after a settle -----------------------

def test_readback_every_property_write_is_reread_after_the_settle(reg):
    waits = []
    sim = HeadrushSim()
    opener = RecordingOpener(sim)
    a = hr.HeadrushAdapter(HeadrushClient("sim.local", "127.0.0.1", opener=opener),
                           reg, settle_s=0.5, sleep=waits.append)
    spec = reg.resolve("Amp", "Bass")
    r = a.set_param_wire(spec, 0.25)
    assert r["ok"] and r["read"] == 0.25
    assert waits == [0.5], "one settle per write, of the measured length"
    puts = [u for m, u in opener.calls if m == "PUT"]
    gets = [u for m, u in opener.calls if m == "GET"]
    assert len(puts) == 1 and any("/Evil/Engine/Patch/Amp" in g for g in gets)


def test_readback_default_settle_is_at_least_half_a_second(reg):
    sim = HeadrushSim()
    a = hr.HeadrushAdapter(HeadrushClient("sim.local", "127.0.0.1", opener=sim.opener), reg)
    assert a.settle_s >= 0.5


def test_readback_catches_a_write_the_unit_silently_reverts(reg):
    """Finding 1, ordinal 4: acknowledged, then put back to 0 by the unit."""
    sim, _op, a = make(reg, revert={(hr.CHAIN, "ModuleType3"): 0})
    r = a.place_block(3, 4)
    assert r["ok"] is False and "not placed" in r["detail"] and "reads 0" in r["detail"]


def test_readback_alone_is_not_enough_the_object_must_answer(reg):
    """Finding 1, the 254 shape: the value sticks but no object exists.
    Simulated with a backed ordinal whose object is hidden."""
    sim, _op, a = make(reg, hide={"/Evil/Engine/Patch/Neural_Amp_Modeler"})
    r = a.place_block(3, 19)
    assert r["ok"] is False and "publishes no object" in r["detail"]
    assert sim.slot(3) == 19, "the value did land; the object is what is missing"


def test_readback_reports_a_mismatch_instead_of_success(reg):
    sim, _op, a = make(reg, revert={(hr.CHAIN, "Routing"): 0})
    r = a.select_topology(4)
    assert r["ok"] is False and "wrote 4" in r["detail"]


# --- allowlist: deny by default, before transport ----------------------------

def test_allowlist_refuses_before_transport(reg):
    _sim, opener, a = make(reg)
    n = len(opener.calls)
    for path, method in [("/Evil/API/Rigs", "deleteRig"), ("/Evil/Engine/GlobalEQMain", "reset"),
                         ("/Evil/API/Rigs", "makeNewRig"), ("/Evil/System", "factoryReset")]:
        with pytest.raises(hr.MethodRefused):
            a.call_method(path, method, [])
    assert len(opener.calls) == n, "a refused method never reached the opener"


def test_allowlist_contains_only_load_rig(reg):
    assert hr.ALLOWED_METHODS == frozenset({("/Evil/API/Rigs", "loadRig")})


def test_allowlist_lets_nothing_dangerous_through_the_published_method_surface():
    published = []
    for path, h in SCHEMA["paths"].items():
        for m in (SCHEMA["metas"][h].get("x-methods") or {}):
            published.append((path, m))
    assert len(published) > 50, "fixture sanity: the schema publishes methods"
    bad = ("firmware", "update", "recover", "reset", "factory", "format",
           "reboot", "delete", "erase", "flash", "upgrade")
    dangerous = [pm for pm in published if any(b in pm[1].lower() for b in bad)]
    assert dangerous, "fixture sanity: there are dangerous names to keep out"
    assert not (set(dangerous) & hr.ALLOWED_METHODS)
    assert hr.ALLOWED_METHODS <= set(published) | {("/Evil/API/Rigs", "loadRig")}


def test_allowlist_the_one_allowed_method_reaches_the_wire(reg):
    _sim, opener, a = make(reg)
    n = len(opener.calls)
    assert a.call_method("/Evil/API/Rigs", "loadRig", ["rig-0000", ""]) is True
    assert len(opener.calls) == n + 1 and "object-method" in opener.calls[-1][1]


# --- #135: select_preset loads by rig ID, found by the #126 hardware pass ---------

def test_select_preset_resolves_a_name_to_the_rig_id_and_settles_before_reading(reg):
    waits = []
    sim = HeadrushSim(rigs=["Init Rig", "Gig", "##HRB ToneCommandTesting"])
    opener = RecordingOpener(sim)
    a = hr.HeadrushAdapter(HeadrushClient("sim.local", "127.0.0.1", opener=opener), reg,
                           settle_s=0.5, sleep=waits.append)
    r = a.select_preset("Gig")
    assert r["ok"] is True and r["loaded"] == "Gig" and r["rig_id"] == "rig-0001", r
    assert r["returned"] is True
    assert waits == [0.5], "loadRig returns before the engine swaps: settle before the read-back"
    assert sim.loaded_rig == "Gig"
    # an id works directly too
    r = a.select_preset("rig-0002")
    assert r["ok"] and r["loaded"] == "##HRB ToneCommandTesting"


def test_select_preset_sends_the_id_never_the_name(reg):
    """The exact defect: a NAME in loadRig's first argument gets 504 on the
    Core and loads nothing. The simulator answers the same way, so the
    adapter cannot regress to sending the name without this test going red."""
    sim = HeadrushSim(rigs=["Init Rig", "Gig"])
    sent = []
    real = sim.opener

    def opener(url, method, body, headers, timeout):
        if "/object-method" in url:
            sent.append(json.loads(body or b"{}").get("arguments"))
        return real(url, method, body, headers, timeout)

    a = hr.HeadrushAdapter(HeadrushClient("sim.local", "127.0.0.1", opener=opener), reg, sleep=lambda s: None)
    assert a.select_preset("Gig")["ok"]
    assert sent == [["rig-0001", ""]], sent
    with pytest.raises(Exception, match="504"):
        a.client.call_method("/Evil/API/Rigs", "loadRig", ["Gig", ""])


def test_select_preset_refuses_an_unknown_rig_before_transport(reg):
    _sim, opener, a = make(reg)
    n = len(opener.calls)
    with pytest.raises(LookupError, match="no rig"):
        a.select_preset("No Such Rig")
    assert not any("object-method" in u for _m, u in opener.calls[n:])


def test_allowlist_refused_module_ordinals_never_reach_the_wire(reg):
    _sim, opener, a = make(reg)
    n = len(opener.calls)
    for ordinal in (20, 254):
        with pytest.raises(PermissionError, match="finding 1"):
            a.place_block(3, ordinal)
    assert len(opener.calls) == n
    assert set(hr.REFUSED_MODULE_ORDINALS) == {20, 254}, "4 is the unit's own refusal"


# --- evidence ------------------------------------------------------------------

def test_evidence_names_the_measured_unit_and_the_unverified_models(reg):
    _sim, _op, a = make(reg)
    e = a.evidence()
    assert e["model"] == "HeadRush Core" and e["firmware"] == "5.1.0.2a63755"
    assert e["measured_on"] == "2026-09-15"
    assert set(e["unverified_models"]) == {"Prime", "Flex Prime"}
    assert (ROOT / e["source"]).exists()
    text = (ROOT / e["source"]).read_text(encoding="utf-8")
    assert e["firmware"] in text and "Prime and Flex Prime are UNVERIFIED" in text


def test_evidence_firmware_label_reads_the_units_own_version(reg):
    sim, _op, a = make(reg)
    sim.set_properties(hr.GUI, {"AppVersion": "5.1.0.2a63755"})
    assert a.firmware_label() == "5.1.0.2a63755"


def test_evidence_capabilities_docstring_cites_the_findings():
    doc = hr.__doc__
    assert "HEADRUSH-HARDWARE-FINDINGS" in doc and "5.1.0.2a63755" in doc
    for flag in ("reads_slot_state", "stores_presets", "composable_scene_slots",
                 "has_modifiers", "installs_files", "can_rename"):
        assert flag in doc, f"{flag} is declared without its reason"
    assert "Prime" not in hr.__doc__.split("WHAT IT REFUSES")[1], \
        "nothing below the evidence section claims Prime behaviour"


# --- display conversion through #130's curve table ----------------------------
#
# The registry still refuses, and that refusal is still right: it describes the
# API, which publishes an opaque `normalizeAlgo` and no formula. These cover the
# other kind of knowledge, read out of the vendor's editor, which a caller has
# to opt into and which can never be mistaken for something the unit said.

HARDWARE_CHECK = json.loads(
    (ROOT / "config" / "headrush_tapers.json").read_text(encoding="utf-8"))["hardware_check"]


def _converting(reg, **kw):
    sim = HeadrushSim()
    opener = RecordingOpener(sim, **kw) if kw else sim.opener
    client = HeadrushClient("sim.local", "127.0.0.1", opener=opener)
    return sim, hr.HeadrushAdapter(client, reg, tapers=hr_tapers.load(),
                                   sleep=lambda s: None)


@pytest.mark.parametrize("row", HARDWARE_CHECK,
                         ids=[f"{r['property']}@{r['wire']}" for r in HARDWARE_CHECK])
def test_display_matches_what_the_screen_showed(reg, row):
    """The anchor. Six readings taken off a Core's screen, committed in
    config/headrush_tapers.json with the wire value that produced each one.

    These are the only rows in this file that a photograph can refute."""
    sim, a = _converting(reg)
    block, name = row["property"].split(".")
    spec = reg.resolve(block, name)
    sim.set_properties(reg.block(block).path, {name: row["wire"]})
    assert a.get_param_display(spec).text.strip() == row["screen"].strip()


def test_without_a_table_the_adapter_still_refuses(reg):
    """Every existing caller builds one without tapers, and none of them
    should start getting numbers because this feature landed."""
    _sim, _op, a = make(reg)
    spec = reg.resolve("Amp", "Bass")
    assert a.tapers is None
    with pytest.raises(NotMeasured):
        a.get_param_display(spec)
    with pytest.raises(NotMeasured):
        a.set_param_display(spec, 75.0)


def test_a_derived_value_never_arrives_as_a_bare_float(reg):
    """get_param_wire returns a float because the unit sent that float. This
    must not, or a converted number can be logged and planned against exactly
    as if the device had reported it."""
    sim, a = _converting(reg)
    spec = reg.resolve("Amp", "TremSpeed")
    sim.set_properties(reg.block("Amp").path, {"TremSpeed": 0.5})
    got = a.get_param_display(spec)
    assert isinstance(got, DerivedDisplay)
    assert got.api_readable is False
    # and it cannot be TURNED INTO one either: a NamedTuple would let
    # `value, *_ = got` and `got[0]` strip the provenance back off.
    with pytest.raises(TypeError):
        got[0]
    with pytest.raises(TypeError):
        _value, *_rest = got
    assert got.curve == "Squared"
    assert got.provenance
    # the wire read, by contrast, is a plain number
    assert isinstance(a.get_param_wire(spec), float)


def test_writing_a_display_value_still_verifies_the_wire_value(reg):
    """Only the caller's units change. The read-back that makes a write
    trustworthy still compares what actually went on the wire."""
    sim, a = _converting(reg)
    spec = reg.resolve("Amp", "TremSpeed")
    out = a.set_param_display(spec, 5.1875)
    assert out["ok"] is True
    assert out["display_wanted"] == 5.1875
    assert out["curve"] == "Squared"
    # The unit does NOT hold the 0.5 that went on the wire: it snaps 5.1875 to
    # the published 0.01 grid, converts back, and keeps 0.5001265... This
    # assertion used to say `approx(0.5)` and passed only because the
    # simulator stored writes verbatim - it was asserting the double's
    # fiction, not the device (#167).
    assert sim.get_properties(reg.block("Amp").path)["TremSpeed"] == \
        0.5001265406608582
    assert out["held"] == 0.5001265406608582
    assert a.get_param_display(spec).text == "5.19 Hz"


def test_a_curve_the_table_has_never_seen_is_not_quietly_linear(reg):
    """The firmware publishing an unknown id means this table was built
    against a different one. Scaling linearly anyway would silently mis-read
    every value of that parameter."""
    _sim, a = _converting(reg)
    spec = reg.resolve("Amp", "Bass")

    class Unknown:
        taper_id = 9999
        block, name = "Amp", "Bass"
        display_minimum, display_maximum = spec.display_minimum, spec.display_maximum
        display_format, unit = spec.display_format, spec.unit

    with pytest.raises(hr_tapers.UnknownTaper):
        a._converted(Unknown(), "to_display", 0.5)


def test_a_parameter_with_no_display_range_refuses(reg):
    _sim, a = _converting(reg)

    class NoRange:
        taper_id = 0
        block, name = "Amp", "Bass"
        display_minimum = display_maximum = None
        display_format = unit = None

    with pytest.raises(NotMeasured):
        a._converted(NoRange(), "to_display", 0.5)


# --- the device's own arithmetic agrees with the table ------------------------

#: Measured on a Core at firmware 5.1.0.2a63755, 2026-09-19, on a ##HRB test
#: preset. `Amp.TremSpeed`, published grid 0.01, display range 0.25..20.0 Hz,
#: normalizeAlgo 5 (Squared). Each row is a wire value written and the float
#: the unit was holding afterwards.
TREMSPEED_ROUND_TRIP = [
    (0.5,       0.5001265406608582),
    (0.25,      0.24955657124519348),
    (0.3333333, 0.33299562335014343),
]


@pytest.mark.parametrize("wrote,held", TREMSPEED_ROUND_TRIP)
def test_the_vendor_curve_predicts_what_the_device_stored(reg, wrote, held):
    """Corroboration from the device rather than from a photograph.

    The unit converts a written wire value to display, snaps the DISPLAY value
    to the published grid, and converts back (#167). Reproducing the float it
    ends up holding therefore runs the curve forwards and backwards through the
    device's own quantisation, and it matches to the last bit on a NON-LINEAR
    curve, where a wrong formula could not survive.

    The six `hardware_check` rows are a screen read by a human. This is the
    device's own arithmetic agreeing with the table, which a misread digit
    cannot produce.
    """
    table = hr_tapers.load()
    spec = reg.resolve("Amp", "TremSpeed")
    assert spec.taper_id == 5 and spec.published.get("grid") == pytest.approx(0.01)

    display = table.to_display(wrote, minimum=spec.display_minimum,
                               maximum=spec.display_maximum, algo=spec.taper_id)
    snapped = round(display / 0.01) * 0.01
    predicted = table.to_wire(snapped, minimum=spec.display_minimum,
                              maximum=spec.display_maximum, algo=spec.taper_id)
    # exact equality, not an approx: "matches to the last bit" is the claim
    # the CHANGELOG makes, and a tolerance would not be evidence for it.
    assert predicted == held


def test_that_prediction_needs_the_real_curve(reg):
    """Guard on the guard: a linear scale cannot produce those floats, so the
    test above is evidence about this table and not arithmetic that any curve
    would satisfy."""
    spec = reg.resolve("Amp", "TremSpeed")
    lo, hi = spec.display_minimum, spec.display_maximum
    for wrote, held in TREMSPEED_ROUND_TRIP:
        linear_display = lo + wrote * (hi - lo)
        snapped = round(linear_display / 0.01) * 0.01
        linear_wire = (snapped - lo) / (hi - lo)
        assert abs(linear_wire - held) > 1e-6, (
            f"a linear scale reproduced {held!r}, so the round-trip test "
            f"proves nothing about the curve")


def test_a_wire_read_that_came_back_empty_is_not_converted(reg):
    """A missing read is not a zero. `get_property` answers None when the
    object does not carry the property, and 0.0 is a real value on every one
    of these curves, so converting None would invent the bottom of the
    range."""
    bass = reg.resolve("Amp", "Bass")
    _sim, a = _converting(reg)

    class Absent:                      # a property this object does not carry
        taper_id = bass.taper_id
        block, name = "Amp", "NotAProperty"
        display_minimum, display_maximum = bass.display_minimum, bass.display_maximum
        display_format, unit = bass.display_format, bass.unit

    spec = Absent()
    assert a.get_param_wire(spec) is None
    with pytest.raises(NotMeasured):
        a.get_param_display(spec)


def test_a_value_the_curve_cannot_express_is_refused_not_rounded(reg):
    """`NotConvertible` is named in the adapter as deliberately uncaught.
    `Volume` is log10(0) at wire 0, which the editor calls -Infinity and this
    refuses rather than substituting the minimum.

    THE SPEC IS FABRICATED, AND HAS TO BE. No parameter this firmware
    publishes reaches a non-finite value at either end of its own range - the
    test below asserts that, so this one is about the adapter PROPAGATING the
    refusal rather than about a case a player can hit today. If the assertion
    below ever fails, this one should be rewritten against the real
    parameter."""
    _sim, a = _converting(reg)
    spec = reg.resolve("Amp", "Bass")

    class Volume:                       # normalizeAlgo 2
        taper_id = 2
        block, name = "Amp", "Volume"
        display_minimum, display_maximum = spec.display_minimum, spec.display_maximum
        display_format, unit = spec.display_format, spec.unit

    with pytest.raises(hr_tapers.NotConvertible):
        a._converted(Volume(), "to_display", 0.0)


def test_a_selector_is_not_dragged_onto_the_continuous_path(reg):
    """The old refusal sent callers to `set_param_ordinal` for selectors, and
    the new path always converts. It cannot swallow one: no parameter in the
    registry carries both `options` and a display range, so a selector has
    nothing to convert between and refuses."""
    _sim, a = _converting(reg)
    selectors = [p for p in _every_parameter(reg) if p.options is not None]
    assert selectors, "the registry publishes no selectors, so this proves nothing"
    assert not [p for p in selectors if p.display_minimum is not None], \
        "a selector now carries a display range; set_param_display must gate on options"

    spec = reg.resolve("Amp", "Type")
    assert spec.options is not None
    with pytest.raises(NotMeasured):
        a.set_param_display(spec, 3.0)


def _every_parameter(reg):
    for block in reg.blocks.values():
        yield from block.parameters.values()


def test_no_real_parameter_can_reach_a_value_its_curve_cannot_express(reg):
    """Why the test above has to fabricate a spec, asserted rather than
    asserted-by-me. `Exponential` divides by zero when a range starts at or
    below 0, and `Volume` is log10(0) at wire 0, but nothing in this dump is
    published with a range that puts either edge there."""
    table = hr_tapers.load()
    reachable = []
    for spec in _every_parameter(reg):
        if spec.display_minimum is None or spec.options is not None:
            continue
        for wire in (0.0, 0.5, 1.0):
            try:
                table.to_display(wire, minimum=spec.display_minimum,
                                 maximum=spec.display_maximum,
                                 algo=spec.taper_id)
            except hr_tapers.NotConvertible:
                reachable.append(f"{spec.block}.{spec.name}@{wire}")
                break
            except hr_tapers.UnknownTaper:
                break
    assert not reachable, (
        f"a published parameter now refuses at its own edge: {reachable[:5]}; "
        f"test_a_value_the_curve_cannot_express_is_refused_not_rounded should "
        f"use it instead of a fabricated spec")


def test_a_format_string_that_will_not_apply_keeps_the_unit(reg):
    """The no-format path appends `spec.unit`, so the fallback must too. A
    device format that cannot take a float used to drop the `Hz` as well as
    the digits, which reads as a bare number with no clue it is unitless by
    accident."""
    bass = reg.resolve("Amp", "Bass")
    _sim, a = _converting(reg)

    class BadFormat:
        taper_id = bass.taper_id
        block, name = "Amp", "Bass"
        display_minimum, display_maximum = bass.display_minimum, bass.display_maximum
        display_format = "%d%"          # a trailing %, which % cannot apply
        unit = "Hz"

    with pytest.raises(ValueError):     # the premise: this format really breaks
        BadFormat.display_format % 12.5
    assert a._formatted(BadFormat(), 12.5) == "12.5 Hz"


def test_the_guards_refuse_before_any_call_reaches_the_device(reg):
    """The guards run BEFORE the read, so a spec that was never convertible
    does not cost a round trip to find that out.

    The opener is asserted on UNCONDITIONALLY. The first version of this test
    built the plain simulator opener and skipped the call count when it had
    none to report, so moving the guard back below `get_param_wire` would
    have left it green - a test that cannot fail for the thing it is named
    after."""
    sim = HeadrushSim()
    opener = RecordingOpener(sim)
    client = HeadrushClient("sim.local", "127.0.0.1", opener=opener)
    a = hr.HeadrushAdapter(client, reg, tapers=hr_tapers.load(),
                           sleep=lambda s: None)
    spec = reg.resolve("Amp", "Type")

    assert opener.calls == []
    with pytest.raises(NotMeasured):
        a.get_param_display(spec)
    assert opener.calls == [], "it read the device before refusing"

    with pytest.raises(NotMeasured):
        a.set_param_display(spec, 3.0)
    assert opener.calls == [], "it wrote to the device before refusing"


def test_a_derived_display_cannot_be_built_claiming_the_unit_said_it():
    """`api_readable=False` is the whole contract. It is init=False so no
    caller can construct one that claims otherwise, and frozen so none can
    assign over it."""
    import dataclasses
    got = DerivedDisplay(value=1.0, text="1 Hz", curve="Linear", provenance="x")
    assert got.api_readable is False
    with pytest.raises(TypeError):
        DerivedDisplay(value=1.0, text="1 Hz", curve="Linear",
                       provenance="x", api_readable=True)
    # replace() refuses an init=False field: ValueError up to Python 3.13,
    # TypeError from 3.14 (#172 CI); either way it does not build one
    with pytest.raises((ValueError, TypeError)):
        dataclasses.replace(got, api_readable=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        got.api_readable = True


def test_a_table_shaped_object_is_not_a_table(reg):
    """`tapers=` is checked at construction, not at the first conversion.
    Something that merely answers to to_display and to_wire would convert
    with a curve nobody can name the provenance of, which is the one thing
    DerivedDisplay exists to make impossible."""
    sim = HeadrushSim()
    client = HeadrushClient("sim.local", "127.0.0.1", opener=sim.opener)

    class LooksRight:
        provenance = "made up"
        def name(self, algo): return "Linear"
        def to_display(self, wire, **kw): return wire * 100
        def to_wire(self, display, **kw): return display / 100

    with pytest.raises(TypeError):
        hr.HeadrushAdapter(client, reg, tapers=LooksRight())
    # and the real one still builds
    assert hr.HeadrushAdapter(client, reg, tapers=hr_tapers.load()).tapers


# --- #167: the read-back is predicted, not tolerated -------------------------
#
# The unit converts a written wire value to display, snaps the DISPLAY value to
# the published grid, converts back and stores float32, so a write it honoured
# read back as a different float and `_write_verified` called it a failure.
#
# The fix predicts what the unit will hold and keeps comparing EXACTLY. A
# tolerance window would have been the obvious shape and is the wrong one: it
# would also accept a value the unit discarded, which is the whole job of the
# read-back (finding 1).

#: Every write/read pair #167 measured on a Core at 5.1.0.2a63755, across two
#: curves and three grids. THIS is the evidence. A test that only compared the
#: adapter against HeadrushSim would prove self-consistency, because the sim
#: quantizes with the same vendor table the adapter predicts with.
MEASURED_ON_THE_UNIT = [
    ("TremSpeed", 0.5,       0.5001265406608582),
    ("TremSpeed", 0.25,      0.24955657124519348),
    ("TremSpeed", 0.3333333, 0.33299562335014343),
    ("Bass",      0.5,       0.5),
    ("Bass",      0.25,      0.25),
    ("Bass",      0.3333333, 0.33000001311302185),
    ("PostGain",  0.5,       0.5),
    ("PostGain",  0.3333333, 0.3333333432674408),
]


@pytest.mark.parametrize("name,wrote,held", MEASURED_ON_THE_UNIT,
                         ids=[f"{n}@{w}" for n, w, _ in MEASURED_ON_THE_UNIT])
def test_the_prediction_reproduces_every_pair_measured_on_the_unit(
        reg, name, wrote, held):
    """The anchor: bit-exact, not approximate, on all eight."""
    _sim, a = _converting(reg)
    assert a._expected_read_back(reg.resolve("Amp", name), wrote) == held


def test_a_quantized_write_the_unit_honoured_is_reported_as_success(reg):
    """The bug. On Amp.TremSpeed every wire value tested reported failure,
    three for three, for writes the device had accepted."""
    _sim, a = _converting(reg)
    spec = reg.resolve("Amp", "TremSpeed")
    out = a.set_param_wire(spec, 0.25)
    assert out["ok"] is True
    assert out["wanted"] == 0.25
    assert out["held"] == 0.24955657124519348
    assert "quantized" in out["detail"]


def test_an_on_grid_write_is_still_required_to_read_back_exactly(reg):
    """#168's hardware run found the rule is narrower than #167 states: a
    request that lands ON the grid is stored exactly, so it must still be
    checked exactly. Accepting a window here would hide a dropped write on
    the one class of value where an exact check is achievable."""
    _sim, a = _converting(reg)
    spec = reg.resolve("Amp", "TremSpeed")
    on_grid = a._expected_read_back(spec, 0.5)          # the 5.19 Hz fixed point
    assert a._expected_read_back(spec, on_grid) == on_grid, \
        "the prediction must be a fixed point, or an honoured write still fails"
    out = a.set_param_wire(spec, on_grid)
    assert out["ok"] is True and "held" not in out


def test_a_write_the_unit_discarded_still_fails(reg):
    """The guarantee that must not be lost. Finding 1: ordinal 4 reads back
    correctly at t+0.04 s and is gone by t+0.39 s, and a tolerance wide enough
    to accept the grid would have accepted that too."""
    sim = HeadrushSim()
    spec = reg.resolve("Amp", "TremSpeed")
    opener = RecordingOpener(sim, revert={(reg.block("Amp").path,
                                           "TremSpeed"): 0.9})
    client = HeadrushClient("sim.local", "127.0.0.1", opener=opener)
    a = hr.HeadrushAdapter(client, reg, tapers=hr_tapers.load(),
                           sleep=lambda s: None)
    out = a.set_param_wire(spec, 0.25)
    assert out["ok"] is False, "a discarded write was accepted"
    assert "unit reads" in out["detail"]


def test_without_a_table_the_write_check_is_exactly_what_it_was(reg):
    """No table, no prediction, and no change for any existing caller."""
    _sim, _op, a = make(reg)
    spec = reg.resolve("Amp", "Bass")
    assert a.tapers is None
    assert a._expected_read_back(spec, 0.25) is None
    out = a.set_param_wire(spec, 0.25)
    assert out["ok"] is True and "held" not in out


def test_a_prediction_that_cannot_be_made_does_not_break_the_write(reg):
    """An unknown curve means the table was built against other firmware. The
    display methods refuse outright, because a converted number would be a
    fiction. A WRITE must not: it falls back to comparing what it sent, which
    is the behaviour that shipped, rather than raising on a value the unit
    would have accepted."""
    _sim, a = _converting(reg)
    bass = reg.resolve("Amp", "Bass")

    class UnknownCurve:
        taper_id = 9999
        block, name = "Amp", "Bass"
        display_minimum, display_maximum = bass.display_minimum, bass.display_maximum
        display_format, unit = bass.display_format, bass.unit
        published = {"grid": 1.0}
        wire_range = bass.wire_range

    assert a._expected_read_back(UnknownCurve(), 0.25) is None
    out = a.set_param_wire(UnknownCurve(), 0.25)
    assert out["ok"] is True


def test_the_grid_is_a_float32_and_must_not_be_used_literally(reg):
    """The trap that cost two wrong versions of this fix. A grid the vendor
    wrote as 0.01 arrives as 0.009999999776482582; snapping with that literal
    puts Amp.TremSpeed at 0.33299559354782104 where the unit holds
    ...62335014343, and nothing about it looks wrong."""
    spec = reg.resolve("Amp", "TremSpeed")
    published = spec.published["grid"]
    assert published != 0.01, "the published grid is exact; this test is moot"

    display = 2.4444440055555776                   # to_display(0.3333333)
    naive = round(display / published) * published
    assert hr_tapers.snap_to_grid(display, published) == 2.44
    assert naive != 2.44, "snapping with the literal float32 grid is harmless"


def test_to_wire_returns_float32_which_this_prediction_relies_on():
    """The prediction does not round to float32 itself, because the table
    already does. If that ever stops being true the predictions drift by an
    ULP and every read-back check starts failing again, so it is pinned here
    rather than assumed by a comment."""
    table = hr_tapers.load()
    for display, lo, hi, algo in ((33.0, 0.0, 100.0, None),
                                  (2.44, 0.25, 20.0, 5),
                                  (-4.0, -12.0, 12.0, None)):
        wire = table.to_wire(display, minimum=lo, maximum=hi, algo=algo)
        assert struct.unpack("f", struct.pack("f", wire))[0] == wire, \
            f"to_wire({display}) returned a float64: {wire!r}"

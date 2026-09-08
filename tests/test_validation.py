"""Validation-before-send regression suite (no hardware, no simulator)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import server
from server import Action, validate_action

CASES = [
    ("in-range", dict(kind="set_param", block="amp", param="DISTORT_DRIVE", value=6.5), 0, 0),
    ("over-range", dict(kind="set_param", block="amp", param="DISTORT_DRIVE", value=15), 1, 0),
    ("under-range", dict(kind="set_param", block="amp", param="DISTORT_DRIVE", value=-2), 1, 0),
    ("unknown-param", dict(kind="set_param", block="amp", param="DISTORT_MOJO", value=5), 1, 0),
    ("unknown-block", dict(kind="set_param", block="kazoo", param="X", value=5), 1, 0),
    ("selector-as-param", dict(kind="set_param", block="amp", param="DISTORT_TYPE", value=3), 1, 0),
    ("non-numeric", dict(kind="set_param", block="amp", param="DISTORT_DRIVE", value=None), 1, 0),
    ("uncalibrated-warns", dict(kind="set_param", block="geq", param="GEQ_MIX", value=50), 0, 1),
    ("scene-ok", dict(kind="set_scene", value=3), 0, 0),
    ("scene-9", dict(kind="set_scene", value=9), 1, 0),
    ("tempo-500", dict(kind="set_tempo", value=500), 1, 0),
    ("tempo-120", dict(kind="set_tempo", value=120), 0, 0),
    ("channel-5", dict(kind="set_channel", block="amp", value=5), 1, 0),
    ("good-model", dict(kind="set_type", block="amp", type_name="PVH 6160 Block Lead"), 0, 0),
    ("real-amp-name", dict(kind="set_type", block="amp", type_name="MESA/Boogie Mark IIC+"), 0, 0),
    ("garbage-model", dict(kind="set_type", block="amp", type_name="Fnord Blaster 9000"), 1, 0),
    ("bypass-no-bool", dict(kind="set_bypass", block="delay"), 1, 0),
    ("bypass-ok", dict(kind="set_bypass", block="delay", bypassed=True), 0, 0),
]


@pytest.mark.parametrize("name,action,want_errs,want_warns",
                         CASES, ids=[c[0] for c in CASES])
def test_validation(name, action, want_errs, want_warns):
    errs, warns = validate_action(Action(**action))
    assert (len(errs) > 0) == (want_errs > 0), errs
    assert (len(warns) > 0) == (want_warns > 0), warns


def test_add_block_and_bind_pedal_carry_honesty_warnings():
    """Factory defaults are not a sound, and pedal curves are undecoded
    (issues #11/#12, hardware session 2026-08-20): both must warn."""
    from server import Action, validate_action
    errs, warns = validate_action(Action(kind="add_block", block="phaser"))
    assert not errs and any("factory-default" in w for w in warns)
    errs, warns = validate_action(
        Action(kind="bind_pedal", block="delay", param="DELAY_MIX"))
    assert any("NOT verified" in w for w in warns)


def test_cab_description_resolves_real_cabinet():
    """Uses the accessor Brian shipped in #14: (ordinal, bank)."""
    from fm9.registry import Registry
    reg = Registry()
    d = reg.cab_description(4, 0)
    assert "=" in d and "Danelectro" in d          # bank0/4 per merged sidecar
    assert reg.cab_description(999, 9) == "999"    # graceful unknown


def test_effect_type_models_load_and_reach_planner():
    from fm9.registry import Registry
    from server import param_reference
    reg = Registry()
    assert reg.effect_type_models["chorus_types"]["Small Copy"].startswith("EHX")
    ref = param_reference()
    assert "Deluxe Mind Guy = Deluxe Memory Man" in ref
    assert "Dytronics Songbird" in ref
    assert "Aurora Delay = Keeley HALO" in ref
    assert reg.effect_type_models["known_ordinals"]["multitap"]["Aurora Delay"] == 1


def test_fm9_satisfies_the_device_adapter_contract():
    """ARCHITECTURE.md step 1, checked against the contract itself.

    This used to walk a hand-written list of method names, which had already
    drifted: `slot_name` and `is_slot_empty` were in the contract and
    certified against nothing. The member list is derived from the Protocol
    now, so the contract cannot grow past its certification again.
    """
    from fm9.adapter import DeviceAdapter, conformance, contract_members
    from fm9.device import FM9
    from fm9.registry import Registry
    from fm9.sim import SimFM9
    assert set(contract_members()) == set(DeviceAdapter.__protocol_attrs__)
    assert conformance(FM9) == []
    # SimFM9 is a FACTORY returning a real FM9 on simulated ports, so this
    # asserts the same class by a second route rather than a second
    # implementation. Kept because the factory is what every test uses, and
    # it breaking is worth knowing; see the test below for why it is not
    # evidence that the contract is portable.
    assert isinstance(SimFM9(Registry()), DeviceAdapter)


def test_the_contract_has_only_ever_had_one_implementation():
    """Honest limit, pinned so it is known rather than discovered.

    ARCHITECTURE.md step 4 says adapter #2 stresses the contract and that the
    CONTRACT gets fixed, not the adapter. Until a second device exists, the
    contract is shaped entirely by the FM9, and conformance() passing proves
    only self-consistency. Writing this down stops "certified" from being
    read as "portable".
    """
    from fm9.sim import SimFM9
    from fm9.device import FM9
    from fm9.registry import Registry
    assert type(SimFM9(Registry())) is FM9


def test_conformance_catches_a_wrong_signature_not_just_a_missing_name():
    """`runtime_checkable` only lets isinstance() test that an attribute
    EXISTS, so a class whose set_scene takes no scene passes isinstance and
    then fails at the first call. That defeats the point of a Protocol, which
    is that a device written against it works without being tried."""
    from fm9.adapter import DeviceAdapter, conformance
    from fm9.device import FM9

    class Wrong:
        pass
    for name in DeviceAdapter.__protocol_attrs__:
        setattr(Wrong, name, getattr(FM9, name))
    assert conformance(Wrong) == [], "the copy should conform"

    Wrong.set_scene = lambda self: None                    # dropped the argument
    problems = conformance(Wrong)
    assert any("set_scene" in p for p in problems), problems
    assert isinstance(Wrong(), DeviceAdapter), \
        "isinstance still passes, which is exactly why conformance() exists"


def test_a_renamed_contract_argument_is_a_conformance_failure():
    """Callers are entitled to pass contract arguments by keyword, so a
    renamed parameter breaks them. This is the real defect found on the FM9:
    the contract said select_preset(number) and set_scene(scene) while the
    implementation took (preset) and (scene_1based). The contract was the
    wrong one, since it already said set_channel(channel_0based)."""
    from fm9.adapter import DeviceAdapter, conformance
    from fm9.device import FM9

    class Renamed:
        pass
    for name in DeviceAdapter.__protocol_attrs__:
        setattr(Renamed, name, getattr(FM9, name))
    Renamed.select_preset = lambda self, number: None      # the old contract name
    assert any("select_preset" in p for p in conformance(Renamed))


def test_an_extra_optional_argument_is_allowed():
    """The FM9's bulk_read takes a timeout the contract now names. An adapter
    may widen with OPTIONAL parameters; it may not require one the contract
    does not supply."""
    from fm9.adapter import DeviceAdapter, conformance
    from fm9.device import FM9

    class Wide:
        pass
    for name in DeviceAdapter.__protocol_attrs__:
        setattr(Wide, name, getattr(FM9, name))
    Wide.set_scene = lambda self, scene_1based, settle=0.2: None
    assert conformance(Wide) == []
    Wide.set_scene = lambda self, scene_1based, settle: None   # now REQUIRED
    assert any("settle" in p for p in conformance(Wide))


def test_an_undeclared_device_promises_nothing():
    """Capabilities are deny-by-default, like the send guard: an unfinished
    adapter under-promises rather than over-promises."""
    from fm9.adapter import UNDECLARED, ReadPath
    assert UNDECLARED.read_path is ReadPath.NONE
    assert not UNDECLARED.can_verify
    assert "no read path" in UNDECLARED.why_unverified()


def test_the_fm9_declares_what_hardware_sessions_proved():
    from fm9.adapter import ReadPath
    from fm9.device import FM9
    caps = FM9.CAPABILITIES
    assert caps.read_path is ReadPath.DEVICE
    assert caps.can_verify
    assert caps.why_unverified() == ""      # nothing to excuse
    assert caps.reads_by_slot and caps.has_scenes and caps.stores_presets
    assert not caps.split_transport


def test_a_read_path_on_a_separate_channel_still_counts_as_evidence():
    """The ToneX shape (#23): control goes out over MIDI, state comes back on
    a serial port. That is weaker than the FM9's same-channel read but it is
    still evidence, and it must not be lumped in with having no read path."""
    from fm9.adapter import Capabilities, ReadPath
    tonex = Capabilities(read_path=ReadPath.OBSERVED, split_transport=True,
                         verifies_writes=True)
    assert tonex.can_verify
    assert ReadPath.NONE < tonex.read_path < ReadPath.DEVICE


def test_ears_outrank_every_read_path():
    """Invariant 4, made comparable rather than merely stated."""
    from fm9.adapter import ReadPath
    assert ReadPath.EARS > ReadPath.DEVICE > ReadPath.OBSERVED > ReadPath.NONE


def test_a_mixed_rig_reports_its_weakest_link():
    """A multi-device 'done' is only as strong as the weakest device, so the
    rig's rank is a min() and never an average."""
    from fm9.adapter import Capabilities, ReadPath
    from fm9.device import FM9
    tonex = Capabilities(read_path=ReadPath.OBSERVED, verifies_writes=True)
    switcher = Capabilities()                      # nothing declared yet
    rig = [FM9.CAPABILITIES, tonex, switcher]
    assert min(c.read_path for c in rig) is ReadPath.NONE
    assert not all(c.can_verify for c in rig)


def test_recipe_replays_clean_in_sim():
    """The published recipe must validate and apply end to end on the sim,
    and recipes may never contain store actions."""
    import json, subprocess, sys, os
    env = dict(os.environ, TONECOMMAND_SIM="1")
    r = subprocess.run([sys.executable, "tools/replay_recipe.py",
                        "recipes/goodbye-yesterday-rock-intro.json", "--apply"],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "EAR CHECKLIST" in r.stdout
    rec = json.load(open("recipes/goodbye-yesterday-rock-intro.json"))
    assert all(a["kind"] != "store" for a in rec["actions"])


def test_zero_ordinal_set_actually_lands():
    """Ordinal 0 via the discrete path is the zeroed-GET no-op; the device
    layer must route it through a continuous 0.0 write instead (found by
    recipe replay; the class of bug that silently no-ops type changes)."""
    from fm9.sim import SimFM9
    import time
    fm9 = SimFM9(); fm9.status_dump()
    spec = fm9.reg.spec("REVERB", 10)
    fm9.set_param_ordinal(spec, 5); time.sleep(0.12)
    fm9.set_param_ordinal(spec, 0); time.sleep(0.12)
    assert fm9.get_param_wire(spec) == 0


def test_gig_mode_locks_out_everything_but_scenes(monkeypatch):
    from fastapi.testclient import TestClient
    import server
    from fm9.sim import SimFM9
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    client = TestClient(server.app)
    assert client.post("/api/gig", json={"on": True}).json()["gig_mode"]
    r = client.post("/api/apply", json={"actions": [
        {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE", "value": 5}]})
    assert r.status_code == 423 and "GIG MODE" in r.json()["error"]
    r = client.post("/api/apply", json={"actions": [{"kind": "set_scene", "value": 2}]})
    assert r.status_code == 200
    client.post("/api/gig", json={"on": False})


def test_never_brick_guard_blocks_unknown_functions():
    """Hard rule: unknown/undecoded function ids are structurally
    unsendable. The tool must be INCAPABLE of reaching firmware or
    bootloader surfaces on any device."""
    import pytest
    from fm9.sim import SimFM9
    from fm9 import protocol as p
    fm9 = SimFM9()
    evil = p.envelope(0x40, [0x00, 0x00])       # undecoded function id
    with pytest.raises(PermissionError, match="NEVER-BRICK"):
        fm9._send(evil)
    fm9._send(p.build_get_scene())               # decoded surface still works

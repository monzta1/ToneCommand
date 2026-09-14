"""The contract stopped being decorative (#109).

What went wrong: ToneCommand declared a `DeviceAdapter` Protocol and a
`Capabilities` mechanism whose whole purpose was to let a device say what it
cannot do, and then never consulted either at runtime. `server.py` did not
import `Capabilities` at all. `conformance()` checked the FM9 against the
contract while `SimFM9` was a factory returning a real FM9, so the contract had
one implementation reached by two routes and passing proved self-consistency
rather than portability.

What it cost: adapter #2 could not be written. A contributor with a HeadRush
(#33) would have conformed to a Protocol nothing consumed, proving nothing, and
would have discovered the contract's real shape only by hitting it.

These tests are the declaration half. Enforcing the gates at every call site,
and auditing the 72 broad `except Exception` blocks that would swallow a
capability decline, is #111.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from fm9 import adapter as A                                      # noqa: E402
from fm9.adapter import (CAPABILITY_PROTOCOLS, Capabilities,      # noqa: E402
                         DeviceAdapter, SceneSlotState, conformance)
from fm9.device import FM9                                        # noqa: E402
from stub_device import StubDevice                                # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER = ROOT / "server.py"


# --- how the handle is reached, derived rather than hand-listed -----------

def _handle_names(tree) -> dict[str, list[int]]:
    """Every name reached on the device handle, by AST rather than by grep.

    A text match on `fm9.` also catches the `fm9` PACKAGE in import lines and
    inflates the count; an AST walk that matches only a bare `fm9` name misses
    `get_fm9().firmware_label()` and `_fm9.close()`. Both mistakes were made
    while measuring this ticket, so the walk is pinned here instead.
    """
    def is_handle(node) -> bool:
        if isinstance(node, ast.Name) and node.id in ("fm9", "_fm9"):
            return True
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("get_fm9", "get_device"))

    found: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and is_handle(node.value):
            found.setdefault(node.attr, []).append(node.lineno)
    return found


def _server_tree():
    return ast.parse(SERVER.read_text())


def _protocol_members(proto) -> set[str]:
    return set(proto.__protocol_attrs__)


# Methods that stay FM9-only, each with the reason it is not device-general.
# Widening this is a visible diff in this file, which is the point.
FM9_ONLY = {
    "get_param_wire": (
        "returns a raw wire16 value and is not the inverse of "
        "set_param_ordinal, which writes a discrete roster index. Per #33 the "
        "HeadRush publishes real-unit ranges with no wire encoding at all, so "
        "requiring this would force adapter #2 to fake one."),
    "set_tempo": (
        "a global tempo is a Fractal concept here. Promoting it would force a "
        "device without one to invent it, which is the harm avoided for "
        "get_param_wire."),
    "_send": (
        "SysEx transport. Reached only from api_moddebug, behind "
        "TONECOMMAND_DEBUG=1, which is not part of the product surface."),
    "_drain": (
        "SysEx transport. Same debug-only endpoint as _send."),
    "read_grid": (
        "returns GridCell: row, col and a cable_in_mask. On a rig device the "
        "row is always 0, there is no mask, and topology is a scalar that is "
        "not per-cell at all. The contract must not define position's "
        "structure; see Topology and ChainEditing."),
    "splice_block": (
        "not a capability, a workaround. Splice exists because real FM9 "
        "presets keep no free pass-through cell before the amp and a cable "
        "only reaches the next column. Neither holds elsewhere, where "
        "inserting a block is place_block(slot)."),
    "plan_splice": (
        "the cost estimate for splice_block, and meaningless without it."),
    "find_donor_slot": (
        "cloning a proven binding is an FM9 remedy for FM9 bindings coming "
        "out reversed or dead. A device without that failure has no donor."),
}

# The one function allowed to touch private device internals at all.
PRIVATE_ACCESS_ALLOWED_IN = "api_moddebug"


def test_every_method_a_route_calls_has_exactly_one_documented_home():
    """A route could call anything on the handle and nothing noticed.

    24 of the 34 names routes reached were absent from the contract, three of
    them private. An adapter written against the contract would have satisfied
    it and still failed on the first request, because the contract described a
    fraction of what the application actually used.
    """
    reached = set(_handle_names(_server_tree()))

    contract = _protocol_members(DeviceAdapter)
    sub_protocol: dict[str, str] = {}
    for _label, _gate, proto in CAPABILITY_PROTOCOLS:
        for name in _protocol_members(proto):
            assert name not in contract, (
                f"{name} is on both DeviceAdapter and {proto.__name__}; a name "
                f"must have exactly one home")
            assert name not in sub_protocol, (
                f"{name} is on both {sub_protocol[name]} and {proto.__name__}")
            sub_protocol[name] = proto.__name__

    homed = contract | set(sub_protocol) | set(FM9_ONLY)
    orphans = reached - homed
    assert not orphans, (
        f"these names are reached on the device handle but live in no "
        f"documented home: {sorted(orphans)}")

    # Every FM9-only entry must carry a real reason, not a placeholder.
    for name, why in FM9_ONLY.items():
        assert len(why) > 40, f"{name} needs a written reason, not a stub"


def test_routes_do_not_reach_into_private_device_methods():
    """`fm9._channels.get(...)` in the /api/state poll path was a private
    attribute reached THROUGH, not a private method called, so a check looking
    for `fm9._name(...)` call patterns would have missed it entirely."""
    tree = _server_tree()
    private = {n: lines for n, lines in _handle_names(tree).items()
               if n.startswith("_")}

    allowed_span = None
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == PRIVATE_ACCESS_ALLOWED_IN):
            allowed_span = (node.lineno, node.end_lineno)
    assert allowed_span, f"{PRIVATE_ACCESS_ALLOWED_IN} not found; update the allowlist"

    stray = {n: [ln for ln in lines
                 if not allowed_span[0] <= ln <= allowed_span[1]]
             for n, lines in private.items()}
    stray = {n: lines for n, lines in stray.items() if lines}
    assert not stray, (
        f"private device access outside {PRIVATE_ACCESS_ALLOWED_IN}: {stray}")


def test_get_device_returns_the_contract_type_not_the_fm9_class():
    """The accessor and every annotation named the concrete class, so the
    indirection existed in name only: nothing could be substituted for it."""
    tree = _server_tree()
    offenders = []
    for node in ast.walk(tree):
        ann = getattr(node, "annotation", None)
        if ann is not None and "FM9" in ast.dump(ann):
            offenders.append(node.lineno)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None and "FM9" in ast.dump(node.returns):
                offenders.append(node.lineno)
    assert not offenders, (
        f"server.py still names FM9 as a type at lines {sorted(set(offenders))}; "
        f"this includes the module-level _fm9 global, not only parameters")

    import typing

    import server
    # server.py uses `from __future__ import annotations`, so the annotation is
    # a string until it is resolved. Resolving it is the stronger check anyway:
    # it proves the name actually binds to the Protocol, not just that the
    # right word was typed.
    assert typing.get_type_hints(server.get_fm9)["return"] is DeviceAdapter


# --- the contract proves portability, in both directions ------------------

def test_a_non_fm9_implementation_satisfies_the_contract_and_conformance_certifies_it():
    """`conformance()` could only ever compare the FM9 with itself.

    SimFM9 is a factory returning a real FM9, so a passing result said the FM9
    is consistent with a contract derived from the FM9. The first real drift it
    caught was found by hand, not by the check: the contract declared
    select_preset(number) while the implementation took (preset).
    """
    stub = StubDevice()
    assert conformance(stub) == []
    assert isinstance(stub, DeviceAdapter)
    assert not isinstance(stub, FM9), "the second implementation must not be an FM9"
    assert FM9 not in type(stub).__mro__

    caps = stub.capabilities()
    opted_in = [lbl for lbl, gate, _ in CAPABILITY_PROTOCOLS if gate(caps)]
    declined = [lbl for lbl, gate, _ in CAPABILITY_PROTOCOLS if not gate(caps)]
    assert opted_in, "a stub that opts into nothing does not exercise the split"
    assert declined, "a stub that declines nothing does not exercise the split"

    # Declining is structural, not a promise: the methods are simply absent.
    for label, gate, proto in CAPABILITY_PROTOCOLS:
        if not gate(caps):
            missing = [m for m in _protocol_members(proto)
                       if not hasattr(stub, m)]
            assert missing, (
                f"{label} is declined but every {proto.__name__} member is "
                f"present, so the decline proves nothing")


def test_conformance_rejects_a_stub_whose_signature_drifted():
    """Without this, a conformance() that always returned [] would satisfy the
    positive test undetected. The contract has drifted exactly this way once
    already."""
    class Drifted(StubDevice):
        def select_preset(self, number: int):      # contract says `preset`
            return number

    problems = conformance(Drifted())
    assert problems, "drifted signature was accepted"
    assert any("select_preset" in p for p in problems)


def test_conformance_rejects_a_capability_declared_true_without_its_sub_protocol():
    """Declaring a capability the device cannot honour is the same dishonesty
    the Capabilities mechanism was built to prevent, and it would otherwise
    surface only when a user tried it."""
    class Liar(StubDevice):
        CAPABILITIES = Capabilities(
            read_path=Capabilities().read_path,
            can_rename=True,          # claimed
            # Claimed as CONSTRUCTED, which promises arbitrary cabling, while
            # implementing none of ChainWiring.
            topology=A.Topology.CONSTRUCTED,
        )

        rename_preset = None
        rename_scene = None

    problems = conformance(Liar())
    assert problems, "a capability declared True with no implementation passed"
    assert any(p.startswith("topology==CONSTRUCTED:") for p in problems), problems


def test_promoted_methods_and_sub_protocols_are_declared_and_satisfied():
    """Five asymmetries in the contract, each of which let an adapter be
    written that could not do what the application already required of it."""
    promoted = {"get_param_display", "scan_slots", "set_params_batch",
                "scene_name", "firmware_label"}
    contract = _protocol_members(DeviceAdapter)
    assert promoted <= contract, f"not promoted: {sorted(promoted - contract)}"

    # get_param_wire must NOT be on the contract; see FM9_ONLY for why.
    assert "get_param_wire" not in contract

    names = [p.__name__ for _, _, p in CAPABILITY_PROTOCOLS]
    assert names == ["ChainEditing", "TopologySelection", "ChainWiring",
                     "Modifiers", "FileInstall", "Renaming", "SceneSlots"]

    # Splice and its helpers are in NO sub-Protocol, at any flag level.
    everywhere = set().union(*(_protocol_members(p) for _, _, p in CAPABILITY_PROTOCOLS))
    for name in ("splice_block", "plan_splice", "find_donor_slot", "read_grid"):
        assert name not in everywhere and name not in contract, (
            f"{name} is in the contract; it is an FM9 workaround, and behind a "
            f"flag every future adapter must answer a question it does not have")

    # Every gate is a live predicate over a real Capabilities object.
    caps = Capabilities()
    for label, gate, _ in CAPABILITY_PROTOCOLS:
        assert gate(caps) is False or gate(caps) is True, f"{label} is not a predicate"


def test_chain_control_is_ranked_not_a_boolean():
    """`edits_chain: bool` was true for both devices while describing
    operations that share almost nothing, which is the exact `has_scenes: bool`
    defect this ticket fixes for scenes.

    Measured by @bschmalz81401 on a HeadRush Core (#109): there are no cables
    on that device at all. Fourteen linear slots, and topology is one integer
    chosen from ten prebuilt routings. Both devices can put a block somewhere;
    only one can decide what connects to what.
    """
    assert [t.name for t in A.Topology] == ["FIXED", "SELECTED", "CONSTRUCTED"]
    assert A.Topology.FIXED < A.Topology.SELECTED < A.Topology.CONSTRUCTED
    assert not hasattr(Capabilities(), "edits_chain"), "the boolean survived"

    # The FM9 draws cables; the stub picks from a list. Both edit the chain,
    # and a single boolean could not have told a caller which world it is in.
    assert FM9.CAPABILITIES.topology is A.Topology.CONSTRUCTED
    stub = StubDevice()
    assert stub.capabilities().topology is A.Topology.SELECTED

    # connect_cells is ABSENT below CONSTRUCTED, not present and refusing:
    # the primitive does not exist on a device that chooses prebuilt routings.
    assert isinstance(FM9, type) and hasattr(FM9, "connect_cells")
    assert not isinstance(stub, A.ChainWiring)

    # A SELECTED device can enumerate, name and choose. It must NOT promise to
    # describe: the unit publishes the routing names and never their shapes.
    assert len(stub.topologies()) == 10
    assert stub.select_topology(3)[1] == "SPS-3"
    assert stub.current_topology() == (3, "SPS-3")
    assert "describe_topology" not in _protocol_members(A.TopologySelection)

    # Ranked for the same reason ReadPath is: min() gives the weakest link.
    assert min(c.topology for c in (FM9.CAPABILITIES, stub.capabilities())) \
        is A.Topology.SELECTED


def test_scene_state_is_tri_state_and_slots_are_addressed_by_name():
    """`has_scenes: bool` was true for both devices and described almost
    nothing they share.

    Measured on HeadRush hardware (#33): a slot's state is tri-state, and
    NO_CHANGE is what makes scenes composable. A boolean model has to invent
    "absent means no change", which loses the difference between a slot nobody
    touched and one deliberately left alone.
    """
    assert {s.name for s in SceneSlotState} == {"NO_CHANGE", "OFF", "ON"}

    stub = StubDevice()
    assert stub.capabilities().composable_scene_slots

    stub.set_scene_slot(2, "Drive 1", SceneSlotState.ON)
    stub.set_scene_slot(2, "Delay 1", SceneSlotState.NO_CHANGE)
    slots = stub.scene_slots(2)

    # Addressed by name: a reorder cannot re-point a scene at another block.
    assert slots["Drive 1"] is SceneSlotState.ON
    # NO_CHANGE is recorded, and is NOT the same as absent.
    assert slots["Delay 1"] is SceneSlotState.NO_CHANGE
    assert "Reverb 1" not in slots

    # The FM9's honest answer is to decline, not to swallow a NO_CHANGE write.
    assert FM9.CAPABILITIES.composable_scene_slots is False
    for member in _protocol_members(A.SceneSlots):
        assert not hasattr(FM9, member), (
            f"FM9 declares composable_scene_slots False but implements "
            f"{member}; declining must be structural")

    # The two flags that used to be one, and the one that was misnamed.
    caps = Capabilities()
    assert hasattr(caps, "reads_slot_names") and hasattr(caps, "reads_slot_state")
    assert hasattr(caps, "observes_foreign_writes")
    assert not hasattr(caps, "reads_by_slot"), "the split flag is still present"
    assert not hasattr(caps, "split_transport"), "the mechanism name survived"


def test_set_tempo_action_still_reports_what_it_reported_before():
    """The tempo write is the one production call site this ticket converts
    from `fm9._send` to a public method.

    It reports ok:True without reading anything back, unlike every other write
    in run_action. That is #110 and is deliberately NOT fixed here; this pins
    the current output so converting the call site cannot absorb that fix by
    accident, in either direction.
    """
    import server
    from fm9.sim import SimFM9
    from fm9.registry import Registry

    dev = SimFM9(Registry())
    sent: list[int] = []
    dev.set_tempo = lambda bpm: sent.append(int(bpm))

    got = server.run_action(dev, server.Action(kind="set_tempo", value=120))
    assert sent == [120], "the action no longer reaches the device"
    assert got["ok"] is True
    assert got["detail"] == "tempo 120 bpm sent"


def test_changelog_entry_exists_and_touched_files_have_no_em_dash():
    """Docs drift silently: ARCHITECTURE.md described a server.py less than
    half the size of the real one."""
    changelog = (ROOT / "CHANGELOG.md").read_text()
    unreleased = changelog.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "device handle" in unreleased.lower() or "contract" in unreleased.lower(), (
        "no Unreleased changelog entry for this work")

    architecture = (ROOT / "ARCHITECTURE.md").read_text()
    assert "2,470 lines and 46 routes" not in architecture, (
        "ARCHITECTURE.md still states the stale server.py size")
    real_lines = len(SERVER.read_text().splitlines())
    assert f"{real_lines:,} lines" in architecture, (
        f"ARCHITECTURE.md should state the measured {real_lines:,} lines")

    # Built from its code point so this file does not trip its own check.
    em_dash = chr(0x2014)
    for rel in ("fm9/adapter.py", "fm9/device.py", "server.py",
                "tests/test_device_handle.py", "tests/stub_device.py",
                "CHANGELOG.md", "ARCHITECTURE.md"):
        text = (ROOT / rel).read_text()
        assert em_dash not in text, f"em dash in {rel}"

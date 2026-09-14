"""The device adapter contract (ARCHITECTURE.md, step 1 of the migration).

Any device family ToneCommand supports satisfies this Protocol. New devices
(HeadRush, ToneX, Kemper, your fridge) implement the same surface and
inherit the invariant safety layer above it.

WHAT "CERTIFIED" MEANS HERE, AND WHAT IT DOES NOT. `conformance()` checks the
FM9 against this contract by signature, and a test pins it. But SimFM9 is a
factory returning a real FM9 on simulated ports, so it is the same class by a
second route, not a second implementation. Until #109 the contract therefore
had exactly one implementation, and passing proved self-consistency rather than
portability. #109 added a second, structurally distinct one (tests/, no
inheritance from FM9, in-memory state) that opts into some capability
sub-Protocols and declines others, so the split is exercised rather than
assumed. ARCHITECTURE.md step 4 remains where a REAL adapter stresses this, and
the rule there is still to fix the CONTRACT, not the adapter. The first evidence arrived early, from the FM9 itself: this file
declared select_preset(number) and set_scene(scene) while the implementation
took (preset) and (scene_1based), so a second adapter written to these names
and called by keyword would have broken. The contract was the wrong one, as
it already said set_channel(channel_0based).

This is a typing.Protocol, not a base class: existing device code is not
forced to inherit anything, it just has to actually provide the surface.

Capabilities (added 2026-08-24, ARCHITECTURE.md step 4) exist because the
second real device disagreed with the first about what it can answer. The
contract used to assume every method was answerable everywhere: status_dump
promised "an honest read path" and set_param_display promised a verified
write. On a device without either, an adapter has two choices, and only one
of them is honest. It can return plausible values from locally tracked state,
which silently converts "I sent this" into "I verified this" and is exactly
the failure the read-back invariant exists to prevent. Or it can say what it
cannot do, and let the layer above degrade openly. Capabilities make the
second option expressible.

Declaring is deny-by-default, like the send guard: a device that says nothing
is treated as answering nothing, so an unfinished adapter under-promises
rather than over-promises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any, Protocol, runtime_checkable


class ReadPath(IntEnum):
    """How a device's state can be known, ranked by honesty.

    Invariant 4 already says read paths are ranked by how well they reflect
    audible reality, and that ears outrank reads for anything audible. This
    is that ranking made comparable, so `min()` over a plan's devices gives
    the weakest link rather than an average.

    NONE is the dangerous one and is therefore the default: it means the only
    "state" available is what we believe we sent, which is not evidence.
    """

    NONE = 0        # no read path; local tracking only, must be labeled unverified
    OBSERVED = 1    # a separate channel reports state (ToneX: MIDI out, serial in)
    DEVICE = 2      # the device answers on the channel it is written on (FM9 SysEx)
    EARS = 3        # a human confirmed it, and for anything audible this wins


class Topology(IntEnum):
    """How much say a caller has over the shape of the signal chain.

    Ranked, not boolean, for the same reason `ReadPath` is: `min()` across a
    plan's devices gives the weakest link. `edits_chain: bool` was true for the
    FM9 and for a HeadRush while describing operations that share almost
    nothing, which is precisely the `has_scenes: bool` defect #109 fixes for
    scenes. A caller reading True learned nothing it could act on.

    Measured by @bschmalz81401 on a HeadRush Core, fw 5.1.0.2a63755 (#109):
    there are no cables on that device at all. The chain is fourteen linear
    slots and topology is ONE integer property chosen from ten prebuilt
    routings. Writing all ten and reading the chain back showed every slot's
    state byte-identical under each, so the device publishes the routing NAMES
    but never their shapes.

    That is why SELECTED promises enumerate, name and choose, and deliberately
    does NOT promise to describe. There is no honest implementation of "how is
    this topology shaped" on a device that cannot say.
    """

    FIXED = 0        # no control; the chain is what it is
    SELECTED = 1     # choose from an enumerated set (HeadRush: 10 routings)
    CONSTRUCTED = 2  # arbitrary connections the caller draws (FM9: cables)


class SceneSlotState(Enum):
    """What one named slot does in one scene. Three states, not two.

    Measured on HeadRush hardware by @bschmalz81401 (#33, 2026-09-07).
    NO_CHANGE is not a tidier spelling of "absent": it is what makes scenes
    composable. A scene that says nothing about a slot leaves whatever the
    last one did, so a boolean model has to invent "absent means no change"
    and immediately loses the difference between a slot nobody touched and
    one deliberately left alone. Those are different intentions.

    Slots are addressed BY NAME, never by index. On a device whose chain can
    be reordered, matching by position re-points a scene at the wrong block
    the moment anyone moves anything.
    """

    NO_CHANGE = "no_change"
    OFF = "off"
    ON = "on"


@dataclass(frozen=True)
class Capabilities:
    """What a device can actually answer, declared rather than assumed.

    Measured examples, both from real hardware rather than datasheets:

    FM9         read_path=DEVICE, observes_foreign_writes=False,
                reads_slot_names=True, reads_slot_state=True,
                verifies_writes=True, has_scenes=True, stores_presets=True,
                topology=Topology.CONSTRUCTED, has_modifiers=True,
                installs_files=True, can_rename=True,
                composable_scene_slots=False

    ToneX Pedal read_path=OBSERVED, observes_foreign_writes=True,
                reads_slot_names=False, verifies_writes=True,
                has_scenes=False, stores_presets=False
                (control goes out over MIDI, state comes back on a CDC serial
                port, and the pedal has no scene concept at all; see #23)

    The FM9's composable_scene_slots is False on measurement, not on omission:
    it stores bypass and channel per scene, so every scene fully determines
    every block and there is no wire encoding for "leave this slot alone".
    Declining is the honest answer. Claiming the capability and quietly
    swallowing a NO_CHANGE write would be precisely the dishonesty this whole
    mechanism exists to prevent.

    `observes_foreign_writes` is the shape the contract could not express
    before. It was called `split_transport` until #109, which named the
    mechanism (read and write on different channels) rather than the thing
    callers actually need to know: that something outside this tool can change
    the device under us, for instance a switcher changing the preset. #33
    showed why the mechanism name was wrong, with a device that is HTTP both
    ways and so had the flag False while having exactly the property, over a
    websocket.

    `reads_by_slot` split into two flags for the same reason. It was doing two
    jobs, and on a HeadRush the answers differ: rig NAMES list without loading
    anything, while a rig's actual chain state cannot be read until it is
    loaded. One flag could only lie about one of them.

    The five gate flags below pair one-to-one with the capability
    sub-Protocols further down. A device declaring one True must implement the
    matching sub-Protocol, and `conformance()` checks that rather than trusting
    it. Declaring False is the honest way to say "this device has no such
    concept", and costs nothing: the methods simply are not required.
    """

    read_path: ReadPath = ReadPath.NONE
    observes_foreign_writes: bool = False
    reads_slot_names: bool = False
    reads_slot_state: bool = False
    verifies_writes: bool = False
    has_scenes: bool = False
    stores_presets: bool = False

    # gates, one per capability sub-Protocol
    topology: Topology = Topology.FIXED
    has_modifiers: bool = False
    installs_files: bool = False
    can_rename: bool = False
    composable_scene_slots: bool = False

    @property
    def can_verify(self) -> bool:
        """Whether a write on this device can be backed by evidence."""
        return self.read_path >= ReadPath.OBSERVED and self.verifies_writes

    def why_unverified(self) -> str:
        """Plain reason a claim cannot be made, for the layer above to relay
        verbatim. Never phrase an absent read path as a passing check."""
        if self.read_path == ReadPath.NONE:
            return ("this device has no read path, so its state is only what "
                    "we believe we sent")
        if not self.verifies_writes:
            return ("this device reports state but does not confirm individual "
                    "writes")
        return ""


# A device that has declared nothing. Answers nothing, verifies nothing.
UNDECLARED = Capabilities()


@runtime_checkable
class DeviceAdapter(Protocol):
    """The swappable layer. Everything above this is device-blind."""

    def capabilities(self) -> Capabilities:
        """What this device can actually answer. Adapters that do not
        override this are treated as UNDECLARED, which is the safe end."""
        ...

    def status_dump(self) -> Any:
        """Current blocks/bypass/channel state from an honest read path."""
        ...

    def current_preset(self) -> Any:
        """(number, name) of the active preset, or None if unreachable."""
        ...

    def select_preset(self, preset: int) -> Any: ...

    def set_scene(self, scene_1based: int) -> Any: ...

    def set_bypass(self, effect_id: int, bypassed: bool) -> Any: ...

    def set_channel(self, effect_id: int, channel_0based: int) -> Any: ...

    def set_param_display(self, spec: Any, display_value: float) -> Any:
        """Verified write: settle, read back, report before/after."""
        ...

    def set_param_ordinal(self, spec: Any, ordinal: int) -> Any: ...

    def bulk_read(self, effect_id: int, timeout: float = 1.5) -> Any:
        """Every value on one block in a single read.

        `timeout` is part of the contract because a bulk read is the slowest
        thing on the wire and the right wait is device-specific: the FM9's
        default was raised to 1.5 s after a 0.6 s wait TRUNCATED a reply and
        produced a diff that looked like real movement (issue #56). An adapter
        may ignore it, but it must accept it, or a caller that knows its
        device needs longer has no way to say so.
        """
        ...

    def slot_name(self, preset: int) -> Any:
        """A slot's STORED name read by number, without selecting it and
        without disturbing the loaded preset (PR #19). Any device with
        addressable preset slots can answer this."""
        ...

    def is_slot_empty(self, preset: int) -> Any:
        """True/False from the device's own empty marker, or None if the
        slot did not answer. Gate for from-scratch builds."""
        ...

    def store_preset(self, slot: int) -> Any:
        """Whitelisted, confirmation-gated persistence. Must refuse
        non-whitelisted targets."""
        ...

    # --- promoted in #109, because their absence was an asymmetry ----------

    def get_param_display(self, spec: Any) -> Any:
        """One parameter's value in the units a human reads.

        The contract declared `set_param_display` and no getter, so an adapter
        could be written that writes a value it cannot read back. Promoted in
        #109. Deliberately the DISPLAY form and not the wire form: what a value
        means is device-general, how it is encoded is not.
        """
        ...

    def scan_slots(self, start: int = 0, end: int = 511) -> Any:
        """Every stored slot NAME in a range, without disturbing the device.

        The bulk form of `slot_name`, which the contract already had. Gated in
        spirit by `reads_slot_names`: per #33 a device may be able to list
        names while being unable to read what is inside a rig without loading
        it, which is why that flag split from `reads_by_slot`.
        """
        ...

    def set_params_batch(self, items: Any) -> Any:
        """Write several params on one block, then verify them all at once.

        A round-trip optimisation, not a new power: N writes then ONE
        settle-and-read that checks them all, rather than N of each. The
        never-write-blind guarantee is unchanged. An adapter with nothing to
        optimise may implement this by looping over `set_param_display`.
        """
        ...

    def scene_name(self, scene: Any = None) -> Any:
        """A scene's stored name. The contract could select a scene and name a
        slot, but never read back what a scene is called."""
        ...

    def firmware_label(self) -> Any:
        """The firmware as the DEVICE writes it, in its own vendor's
        convention.

        For display and for recording what a result was produced on. It is
        deliberately NOT machine-parseable: the FM9 writes "12.00", another
        device will write something else entirely, and any adapter that tried
        to impose a common shape would be inventing one. Compare version
        strings across devices at your peril.
        """
        ...

    def close(self) -> Any: ...



# --- capability sub-Protocols --------------------------------------------
#
# These exist because typing.Protocol cannot express a conditionally required
# member. Putting chain editing on DeviceAdapter would force every adapter to
# implement a grid it may not have, and the whole point of Capabilities is to
# let a device say what it cannot do rather than fake it. So each group of
# methods lives behind one flag, an adapter opts in per group, and
# conformance() checks only the groups it claimed.


@runtime_checkable
class ChainEditing(Protocol):
    """Putting a block somewhere and moving it. Gate: topology >= SELECTED.

    Only the two operations that map cleanly onto a device with no cables.
    `splice_block`, `plan_splice` and `find_donor_slot` are NOT here and are
    not in the contract at any flag level: splice is not a capability, it is a
    workaround for two FM9 facts (real presets keep no free pass-through cell
    before the amp, and a cable only ever reaches the next column). Neither
    holds on a rig device, where a blank slot is genuinely blank and inserting
    a block is `place_block(slot)`. Behind a flag they would oblige every
    future adapter to answer a question it does not have, and the only honest
    answers are "not applicable" or a lie (#109, @bschmalz81401).

    Position is deliberately opaque. FM9 positions are (row, col); HeadRush
    positions are an int in 1..14; a third device will be something else. What
    every device can honestly promise is that positions are enumerable,
    comparable and addressable. Anything richer is one device's geometry
    wearing the contract's name.
    """

    def place_block(self, row_1based: int, col_1based: int, effect_id: int) -> Any: ...
    def reorder_block(self, moving_eid: int, ref_eid: int) -> Any: ...


@runtime_checkable
class TopologySelection(Protocol):
    """Choosing a whole prebuilt chain shape. Gate: topology == SELECTED.

    Enumerate, name, choose. Never describe: see `Topology`.
    """

    def topologies(self) -> Any:
        """Every topology this device offers, in its own order."""
        ...

    def current_topology(self) -> Any:
        """Which one is active now."""
        ...

    def select_topology(self, index: int) -> Any:
        """Choose one by its index in `topologies()`."""
        ...


@runtime_checkable
class ChainWiring(Protocol):
    """Drawing connections the caller decides. Gate: topology == CONSTRUCTED.

    Absent below CONSTRUCTED rather than present and refusing, because on a
    device that picks from prebuilt routings the primitive does not exist at
    all. It is not a differently shaped connect; there is nothing to connect.
    """

    def connect_cells(self, src_row: int, src_col: int, dest_row: int) -> Any: ...


@runtime_checkable
class Modifiers(Protocol):
    """Pedal and controller bindings. Gate: `has_modifiers`.

    `find_donor_slot` was moved here from ChainEditing, and then out of the
    contract entirely: cloning a proven binding is an FM9 remedy for FM9
    bindings coming out reversed or dead (finding 12), and a device without
    that failure has no donor to find. It stays reachable through the FM9
    adapter.
    """

    def bind_modifier(self, slot_1based: int, target_effect_id: int,
                      target_param_id: int, source_ordinal: int) -> Any:
        """Bind a controller to one parameter. All four are required:
        which slot, which block, which parameter on it, and which source
        drives it. A contract that named only the first two would let an
        adapter be written that cannot say what it is binding to what.
        """
        ...

    def read_modifier(self, slot_1based: int) -> Any: ...
    def clear_modifier(self, slot_1based: int) -> Any: ...


@runtime_checkable
class FileInstall(Protocol):
    """Writing preset and cabinet files onto the device. Gate:
    `installs_files`."""

    def install_preset(self, raw: bytes, slot: int, name: Any = None) -> Any: ...
    def install_user_cab_at(self, raw: bytes, bank: int, number: int) -> Any: ...
    def read_user_cab_addr(self, idx: int, tag: int, timeout: float = 4.0) -> Any: ...


@runtime_checkable
class Renaming(Protocol):
    """Renaming what is already stored. Gate: `can_rename`."""

    def rename_preset(self, name: str) -> Any: ...
    def rename_scene(self, scene_1based: int, name: str) -> Any: ...


@runtime_checkable
class SceneSlots(Protocol):
    """Composable per-slot scene state. Gate: `composable_scene_slots`.

    The capability the FM9 does not have. A device here can say, for one named
    slot in one scene, ON, OFF, or NO_CHANGE, and NO_CHANGE genuinely means
    "whatever the last scene did" rather than "unset". Slots are addressed by
    name so a chain reorder cannot silently re-point a scene at another block.

    A device that fully determines every block in every scene, as the FM9 does,
    declares the flag False and implements none of this. That is the honest
    answer and it costs nothing.
    """

    def scene_slots(self, scene_1based: int) -> Any:
        """Mapping of slot NAME to SceneSlotState for one scene."""
        ...

    def set_scene_slot(self, scene_1based: int, slot_name: str,
                       state: SceneSlotState) -> Any:
        """Set one named slot's state in one scene, NO_CHANGE included."""
        ...


# Gate -> the sub-Protocol it promises. A predicate rather than a flag name,
# because topology is ranked: ">= SELECTED" and "== CONSTRUCTED" are different
# promises and a boolean could not tell them apart. Declaring a gate without
# satisfying its Protocol is the lie conformance() is here to catch.
CAPABILITY_PROTOCOLS = (
    ("topology>=SELECTED", lambda c: c.topology >= Topology.SELECTED, ChainEditing),
    ("topology==SELECTED", lambda c: c.topology == Topology.SELECTED, TopologySelection),
    ("topology==CONSTRUCTED", lambda c: c.topology == Topology.CONSTRUCTED, ChainWiring),
    ("has_modifiers", lambda c: c.has_modifiers, Modifiers),
    ("installs_files", lambda c: c.installs_files, FileInstall),
    ("can_rename", lambda c: c.can_rename, Renaming),
    ("composable_scene_slots", lambda c: c.composable_scene_slots, SceneSlots),
)


# --- certification -------------------------------------------------------

def contract_members() -> tuple:
    """Every name DeviceAdapter requires, read off the Protocol itself.

    The certification test used to check a hand-written list of method names,
    which had already drifted: `slot_name` and `is_slot_empty` were in the
    contract and certified against nothing. A list maintained by hand beside
    a contract will always drift, so it is derived here instead.
    """
    return tuple(sorted(DeviceAdapter.__protocol_attrs__))


def _members_of(proto) -> tuple:
    """Every name a Protocol requires, read off the Protocol itself."""
    return tuple(sorted(proto.__protocol_attrs__))


def _signature_problems(impl, proto, label: str) -> list[str]:
    """Where `impl` fails to satisfy one Protocol, by signature not just name.
    Factored out of conformance() in #109 so the capability sub-Protocols are
    checked exactly as strictly as the core contract is."""
    import inspect

    problems: list[str] = []
    for name in _members_of(proto):
        want, got = getattr(proto, name, None), getattr(impl, name, None)
        if got is None:
            problems.append(f"{label}{name}: missing")
            continue
        if not callable(got) and not isinstance(got, property):
            continue                      # a plain attribute satisfies the name
        try:
            wsig = inspect.signature(want.fget if isinstance(want, property) else want)
            gsig = inspect.signature(got.fget if isinstance(got, property) else got)
        except (TypeError, ValueError):
            continue                      # not introspectable; the name is all we get
        need = [q for q in wsig.parameters if q != "self"]
        have = [q for q in gsig.parameters if q != "self"]
        if have[:len(need)] != need:
            problems.append(
                f"{label}{name}: contract takes {tuple(need)}, implementation "
                f"takes {tuple(have)}")
            continue
        for extra in have[len(need):]:
            if gsig.parameters[extra].default is inspect.Parameter.empty:
                problems.append(
                    f"{label}{name}: implementation requires an extra argument "
                    f"{extra!r} the contract does not supply")
    return problems


def conformance(impl) -> list[str]:
    """Where `impl` fails to satisfy the contract. Empty means it conforms.

    Checks SIGNATURES, not just names. `runtime_checkable` only lets
    isinstance() test that an attribute exists, so a class whose set_scene
    takes no scene would still pass isinstance and then fail at the first
    call. That is the whole risk this contract exists to remove, since the
    point of a Protocol is that a device written against it works without
    being tried.

    An implementation may ADD optional parameters (the FM9's bulk_read takes a
    timeout), but it may not rename or drop a required one, because a caller
    written against the contract is entitled to pass them by keyword.

    Since #109 this also checks the CAPABILITY GATES. A device that declares
    `edits_chain=True` must actually satisfy `ChainEditing`; declaring a
    capability it cannot honour is the same dishonesty the whole mechanism was
    built to prevent, and it would otherwise be caught only when a user tried
    it. The reverse is not checked and needs no test: declaring False while
    happening to implement the methods is under-promising, which is the safe
    end, exactly as the deny-by-default rule above says.
    """
    import inspect

    problems = _signature_problems(impl, DeviceAdapter, "")

    # A CLASS can be certified for signatures but not for capabilities: there
    # is no instance to ask, and calling the unbound function would just raise
    # for want of `self`. Certifying a class is an established use here (the
    # FM9 itself is checked that way), so this is a legitimate partial answer
    # rather than a failure.
    if inspect.isclass(impl):
        return problems

    got = getattr(impl, "capabilities", None)
    if not callable(got):
        return problems                   # nothing declared; UNDECLARED is safe
    try:
        caps = got()
    except Exception as exc:              # an adapter that cannot even say
        problems.append(f"capabilities(): raised {exc!r}")   # what it is
        return problems
    if not isinstance(caps, Capabilities):
        # Returning None or some other shape would silently skip every gate
        # below, which is the one loophole this check exists to close.
        problems.append(
            f"capabilities(): returned {type(caps).__name__}, not Capabilities")
        return problems

    for label, gate, proto in CAPABILITY_PROTOCOLS:
        if gate(caps):
            problems += _signature_problems(impl, proto, f"{label}: ")
    return problems

"""The device adapter contract (ARCHITECTURE.md, step 1 of the migration).

Any device family ToneCommand supports satisfies this Protocol. New devices
(HeadRush, ToneX, Kemper, your fridge) implement the same surface and
inherit the invariant safety layer above it.

WHAT "CERTIFIED" MEANS HERE, AND WHAT IT DOES NOT. `conformance()` checks the
FM9 against this contract by signature, and a test pins it. But SimFM9 is a
factory returning a real FM9 on simulated ports, so it is the same class by a
second route, not a second implementation. The contract therefore has exactly
one implementation, and passing proves self-consistency rather than
portability. That is expected at this stage: ARCHITECTURE.md step 4 is where
adapter #2 stresses it, and the rule there is to fix the CONTRACT, not the
adapter. The first evidence arrived early, from the FM9 itself: this file
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
from enum import IntEnum
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


@dataclass(frozen=True)
class Capabilities:
    """What a device can actually answer, declared rather than assumed.

    Measured examples, both from real hardware rather than datasheets:

    FM9         read_path=DEVICE, split_transport=False, reads_by_slot=True,
                verifies_writes=True, has_scenes=True, stores_presets=True

    ToneX Pedal read_path=OBSERVED, split_transport=True, reads_by_slot=False,
                verifies_writes=True, has_scenes=False, stores_presets=False
                (control goes out over MIDI, state comes back on a CDC serial
                port, and the pedal has no scene concept at all; see #23)

    `split_transport` is the shape the contract could not express before: one
    device whose read path and write path are different channels. It matters
    beyond bookkeeping, because a separate read channel can observe writes
    this tool did not make, for instance a switcher changing the preset.
    """

    read_path: ReadPath = ReadPath.NONE
    split_transport: bool = False
    reads_by_slot: bool = False
    verifies_writes: bool = False
    has_scenes: bool = False
    stores_presets: bool = False

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

    def close(self) -> Any: ...


# --- certification -------------------------------------------------------

def contract_members() -> tuple:
    """Every name DeviceAdapter requires, read off the Protocol itself.

    The certification test used to check a hand-written list of method names,
    which had already drifted: `slot_name` and `is_slot_empty` were in the
    contract and certified against nothing. A list maintained by hand beside
    a contract will always drift, so it is derived here instead.
    """
    return tuple(sorted(DeviceAdapter.__protocol_attrs__))


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
    """
    import inspect

    problems: list[str] = []
    for name in contract_members():
        want, got = getattr(DeviceAdapter, name, None), getattr(impl, name, None)
        if got is None:
            problems.append(f"{name}: missing")
            continue
        if not callable(got) and not isinstance(got, property):
            continue                      # a plain attribute satisfies the name
        try:
            wsig = inspect.signature(want.fget if isinstance(want, property) else want)
            gsig = inspect.signature(got.fget if isinstance(got, property) else got)
        except (TypeError, ValueError):
            continue                      # not introspectable; the name is all we get
        need = [p for p in wsig.parameters if p != "self"]
        have = [p for p in gsig.parameters if p != "self"]
        if have[:len(need)] != need:
            problems.append(
                f"{name}: contract takes {tuple(need)}, implementation takes "
                f"{tuple(have)}")
            continue
        for extra in have[len(need):]:
            if gsig.parameters[extra].default is inspect.Parameter.empty:
                problems.append(
                    f"{name}: implementation requires an extra argument "
                    f"{extra!r} the contract does not supply")
    return problems

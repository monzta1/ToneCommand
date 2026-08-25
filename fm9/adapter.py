"""The device adapter contract (ARCHITECTURE.md, step 1 of the migration).

Any device family ToneCommand supports satisfies this Protocol. The FM9
device and its simulator are certified against it by tests; new devices
(HeadRush, ToneX, Kemper, your fridge) implement the same surface and
inherit the invariant safety layer above it.

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

    def select_preset(self, number: int) -> Any: ...

    def set_scene(self, scene: int) -> Any: ...

    def set_bypass(self, effect_id: int, bypassed: bool) -> Any: ...

    def set_channel(self, effect_id: int, channel_0based: int) -> Any: ...

    def set_param_display(self, spec: Any, display_value: float) -> Any:
        """Verified write: settle, read back, report before/after."""
        ...

    def set_param_ordinal(self, spec: Any, ordinal: int) -> Any: ...

    def bulk_read(self, effect_id: int) -> Any: ...

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

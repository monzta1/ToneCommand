"""Invariant 0: this tool must never be able to damage any device.

The guard used to live on the FM9 class, as a frozenset of sendable SysEx
function ids checked inside its `_send`. That protected the FM9 and only the
FM9. When a second device arrived (ToneX, 2026-08-24) it became obvious that
a new adapter inherited nothing at all: the contract in adapter.py has no
send path, so "not policy, architecture" was true of one class rather than of
the system. This module is the lift.

The guarantee is deny by default. A transport constructs a SendGuard with the
set of message kinds that are decoded, hardware-verified, and user-data
scoped, and every outbound message passes `check()` first. A device that
declares nothing can send nothing, so forgetting to write an allowlist fails
closed rather than open.

What must never be reachable on any device: firmware update, bootloader,
flash, and every kind that has not been decoded. Extending an allowlist
requires a hardware-verified decode of the new kind and a documented recovery
path (power cycle plus preset reselect).
"""
from __future__ import annotations

from typing import Callable, Iterable


class BrickGuardRefusal(PermissionError):
    """Raised instead of putting an undeclared message on the wire."""


class SendGuard:
    """Deny-by-default gate that every device transport passes through.

    `kinds` is whatever identifies a message class on that device's wire:
    SysEx function ids on the FM9, mido message type names on a device driven
    by Program and Control Change. The guard does not care which, only that
    the set is explicit and closed.
    """

    def __init__(self, device: str, kinds: Iterable = (),
                 render: Callable[[object], str] = repr,
                 note: str = ""):
        self.device = device
        self.kinds = frozenset(kinds)
        self._render = render
        self.note = note

    def check(self, kind) -> None:
        if kind not in self.kinds:
            raise BrickGuardRefusal(
                f"NEVER-BRICK GUARD: refusing to send {self._render(kind)} to "
                f"{self.device}. Only decoded, user-data-scoped messages may "
                f"reach any device. {self.note}".rstrip() +
                " See ARCHITECTURE.md invariant 0.")

    def permits(self, kind) -> bool:
        """Non-raising form, for reporting what a device can be asked to do."""
        return kind in self.kinds

    def __repr__(self) -> str:
        return f"SendGuard({self.device!r}, {len(self.kinds)} kinds allowed)"


# A transport that has not declared an allowlist. Sends nothing, by
# construction. New adapters get this until they earn something wider, so
# the unsafe state is the one you have to opt into rather than the default.
DENY_ALL = SendGuard("undeclared device", (),
                     note="This transport has not declared an allowlist.")


def sysex_guard(device: str, function_ids: Iterable[int],
                note: str = "") -> SendGuard:
    """Guard for a device addressed by SysEx function id (the FM9 shape)."""
    return SendGuard(device, function_ids,
                     render=lambda fn: f"function 0x{fn:02x}", note=note)


def message_type_guard(device: str, types: Iterable[str],
                       note: str = "") -> SendGuard:
    """Guard for a device driven by MIDI message type (the ToneX shape).

    SysEx is deliberately absent from every allowlist built this way: on an
    undecoded device it is where firmware and bootloader traffic lives.
    """
    return SendGuard(device, types, render=lambda t: f"{t!r}", note=note)

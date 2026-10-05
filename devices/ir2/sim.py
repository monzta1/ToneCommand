"""An in-memory IR-2, so the suite runs with no pedal on the desk.

It models what the unit actually does, INCLUDING the two behaviours that
would otherwise be discovered only on hardware: a value above a parameter's
maximum is clamped rather than refused (found by writing 0x0B to AMP and
reading 0x0A back), and the pedal answers a read of a block with the block's
real length however much was asked for.

It does not pretend about anything undecoded. IR file transfer is absent
here because it is absent from the adapter.
"""
from __future__ import annotations

from . import protocol as p
from . import registry as reg


class SimIR2:
    """Quacks like MidiClient, keeps state in a dict."""

    def __init__(self):
        self.blocks: dict[int, list[int]] = {
            p.SETUP: [0],
            p.SYSTEM: [0, 0, 0, 0, 1, 6, 4, 6, 4, 0, 6, 4],
            p.PATCH: [pa.init for pa in reg.PATCH_PARAMS],
        }
        for slot in range(p.IR_FIRST_SLOT, p.IR_FIRST_SLOT + p.IR_SLOTS):
            self.blocks[p.ir_slot_addr(slot, p.IR_NAME)] = [0x20] * 32
            self.blocks[p.ir_slot_addr(slot, p.IR_SIZE)] = [0] * 4
            self.blocks[p.ir_slot_addr(slot, p.IR_FILE)] = [0] * 128
            # 3,400 words, as the unit holds: 1,632 samples, the quantised
            # tables, then zero padding.
            self.blocks[p.ir_slot_addr(slot, p.IR_DATA)] = [0] * (3400 * 8)
        self.writes: list[tuple[int, list[int]]] = []
        self._events: list[tuple[int, list[int]]] = []
        self.closed = False

    def _base_and_offset(self, addr: int) -> tuple[int, int]:
        for base in sorted(self.blocks, reverse=True):
            if base <= addr < base + len(self.blocks[base]):
                return base, addr - base
        raise KeyError(addr)

    def read(self, addr: int, size: int, timeout: float = 0.0) -> list[int]:
        try:
            base, off = self._base_and_offset(addr)
        except KeyError:
            from .client import IR2NotFound
            raise IR2NotFound(f"the IR-2 did not answer a read of {addr:#010x}.")
        block = self.blocks[base]
        return block[off:off + size] if size else []

    def write(self, addr: int, data: list[int], verify: bool = True) -> list[int]:
        base, off = self._base_and_offset(addr)
        block = self.blocks[base]
        params = {p.PATCH: reg.PATCH_PARAMS, p.SYSTEM: reg.SYSTEM_PARAMS,
                  p.SETUP: reg.SETUP_PARAMS}.get(base, ())
        stored = []
        for i, value in enumerate(data):
            spec = next((s for s in params if s.offset == off + i), None)
            # the hardware clamps rather than refusing (AMP, 0x0B -> 0x0A)
            stored.append(min(value, spec.hi) if spec and spec.nibbles == 1
                          else value)
        block[off:off + len(stored)] = stored
        self.writes.append((addr, list(data)))
        if verify and stored != list(data):
            from .client import VerifyFailed
            raise VerifyFailed(
                f"wrote {' '.join(f'{b:02X}' for b in data)} to {addr:#010x} "
                f"but the IR-2 reports {' '.join(f'{b:02X}' for b in stored)}. "
                "The value was refused or clamped; nothing is being claimed.")
        return list(stored)

    def push(self, addr: int, data: list[int]) -> None:
        """Model a knob turn: the pedal announces it unprompted."""
        base, off = self._base_and_offset(addr)
        self.blocks[base][off:off + len(data)] = list(data)
        self._events.append((addr, list(data)))

    def drain_events(self):
        out, self._events = self._events, []
        return out

    def close(self) -> None:
        self.closed = True

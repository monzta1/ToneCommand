"""The IR-2 over USB MIDI.

Every write is followed by a read of the same address, and a write whose
read-back disagrees raises rather than reporting success. That is the same
rule fm9/device.py follows and the reason this adapter may declare
verifies_writes=True at all.

The pedal also emits DT1 unprompted whenever a knob moves or the footswitch
is pressed. `drain_events` collects those, so a caller can know the player
turned something without polling for it.
"""
from __future__ import annotations

import time

from . import protocol as p

PORT_HINT = "ir-2"
SETTLE = 0.06          # measured: a read this soon after a write is correct
READ_TIMEOUT = 0.6


class IR2NotFound(RuntimeError):
    """One line, written for the person at the rig."""


class VerifyFailed(RuntimeError):
    """A write did not read back. Never downgraded to a warning."""


class MidiClient:
    """Real hardware. `ports=(inp, outp)` injects a simulator instead."""

    def __init__(self, ports=None, hint: str = PORT_HINT):
        if ports is not None:
            self.inp, self.outp = ports
            return
        try:
            import rtmidi
        except ImportError as e:                      # pragma: no cover
            raise IR2NotFound(f"no MIDI binding available: {e}")
        mi, mo = rtmidi.MidiIn(), rtmidi.MidiOut()
        ins = [n for n in mi.get_ports() if hint in n.lower()]
        outs = [n for n in mo.get_ports() if hint in n.lower()]
        if not ins or not outs:
            raise IR2NotFound(
                "no BOSS IR-2 on MIDI; is it plugged in by USB and is the "
                "BOSS IR-2 IR Loader closed? Only one program can hold the "
                "port at a time.")
        mi.open_port(mi.get_ports().index(ins[0]))
        mi.ignore_types(sysex=False, timing=False, active_sense=False)
        mo.open_port(mo.get_ports().index(outs[0]))
        self.inp, self.outp = mi, mo
        self._events: list[tuple[int, list[int]]] = []

    # --- raw ---------------------------------------------------------------

    def _send(self, frame: list[int]) -> None:
        self.outp.send_message(frame)

    def _collect(self, want_addr: int, timeout: float) -> list[int] | None:
        """Wait for a DT1 at `want_addr`. Unsolicited pushes that arrive
        meanwhile are kept, not dropped, so a knob moved mid-read is still
        observed rather than silently lost."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.inp.get_message()
            if not msg:
                time.sleep(0.003)
                continue
            got = p.parse(list(msg[0]))
            if got is None:
                continue
            addr, data = got
            if addr == want_addr:
                return data
            self._events.append((addr, data))
        return None

    # --- the surface -------------------------------------------------------

    def read(self, addr: int, size: int, timeout: float = READ_TIMEOUT) -> list[int]:
        self._send(p.read_frame(addr, size))
        data = self._collect(addr, timeout)
        if data is None:
            raise IR2NotFound(
                f"the IR-2 did not answer a read of {addr:#010x}. It may be "
                "unplugged, or another program is holding the MIDI port.")
        return data

    def write(self, addr: int, data: list[int], verify: bool = True) -> list[int]:
        """DT1, then read the same address back. Returns what the unit
        reports, which is the only thing a caller may treat as true."""
        self._send(p.write_frame(addr, data))
        if not verify:
            return list(data)
        time.sleep(SETTLE)
        back = self.read(addr, len(data))
        if list(back) != list(data):
            raise VerifyFailed(
                f"wrote {' '.join(f'{b:02X}' for b in data)} to {addr:#010x} "
                f"but the IR-2 reports {' '.join(f'{b:02X}' for b in back)}. "
                "The value was refused or clamped; nothing is being claimed.")
        return list(back)

    def drain_events(self) -> list[tuple[int, list[int]]]:
        """Every unsolicited change the pedal announced since the last call."""
        while True:
            msg = self.inp.get_message()
            if not msg:
                break
            got = p.parse(list(msg[0]))
            if got is not None:
                self._events.append(got)
        out, self._events = self._events, []
        return out

    def close(self) -> None:
        for port in (self.inp, self.outp):
            try:
                port.close_port()
            except Exception:      # noqa: BLE001  a dead handle is being dropped anyway
                pass

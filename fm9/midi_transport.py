"""The one place MIDI ports are opened (issue #172).

The device layer and the simulator already agree on a port shape: an input
with `iter_pending()` yielding messages that carry `.type` and, for sysex,
`.data` (the payload without F0 and F7); an output with `send(mido.Message)`
and `close()`. mido supplied that shape on top of python-rtmidi, and
python-rtmidi has no wheels past Python 3.12 and no release since 2023, so
on a current Python the install tried to compile it and failed. This module
keeps the shape and makes the binding a choice:

    TONECOMMAND_MIDI_BACKEND=auto      mido's rtmidi when python-rtmidi
                                       imports, else supriya-midi (default)
    TONECOMMAND_MIDI_BACKEND=mido      mido over python-rtmidi, as before
    TONECOMMAND_MIDI_BACKEND=supriya   supriya-midi, a nanobind RtMidi
                                       binding with wheels to 3.14

mido stays as the message class either way; it is pure Python. The
never-brick guard (device.FM9._send) sits ABOVE this module: a frame is
checked before any port sees it, so no backend can widen what reaches the
wire. The supriya path is fake-port proven here and hardware-pass pending
(#172 REQ-004); the mido path is unchanged.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import mido

BACKENDS = ("auto", "mido", "supriya")
ENV = "TONECOMMAND_MIDI_BACKEND"
#: a CABINET bulk read is about 2,100 frames of up to 3 KB; the input
#: queue must hold them all while the reader drains
SUPRIYA_BUFFER = (4096, 8)


class TransportError(RuntimeError):
    """One line, written for the person at the rig, naming what to install."""


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def backend(env: dict | None = None) -> str:
    """'mido' or 'supriya', resolved from the environment and what imports."""
    env = os.environ if env is None else env
    want = str(env.get(ENV, "auto") or "auto").strip().lower()
    if want not in BACKENDS:
        raise TransportError(f"{ENV}={want!r} is not one of {', '.join(BACKENDS)}")
    if want == "mido":
        if not _importable("rtmidi"):
            raise TransportError("the mido backend needs python-rtmidi, which has no wheel for this "
                                 "Python; use Python 3.11 or 3.12, or set TONECOMMAND_MIDI_BACKEND=supriya")
        return "mido"
    if want == "supriya":
        if not _importable("supriya_midi"):
            raise TransportError("the supriya backend needs supriya-midi: pip install supriya-midi")
        return "supriya"
    if _importable("rtmidi"):
        return "mido"
    if _importable("supriya_midi"):
        return "supriya"
    raise TransportError("no MIDI backend: install python-rtmidi (Python 3.11 or 3.12) or "
                         "supriya-midi (any Python from 3.10), then start again")


def port_names(env: dict | None = None, supriya_module: Any = None) -> list[str]:
    """Input port names on the bus through the resolved backend, opening
    nothing. An enumeration the watcher can ask every second; a backend
    that cannot be resolved answers an empty list rather than raising, so
    presence reads as absent, never as an error page."""
    try:
        b = backend(env)
    except TransportError:
        return []
    if b == "mido":
        return [str(n) for n in mido.get_input_names()]
    sm = supriya_module or __import__("supriya_midi")
    port = sm.MidiIn()
    try:
        return [str(n) for n in port.get_ports()]
    finally:
        close = getattr(port, "delete", None) or getattr(port, "close_port", None)
        if close:
            try:
                close()
            except Exception:
                pass


def output_names(env: dict | None = None, supriya_module: Any = None) -> list[str]:
    """Output port names, opening nothing, for Report a problem (#212).
    Empty, never raising, when no backend resolves."""
    try:
        b = backend(env)
    except TransportError:
        return []
    if b == "mido":
        return [str(n) for n in mido.get_output_names()]
    sm = supriya_module or __import__("supriya_midi")
    port = sm.MidiOut()
    try:
        return [str(n) for n in port.get_ports()]
    finally:
        close = getattr(port, "delete", None) or getattr(port, "close_port", None)
        if close:
            try:
                close()
            except Exception:
                pass


def open_ports(hint: str, env: dict | None = None, supriya_module: Any = None) -> tuple[Any, Any]:
    """(inp, outp) for the first input and output whose names contain
    `hint` (case-insensitive), through the resolved backend. Raises
    TransportError when the ports are not there, one line."""
    b = backend(env)
    hint = hint.lower()
    if b == "mido":
        ins = [n for n in mido.get_input_names() if hint in n.lower()]
        outs = [n for n in mido.get_output_names() if hint in n.lower()]
        if not ins or not outs:
            raise TransportError(_not_found(hint))
        return mido.open_input(ins[0]), mido.open_output(outs[0])
    sm = supriya_module or __import__("supriya_midi")
    return SupriyaIn.open(sm, hint), SupriyaOut.open(sm, hint)


# --- supriya-midi behind the mido-shaped ports -----------------------------------------

def _decode(raw: list[int]) -> SimpleNamespace:
    """A mido-shaped message from raw bytes. Sysex keeps the payload without
    F0 and F7, as mido does; the rest carries what the device layer reads."""
    if not raw:
        return SimpleNamespace(type="other", data=[])
    status = raw[0]
    if status == 0xF0:
        end = len(raw) - 1 if raw[-1] == 0xF7 else len(raw)
        return SimpleNamespace(type="sysex", data=list(raw[1:end]))
    kind, channel = status & 0xF0, status & 0x0F
    if kind == 0xC0 and len(raw) >= 2:
        return SimpleNamespace(type="program_change", channel=channel, program=raw[1])
    if kind == 0xB0 and len(raw) >= 3:
        return SimpleNamespace(type="control_change", channel=channel, control=raw[1], value=raw[2])
    return SimpleNamespace(type="other", data=list(raw))


def _encode(msg: Any) -> list[int]:
    t = getattr(msg, "type", None)
    if t == "sysex":
        return [0xF0, *list(msg.data), 0xF7]
    ch = int(getattr(msg, "channel", 0)) & 0x0F
    if t == "program_change":
        return [0xC0 | ch, int(msg.program) & 0x7F]
    if t == "control_change":
        return [0xB0 | ch, int(msg.control) & 0x7F, int(msg.value) & 0x7F]
    raise TransportError(f"the transport does not send {t!r} messages")


def _pick(names: list[str], hint: str) -> int:
    for i, n in enumerate(names):
        if hint in str(n).lower():
            return i
    raise TransportError(_not_found(hint))


def _not_found(hint: str) -> str:
    """#212: name the device that was looked for. Before, an FM3 owner was
    told the FM9 was missing."""
    return f"{hint.upper()} MIDI ports not found; is it connected and powered on?"


class SupriyaIn:
    """supriya_midi.MidiIn behind iter_pending()/close()."""

    def __init__(self, port: Any):
        self.port = port

    @classmethod
    def open(cls, sm: Any, hint: str) -> "SupriyaIn":
        port = sm.MidiIn()
        idx = _pick(list(port.get_ports()), hint)
        port.set_buffer_size(*SUPRIYA_BUFFER)
        port.open_port(idx, "ToneCommand in")
        port.ignore_types(sysex=False, timing=True, active_sense=True)
        return cls(port)

    def iter_pending(self):
        while True:
            got = self.port.get_message()
            if not got:
                return
            raw = got[0] if isinstance(got, (tuple, list)) else got
            yield _decode(list(raw))

    def close(self) -> None:
        self.port.close_port()


class SupriyaOut:
    """supriya_midi.MidiOut behind send(mido.Message)/close()."""

    def __init__(self, port: Any):
        self.port = port

    @classmethod
    def open(cls, sm: Any, hint: str) -> "SupriyaOut":
        port = sm.MidiOut()
        idx = _pick(list(port.get_ports()), hint)
        port.open_port(idx, "ToneCommand out")
        return cls(port)

    def send(self, msg: Any) -> None:
        self.port.send_message(_encode(msg))

    def close(self) -> None:
        self.port.close_port()

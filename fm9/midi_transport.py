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

import json
import os
import platform
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import mido

BACKENDS = ("auto", "mido", "supriya")
ENV = "TONECOMMAND_MIDI_BACKEND"
FM3_PORT_ENV = "TONECOMMAND_FM3_PORT"
#: a CABINET bulk read is about 2,100 frames of up to 3 KB; the input
#: queue must hold them all while the reader drains
SUPRIYA_BUFFER = (4096, 8)


class TransportError(RuntimeError):
    """One line, written for the person at the rig, naming what to install."""


def fm3_binding_path() -> Path:
    """#221: beside the other local settings, not the working directory."""
    return Path(__file__).resolve().parent.parent / "fm3_port.json"


def load_fm3_binding(env: dict | None = None, path: Path | None = None) -> dict:
    """#221: {port, source}; an environment binding always wins, even empty.

    A missing file means no binding. A damaged file fails closed rather than
    silently selecting some other port. Callers can show source='env' as fixed.
    """
    env = os.environ if env is None else env
    if FM3_PORT_ENV in env:
        return {"port": env[FM3_PORT_ENV], "source": "env"}
    path = fm3_binding_path() if path is None else Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"port": None, "source": "none"}
    except (OSError, ValueError) as e:
        raise TransportError("FM3 port binding could not be read; choose the "
                             "USB MIDI interface port on the Devices page.") from e
    if not isinstance(value, dict) or not isinstance(value.get("port"), str) or not value["port"]:
        raise TransportError("FM3 port binding is invalid; choose the USB MIDI "
                             "interface port on the Devices page.")
    return {"port": value["port"], "source": "file"}


def save_fm3_binding(port: str, env: dict | None = None, path: Path | None = None) -> dict:
    """#221: validate both directions and atomically persist an exact name.

    The server must hold its device-switch lock around saving and reconnecting.
    No MIDI port is opened here, and an environment binding cannot be changed.
    """
    env = os.environ if env is None else env
    if FM3_PORT_ENV in env:
        raise TransportError(f"FM3 port is fixed by {FM3_PORT_ENV}; Save is unavailable.")
    if not isinstance(port, str) or not port or port not in port_names(env) or port not in output_names(env):
        raise TransportError("Choose an FM3 USB MIDI interface port present in both "
                             "the MIDI input and output lists on the Devices page.")
    path = fm3_binding_path() if path is None else Path(path)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".fm3_port-", suffix=".tmp", delete=False) as f:
            tmp = Path(f.name)
            json.dump({"port": port}, f)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return {"port": port, "source": "file"}


FM3_INTERFACE_GUIDANCE = (
    "The FM3 has no MIDI over USB; its USB carries Fractal's own channel for "
    "FM3-Edit, Fractal-Bot and Cab-Lab. Connect a USB MIDI interface to the FM3's "
    "5-pin MIDI IN and MIDI OUT (interface OUT to FM3 IN, FM3 OUT to interface IN). "
    "Choose that interface's port in the FM3 card on the Devices page.")


def fm3_connection_failure(reason: str = "missing") -> str:
    """#221: shared by transport, preflight and the server's failure surfaces."""
    head = ("FM3 port opened but the device did not answer. " if reason == "silent"
            else "FM3 MIDI ports not found. ")
    return head + FM3_INTERFACE_GUIDANCE


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
    # #221: a machine with no MIDI system (CI without ALSA) has no ports;
    # the backend raising there must not turn into an error page.
    try:
        if b == "mido":
            return [str(n) for n in mido.get_input_names()]
        sm = supriya_module or __import__("supriya_midi")
        port = sm.MidiIn()
    except Exception:  # noqa: BLE001  any enumeration failure reads as no ports
        return []
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
    # #221: a machine with no MIDI system (CI without ALSA) has no ports;
    # the backend raising there must not turn into an error page.
    try:
        if b == "mido":
            return [str(n) for n in mido.get_output_names()]
        sm = supriya_module or __import__("supriya_midi")
        port = sm.MidiOut()
    except Exception:  # noqa: BLE001  any enumeration failure reads as no ports
        return []
    try:
        return [str(n) for n in port.get_ports()]
    finally:
        close = getattr(port, "delete", None) or getattr(port, "close_port", None)
        if close:
            try:
                close()
            except Exception:
                pass


def open_ports(hint: str, env: dict | None = None, supriya_module: Any = None,
               *, exact_name: str | None = None) -> tuple[Any, Any]:
    """(inp, outp) for the first input and output whose names contain
    `hint` (case-insensitive), through the resolved backend. Raises
    TransportError when the ports are not there, one line. An FM3 binding
    overrides discovery and matches both directions exactly (#221)."""
    b = backend(env)
    hint = hint.lower()
    if hint == "fm3":
        binding = load_fm3_binding(env)
        if binding["source"] != "none":
            exact_name = binding["port"]
    if b == "mido":
        every_in = list(mido.get_input_names())
        ins = [n for n in every_in if (n == exact_name if exact_name is not None else hint in n.lower())]
        outs = [n for n in mido.get_output_names()
                if (n == exact_name if exact_name is not None else hint in n.lower())]
        if not ins or not outs:
            raise TransportError(_not_found(hint, inputs=every_in))
        if hint == "fm3":
            inp = mido.open_input(ins[0])
            opened = False
            try:
                outp = mido.open_output(outs[0])
                opened = True
                return inp, outp
            finally:
                if not opened:
                    inp.close()
        return mido.open_input(ins[0]), mido.open_output(outs[0])
    sm = supriya_module or __import__("supriya_midi")
    if hint == "fm3":
        return _open_fm3_supriya(sm, exact_name)
    return SupriyaIn.open(sm, hint), SupriyaOut.open(sm, hint)


def _open_fm3_supriya(sm: Any, exact_name: str | None) -> tuple[Any, Any]:
    """Check both directions before opening either; never fall back."""
    inp, outp = sm.MidiIn(), None
    opened = False
    try:
        outp = sm.MidiOut()
        ins, outs = list(inp.get_ports()), list(outp.get_ports())
        i = _pick(ins, "fm3", inputs=True, exact_name=exact_name)
        o = _pick(outs, "fm3", exact_name=exact_name)
        inp.set_buffer_size(*SUPRIYA_BUFFER)
        inp.open_port(i, "ToneCommand in")
        inp.ignore_types(sysex=False, timing=True, active_sense=True)
        outp.open_port(o, "ToneCommand out")
        opened = True
        return SupriyaIn(inp), SupriyaOut(outp)
    finally:
        if not opened:
            inp.close_port()
            if outp is not None:
                outp.close_port()


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


def _pick(names: list[str], hint: str, inputs: bool = False,
          exact_name: str | None = None) -> int:
    for i, n in enumerate(names):
        if (n == exact_name if exact_name is not None else hint in str(n).lower()):
            return i
    raise TransportError(_not_found(hint, inputs=names if inputs else None))


#: #221: only the FM9 uses MIDI over USB and needs this Windows advice.
FRACTAL_HINTS = ("fm9",)


def _system() -> str:
    return platform.system()


def _not_found(hint: str, inputs: list[str] | None = None,
               system: str | None = None) -> str:
    """#212: name the device that was looked for. Before, an FM3 owner was
    told the FM9 was missing.

    #221 corrects #216 for the FM3: its USB never enumerates as MIDI.
    The FM9's #216 text remains byte-identical.
    `inputs` is the input port list when the caller has it (an output list
    says nothing: Windows always lists its GS Wavetable Synth there)."""
    if hint == "fm3":
        return fm3_connection_failure()
    head = f"{hint.upper()} MIDI ports not found"
    if hint not in FRACTAL_HINTS:
        return f"{head}; is it connected and powered on?"
    if inputs is not None and not inputs:
        msg = (f"{head}: this computer sees no MIDI input at all. Is it "
               "connected and powered on, with a USB cable that carries data?")
    else:
        msg = f"{head}; is it connected and powered on?"
    system = _system() if system is None else system
    if system == "Windows":
        msg += (" On Windows a Fractal FM3 or FM9 also needs Fractal's USB "
                "driver, the one FM3-Edit and FM9-Edit use, from fractalaudio.com.")
    return msg


class SupriyaIn:
    """supriya_midi.MidiIn behind iter_pending()/close()."""

    def __init__(self, port: Any):
        self.port = port

    @classmethod
    def open(cls, sm: Any, hint: str) -> "SupriyaIn":
        port = sm.MidiIn()
        idx = _pick(list(port.get_ports()), hint, inputs=True)
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

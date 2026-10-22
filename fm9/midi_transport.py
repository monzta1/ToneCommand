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
(#172 REQ-004). Opening either backend releases the input if opening the
output fails; successful mido traffic is unchanged.
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
#: #255: an interface may list its output under another name than its input
#: ("MidiPort 1" in, "MidiPort 2" out); this fixes the output by itself
FM3_PORT_OUT_ENV = "TONECOMMAND_FM3_PORT_OUT"
#: a CABINET bulk read is about 2,100 frames of up to 3 KB; the input
#: queue must hold them all while the reader drains
SUPRIYA_BUFFER = (4096, 8)


class TransportError(RuntimeError):
    """One line, written for the person at the rig, naming what to install."""


def fm3_binding_path() -> Path:
    """#221: beside the other local settings, not the working directory."""
    return Path(__file__).resolve().parent.parent / "fm3_port.json"


def _binding(port_in, port_out, source) -> dict:
    """{port_in, port_out, port, source}; port is the one name when both
    directions share it (the #221 shape callers already read), else None."""
    return {"port_in": port_in, "port_out": port_out,
            "port": port_in if port_in == port_out else None, "source": source}


def load_fm3_binding(env: dict | None = None, path: Path | None = None) -> dict:
    """#221, #255: {port_in, port_out, port, source}. An environment binding
    always wins, even empty: TONECOMMAND_FM3_PORT fixes both directions and
    TONECOMMAND_FM3_PORT_OUT, when set, the output alone. Set without
    TONECOMMAND_FM3_PORT, the output comes from the environment and the input
    from the saved file; with no saved input, port_in is None and connecting
    fails rather than guessing. Either variable makes the binding source 'env'.

    A missing file means no binding. A damaged file fails closed rather than
    silently selecting some other port. The #221 file {port} still loads as
    both directions. Callers can show source='env' as fixed.
    """
    env = os.environ if env is None else env
    if FM3_PORT_ENV in env:
        return _binding(env[FM3_PORT_ENV], env.get(FM3_PORT_OUT_ENV, env[FM3_PORT_ENV]), "env")
    if FM3_PORT_OUT_ENV in env:
        saved = load_fm3_binding({}, path)
        return _binding(saved["port_in"], env[FM3_PORT_OUT_ENV], "env")
    path = fm3_binding_path() if path is None else Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _binding(None, None, "none")
    except (OSError, ValueError) as e:
        raise TransportError("FM3 port binding could not be read; choose the "
                             "USB MIDI interface port on the Devices page.") from e
    ok = lambda v: isinstance(v, str) and bool(v)
    if isinstance(value, dict) and ok(value.get("port_in")) and ok(value.get("port_out")):
        return _binding(value["port_in"], value["port_out"], "file")
    if isinstance(value, dict) and ok(value.get("port")):
        return _binding(value["port"], value["port"], "file")
    raise TransportError("FM3 port binding is invalid; choose the USB MIDI "
                         "interface port on the Devices page.")


def save_fm3_binding(port_in: str, port_out: str | None = None, env: dict | None = None,
                     path: Path | None = None) -> dict:
    """#221, #255: validate each direction against its own list and
    atomically persist the exact names. port_out defaults to port_in.

    The server must hold its device-switch lock around saving and reconnecting.
    No MIDI port is opened here, and an environment binding cannot be changed.
    """
    env = os.environ if env is None else env
    for name in (FM3_PORT_ENV, FM3_PORT_OUT_ENV):
        if name in env:
            raise TransportError(f"FM3 port is fixed by {name}; Save is unavailable.")
    port_out = port_in if port_out is None else port_out
    if not isinstance(port_in, str) or not port_in or port_in not in port_names(env):
        raise TransportError("Choose the MIDI input your FM3's MIDI OUT is connected to, "
                             "from the inputs listed on the Devices page.")
    if not isinstance(port_out, str) or not port_out or port_out not in output_names(env):
        raise TransportError("Choose the MIDI output connected to your FM3's MIDI IN, "
                             "from the outputs listed on the Devices page.")
    path = fm3_binding_path() if path is None else Path(path)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".fm3_port-", suffix=".tmp", delete=False) as f:
            tmp = Path(f.name)
            json.dump({"port": port_in} if port_in == port_out
                      else {"port_in": port_in, "port_out": port_out}, f)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return _binding(port_in, port_out, "file")


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
    except Exception:  # noqa: BLE001  #221: an enumeration failure reads as no ports
        return []
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
    except Exception:  # noqa: BLE001  #221: an enumeration failure reads as no ports
        return []
    finally:
        close = getattr(port, "delete", None) or getattr(port, "close_port", None)
        if close:
            try:
                close()
            except Exception:
                pass


def open_ports(hint: str, env: dict | None = None, supriya_module: Any = None,
               *, exact_name: str | None = None, exact_out: str | None = None) -> tuple[Any, Any]:
    """(inp, outp) for the first input and output whose names contain
    `hint` (case-insensitive), through the resolved backend. Raises
    TransportError when the ports are not there, one line. An FM3 binding
    overrides discovery and matches both directions exactly (#221)."""
    b = backend(env)
    hint = hint.lower()
    if hint == "fm3":
        binding = load_fm3_binding(env)
        if binding["source"] != "none":
            # a binding never falls back to discovery: an unset direction
            # matches nothing
            exact_name, exact_out = binding["port_in"] or "", binding["port_out"] or ""
    if exact_out is None:
        exact_out = exact_name
    if b == "mido":
        every_in = list(mido.get_input_names())
        ins = [n for n in every_in if (n == exact_name if exact_name is not None else hint in n.lower())]
        outs = [n for n in mido.get_output_names()
                if (n == exact_out if exact_out is not None else hint in n.lower())]
        if not ins or not outs:
            raise TransportError(_not_found(hint, inputs=every_in))
        inp = mido.open_input(ins[0])
        try:
            return inp, mido.open_output(outs[0])
        except BaseException:
            inp.close()
            raise
    sm = supriya_module or __import__("supriya_midi")
    if hint == "fm3":
        return _open_fm3_supriya(sm, exact_name, exact_out)
    inp = SupriyaIn.open(sm, hint)
    try:
        return inp, SupriyaOut.open(sm, hint)
    except BaseException:
        inp.close()
        raise


def _open_fm3_supriya(sm: Any, exact_name: str | None,
                      exact_out: str | None = None) -> tuple[Any, Any]:
    """Check both directions before opening either; never fall back."""
    inp, outp = sm.MidiIn(), None
    opened = False
    try:
        outp = sm.MidiOut()
        ins, outs = list(inp.get_ports()), list(outp.get_ports())
        i = _pick(ins, "fm3", inputs=True, exact_name=exact_name)
        o = _pick(outs, "fm3", exact_name=exact_name if exact_out is None else exact_out)
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


#: software MIDI buses, never a hardware interface an FM3 could hang off
VIRTUAL_PORTS = ("iac driver", "network session", "loopmidi", "midi monitor")


def readable_port(name) -> bool:
    """#255: a port name a person can read. A Windows MIDI service endpoint
    reported '-\u00e2\u0080\u00ban\x17\u00c3\u00bf\x7f 0': control characters
    a driver handed over, not a name anyone could pick from a list."""
    import unicodedata
    text = str(name)
    return bool(text.strip()) and not any(
        (unicodedata.category(ch) == "Cc" and ch not in " ") or ch == "\ufeff" for ch in text)


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
        # #255: the FM9 only. An FM3 has no MIDI over USB (#221), so that
        # driver never makes one visible here; telling an FM3 owner to install
        # it sent him in circles.
        msg += (" On Windows an FM9 also needs Fractal's USB driver, the one "
                "FM9-Edit uses, from fractalaudio.com.")
    others = [n for n in (inputs or []) if readable_port(n) and "fm9" not in str(n).lower()
              and not str(n).lower().startswith(VIRTUAL_PORTS)]
    if others:
        msg += (" If your unit is an FM3, or you reach it through a MIDI interface, choose "
                "FM3 under Devices and pick that interface's port: "
                + ", ".join(str(n) for n in others) + ".")
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

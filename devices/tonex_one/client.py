"""The ToneX One's serial link, and the request/answer layer over it.

The One appears as a USB CDC serial port (/dev/cu.usbmodem... on macOS),
found by its USB identity through devices.usb, never by guessing a port.
The port is held exclusively (TIOCEXCL) while ToneCommand uses it, so a
second program cannot open it mid-conversation; close the TONEX Editor
first, since it would be talking to the same pedal.

Every byte written goes through protocol.SendGate. Every write is followed
by a read of what the pedal now holds; a change counts only when that read
shows it.
"""
from __future__ import annotations

import os
import struct
import time

from . import params as P
from . import protocol as p


class ToneXOneNotFound(RuntimeError):
    """The pedal is not plugged in, or did not answer."""


class VerifyFailed(RuntimeError):
    """The pedal did not report the value that was written."""


def find_port() -> str | None:
    env = os.environ.get("TONECOMMAND_TONEX_ONE_PORT")
    if env:
        return env
    try:
        from devices import usb
        for d in usb.list_usb():
            if d.get("vid") == p.VENDOR_ID and d.get("pid") == p.PRODUCT_ID:
                return d.get("serial_port")
    except Exception:                    # noqa: BLE001  discovery never raises
        return None
    return None


class SerialLink:
    """Raw bytes in and out of the CDC port (POSIX)."""

    def __init__(self, port: str):
        if os.name != "posix":
            raise ToneXOneNotFound("the ToneX One link runs on macOS and Linux for now")
        import termios
        import tty
        self.port = port
        try:
            self.fd = os.open(port, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        except OSError as e:
            raise ToneXOneNotFound(f"could not open the ToneX One at {port}: {e.strerror}")
        try:
            tty.setraw(self.fd)
            import fcntl
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
        except Exception:
            os.close(self.fd)
            raise

    def _live(self) -> None:
        if self.fd < 0:
            raise ToneXOneNotFound("the ToneX One link is closed")

    def write(self, data: bytes) -> None:
        self._live()
        view = memoryview(data)
        deadline = time.monotonic() + 2.0
        while view:
            try:
                n = os.write(self.fd, view)
                view = view[n:]
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise ToneXOneNotFound("the ToneX One stopped taking data")
                time.sleep(0.002)
            except OSError as e:
                raise ToneXOneNotFound(f"the ToneX One link dropped: {e.strerror}")

    def read(self) -> bytes:
        self._live()
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return b""
        except OSError as e:
            raise ToneXOneNotFound(f"the ToneX One link dropped: {e.strerror}")
        if not data:
            # No data is EAGAIN on a live port; an empty read is the port
            # hanging up, which is what an unplug looks like.
            raise ToneXOneNotFound("the ToneX One was unplugged")
        return data

    def close(self) -> None:
        # Marked dead at once: the OS reuses fd numbers, and a later read or
        # write on a closed link must not reach whatever opened next.
        fd, self.fd = self.fd, -1
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


class ToneXOneClient:
    READ_TIMEOUT = 2.0
    #: After a write the pedal stores the change (it saves automatically);
    #: the read that proves it waits this long first, then retries.
    SETTLE = (0.3, 0.3, 0.3, 0.5, 0.5, 1.0)

    def __init__(self, link=None):
        if link is None:
            port = find_port()
            if not port:
                raise ToneXOneNotFound("no ToneX One on USB; plug it in (and close the "
                                       "TONEX Editor, which holds the same link)")
            link = SerialLink(port)
        self.link = link
        self.gate = p.SendGate(P.WRITABLE)
        self._buf = b""
        self.events: list[p.Message] = []     # what the pedal pushed unasked
        self.firmware: str | None = None
        self.hello()

    # --- plumbing ---------------------------------------------------------

    def _send(self, payload: bytes) -> None:
        self.link.write(self.gate.checked_frame(payload))

    def _pump(self) -> list[p.Message]:
        chunk = self.link.read()
        if chunk:
            self._buf += chunk
        payloads, self._buf = p.unframe_stream(self._buf)
        out = []
        for pl in payloads:
            try:
                out.append(p.parse(pl))
            except p.ProtocolError:
                continue
        return out

    def _wait(self, want, timeout: float | None = None) -> p.Message:
        end = time.monotonic() + (timeout or self.READ_TIMEOUT)
        while time.monotonic() < end:
            for m in self._pump():
                if want(m):
                    return m
                self._remember(m)
            time.sleep(0.004)
        raise ToneXOneNotFound("the ToneX One did not answer")

    def _remember(self, m: p.Message) -> None:
        if m.type == p.T_STATE:
            st = p.State(m.payload[m.body_at:])
            try:
                st.check()
                self.gate.last_state = st
            except p.ProtocolError:
                pass
        self.events.append(m)
        del self.events[:-50]

    # --- requests ---------------------------------------------------------

    def hello(self) -> str:
        # Seen on the unit: a hello sent straight after another program
        # closed the port went unanswered, and the same hello a moment later
        # was answered. A hello changes nothing, so it is simply asked again.
        m = None
        for attempt in range(3):
            self._send(p.HELLO)
            try:
                m = self._wait(lambda m: m.type == p.T_HELLO, timeout=1.5)
                break
            except ToneXOneNotFound:
                if attempt == 2:
                    raise
        try:
            fw = m.body()[0][3]
            self.firmware = ".".join(str(x) for x in fw)
        except (IndexError, TypeError, p.ProtocolError):
            self.firmware = None
        return self.firmware or ""

    def read_state(self) -> p.State:
        self._send(p.REQUEST_STATE)
        m = self._wait(lambda m: m.type == p.T_STATE)
        st = p.State(m.payload[m.body_at:])
        st.check()
        self.gate.last_state = st
        return st

    def read_preset(self, index: int) -> p.Preset:
        self._send(p.request_preset(index))

        def want(m):
            if m.type != p.T_PRESET:
                return False
            try:
                return p.parse_preset(m).index == index
            except p.ProtocolError:
                return False
        return p.parse_preset(self._wait(want))

    def drain_events(self) -> list[p.Message]:
        for m in self._pump():
            self._remember(m)
        out, self.events = self.events, []
        return out

    # --- writes, each read back ---------------------------------------------

    def set_param(self, index: int, value: float) -> float:
        """Change one setting of the preset now playing; returns what the
        pedal then reports for it."""
        # The preset playing is read NOW, not remembered: a footswitch press
        # since the last read moves it, and this write lands on whichever
        # preset plays, where the pedal saves it at once.
        self.drain_events()
        active = self.read_state().active_preset
        self._send(p.set_param(index, value))
        # The pedal stores a float32; what it reports back must be exactly
        # that float, so a clamp or a rounding is a failure, not a pass.
        want = struct.unpack("<f", struct.pack("<f", float(value)))[0]
        got = None
        for wait in self.SETTLE:
            time.sleep(wait)
            got = self.read_preset(active).params[index]
            if got == want:
                return got
        raise VerifyFailed(f"setting {P.PARAMS[index].name}: wrote {value}, the pedal "
                           f"reports {got}")

    def write_state(self, **fields) -> p.State:
        self.drain_events()
        st = self.read_state()
        new = st.changed(**fields)
        self._send(p.write_state(new))
        got = None
        for wait in self.SETTLE:
            time.sleep(wait)
            got = self.read_state()
            if all(getattr(got, k) == (bool(v) if isinstance(getattr(got, k), bool) else v)
                   for k, v in fields.items() if k != "input_trim") and \
                    ("input_trim" not in fields or abs(got.input_trim - fields["input_trim"]) < 0.01):
                return got
        raise VerifyFailed(f"the pedal did not take the change {fields}")

    def close(self) -> None:
        self.link.close()

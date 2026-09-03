"""FM9 device transport and high-level control API.

Safety contract: this module NEVER stores/saves anything on the unit.
All writes hit the volatile edit buffer only. The editor protocol's
store command (fn 0x01 sub 0x26) is deliberately not implemented.
"""
from __future__ import annotations

import time
from pathlib import Path
from dataclasses import dataclass

import mido

from . import protocol as p
from .adapter import Capabilities, ReadPath
from .registry import Registry, ParamSpec
from .safety import sysex_guard
from .signal_path import scene_alive

RESULT_CODES = {
    0x00: "ok",
    0x05: "rejected (invalid function for this device)",
    0x08: "invalid effect id",
    0x09: "invalid param id",
}


def _check_preset_range(preset: int) -> None:
    """Refuse an out-of-range slot rather than believe the answer.

    The unit ANSWERS a query for a nonexistent preset (512 and up) with a
    blank name field and the requested number echoed back. A blank is not
    the <EMPTY> marker, so an unguarded read reports such a slot as
    OCCUPIED - the exact wrong direction for anything that then decides
    where to write.
    """
    if not 0 <= preset < p.PRESET_COUNT:
        raise ValueError(
            f"preset {preset} is out of range: the wire numbers presets "
            f"0-{p.PRESET_COUNT - 1}, which FM9-Edit shows as "
            f"1-{p.PRESET_COUNT}")


class NoEmptySlot(RuntimeError):
    """Nothing free to build into. A build refuses rather than pick a victim."""


class FM9NotFound(RuntimeError):
    pass


def store_slots_path() -> Path:
    """Where a whitelist chosen in the UI is kept. Gitignored, like .env."""
    import os
    override = os.environ.get("TONECOMMAND_STORE_SLOTS_FILE", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "store_slots.json"


def get_store_slots_spec() -> tuple[str, str]:
    """The raw whitelist spec and where it came from, for showing the owner.

    A safety boundary the owner cannot see is one they forget they set, which
    is exactly what happened here: the range was authorised in conversation,
    written to .env by a script, and six days later the owner had no way to
    check it from the product and misremembered what it was.
    """
    import json
    import os
    raw = os.environ.get("TONECOMMAND_STORE_SLOTS", "")
    if raw:
        # An explicit env var is an operator pin and outranks the UI, so a
        # browser cannot widen a boundary someone set deliberately outside it.
        return raw, "environment"
    path = store_slots_path()
    if path.exists():
        try:
            got = json.loads(path.read_text())
            if isinstance(got, dict) and isinstance(got.get("slots"), str):
                return got["slots"], "app"
        except (json.JSONDecodeError, ValueError, OSError):
            pass          # a corrupt file must not silently widen anything
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("TONECOMMAND_STORE_SLOTS="):
                return line.split("=", 1)[1].strip(), ".env"
    return "", "unset"


def set_store_slots_spec(raw: str) -> tuple[str, str]:
    """Persist a whitelist chosen in the UI. Returns the stored spec+source."""
    import json
    import os
    if os.environ.get("TONECOMMAND_STORE_SLOTS", ""):
        raise PermissionError(
            "TONECOMMAND_STORE_SLOTS is pinned in the environment; change it "
            "there rather than in the app")
    store_slots_path().write_text(json.dumps({"slots": raw.strip()}, indent=1))
    return get_store_slots_spec()


def parse_store_slots(raw: str) -> set[int]:
    """Slot numbers from a spec string. Wire numbers, 0-511."""
    return _parse_slots(raw)


def get_cab_slots() -> set[int]:
    """The ONLY user-cab slots this tool may write IRs into. Same shape and
    same philosophy as the preset whitelist: user cabs are user property,
    an installed IR permanently overwrites one, and nobody but the owner
    knows which of theirs are disposable. TONECOMMAND_CAB_SLOTS, env or
    .env, 0-based wire indices ("0-15" covers what the editor shows as
    User Cab 1-16). DEFAULT IS EMPTY: cab installs are disabled until the
    owner designates slots."""
    import os
    raw = os.environ.get("TONECOMMAND_CAB_SLOTS", "").strip()
    if not raw:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip().startswith("TONECOMMAND_CAB_SLOTS="):
                    raw = line.split("=", 1)[1].strip()
                    break
    # User-cab indices run past the preset range, so the preset parser's
    # 0-511 cap does not apply here.
    slots: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                slots.update(range(int(a), int(b) + 1))
            except ValueError:
                pass
        else:
            try:
                slots.add(int(part))
            except ValueError:
                pass
    return {n for n in slots if 0 <= n <= 1023}


def get_store_slots() -> set[int]:
    """The ONLY preset slots this tool is allowed to store to, configured by
    the user for their own unit. Sources, first match wins:

      1. env var  TONECOMMAND_STORE_SLOTS   (an operator pin, unoverridable)
      2. store_slots.json                    (chosen in the app)
      3. a TONECOMMAND_STORE_SLOTS= line in .env at the repo root

    Format: "133-148" or "133,140,150-155". These are WIRE numbers, 0-511.
    FM9-Edit and the front panel number the same slots 1-512, so "133-148"
    here is what the editor shows as 134-149. Read the range off the wire,
    not off the editor, or the whitelist is one slot out.

    DEFAULT IS EMPTY: storing is disabled until the owner designates
    disposable slots, because nobody but the owner knows what lives in
    their banks."""
    raw, _source = get_store_slots_spec()
    return _parse_slots(raw)


def _parse_slots(raw: str) -> set[int]:
    slots: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                slots.update(range(int(a), int(b) + 1))
            except ValueError:
                pass
        else:
            try:
                slots.add(int(part))
            except ValueError:
                pass
    return {n for n in slots if 0 <= n <= 511}


@dataclass
class SetResult:
    ok: bool
    detail: str
    display_before: float | str | None
    display_after: float | str | None


class FM9:
    def __init__(self, registry: Registry | None = None, port_hint: str = "fm9",
                 ports=None):
        """`ports=(inp, outp)` injects transport objects (used by fm9.sim for
        hardware-free testing); default discovers the real FM9 over mido."""
        self.reg = registry or Registry()
        if ports is not None:
            self.inp, self.outp = ports
        else:
            ins = [n for n in mido.get_input_names() if port_hint in n.lower()]
            outs = [n for n in mido.get_output_names() if port_hint in n.lower()]
            if not ins or not outs:
                raise FM9NotFound("FM9 MIDI ports not found; is it connected and powered on?")
            self.inp = mido.open_input(ins[0])
            self.outp = mido.open_output(outs[0])
        # per-effect channel info, refreshed from status dumps
        self._channels: dict[int, int] = {}
        self._current_channel: dict[int, int] = {}
        # preflight: if another process holds the port or the stream is
        # poisoned, reads return garbage while writes appear to work
        # (observed 2026-08-20). Fail loudly instead.
        import atexit
        atexit.register(self.close)     # zombie ports poison later sessions
        self._drain()
        if self.current_preset() is None:
            self.close()
            raise FM9NotFound(
                "FM9 port opened but the device did not answer a preset-name "
                "query. Either it is still booting, FM9-Edit is running, or a "
                "zombie process is holding the MIDI port (ps aux | grep python).")

    # What the FM9 can actually answer. Every field here is backed by
    # hardware sessions, not by the manual: SysEx reads answer on the same
    # channel writes go out on, slot names read by number without disturbing
    # the loaded preset (PR #19), and set_param_display already settles and
    # reads back before reporting.
    CAPABILITIES = Capabilities(
        read_path=ReadPath.DEVICE,
        split_transport=False,
        reads_by_slot=True,
        verifies_writes=True,
        has_scenes=True,
        stores_presets=True,
    )

    def capabilities(self) -> Capabilities:
        return self.CAPABILITIES

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        # mido/CoreMIDI port close can hang forever, leaving a zombie
        # process that holds the port and silently poisons the next
        # session's reads (observed 2026-08-20). Close with a hard deadline.
        import threading

        def _close():
            try:
                self.inp.close()
                self.outp.close()
            except Exception:
                pass
        t = threading.Thread(target=_close, daemon=True)
        t.start()
        t.join(timeout=3.0)

    # --- transport ---

    def _drain(self):
        for _ in self.inp.iter_pending():
            pass

    # NEVER-BRICK GUARD (hard rule, 2026-08-22): this tool must never be
    # able to damage any device. Only function ids that are decoded,
    # hardware-verified, and USER-DATA scoped may ever reach the wire.
    # Firmware update, bootloader, flash, and every unknown function id
    # are structurally unreachable - not policy, architecture. Extending
    # this set requires a hardware-verified decode of the new function
    # and a documented recovery path (power-cycle + preset reselect).
    #
    # The enforcement lives in fm9.safety (lifted there 2026-08-24) so a
    # second device inherits it. It used to be a check inside this method,
    # which protected the FM9 and nothing else.
    SENDABLE_FNS = frozenset({0x01, 0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E,
                              0x13, 0x14, 0x1F})
    guard = sysex_guard("FM9", SENDABLE_FNS)
    #: The preset-dump family (0x77/0x78/0x79), sendable ONLY through
    #: install_preset, which takes nothing but frames the presetfile module
    #: has validated. A separate guard, so no other code path can emit them
    #: and the main surface stays exactly as narrow as it was.
    install_guard = sysex_guard("FM9-preset-install",
                                frozenset({0x77, 0x78, 0x79}))
    #: Likewise for user-cab (IR) installs: the 0x7A/0x7B/0x7C family,
    #: reachable only through install_user_cab with parser-validated
    #: frames. The read REQUEST (fn 0x19) sits in SENDABLE_FNS' spirit but
    #: gets its own guard here too, keeping the main surface untouched.
    cab_guard = sysex_guard("FM9-cab-install",
                            frozenset({0x19, 0x7A, 0x7B, 0x7C}))

    def _send(self, frame: list[int]):
        if len(frame) > 5 and frame[0] == 0xF0:
            self.guard.check(frame[5])
        self.outp.send(mido.Message("sysex", data=frame[1:-1]))

    def _request(self, frame: list[int], want, timeout: float = 1.0):
        """Send a frame, return first inbound sysex for which want(data) is
        not None. Other frames (broadcasts) are ignored."""
        self._drain()
        self._send(frame)
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self.inp.iter_pending():
                if msg.type != "sysex":
                    continue
                data = list(msg.data)
                got = want(data)
                if got is not None:
                    return got
                nack = p.parse_multipurpose(data)
                if nack is not None and nack[1] != 0x00:
                    fn, code = nack
                    raise RuntimeError(
                        f"device rejected fn 0x{fn:02X}: "
                        f"{RESULT_CODES.get(code, f'result 0x{code:02X}')}")
            time.sleep(0.005)
        return None

    # --- official surface ---

    def firmware(self):
        return self._request(p.build_get_firmware(),
                             lambda d: d[5:7] if p.is_fractal(d, p.FN_FIRMWARE) else None)

    def firmware_label(self) -> str:
        """The firmware as the unit writes it, e.g. "12.00".

        Two bytes, major and minor, and the minor is shown zero padded to two
        digits because that is how Fractal writes it everywhere and how the
        recipes in this repository record it.
        """
        got = self.firmware()
        if not got or len(got) < 2:
            return ""
        return f"{got[0]}.{got[1]:02d}"

    def current_preset(self) -> tuple[int, str] | None:
        return self._request(p.build_get_patch_name(), p.parse_patch_name)

    def slot_name(self, preset: int) -> p.SlotName | None:
        """A slot's STORED name, read WITHOUT selecting it.

        fn 0x0D takes a preset number and the device answers from flash, so
        the loaded preset and the edit buffer are untouched. Verified over all
        512 slots on fw 12.00: byte-identical to a select-and-read sweep of
        the same unit, with the loaded preset unchanged. Answers carry the
        requested number back, so a stale or current-preset reply is rejected
        rather than misattributed.
        """
        _check_preset_range(preset)

        def want(d):
            got = p.parse_patch_name_full(d)
            return got if got is not None and got.number == preset else None
        return self._request(p.build_get_patch_name(preset), want)

    def is_slot_empty(self, preset: int) -> bool | None:
        """True/False, or None if the slot did not answer."""
        got = self.slot_name(preset)
        return None if got is None else got.empty

    def scan_slots(self, start: int = 0, end: int = 511):
        """Read every slot name in a range without disturbing the device.

        Yields SlotName per answering slot, skipping any that stays silent
        after one retry. Read-only by construction: no select, no write.
        """
        _check_preset_range(start)      # eagerly: a generator body would not
        _check_preset_range(end)        # raise until the first iteration
        if start > end:
            # Scanning nothing and reporting "every slot holds a preset" tells
            # the owner their unit is full when it may be empty.
            raise ValueError(
                f"range {start}-{end} runs backwards: start must not be "
                f"greater than end")

        def walk():
            for n in range(start, end + 1):
                got = self.slot_name(n) or self.slot_name(n)
                if got is not None:
                    yield got
        return walk()

    def first_empty_slot(self, start: int = 0, end: int = 511) -> p.SlotName:
        """The lowest-numbered empty slot in the range.

        A from-scratch build must land somewhere free, and choosing the slot
        is not the caller's problem: this finds one or refuses. Raises
        NoEmptySlot when every slot that answered holds a preset, because
        overwriting someone's work is never the safe fallback.
        """
        for got in self.scan_slots(start, end):
            if got.empty:
                return got
        raise NoEmptySlot(
            f"no empty presets to build on: every slot in {start}-{end} "
            f"(FM9-Edit {p.editor_number(start)}-{p.editor_number(end)}) that "
            "answered holds a preset. Clear one on the unit (or widen the "
            "range) and try again; tools/find_empty_slots.py shows the map.")

    def require_empty_slot(self, preset: int) -> p.SlotName:
        """Gate for building a preset from scratch into a slot.

        Refuses anything but a slot the FM9 itself reports as <EMPTY>, so a
        from-scratch build cannot start by clobbering a preset someone owns.
        Store remains separately whitelisted (see store_preset); this is a
        target check, not a store permission.
        """
        got = self.slot_name(preset)
        if got is None:
            raise FM9NotFound(
                f"preset {p.slot_label(preset)} did not answer a name query")
        if not got.empty:
            raise ValueError(
                f"preset {p.slot_label(preset)} holds {got.name!r}; building "
                "from scratch requires a slot the device reports as <EMPTY>")
        return got

    def current_scene(self) -> int | None:
        return self._request(p.build_get_scene(), p.parse_scene)

    def scene_name(self, scene: int | None = None) -> tuple[int, str] | None:
        return self._request(p.build_get_scene_name(scene), p.parse_scene_name)

    def set_scene(self, scene_1based: int) -> int | None:
        """Returns the scene the device reports after the change."""
        got = self._request(p.build_set_scene(scene_1based), p.parse_scene)
        if got is None:  # some responses race; confirm with a query
            got = self.current_scene()
        return got

    def status_dump(self):
        blocks = self._request(p.build_status_dump(), p.parse_status_dump, timeout=1.5)
        if blocks:
            for b in blocks:
                self._channels[b.effect_id] = max(1, b.channels_supported)
                self._current_channel[b.effect_id] = b.channel
        return blocks

    def get_bypass(self, effect_id: int) -> bool | None:
        got = self._request(p.build_get_bypass(effect_id),
                            lambda d: p.parse_bypass(d))
        return got[1] if got else None

    def set_bypass(self, effect_id: int, bypassed: bool) -> bool | None:
        got = self._request(p.build_set_bypass(effect_id, bypassed), p.parse_bypass)
        if got is None:
            got_b = self.get_bypass(effect_id)
            return got_b
        return got[1]

    def get_channel(self, effect_id: int) -> int | None:
        got = self._request(p.build_get_channel(effect_id), p.parse_channel)
        return got[1] if got else None

    def set_channel(self, effect_id: int, channel_0based: int) -> int | None:
        got = self._request(p.build_set_channel(effect_id, channel_0based), p.parse_channel)
        return got[1] if got else None

    def select_preset(self, preset: int) -> tuple[int, str] | None:
        """Preset switch via PC + CC0 bank (FM9 reads bank from CC0).
        Discards the edit buffer by loading the stored preset."""
        bank, pc = divmod(preset, 128)
        self.outp.send(mido.Message("control_change", control=0, value=bank))
        self.outp.send(mido.Message("program_change", program=pc))
        time.sleep(0.4)
        return self.current_preset()

    # --- editor protocol (community, fw 11.x) ---

    def _param_echo(self, frame: list[int], effect_id: int, param_id: int,
                    timeout: float = 1.0) -> p.ParamEcho | None:
        def want(d):
            echo = p.parse_param_echo(d)
            if echo and echo.effect_id == effect_id and echo.param_id == param_id:
                return echo
            return None
        return self._request(frame, want, timeout)

    def bulk_read(self, effect_id: int, timeout: float = 1.5) -> list[int] | None:
        """fn=0x1F whole-block read: returns positional wire16 values where
        index == device paramId (channel-blocked across the block's channels)."""
        self._drain()
        self._send(p.build_bulk_read_poll(effect_id))
        deadline = time.time() + timeout
        head = None
        values: list[int] = []
        while time.time() < deadline:
            for msg in self.inp.iter_pending():
                if msg.type != "sysex":
                    continue
                data = list(msg.data)
                h = p.parse_bcast_head(data)
                if h is not None:
                    if h[0] == effect_id:
                        head = h
                    continue
                if head is None:
                    continue
                body = p.parse_bcast_body(data)
                if body is not None:
                    values.extend(body)
                    continue
                if p.is_fractal(data, p.FN_BCAST_END):
                    return values if head and len(values) >= head[1] else values or None
            time.sleep(0.002)
        return values or None

    def read_grid(self, timeout: float = 2.0):
        """Live routing-grid read (fn 0x01 sub 0x2E). Returns GridCell list."""
        return self._request(p.build_request_grid_layout(), p.parse_grid_layout,
                             timeout)

    def place_block(self, row_1based: int, col_1based: int, effect_id: int):
        """Place a block (or 0 to clear) at a grid cell. Edit buffer only.
        Sends the cell-select first; without it the insert lands on the
        device's internal cursor instead of the target cell."""
        self._drain()
        self._send(p.build_select_grid_cell(row_1based, col_1based))
        time.sleep(0.05)
        self._send(p.build_set_grid_cell(row_1based, col_1based, effect_id))
        time.sleep(0.3)

    def send_preset_file(self, syx_bytes: bytes) -> bool:
        """Send a .syx preset dump (0x77/0x78/0x79 chain addressed to the
        edit buffer) to the device, paced like Fractal-Bot. Loads into the
        volatile edit buffer only; persisting needs store_preset."""
        msgs = []
        i = 0
        while i < len(syx_bytes):
            j = syx_bytes.find(b"\xf7", i)
            if syx_bytes[i] != 0xF0 or j == -1:
                raise ValueError("not a clean .syx sysex stream")
            msgs.append(list(syx_bytes[i:j + 1]))
            i = j + 1
        if not msgs or msgs[0][4] != 0x12:
            raise ValueError(
                f"not an FM9 preset (model byte 0x{msgs[0][4]:02x})" if msgs
                else "empty .syx file")
        self._drain()
        for m in msgs:
            self._send(m)
            time.sleep(0.06)
        time.sleep(1.0)
        return True

    def store_preset(self, slot: int):
        """Persist the working buffer to a preset slot. Only slots the user
        has designated via TONECOMMAND_STORE_SLOTS; refuses everything else,
        and refuses everything when nothing is configured."""
        allowed = get_store_slots()
        if not allowed:
            raise PermissionError(
                "storing is disabled: no store slots configured. Set "
                "TONECOMMAND_STORE_SLOTS (env or .env), e.g. "
                "TONECOMMAND_STORE_SLOTS=133-148 (WIRE numbers, which FM9-Edit "
                "shows as 134-149), choosing slots on YOUR unit that are safe "
                "to overwrite")
        if slot not in allowed:
            raise PermissionError(
                f"store to slot {p.slot_label(slot)} refused: configured store "
                f"slots are {p.slot_set_label(allowed)}")
        self._drain()
        self._send(p.build_store_preset(slot))
        time.sleep(1.5)
        return self.current_preset()

    def install_preset(self, raw: bytes, slot: int, name: str | None = None):
        """Send a validated preset file to a whitelisted slot.

        The recipe is the official editor's own store path (Ghidra-decoded
        upstream): the file's frames verbatim, header retargeted to `slot`.
        When `name` is given, the embedded preset name is replaced first
        and the footer refolded, so the slot ends up carrying the owner's
        chosen name. The host-to-device direction is hardware-UNVERIFIED
        territory, so the caller must verify by reading the slot's name
        back; this method only transmits. Same whitelist, same refusals,
        as store_preset: this writes flash.
        """
        from fm9 import presetfile
        allowed = get_store_slots()
        if not allowed:
            raise PermissionError(
                "installing is disabled: no store slots configured. Set "
                "TONECOMMAND_STORE_SLOTS (env or .env) with slots on YOUR "
                "unit that are safe to overwrite")
        if slot not in allowed:
            raise PermissionError(
                f"install to slot {p.slot_label(slot)} refused: configured "
                f"store slots are {p.slot_set_label(allowed)}")
        pf = presetfile.parse(raw)          # re-validated at this boundary
        # FM9-Edit's own recipe, captured on the wire 2026-09-03: a sub 0x27
        # "prepare", then the preset dumped into the EDIT BUFFER (header
        # 7F 7F) with FLOW CONTROL (the device acks every frame with a 0x64;
        # firing frames blind drops chunks and the body never lands), then a
        # STORE (sub 0x26) of the buffer to the slot.
        frames = presetfile.for_edit_buffer(pf)
        self._drain()
        # prepare: fn 0x01 sub 0x27, all-zero payload; device replies.
        self._request(p.envelope(0x01, [0x27] + [0x00] * 14),
                      lambda d: True if len(d) > 5 and d[4] == 0x01
                      and d[5] == 0x27 else None, timeout=1.0)
        for frame in frames:
            self.install_guard.check(frame[5])
            self._send_await_dump_ack(frame)
        time.sleep(0.3)
        # Rename via the device's OWN name command on the buffer (not by
        # patching the file body: rewriting the name in the dump and
        # recomputing the footer produced a body the device rejected, so
        # the slot stored empty). The dump populated the buffer; rename it,
        # then store.
        if name and name.strip():
            self._send(p.build_rename_preset(name.strip()[:32]))
            time.sleep(0.3)
            pf.name = name.strip()[:32]     # so verification expects this
        self._send(p.build_store_preset(slot))   # fn 0x01 sub 0x26, allowed
        time.sleep(1.5)                     # let flash settle before reads
        return pf

    def _send_await_dump_ack(self, frame, timeout: float = 2.0):
        """Send one dump frame and wait for the device's 0x64 ack.

        The FM9 acks each 0x77/0x78/0x79 frame with `fn 0x64 [acked-fn] ..`.
        Waiting for it is the flow control that keeps chunks from being
        dropped; the sim answers instantly, real hardware in a few ms.
        """
        self.outp.send(mido.Message("sysex", data=frame[1:-1]))
        want = frame[5]                     # the fn we expect acked
        deadline = time.time() + timeout
        while time.time() < deadline:
            for msg in self.inp.iter_pending():
                if msg.type != "sysex":
                    continue
                d = list(msg.data)
                if len(d) > 5 and d[4] == 0x64 and d[5] == want:
                    return d
            time.sleep(0.002)
        return None                         # proceed; the read-back is the judge

    def install_user_cab(self, raw: bytes, slot: int, filename: str = ""):
        """Send a validated IR file to a whitelisted user-cab slot.

        Same discipline as install_preset: parser-validated frames only,
        their own guard, a whitelist with an empty default. The model-byte
        rewrite (artists export IRs under whatever device their editor
        had) and the slot addressing are UNVERIFIED on hardware until the
        first live install; callers verify via read_user_cab.
        """
        from fm9 import cabfile
        allowed = get_cab_slots()
        if not allowed:
            raise PermissionError(
                "IR installs are disabled: no user-cab slots configured. "
                "Set TONECOMMAND_CAB_SLOTS (env or .env), e.g. "
                "TONECOMMAND_CAB_SLOTS=0-15 for what the editor shows as "
                "User Cab 1-16, choosing slots on YOUR unit that are safe "
                "to overwrite")
        if slot not in allowed:
            raise PermissionError(
                f"IR install to user cab {slot + 1} (index {slot}) refused: "
                f"configured cab slots are "
                f"{sorted(allowed)[0]}-{sorted(allowed)[-1]}")
        cf, _idx, _tag = self.install_user_cab_at(raw, 1, slot + 1,
                                                  filename)
        return cf

    def read_user_cab_addr(self, idx: int, tag: int, timeout: float = 4.0):
        """Request the user cab at (idx, tag) back via fn 0x19.

        Returns (head_payload, chunk_payloads) when the device answered,
        else None. An empty slot still ANSWERS (all-0x7F body per the
        upstream capture), which is what makes read-probing a destination
        safe and conclusive before any write.
        """
        req = p.envelope(0x19, [(idx >> 7) & 0x7F, idx & 0x7F, tag & 0x7F])
        self.cab_guard.check(req[5])
        self._drain()
        self.outp.send(mido.Message("sysex", data=req[1:-1]))
        deadline = time.time() + timeout
        head, chunks, done = None, [], False
        while time.time() < deadline and not done:
            for msg in self.inp.iter_pending():
                if msg.type != "sysex":
                    continue
                data = list(msg.data)
                if len(data) < 6 or data[:3] != list(p.MFR):
                    continue
                if data[4] == 0x7A:
                    head = data[5:-1]
                elif data[4] == 0x7B:
                    chunks.append(data[5:-1])
                elif data[4] == 0x7C:
                    done = True
                    break
            time.sleep(0.005)
        if head is None and not chunks:
            return None
        return (head or [], chunks)

    #: How a (bank, number) shown by the editor might encode on the wire.
    #: Candidate A: the head tag carries the bank (0x10 = bank 1). B: a
    #: flat index across 512-slot banks under the captured 0x10 tag.
    #: NEITHER is assumed: the device is read-probed and only an encoding
    #: it answered for is ever used to write. See install_user_cab_at.
    @staticmethod
    def _cab_addr_candidates(bank: int, number: int):
        yield (number - 1, 0x10 + (bank - 1))
        yield ((bank - 1) * 512 + (number - 1), 0x10)

    def probe_cab_encoding(self, bank: int, number: int):
        """The (idx, tag) this device actually answers for (bank, number).

        Read-only. Raises PermissionError-free RuntimeError when nothing
        answers, so callers never fall through to a guessed write.
        """
        for idx, tag in self._cab_addr_candidates(bank, number):
            got = self.read_user_cab_addr(idx, tag, timeout=2.0)
            if got is not None:
                return idx, tag
        raise RuntimeError(
            f"the device did not answer a read for user cab bank {bank} "
            f"number {number} under any known addressing; refusing to "
            "write blind")

    def install_user_cab_at(self, raw: bytes, bank: int, number: int,
                            filename: str = ""):
        """Send a validated IR to user-cab (bank, number), as the editor
        numbers them. Whitelisted flat as (bank-1)*512+(number-1); the
        destination is read-probed first and the write uses only the
        addressing the device itself answered for; verified by callers via
        read_user_cab_addr comparing byte-for-byte.
        """
        from fm9 import cabfile
        if bank < 1 or number < 1:
            raise ValueError("bank and number are 1-based, as FM9-Edit "
                             "shows them")
        flat = (bank - 1) * 512 + (number - 1)
        allowed = get_cab_slots()
        if not allowed:
            raise PermissionError(
                "IR installs are disabled: no user-cab slots configured. "
                "Set TONECOMMAND_CAB_SLOTS (env or .env) with flat indices "
                "(bank 1 = 0-511, bank 2 = 512-1023), choosing cabs on "
                "YOUR unit that are safe to overwrite")
        if flat not in allowed:
            raise PermissionError(
                f"IR install to user cab bank {bank} number {number} "
                f"(flat index {flat}) refused: it is outside "
                "TONECOMMAND_CAB_SLOTS")
        cf = cabfile.parse(raw, filename)   # re-validated at this boundary
        idx, tag = self.probe_cab_encoding(bank, number)
        frames = cabfile.retarget(cf, idx, tag=tag)
        self._drain()
        for frame in frames:
            self.cab_guard.check(frame[5])
            self.outp.send(mido.Message("sysex", data=frame[1:-1]))
            time.sleep(0.03)
        time.sleep(1.0)
        return cf, idx, tag

    def rename_preset(self, name: str):
        self._drain()
        self._send(p.build_rename_preset(name))
        time.sleep(0.2)

    def rename_scene(self, scene_1based: int, name: str):
        self._drain()
        self._send(p.build_set_scene_name(scene_1based - 1, name))
        time.sleep(0.2)

    def read_display_name(self, effect_id: int, param_id: int) -> str | None:
        """Read a param's display string via the type-name query (sub 0x1F)."""
        def want(d):
            got = p.parse_type_name_response(d)
            if got and got[0] == effect_id and got[1] == param_id:
                return got[2]
            return None
        return self._request(p.build_get_type_name(effect_id, param_id), want,
                             timeout=0.8)

    def mod_source_name(self, slot_1based: int) -> str | None:
        """Read the display name of a modifier slot's current source."""
        return self.read_display_name(p.mod_slot_eid(slot_1based), p.MOD_PID_SOURCE)

    def read_modifier(self, slot_1based: int) -> list[int] | None:
        """The slot's raw field values, as the device holds them."""
        return self.bulk_read(p.mod_slot_eid(slot_1based))

    def find_donor_slot(self, skip: set[int] | None = None) -> tuple[int, list[int]] | None:
        """A modifier slot in this preset that the DEVICE built, to copy the
        transfer curve from.

        Finding 12: bindings written from scratch come out reversed or dead,
        and the working practice is to clone a proven slot and retarget only
        its target ids. A slot the owner made on the front panel is proven by
        the fact that it exists and works, which is a stronger guarantee than
        anything this project can construct out of defaults.

        `skip` is how the caller keeps its OWN from-scratch slots out of the
        pool. A slot this tool built out of MOD_DEFAULT_FIELDS looks exactly
        like a device-built one from here, so cloning it would launder a
        default into something the log calls a clone, one slot at a time.
        """
        skip = skip or set()
        for slot in range(1, p.MOD_SLOT_COUNT + 1):
            if slot in skip:
                continue
            vals = self.read_modifier(slot)
            if vals and len(vals) > p.MOD_PID_TARGET_PARAM \
                    and vals[p.MOD_PID_TARGET_EFFECT]:
                return slot, vals
        return None

    def bind_modifier(self, slot_1based: int, target_effect_id: int,
                      target_param_id: int, source_ordinal: int,
                      donor: list[int] | None = None,
                      min_norm: float | None = None,
                      max_norm: float | None = None) -> bool:
        """Bind a modifier slot: pedal/controller source -> block parameter.
        Edit buffer only. Returns whether a donor curve was used.

        The write ORDER is not a style choice. Finding 17: rewrite the slot's
        own fields as continuous writes FIRST, then the target effect id, the
        target param id and the source as discrete writes, in that order.
        Verified across sixteen presets, two of them ear-confirmed. The
        earlier code here did it the other way round, targets first and a
        partial curve after, which is the shape finding 16 describes: it reads
        healthy immediately, survives a store, and comes back with target and
        source zeroed once the preset reloads.

        A fresh slot is ALL zeroes, curve included, and a zero curve maps
        every pedal position to zero, so a bind that does not write the curve
        is a bind that silently does nothing.
        """
        eid = p.mod_slot_eid(slot_1based)
        if donor:
            fields = {pid: donor[pid] / 65534 for pid in p.MOD_FIELD_PIDS
                      if pid < len(donor)}
        else:
            fields = dict(p.MOD_DEFAULT_FIELDS)
        # The caller's range floor outranks the donor's, since that is the one
        # thing they asked for by name.
        if min_norm is not None:
            fields[p.MOD_PID_MIN] = min_norm
        if max_norm is not None:
            fields[p.MOD_PID_MAX] = max_norm

        for pid in p.MOD_FIELD_PIDS:
            if pid not in fields:
                continue
            self._drain()
            self._send(p.build_set_param_continuous(eid, pid, fields[pid]))
            time.sleep(0.08)
        for pid, val in ((p.MOD_PID_TARGET_EFFECT, target_effect_id),
                         (p.MOD_PID_TARGET_PARAM, target_param_id),
                         (p.MOD_PID_SOURCE, source_ordinal)):
            self._drain()
            self._send(p.build_set_param_discrete(eid, pid, val))
            time.sleep(0.15)
        return bool(donor)

    def clear_modifier(self, slot_1based: int) -> None:
        """Detach a modifier slot, leaving the parameter to its own value.

        Zeroing the target and the source is what the device itself does to a
        slot that fails its load-time validation (finding 16), so it is the
        device's own idea of an empty slot rather than ours.
        """
        eid = p.mod_slot_eid(slot_1based)
        for pid in (p.MOD_PID_TARGET_EFFECT, p.MOD_PID_TARGET_PARAM,
                    p.MOD_PID_SOURCE):
            self._drain()
            self._send(p.build_set_param_discrete(eid, pid, 0))
            time.sleep(0.15)

    def plan_splice(self, row_1based: int, at_col: int) -> dict:
        """What a splice at this cell WOULD do, without doing any of it.

        Split out of splice_block because the answer has to be shown before
        anyone approves it. Two of the consequences are not equivalent:
        re-selecting the preset puts the slid blocks back, while nothing puts
        a spent pass-through cell back on its own, since shunts cannot be
        re-inserted (finding 8). Discarding the whole edit is the only route,
        and a store makes the loss permanent (finding 27). A confirmation
        that shows both the same way is not informed consent, so they are
        reported separately.

        Refusals carry a `reason` as well as prose, so a caller can say which
        wall it hit rather than a generic no.
        """
        cells = {(c.row + 1, c.col + 1): c for c in (self.read_grid() or [])}
        row = row_1based
        if not any(r == row for (r, _) in cells):
            return {"ok": False, "reason": "empty_row", "moves": [],
                    "detail": f"row {row} is empty; nothing to splice into"}
        if (row, at_col) not in cells:
            return {"ok": False, "reason": "already_free", "moves": [],
                    "detail": f"row {row} col {at_col} is already free, so the "
                              "block can be placed directly rather than spliced"}

        # Slack is the first column right that can absorb the shift: a free
        # cell (nothing lost) or a shunt (spent, and not re-insertable).
        slack = next((c for c in range(at_col + 1, p.GRID_COLS + 1)
                      if (row, c) not in cells or cells[(row, c)].is_shunt), None)
        if slack is None:
            return {"ok": False, "reason": "no_room_right", "moves": [],
                    "detail": f"no free or pass-through cell right of col "
                              f"{at_col} on row {row}: a block would have to "
                              "fall off the end of the grid. Try another preset, "
                              "or free a slot on this row"}

        # Cross-row feeds into the span would be silently broken: the cables
        # redrawn here are same-row only, and multi-row geometry is not decoded.
        foreign = [c for c in range(at_col, slack + 1)
                   if (row, c) in cells
                   and cells[(row, c)].cable_in_mask & ~(1 << row)]
        if foreign:
            return {"ok": False, "reason": "fed_from_another_row", "moves": [],
                    "detail": f"cells {foreign} on row {row} are fed from "
                              "another row, and the same-row redraw would "
                              "silently break routing this code does not model"}

        moves = []
        for col in range(slack - 1, at_col - 1, -1):
            cell = cells.get((row, col))
            if cell is None or cell.effect_id is None:
                continue                       # a shunt in the span: it dies
            fam = self.reg.family_of_effect_id(cell.effect_id)
            moves.append({"effect_id": cell.effect_id,
                          "family": fam[0] if fam else None,
                          "instance": fam[1] if fam else None,
                          "from_col": col, "to_col": col + 1})
        return {"ok": True, "reason": "", "row": row, "at_col": at_col,
                "slack_col": slack, "moves": moves,
                "spends_shunt": (row, slack) in cells,
                "detail": ""}

    def splice_block(self, row_1based: int, at_col: int, effect_id: int,
                     settle: float = 0.35) -> dict:
        """Insert a block into a PACKED row, shifting neighbours right.

        add_block can only replace a free pass-through cell, and real presets
        keep none before the amp (issue #10). Splicing needs three things that
        are all verified on hardware: blocks displace without loss (finding
        25), cables can be removed selectively (finding 24), and same-row
        draws work on rows 2-5 (findings 6 and 20).

        What it will do is decided by plan_splice, so a caller can show the
        consequences first and execute the same decision afterwards.
        """
        intent = self.plan_splice(row_1based, at_col)
        if not intent["ok"]:
            return dict(intent, moved=[])
        row, slack = intent["row"], intent["slack_col"]

        moved = []
        for move in intent["moves"]:
            col = move["from_col"]
            self.place_block(row, col, 0)      # clear frees the cell AND cables
            time.sleep(settle)
            self.place_block(row, col + 1, move["effect_id"])
            time.sleep(settle)
            moved.append((move["effect_id"], col, col + 1))

        self.place_block(row, at_col, effect_id)
        time.sleep(settle)

        # Clearing destroys cables, so redraw the whole disturbed span.
        after = {(c.row + 1, c.col + 1): c for c in (self.read_grid() or [])}
        span = sorted(c for (r, c) in after if r == row and c >= max(1, at_col - 1))
        for a, b in zip(span, span[1:]):
            if b == a + 1:
                self.connect_cells(row, a, row)
                time.sleep(settle)

        cells_after = self.read_grid() or []
        final = {(c.row + 1, c.col + 1): c for c in cells_after}
        placed = final.get((row, at_col))
        # "nothing breaks" has to be proven by walking Input to Output over the
        # real cable masks. Counting members, or even counting cells with no
        # input cable, passes for a block that is present and stranded off the
        # path - the silent-preset class this project keeps meeting.
        st = {b.effect_id: b for b in self.status_dump() or []}
        alive, why = scene_alive(cells_after, st, self.reg)
        landed = placed is not None and placed.effect_id == effect_id
        return {
            "ok": landed and alive,
            "placed_at": (row, at_col),
            "moved": moved,
            "slack_col": slack,
            "spent_a_shunt": intent["spends_shunt"],
            "alive": alive,
            "detail": (f"spliced in, live signal path confirmed: {why}"
                       if landed and alive else
                       f"block did not land at row {row} col {at_col}"
                       if not landed
                       else f"NO LIVE SIGNAL PATH after splice: {why}"),
        }

    def connect_cells(self, src_row: int, src_col: int, dest_row: int,
                      disconnect: bool = False):
        op = p.ROUTING_DISCONNECT if disconnect else p.ROUTING_CONNECT
        self._drain()
        self._send(p.build_set_grid_routing(src_row, src_col, dest_row, op))
        time.sleep(0.25)

    def get_param_wire(self, spec: ParamSpec, channel: int | None = None) -> int | None:
        """Read one param's wire16 value via bulk read. `channel` 0..3 picks the
        channel copy; defaults to the block's current channel."""
        values = self.bulk_read(spec.effect_id)
        if not values:
            return None
        if spec.effect_id not in self._channels:
            # unpopulated channel cache silently collapses every channel
            # read to channel A (issue #12); populate before indexing
            self.status_dump()
        chans = max(1, self._channels.get(spec.effect_id, 1))
        stride = len(values) // chans if chans > 1 else len(values)
        if channel is None:
            # channel cache goes stale after set_channel/scene changes; a
            # live 0x0B query is cheap and keeps reads on the right channel
            live = self.get_channel(spec.effect_id)
            if live is not None:
                self._current_channel[spec.effect_id] = live
            channel = self._current_channel.get(spec.effect_id, 0)
        idx = min(channel, chans - 1) * stride + spec.param_id
        if idx >= len(values):
            idx = spec.param_id
        return values[idx] if idx < len(values) else None

    def get_param_display(self, spec: ParamSpec) -> float | str | None:
        wire = self.get_param_wire(spec)
        if wire is None:
            return None
        if spec.kind == "enum":
            return wire
        if spec.dmin is None or spec.dmax is None:
            return wire / 65534
        return round(p.normalized_to_display(wire / 65534, spec.dmin, spec.dmax,
                                             spec.scale), 2)

    def set_param_display(self, spec: ParamSpec, display_value: float) -> SetResult:
        """Set a continuous param by display value, with read-back verify."""
        if spec.dmin is None or spec.dmax is None:
            return SetResult(False, f"{spec.name} has no calibrated range", None, None)
        before = self.get_param_display(spec)
        normalized = p.display_to_normalized(display_value, spec.dmin, spec.dmax, spec.scale)
        frame = p.build_set_param_continuous(spec.effect_id, spec.param_id, normalized)
        self._param_echo(frame, spec.effect_id, spec.param_id, timeout=0.3)
        # The device applies the write asynchronously; a bulk read fired too
        # soon returns the pre-write value. Settle, then verify with retries.
        target = min(spec.dmax, max(spec.dmin, display_value))
        quantum = (spec.dmax - spec.dmin) / 65534 * 2 + 1e-6
        tol = max(quantum, 0.02)
        after = None
        ok = False
        for _ in range(4):
            time.sleep(0.15)
            after = self.get_param_display(spec)
            if isinstance(after, (int, float)) and abs(after - target) <= tol:
                ok = True
                break
        return SetResult(ok, "verified by read-back" if ok else f"read-back mismatch: {after}",
                         before, after)

    def set_param_wire(self, spec: ParamSpec, wire: int) -> SetResult:
        """Set a parameter to an EXACT wire value, verified by integer equality.

        For restoring a snapshot, this is the only correct write. Going back
        through display units loses parameters whose meaning is the raw wire
        rather than a position on a calibrated scale: a cab slot is an ordinal
        stored directly in the wire, so display 1.64 on a 0-1023 scale came
        back as cab 1 instead of cab 105 and an undo silently loaded the wrong
        cabinet.

        The continuous path is right for both kinds. For a calibrated
        parameter it reproduces the value; for an ordinal it writes the
        ordinal, which is the same reasoning that makes a continuous 0.0 the
        way to select ordinal 0 (see set_param_ordinal).

        Verification is integer equality, not a tolerance, because there is a
        single correct answer and we already know exactly what it is.
        """
        before = self.get_param_wire(spec)
        wire = max(0, min(65534, int(wire)))
        if before == wire:
            return SetResult(True, "already there", before, before)

        # Two encodings exist and the parameter does not say which it uses.
        # For a calibrated parameter the wire is a normalized 0-65534 position
        # and the continuous frame reproduces it. For an ordinal-bearing one
        # the wire IS the ordinal and a continuous write gets scaled against
        # the parameter's own range instead: writing cab 105 that way landed
        # on cab 1, because 105/65534 of the way along 0-1023 is 1.64.
        #
        # spec.kind does not separate them (CABINET_TYPE1 declares float while
        # holding an ordinal), so rather than guess from metadata this tries
        # both and lets the read-back decide. That is only sound because the
        # check is integer equality against a value we already know.
        attempts = (
            ("continuous", lambda: p.build_set_param_continuous(
                spec.effect_id, spec.param_id, wire / 65534)),
            ("ordinal", lambda: (p.build_set_param_discrete(
                spec.effect_id, spec.param_id, wire) if wire else
                p.build_set_param_continuous(spec.effect_id, spec.param_id, 0.0))),
        )
        after = None
        for how, build in attempts:
            self._param_echo(build(), spec.effect_id, spec.param_id, timeout=0.3)
            for _ in range(3):
                time.sleep(0.15)
                after = self.get_param_wire(spec)
                if after == wire:
                    return SetResult(True, f"verified by read-back ({how})",
                                     before, after)
        return SetResult(False, f"read-back mismatch: wanted {wire}, got {after}",
                         before, after)

    def set_param_ordinal(self, spec: ParamSpec, ordinal: int) -> SetResult:
        """Set a discrete (enum/type) param by roster ordinal.

        Ordinal 0 CANNOT go through the discrete path: a sub 09 frame with
        a zero value is the device's zeroed-GET no-op, so the set silently
        does nothing (caught by recipe replay in the sim, 2026-08-22 -
        which also means earlier zero-ordinal sets like Small Room reverb
        may never have landed; verify on hardware). Send a continuous 0.0
        instead, which writes wire 0 = ordinal 0.
        """
        before = self.get_param_display(spec)
        if ordinal == 0:
            frame = p.build_set_param_continuous(spec.effect_id, spec.param_id, 0.0)
        else:
            frame = p.build_set_param_discrete(spec.effect_id, spec.param_id, ordinal)
        self._param_echo(frame, spec.effect_id, spec.param_id, timeout=0.6)
        after = self.get_param_display(spec)
        return SetResult(True, "sent (discrete)", before, after)

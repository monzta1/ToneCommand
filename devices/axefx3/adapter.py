"""Independent Axe-Fx III transport with opt-in, verified edit-buffer writes.

No FM9 inheritance, process-wide protocol switch, global routing restore,
preset upload, firmware traffic or physical-volume guarantee. Unported
capabilities decline explicitly instead of calling an FM9 implementation.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
import re
import threading
import time

import mido

from fm9.adapter import Capabilities, ReadPath
from fm9.device import FM9NotFound, SetResult
from fm9 import protocol as shared
from fm9.safety import sysex_guard
from . import protocol, audio_safety, cab_mix, models, cab_selection, grid, modifiers, pedal_control
from .registry import Registry, SUPPORTED_FIRMWARE
from . import evidence, nam_slots, fw33_profile


class AxeFxIII:
    model = protocol.MODEL
    device_name = "Axe-Fx III"
    # A narrower transport than the FM9, using the same invariant guard.
    guard = sysex_guard("Axe-Fx III", (1, 8, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x13, 0x1F))

    def __init__(self, ports=None):
        self._injected_ports = ports is not None
        if ports is None:
            from fm9 import midi_transport
            try:
                ports = midi_transport.open_ports("axe-fx")
            except midi_transport.TransportError as exc:
                raise FM9NotFound(str(exc).replace("FM9", "Axe-Fx III")) from exc
        self.inp, self.outp = ports
        self._lock = threading.RLock()
        self._edit_target = None
        self._edit_owner = None
        self._approved_frame = None
        self._grid_move_permit = None
        # Developer fixture setup only, never an executor action or API route.
        self._grid_fixture_permit = None
        self._channels = {}
        self._current_channel = {}
        self.reg = Registry()
        try:
            firmware = self.firmware_label()
            if not firmware or self.current_preset() is None:
                raise FM9NotFound("Axe-Fx III did not answer; no writes were attempted")
            self.reg = Registry(firmware)
        except BaseException:
            self.close()
            raise

    def capabilities(self):
        verified=self.reg.firmware in SUPPORTED_FIRMWARE
        if self.reg.firmware=='33.00-beta.20261006':
            from . import fw33
            verified=verified and fw33.runtime_write_error(self) is None
        return Capabilities(read_path=ReadPath.DEVICE, reads_slot_names=True,
                            verifies_writes=verified,
                            has_scenes=True, can_rename=True)

    def close(self):
        try:
            self.inp.close()
        finally:
            self.outp.close()

    def _pending(self):
        for message in self.inp.iter_pending():
            if message.type == "sysex":
                data = list(message.data)
                if protocol.valid_reply(data):
                    yield data

    def _drain(self):
        for _ in self.inp.iter_pending():
            pass

    def _send(self, frame):
        if (not frame or frame[0] != 0xF0 or frame[-1] != 0xF7
                or not protocol.valid_reply(frame[1:-1])):
            raise ValueError("Not a valid Axe-Fx III frame")
        self.guard.check(frame[5])
        fn, payload = frame[5], frame[6:-2]
        if self.reg.firmware == '33.00-beta.20261006':
            from . import fw33
            fw33.check_frame(self, frame)
        readonly = ((self.reg.firmware == '33.00-beta.20261006' and nam_slots.is_name_request(frame))
                    or (fn in (8, 0x13) and payload == [])
                    or (fn in (0x0D, 0x1F) and len(payload) == 2)
                    or (fn == 0x0E and len(payload) == 1)
                    or (fn == 0x0C and payload == [127])
                    or (fn in (0x0A, 0x0B) and len(payload) == 3 and payload[2] == 127)
                    or (fn == 1 and len(payload) == 6 and payload[:2] == [0x10, 0]
                        and (shared.decode14(payload[4], payload[5]) != 0
                             or (self.reg.firmware in SUPPORTED_FIRMWARE and
                                 shared.decode14(payload[2],payload[3]) in protocol.NUMERIC_ZERO_EFFECTS)))
                    or frame == grid.reframe(shared.build_request_grid_layout()))
        if not readonly:
            # A closed developer measurement cannot fall through to a newly
            # released general setter, even if that value is normally valid.
            if self.reg.firmware==fw33_profile.KEY:
                from . import zero_tempo_calibration
                if (isinstance(getattr(self,'_zero_tempo_calibration',None),zero_tempo_calibration.Probe)
                        and not zero_tempo_calibration.allowed(self,frame)):
                    raise PermissionError('Only the current closed calibration literal may be written')
            if self._approved_frame != tuple(frame):
                raise PermissionError("Raw writes must pass the verified Axe-Fx III action path")
            if fn == 1:
                from . import album_build
                from . import inherited_controls_probe
                if inherited_controls_probe.allowed(self,frame):
                    pass  # Exact immutable developer fixture, never a generic SET.
                elif album_build.frame_allowed(self,frame):
                    pass  # Exact active reviewed operation, plus approved frame above.
                elif (self.reg.firmware=='33.00-beta.20261006'
                        and getattr(self,'_fw33_tempo_permit',None)==tuple(frame)):
                    from . import tempo_control
                    if not tempo_control.allowed(self,frame):
                        raise PermissionError('Outside the exact reviewed Tempo NONE operation')
                elif (self.reg.firmware=='33.00-beta.20261006'
                        and getattr(self,'_zero_tempo_permit',None)==tuple(frame)):
                    from . import zero_tempo_calibration
                    if not zero_tempo_calibration.allowed(self,frame):
                        raise PermissionError('Outside the closed zero/tempo calibration')
                elif (self.reg.firmware == '33.00-beta.20261006'
                        and getattr(self,'_effects_calibration_permit',None)==tuple(frame)):
                    from . import effects_calibration
                    if not effects_calibration.allowed(self,frame):
                        raise PermissionError('Outside the fixed recorded effect calibration')
                elif (self.reg.firmware == '33.00-beta.20261006'
                        and getattr(self,'_effect_probe_permit',None)==tuple(frame)):
                    from . import effect_probe
                    if not effect_probe.allowed(self,frame):
                        raise PermissionError('Outside the fixed recorded Drive calibration')
                elif (self.reg.firmware == '33.00-beta.20261006'
                        and getattr(self, '_cab_probe_permit', None) == tuple(frame)):
                    from . import cab_probe
                    if not cab_probe.allowed(self, frame):
                        raise PermissionError('Outside the fixed developer Cab measurement')
                elif (self.reg.firmware == '33.00-beta.20261006'
                        and getattr(self, '_amp_probe_permit', None) == tuple(frame)):
                    from . import amp_probe
                    if not amp_probe.allowed(self, frame):
                        raise PermissionError('Outside the fixed developer AMP measurement')
                elif payload[:2] in ([9, 0], [0x52, 0]) and len(payload) == 15:
                    effect_id = shared.decode14(payload[2], payload[3])
                    family = self.reg.family_of_effect_id(effect_id)
                    if effect_id in range(3, 35):
                        family = ("MODIFIER", effect_id - 2)
                    if family is None or family[0] == "GLOBAL":
                        raise PermissionError("No generic/global parameter writes on Axe-Fx III")
                    pid = shared.decode14(payload[4], payload[5])
                    tempo_none = (family[0] == "DELAY" and pid == 9
                                  and frame == protocol.param_frame(effect_id, 9, 0, opcode=0x52))
                    if family[0] == "MODIFIER":
                        source = shared.decode_f32_septets(payload[6:11])
                        if (not math.isfinite(source) or source != int(source)
                                or pid not in (0, 10)):
                            raise PermissionError("No arbitrary modifier field writes")
                        expected = (modifiers.source_frame(family[1], int(source)) if pid == 0
                                    else pedal_control.auto_frame(family[1], int(source)))
                        if frame != expected:
                            raise PermissionError("Modifier SET differs from captured encoding")
                    elif family[0] == "CABINET" and pid in (0, 1, 4, 5):
                        value = shared.decode_f32_septets(payload[6:11])
                        if (not math.isfinite(value) or value != int(value) or
                                frame != cab_selection.frame(effect_id, pid, int(value))):
                            raise PermissionError("Cab selector is not a verified discrete frame")
                    elif self.reg.firmware == '33.00-beta.20261006' and effect_id == 206 and pid == 0:
                        if getattr(self, '_nam_select_permit', None) != tuple(frame):
                            raise PermissionError('NAM selector requires its independently verified operation')
                    elif pid == models.SELECTORS.get(family[0]):
                        ordinal = shared.decode_f32_septets(payload[6:11])
                        names = models.roster(self.reg, family[0], selectable=True)
                        if (not math.isfinite(ordinal) or ordinal != int(ordinal)
                                or str(int(ordinal)) not in names):
                            raise PermissionError("Model ordinal has not been enabled")
                        models.target(self.reg, family[0], effect_id, names[str(int(ordinal))])
                        if frame != protocol.param_frame(effect_id, pid, ordinal, opcode=9):
                            raise PermissionError("Model SET is not the captured frame")
                    elif pid == 0 and effect_id not in protocol.NUMERIC_ZERO_EFFECTS:
                        raise PermissionError("Parameter zero has no verified numeric or model selector")
                    elif not tempo_none:
                        self.reg.spec(family[0], pid, family[1])
                elif payload[:2] == [0x3A, 0]:
                    if len(payload) != 15 or frame != pedal_control.allocation_frame(shared.decode14(*payload[2:4])):
                        raise PermissionError("Unverified modifier allocation frame")
                elif (self.reg.firmware == '33.00-beta.20261006'
                      and getattr(self, '_serial_session', None) is not None
                      and payload[:2] in ([0x30,0],[0x32,0],[0x35,0])):
                    from . import serial_build
                    if not serial_build.allowed(self,frame):
                        raise PermissionError('Outside the reviewed measured serial sequence')
                elif (self.reg.firmware == '33.00-beta.20261006'
                      and getattr(self, '_block_probe_permit', None) == tuple(frame)):
                    from . import block_probe
                    if not block_probe.allowed(self,frame):
                        raise PermissionError('Outside the exact ordered developer block fixture')
                elif (self.reg.firmware == '33.00-beta.20261006'
                      and getattr(self, '_row_probe_permit', None) == tuple(frame)):
                    from . import row_probe
                    if not row_probe.allowed(self,frame):
                        raise PermissionError('Outside the exact ordered developer row fixture')
                elif (self.reg.firmware == '33.00-beta.20261006'
                      and getattr(self, '_grid_probe_permit', None) == tuple(frame)):
                    from . import grid_probe
                    if not grid_probe.allowed(self,frame):
                        raise PermissionError('Outside the exact captured developer grid fixture')
                elif payload[:2] == [0x36, 0]:
                    from .insertion import move_right_frame
                    fixture = (getattr(self, '_edit_target', None) == 323 and self.reg.firmware == '32.06'
                               and getattr(self, '_grid_fixture_permit', None) == tuple(frame)
                               and frame == grid.fixture_left_frame())
                    if ((frame != move_right_frame() and not fixture)
                            or self._grid_move_permit != tuple(frame)):
                        raise PermissionError('Grid move must belong to the checked insertion transaction')
                elif payload[:2] == [0x33, 0]:
                    if (getattr(self, '_edit_target', None) != 323 or self.reg.firmware != '32.06'
                            or getattr(self, '_grid_fixture_permit', None) != tuple(frame)
                            or frame not in (grid.fixture_remove_frame(2), grid.fixture_remove_frame(3))):
                        raise PermissionError('Removal is limited to the explicitly approved developer fixture')
                    col = 2 if frame == grid.fixture_remove_frame(2) else 3
                    cell = grid.snapshot(self.read_grid()).get((3,col))
                    if not cell or cell[1] or cell[0] not in (118,46):
                        raise PermissionError('Only test Drive1 or Compressor1 may be removed')
                elif payload[:2] in ([0x30, 0], [0x32, 0], [0x35, 0]):
                    if not grid.valid_write(frame, self.reg):
                        raise PermissionError("Unverified/destructive grid frame")
                elif payload[:2] == [0x26, 0] and self.reg.firmware == '33.00-beta.20261006':
                    if getattr(self, '_store_permit', None) != tuple(frame):
                        raise PermissionError('Store requires its bounded same-slot operation')
                elif payload[:2] not in ([0x28, 0], [0x2B, 0]):
                    raise PermissionError("Editor command has not been enabled for Axe-Fx III")
            elif not (fn == 0x0C and len(payload) == 1 and payload[0] in range(8)) \
                    and not (fn in (0x0A, 0x0B) and len(payload) == 3
                             and payload[2] in range(2 if fn == 0x0A else 4)):
                raise PermissionError("Command is not an enabled Axe-Fx III edit")
            self._check_edit_target()
        self.outp.send(mido.Message("sysex", data=frame[1:-1]))

    def _request(self, frame, parse, timeout=1.0):
        with self._lock:
            self._drain()
            self._send(frame)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                for data in self._pending():
                    got = parse(data)
                    if got is not None:
                        return got
                    nack = shared.parse_multipurpose(data)
                    if nack is not None and nack[1] != 0:
                        raise RuntimeError(f"Axe-Fx III rejected function {nack[0]}: {nack[1]}")
                time.sleep(.005)
        return None

    def firmware_label(self):
        from .fw33_profile import identity_key
        got = self._request(protocol.envelope(8, []),
                            lambda d: tuple(d) if d[4] == 8 and len(d) >= 8 else None)
        return identity_key(got) or (f"{got[5]}.{got[6]:02d}" if got else "")

    def current_preset(self):
        return self._request(protocol.envelope(0x0D, [127, 127]), shared.parse_patch_name)

    def current_scene(self):
        return self._request(protocol.envelope(0x0C, [127]), shared.parse_scene)

    def scene_name(self, scene=None):
        if scene is not None and (type(scene) is not int or scene not in range(1, 9)):
            raise ValueError("Scene must be 1..8")
        return self._request(protocol.envelope(0x0E, [127 if scene is None else scene - 1]),
                             shared.parse_scene_name)

    def status_dump(self):
        blocks = self._request(protocol.envelope(0x13, []), shared.parse_status_dump, 1.5)
        if blocks is not None:
            self._channels = {b.effect_id: b.channels_supported for b in blocks}
            self._current_channel = {b.effect_id: b.channel for b in blocks}
        return blocks

    def slot_name(self, preset):
        # Keep the historical tested range; do not infer extra slots.
        if type(preset) is not int or preset not in range(512):
            raise ValueError("Preset must be in the verified range 0..511")
        def parse(data):
            got = shared.parse_patch_name_full(data)
            return got if got is not None and got.number == preset else None
        return self._request(protocol.envelope(0x0D, list(shared.encode14(preset))), parse)

    def is_slot_empty(self, preset):
        got = self.slot_name(preset)
        return got.empty if got else None

    def scan_slots(self, start=0, end=511):
        if type(start) is not int or type(end) is not int or not 0 <= start <= end < 512:
            raise ValueError("Invalid preset name range")
        def walk():
            for number in range(start, end + 1):
                got = self.slot_name(number)
                if got is not None:
                    yield got
        return walk()

    def get_channel(self, effect_id):
        def parse(data):
            got = shared.parse_channel(data)
            return got[1] if got and got[0] == effect_id else None
        return self._request(protocol.envelope(0x0B, [*shared.encode14(effect_id), 127]), parse)

    def get_bypass(self, effect_id):
        def parse(data):
            got = shared.parse_bypass(data)
            return got[1] if got and got[0] == effect_id else None
        return self._request(protocol.envelope(0x0A, [*shared.encode14(effect_id), 127]), parse)

    def bulk_read(self, effect_id, timeout=1.5):
        with self._lock:
            self._drain()
            self._send(protocol.envelope(0x1F, list(shared.encode14(effect_id))))
            deadline = time.monotonic() + timeout
            count = None
            values = []
            while time.monotonic() < deadline:
                for data in self._pending():
                    head = shared.parse_bcast_head(data)
                    if head is not None:
                        if len(data) != 10:
                            return None
                        count = head[1] if head[0] == effect_id else None
                        values = []
                    elif data[4] == shared.FN_BCAST_BODY and count is not None:
                        body = data[7:-1]
                        if (not body or len(body) % 3 or any(b > 3 for b in body[2::3])):
                            return None
                        values.extend(shared.parse_bcast_body(data) or [])
                        if len(values) > count:
                            return None
                    elif data[4] == shared.FN_BCAST_END and count is not None:
                        return values if len(data) == 6 and len(values) == count else None
                time.sleep(.005)
        return None

    def read_display_text(self, effect_id, param_id):
        def parse(data):
            got = protocol.parse_display_text_response(data)
            return got[2] if got and got[:2] == (effect_id, param_id) else None
        return self._request(protocol.display_query(effect_id, param_id), parse)

    def read_grid(self, timeout=2.0):
        return self._request(grid.reframe(shared.build_request_grid_layout()),
                             protocol.parse_grid_layout, timeout)

    def read_modifier(self, slot_1based):
        return self.bulk_read(modifiers.slot_eid(slot_1based))

    def modifier_report(self):
        with self._lock:
            return modifiers.inspect(self)

    def assign_existing_modifier(self, slot_1based, target_effect_id, target_param_id, source_ordinal):
        with self._lock:
            self._check_edit_target()
            return modifiers.assign_existing(self, slot_1based, target_effect_id, target_param_id, source_ordinal)

    def create_wah_modifier(self, effect_id, source_ordinal):
        with self._lock:
            self._check_edit_target()
            return modifiers.create_wah(self, effect_id, source_ordinal)

    def bind_pedal_control(self, effect_id, source, auto_engage=None):
        with self._lock:
            self._check_edit_target()
            return pedal_control.bind(self, effect_id, source, auto_engage)

    def place_block(self, position, effect_id):
        with self._lock:
            self._check_edit_target()
            return grid.place(self, position, effect_id)

    def connect_cells(self, src_row, src_col, dest_row):
        with self._lock:
            self._check_edit_target()
            return grid.connect(self, src_row, src_col, dest_row)

    def build_route(self, required_route, actions):
        with self._lock:
            self._check_edit_target()
            return grid.build(self, required_route, actions)

    @staticmethod
    def _parse_display_value(text, unit):
        if unit=='switch':
            return {'OFF':0,'ON':1}.get(str(text).strip().upper())
        if unit == "IR mode":
            return {"--": 0, "MUTE": 1, "SOLO": 2}.get(str(text).strip().upper())
        match = re.fullmatch(r"\s*([-+]?\d+(?:[.,]\d+)?)\s*(dB|s|sec|seconds|ms|Hz|kHz|%)?\s*",
                             text or "", re.IGNORECASE)
        if not match:
            return None
        value = float(match.group(1).replace(",", "."))
        shown, wanted = (match.group(2) or "").lower(), (unit or "").lower()
        seconds = {"s", "sec", "seconds"}
        if shown:
            if wanted == "ms" and shown in seconds:
                value *= 1000
            elif wanted in seconds and shown == "ms":
                value /= 1000
            elif wanted == "hz" and shown == "khz":
                value *= 1000
            elif shown != wanted and not (shown in seconds and wanted in seconds):
                return None
        return value if math.isfinite(value) else None

    def get_param_display(self, spec):
        self.reg.validate_spec(spec)
        return self._parse_display_value(self.read_display_text(spec.effect_id, spec.param_id), spec.unit)

    def get_param_wire(self, spec, channel=None):
        self.reg.validate_spec(spec)
        values = self.bulk_read(spec.effect_id)
        blocks = self.status_dump()
        if values is None or blocks is None:
            return None
        channels = self._channels.get(spec.effect_id)
        if not channels or len(values) % channels:
            return None
        if channel is None:
            channel = self.get_channel(spec.effect_id)
        if type(channel) is not int or channel not in range(channels):
            return None
        stride = len(values) // channels
        if spec.param_id not in range(stride):
            return None
        return values[channel * stride + spec.param_id]

    @contextmanager
    def edit_session(self, *, external_audio_muted, expected_preset):
        """Explicit caller consent, never inferred from an env var or boot.

        This does not mute the unit or replace route/modifier preflight. The
        server must do those checks before entering this device boundary.
        """
        if external_audio_muted is not True or type(expected_preset) is not int:
            raise PermissionError("External mute confirmation and an explicit preset are required")
        with self._lock:
            if self._edit_target is not None:
                raise PermissionError("An edit session is already active")
            self._edit_target = expected_preset
            self._edit_owner = threading.get_ident()
            try:
                self._check_edit_target()
                yield self
            finally:
                self._edit_target = None
                self._edit_owner = None

    def _check_edit_target(self):
        if self._edit_target is None or self._edit_owner != threading.get_ident():
            raise PermissionError("Axe-Fx III writes require a confirmed edit session")
        if self.firmware_label() != self.reg.firmware or self.reg.firmware not in SUPPORTED_FIRMWARE:
            raise PermissionError("Firmware changed or is not supported; nothing written")
        if self.reg.firmware=='33.00-beta.20261006':
            from . import fw33
            error=fw33.runtime_write_error(self)
            if error:raise PermissionError(error)
        current = self.current_preset()
        if current is None or current[0] != self._edit_target:
            raise PermissionError("Preset changed or is unreadable; nothing written")

    def _write(self, frame):
        self._check_edit_target()
        self._drain()
        self._approved_frame = tuple(frame)
        try:
            self._send(frame)
        finally:
            self._approved_frame = None

    def _param_echo(self, frame, effect_id, param_id, timeout=.3):
        # Receipt is not verification. Callers settle and verify through
        # independent display/bulk reads instead of accepting an echo.
        self._write(frame)
        return None

    def _set_domain_guard(self, spec, channel):
        try:
            self.reg.validate_spec(spec)
        except (ValueError, KeyError):
            return "No matching Axe-Fx III parameter reference; nothing written"
        if self.firmware_label() != self.reg.firmware:
            return "Firmware changed; nothing written"
        if type(channel) is not int or channel not in range(4):
            return "Channel unreadable; nothing written"
        if self.reg.firmware == '33.00-beta.20261006':
            from . import fw33
            return fw33.domain_error(self, spec, channel)
        return None

    def _delay_tempo_word(self, spec, channel):
        words = self.bulk_read(spec.effect_id)
        if words is None or len(words) != 4 * 89:
            return None
        return words[channel * 89 + spec.tempo_param_id]

    def _prepare_delay_milliseconds(self, spec, channel):
        if spec.tempo_param_id is None:
            return None
        if self.reg.firmware=='33.00-beta.20261006' and fw33_profile.TEMPO_NONE_RELEASED:
            from . import tempo_control
            try:tempo_control.ensure(self,spec)
            except (ValueError,PermissionError) as exc:return str(exc)
            return None
        if spec.family == 'CHORUS':
            words = self.bulk_read(spec.effect_id)
            shown = self.read_display_text(spec.effect_id, spec.tempo_param_id)
            if (words is not None and len(words) == 128
                    and words[channel * 32 + 3] == 0
                    and str(shown).strip().upper() == 'NONE'
                    and self.get_channel(spec.effect_id) == channel):
                return None
            return 'Chorus Rate requires independently verified Tempo NONE; nothing written'
        shown = self.read_display_text(spec.effect_id, spec.tempo_param_id)
        word = self._delay_tempo_word(spec, channel)
        if word == 0 and str(shown).strip().upper() == "NONE":
            return None
        if self.reg.firmware != '32.06':
            return 'FW33 delay time requires independently verified Tempo NONE; nothing written'
        if (type(word) is not int or not 0 < word < 65535 or not shown
                or self.get_channel(spec.effect_id) != channel):
            return "Delay tempo/channel unreadable; time not written"
        self._write(protocol.param_frame(spec.effect_id, spec.tempo_param_id, 0, opcode=0x52))
        for _ in range(4):
            time.sleep(.15)
            if self.get_channel(spec.effect_id) != channel:
                break
            word = self._delay_tempo_word(spec, channel)
            shown = self.read_display_text(spec.effect_id, spec.tempo_param_id)
            if word == 0 and str(shown).strip().upper() == "NONE":
                return None
        return "Tempo NONE was requested but not verified; delay time not written"

    def set_param_display(self, spec, display_value):
        frame = protocol.set_parameter(self.reg, spec, display_value)
        if spec.family == "CABINET":
            with self._lock:
                self._check_edit_target()
                return cab_mix.set_control(self, spec, display_value)
        with self._lock:
            self._check_edit_target()
            channel = self.get_channel(spec.effect_id)
            if channel not in (0, 1, 2, 3):
                return SetResult(False, "Channel unreadable; nothing written", None, None)
            before = self.get_param_display(spec)
            deferred_timing=(self.reg.firmware==fw33_profile.KEY and fw33_profile.TEMPO_NONE_RELEASED
                             and spec.tempo_param_id is not None)
            if before is None and not deferred_timing:
                return SetResult(False, "Display unreadable; nothing written", None, None)
            from .tone_controls import domain_error
            control_error = (self._set_domain_guard(spec, channel)
                             if self.reg.firmware != '32.06' else domain_error(self,spec,channel))
            if control_error:
                return SetResult(False,control_error,before,None)
            if self.reg.firmware==fw33_profile.KEY:
                from . import fw33
                zero_error=fw33.zero_control_error(self,spec,display_value)
                if zero_error:return SetResult(False,zero_error,before,None)
            tempo_error = self._prepare_delay_milliseconds(spec, channel)
            if tempo_error:
                return SetResult(False, tempo_error, before, None)
            if before is None:
                # A synchronized display can contain a note suffix instead of
                # a standalone number. NONE has just been independently
                # verified; settle its numeric display before the value write.
                for _ in range(5):
                    time.sleep(.15)
                    before=self.get_param_display(spec)
                    if before is not None:break
                if before is None:
                    return SetResult(False,"Numeric display unreadable after tempo verification; target value not written",None,None)
            if self.get_channel(spec.effect_id) != channel:
                return SetResult(False, "Channel changed; nothing written", before, None)
            self._write(frame)
            after = None
            tolerance = spec.display_tolerance or .02
            for _ in range(4):
                time.sleep(.15)
                if self.get_channel(spec.effect_id) != channel:
                    break
                after = self.get_param_display(spec)
                if after is not None and abs(after - display_value) <= tolerance:
                    return SetResult(True, "Independent display readback matched", before, after)
            return SetResult(False, "Display/channel readback did not verify; stop the build", before, after)

    def set_param_wire(self, spec, wire):
        """Exact restore, with no guessed ordinal/alternate-opcode fallback."""
        self.reg.validate_spec(spec)
        if self.reg.firmware != '32.06':
            return SetResult(False, 'FW33 raw restore is not exposed by this adapter port', None, None)
        if type(wire) is not int or not 0 <= wire <= 65534:
            return SetResult(False, "Invalid raw restore value", None, None)
        if not evidence.afx3_bulk_restore_supported(spec, self.reg.firmware):
            return SetResult(False, "Raw restore law is not verified", None, None)
        with self._lock:
            self._check_edit_target()
            if spec.family == "CABINET":
                return cab_mix.restore_control(self, spec, wire)
            channel = self.get_channel(spec.effect_id)
            if channel not in (0, 1, 2, 3):
                return SetResult(False, "Restore channel unavailable", None, None)
            if spec.tempo_param_id is not None:
                if (self._delay_tempo_word(spec, channel) != 0 or
                        str(self.read_display_text(spec.effect_id, spec.tempo_param_id)).strip().upper() != "NONE"):
                    return SetResult(False, "Restore cannot change the delay tempo dependency", None, None)
            before = self.get_param_wire(spec, channel=channel)
            if before is None:
                return SetResult(False, "Raw restore target unreadable", None, None)
            value = evidence.param_normalized_to_display(spec, wire / 65534, self.reg.firmware)
            # Validate even a no-op; a dangerous saved value is not permission.
            protocol.set_parameter(self.reg, spec, value)
            if before == wire:
                return SetResult(True, "Already matches the exact raw word", before, before)
            result = self.set_param_display(spec, value)
            after = self.get_param_wire(spec, channel=channel)
            ok = result.ok and after == wire and self.get_channel(spec.effect_id) == channel
            return SetResult(ok, "Exact raw restore verified" if ok else
                             "Raw restore did not verify; no alternate encoding attempted", before, after)

    def set_params_batch(self, items):
        items = list(items)
        for spec, value in items:
            protocol.set_parameter(self.reg, spec, value)
        results = []
        for spec, value in items:
            if results and not results[-1].ok:
                results.append(SetResult(False, "Skipped after preceding write failed", None, None))
            else:
                results.append(self.set_param_display(spec, value))
        return results

    def set_param_ordinal(self, spec, ordinal):
        if spec.kind != "enum":
            raise PermissionError("Generic ordinal writes are not an Axe-Fx III model setter")
        return self.set_param_display(spec, ordinal)

    def read_model(self, family, effect_id):
        with self._lock:
            return models.read(self, family, effect_id)

    def set_cab(self, effect_id, bank, ordinal, side="left"):
        if self.reg.firmware != '32.06':
            raise PermissionError('FW33 cab selection is not independently measured')
        with self._lock:
            self._check_edit_target()
            if bank == 2 and ordinal >= 512 and not self.reg.cab_catalog.user2_enabled:
                raise ValueError('User2 is reserved for NAM on this hardware profile.')
            return cab_selection.select(self, effect_id, bank, ordinal, side)

    def set_model(self, family, effect_id, name):
        if self.reg.firmware != '32.06':
            raise PermissionError('FW33 model selection is not independently measured')
        with self._lock:
            self._check_edit_target()
            return models.select(self, family, effect_id, name)

    def set_scene(self, scene_1based):
        if type(scene_1based) is not int or scene_1based not in range(1, 9):
            raise ValueError("Scene must be 1..8")
        with self._lock:
            self._write(protocol.envelope(0x0C, [scene_1based - 1]))
            time.sleep(.15)
            return self.current_scene()

    def set_channel(self, effect_id, channel_0based):
        if type(channel_0based) is not int or channel_0based not in range(4):
            raise ValueError("Channel must be A..D")
        family = self.reg.family_of_effect_id(effect_id)
        if family is None or family[0] in audio_safety.BLOCKED_LOOP_FAMILIES:
            raise PermissionError("Channel transition on an unassessed block is refused")
        with self._lock:
            self._write(protocol.envelope(0x0B, [*shared.encode14(effect_id), channel_0based]))
            time.sleep(.15)
            return self.get_channel(effect_id)

    def set_bypass(self, effect_id, bypassed):
        if type(bypassed) is not bool:
            raise ValueError("Bypass must be a boolean")
        family = self.reg.family_of_effect_id(effect_id)
        if family is None or (family[0] in audio_safety.BLOCKED_LOOP_FAMILIES and not bypassed):
            raise PermissionError("Engaging an unassessed block is refused")
        with self._lock:
            self._write(protocol.envelope(0x0A, [*shared.encode14(effect_id), int(bypassed)]))
            time.sleep(.15)
            return self.get_bypass(effect_id)

    def rename_preset(self, name):
        with self._lock:
            frame = shared.build_rename_preset(name)
            self._write(protocol.envelope(frame[5], frame[6:-2]))
            time.sleep(.15)
            return self.current_preset()

    def rename_scene(self, scene_1based, name):
        with self._lock:
            frame = shared.build_set_scene_name(scene_1based - 1, name)
            self._write(protocol.envelope(frame[5], frame[6:-2]))
            time.sleep(.15)
            return self.scene_name(scene_1based)

    def select_preset(self, preset):
        raise PermissionError("Preset reload is not enabled in the integration adapter")

    def store_preset(self, slot):
        if self.reg.firmware == '33.00-beta.20261006':
            from . import fw33
            return fw33.store(self, slot)
        raise PermissionError("Permanent storage is not enabled in the integration adapter")

    def read_nam_slot1(self):
        from . import nam_memory
        return self._nam_memory_read(nam_memory.read_slot1)

    def select_nam_slot(self, slot):
        from . import nam_selector
        with self._lock:
            self._check_edit_target()
            return nam_selector.select(self, slot)

    def export_nam_slot1(self):
        from . import nam_memory
        return self._nam_memory_read(nam_memory.export_slot1)

    def scan_nam_slots(self):
        return nam_slots.scan(self)

    def read_nam_slot(self, slot):
        from . import nam_memory
        nam_slots.number(slot)
        return self._nam_memory_read(lambda outp: nam_memory.read_slot(outp,slot))

    def export_nam_slot(self, slot):
        from . import nam_memory
        nam_slots.number(slot)
        return self._nam_memory_read(lambda outp: nam_memory.export_slot(outp,slot))

    def _nam_memory_read(self, read):
        from . import fw33
        with self._lock:
            return fw33.memory_read(self, read)

    def install_nam_slot1(self, compiled, expected_sha256):
        return self.install_nam_slot(1,compiled,expected_sha256)

    def install_nam_slot(self, slot, compiled, expected_sha256):
        from . import fw33
        with self._lock:
            return fw33.install(self, compiled, expected_sha256,slot=slot)

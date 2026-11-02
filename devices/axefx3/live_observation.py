"""Explicit read-only editor observations, not registered in the application.

No writer, firmware qualification, preset loading or scene recall. The normal
adapter/output remain unchanged. Editor protocol attribution: fm9.protocol and
THIRD_PARTY_NOTICES.md. Full eight-bit grid IDs differ from the FM9 parser.
"""
from dataclasses import asdict
import time

import mido

from fm9 import protocol as shared
from fm9.device import FM9NotFound, ReadOnly
from fm9.safety import sysex_guard
from . import protocol, preset_observation
from .adapter import AxeFxIII, ReadOnlyOutput
from .observed_words import assemble


GRID_QUERY = tuple(protocol.envelope(1, [shared.SUB_GRID_LAYOUT, 0] + [0] * 13))


def extra_read(frame):
    """Only the literal grid GET and bounded complete-block GETs, never SETs."""
    if (type(frame) not in (tuple, list) or len(frame) < 8
            or frame[0] != 240 or frame[-1] != 247
            or not protocol.valid_reply(frame[1:-1])):
        return False
    if tuple(frame) == GRID_QUERY:
        return True
    return (frame[5] == 31 and len(frame) == 10
            and 1 <= shared.decode14(*frame[6:8]) <= 207)


class ObservationOutput(ReadOnlyOutput):
    """Final boundary also checks direct outp.send; no write permit exists."""
    guard = sysex_guard('Axe-Fx III observations only', protocol.FUNCTIONS | {1, 31})

    def send(self, message):
        if message.type != 'sysex':
            raise ReadOnly('Observation connection cannot send channel messages')
        frame = [240, *message.data, 247]
        if protocol.allowed(frame, self._chassis):
            return super().send(mido.Message('sysex', data=frame[1:-1]))
        if not extra_read(frame):
            raise ReadOnly('Observation connection permits only literal read requests')
        self.guard.check(frame[5])
        self._port.send(mido.Message('sysex', data=frame[1:-1]))


def parse_grid(data):
    """Retain shunts, full IDs (including NAM206) and raw cable masks."""
    if (len(data) < 8 or not protocol.valid_reply(data) or data[4:6] != [1, shared.SUB_GRID_LAYOUT]
            or data[6] != 0):
        return None
    size = (46 + 14 * 6 * 32 + 6) // 7
    offset = len(data) - 1 - size
    if offset < 349:
        return None
    region, cells = data[offset:-1], []
    for col in range(14):
        for row in range(6):
            base = 46 + col * 6 * 32 + row * 32
            eid = shared._read_bits_msb(region, base - 1, 8)
            shunt = shared._read_bits_msb(region, base + 8, 8) == 8
            if eid or shunt:
                cells.append(shared.GridCell(row, col, None if shunt else eid,
                    shunt, shared._read_bits_msb(region, base + 16, 8)))
    return cells


class LiveReader(AxeFxIII):
    """Opt-in complete current-scene observations; not an all-scenes survey.

    One owner holds the ports. Every snapshot obtains fresh identity/target,
    grid, status, all counted blocks, 32 modifiers and eight scene names, then
    rechecks the original target/identity/status/grid. A second whole matching
    observation is required by capture(). Unknown valid firmware is read-only.
    """
    @staticmethod
    def _output(port, chassis):
        return ObservationOutput(port, chassis)

    def _send(self, frame):
        if not protocol.allowed(frame, self.chassis) and not extra_read(frame):
            raise ReadOnly('No writes on the observation connection')
        self.outp.send(mido.Message('sysex', data=frame[1:-1]))

    def _discard_pending(self):
        for index, _ in enumerate(self.inp.iter_pending()):
            if index >= 4096:
                raise ValueError('Excessive pending traffic; no fresh burst can be isolated')

    def broadcast(self, effect_id, timeout=1.5):
        if type(effect_id) is not int or not 1 <= effect_id <= 207:
            raise ValueError('An explicit observed block or modifier ID is required')
        if type(timeout) not in (int, float) or not .01 <= timeout <= 5:
            raise ValueError('A bounded broadcast timeout is required')
        with self._lock:
            if self._closed:
                raise FM9NotFound('Axe-Fx III connection is closed')
            self._discard_pending()
            self._send(protocol.envelope(31, list(shared.encode14(effect_id))))
            deadline, packets = time.monotonic() + timeout, []
            while time.monotonic() < deadline:
                ended = False
                for message in self.inp.iter_pending():
                    if message.type != 'sysex':
                        continue
                    data = list(message.data)
                    if (len(packets) >= 1024 or not protocol.valid_reply(data)
                            or data[4] not in (116, 117, 118)):
                        raise ValueError('Damaged, interleaved or excessive broadcast traffic')
                    packets.append(data)
                    ended = ended or data[4] == 118
                if ended:
                    return assemble(packets, effect_id)
                time.sleep(.005)
            raise ValueError('Incomplete fresh block broadcast; no cached fallback')

    def bulk_read(self, effect_id, timeout=1.5):
        return list(self.broadcast(effect_id, timeout).words)

    def read_grid(self):
        value = self._request(1, list(GRID_QUERY[6:-2]), parse_grid, timeout=2)
        if value is None:
            raise ValueError('Complete editor grid did not answer')
        return value

    def _identity_reply(self):
        reply = self._request(8, [], tuple)
        if (reply is None or not 8 <= len(reply) <= 256
                or not protocol.valid_reply(reply)):
            raise ValueError('Complete fresh identity reply required')
        return reply

    def observation(self):
        with self._lock:
            identity, variant = self._identity_reply(), self.chassis
            preset, scene = self.current_preset(), self.current_scene()
            if preset is None or scene is None:
                raise ValueError('Fresh current preset and scene required')
            status, grid = self.status_dump(), self.read_grid()
            if status is None:
                raise ValueError('Complete status inventory required')
            ids = [b.effect_id for b in status]
            if len(ids) != len(set(ids)) or not {200, 201} <= set(ids):
                raise ValueError('Unique inventory and both system blocks required')
            bulk = {str(eid): self.broadcast(eid) for eid in ids}
            modifiers = [self.broadcast(eid) for eid in range(3, 35)]
            names = [self.scene_name(n) for n in range(1, 9)]
            if (self._identity_reply() != identity or self.chassis != variant
                    or self.current_preset() != preset or self.current_scene() != scene
                    or self.status_dump() != status or self.read_grid() != grid):
                raise ValueError('Identity, target or inventory changed during observation')
            return dict(identity=identity, variant=variant,
                firmware=f'{identity[5]}.{identity[6]:02d}', preset=preset, scene=scene,
                status=[asdict(b) for b in status], grid=[asdict(c) for c in grid],
                bulk=bulk, modifiers=modifiers, scenes=names)

    def capture(self, *, max_reads=4):
        with self._lock:
            return preset_observation.capture(self.observation, max_reads=max_reads)

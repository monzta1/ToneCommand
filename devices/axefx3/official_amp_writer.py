"""Exact official 33.01 Gain/Mid experiment with complete opaque preservation.

Separate opt-in component, not app registration or an older writer's firmware
alias. Existing model 0, Amp 1/A only; no model, bypass, level or routing SET.
"""
from copy import deepcopy
import hashlib

import mido

from fm9.device import ReadOnly
from . import protocol
from .amp_writer import AmpWriter, _AmpOutput
from .live_observation import LiveReader, extra_read


IDENTITY_SHA256 = '5cb7d1d51cfd96ce65058e10f33e2e3c9722d57ff0b3c41b07ee7b63d05fb2d7'


class _OfficialOutput(_AmpOutput):
    """Literal reads plus the inherited one-use exact Gain/Mid permit."""
    def send(self, message):
        frame = message.bytes() if message.type == 'sysex' else []
        if extra_read(frame):
            self.guard.check(frame[5])
            return self._port.send(mido.Message('sysex', data=frame[1:-1]))
        return super().send(message)


class OfficialAmpWriter(AmpWriter, LiveReader):
    """Reuse typed bounds and one-shot execution, not prior firmware approval.

    All complete raw state, including unknown blocks, system 200/201 and
    unrelated custom modifiers, survives the full before/after comparison.
    The independently qualified native profile is deliberately model 0/A only.
    Default capabilities remain read-only and Store is never implemented here.
    """
    @staticmethod
    def _output(port, chassis):
        return _OfficialOutput(port, chassis)

    def _identity(self):
        if self._closed or self._uncertain or self.chassis != 'mk2':
            raise ReadOnly('Exact official 33.01 MK2 connection required; reconnect after uncertainty')
        reply = self._identity_reply()
        if hashlib.sha256(bytes(reply)).hexdigest() != IDENTITY_SHA256:
            raise ReadOnly('Full official 33.01 identity differs; no inherited write approval')

    def _observe(self, edit):
        self._identity()
        observation = self.capture().data()
        if observation['preset'][0] != edit.preset:
            raise ReadOnly('Selected target differs from the reviewed preset')
        block = [b for b in observation['status'] if b['effect_id'] == 58]
        amp = observation['bulk'].get('58')
        if (len(block) != 1 or block[0]['channel'] != 0 or block[0]['channels_supported'] != 4
                or amp is None or len(amp) != 568 or amp[0] != 0):
            raise ReadOnly('Existing 59 Bassguy Bright, Amp 1/A and full 568-word layout required')
        if any(words[8:10] == [58, edit.pid] for words in observation['modifiers']):
            raise ReadOnly('The proposed parameter is modifier-owned, even with source NONE')
        shown = self._display(edit.pid)
        if (type(shown) not in (int, float) or not 0 <= shown <= 10
                or abs(amp[edit.pid] / 65534 * 10 - shown) > .011):
            raise ReadOnly('Independent parameter display and bulk value must agree')
        if self.capture().data() != observation:
            raise ReadOnly('Complete preset changed during display inspection')
        self._identity()
        # AmpEdit.matches checks all 568 Amp words separately, masking only
        # the single addressed word. Keep every other surface in its context.
        opaque = deepcopy(observation)
        del opaque['bulk']['58']
        del opaque['modifiers']
        return dict(status=dict(preset=dict(number=observation['preset'][0],
            name=observation['preset'][1]), observation=opaque), amp=amp,
            modifiers=observation['modifiers'], shown=shown)

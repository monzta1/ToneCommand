"""Separate opt-in Beta5 Gain/Mid experiment, never a general write profile.

Existing Amp 1/A, model 0 only. The legacy writer's identity and the full
workspace registry stay unchanged. Native/editor acceptance is recorded
separately from this component's software tests.
"""
import hashlib

from fm9.device import ReadOnly
from .amp_writer import AmpWriter
from .firmware_identity import BETA5_IDENTITY_SHA256


class Beta5AmpWriter(AmpWriter):
    """Reuse the checked two-control transport, not old firmware approval."""

    def _identity(self):
        if self._closed or self._uncertain or self.chassis != 'mk2':
            raise ReadOnly('Exact measured Beta5 MK2 identity required; reconnect after uncertainty')
        reply = self._request(8, [], tuple)
        if (self._closed or self._uncertain or self.chassis != 'mk2'
                or reply is None
                or hashlib.sha256(bytes(reply)).hexdigest() != BETA5_IDENTITY_SHA256):
            raise ReadOnly('Exact measured Beta5 MK2 identity required; reconnect after uncertainty')

    def _observe(self, edit):
        observed = super()._observe(edit)
        if observed['amp'][0] != 0:
            raise ReadOnly('This Beta5 experiment requires existing 59 Bassguy Bright on Amp 1/A')
        return observed

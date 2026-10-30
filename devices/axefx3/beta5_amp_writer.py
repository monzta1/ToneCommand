"""Separate opt-in Beta5 Gain/Mid experiment, not a general write profile.

Existing Amp 1/A, model 0 only. Older firmware approval is unchanged.
"""
import hashlib

from fm9.device import ReadOnly
from .amp_writer import AmpWriter


# Full measured response, not the raw 97.00 version fields or a version alias.
BETA5_IDENTITY_SHA256 = '15e9277d25e2180599d6d8a9d1fda73373ee592cdc0ce8682a1f7c007b67a616'


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

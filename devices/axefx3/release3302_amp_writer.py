"""Opt-in 33.02 Gain/Mid qualification, not an inherited firmware approval.

Reuse the complete-preservation writer contract, not its 33.01 identity pin.
Existing Amp 1, channel A, model 0 only. Not registered in the app or AI reference.
"""
import hashlib

from fm9.device import ReadOnly
from .official_amp_writer import OfficialAmpWriter


# Independent writer pin: expanding display recognition never grants a SET.
IDENTITY_SHA256 = '7f6b964ac95cdab2512926d6f735a32328e133d76475b1aea7e443cd637ee0e5'


class Release3302AmpWriter(OfficialAmpWriter):
    """Retain exact one-use Gain/Mid bounds, readback and opaque preservation."""
    def _identity(self):
        if self._closed or self._uncertain or self.chassis != 'mk2':
            raise ReadOnly('Exact 33.02 MK2 connection required; reconnect after uncertainty')
        reply = self._identity_reply()
        if hashlib.sha256(bytes(reply)).hexdigest() != IDENTITY_SHA256:
            raise ReadOnly('Full 33.02 identity differs; no prior firmware write approval')

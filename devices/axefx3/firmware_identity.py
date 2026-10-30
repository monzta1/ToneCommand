"""Recognize exact observed builds without granting write capabilities.

Release numbers and dates alone never establish parameter compatibility.
The Beta 5 fingerprint is a read-only discovery result, not a write profile.
"""
import hashlib

from . import fw33_profile, protocol


BETA5_KEY = '33.00-beta5.20261026'
BETA5_IDENTITY_SHA256 = '15e9277d25e2180599d6d8a9d1fda73373ee592cdc0ce8682a1f7c007b67a616'


def parse_response(reply):
    """Ignore unrelated acknowledgements; retain unknown firmware for rejection."""
    if (type(reply) not in (list, tuple) or len(reply) < 8
            or not protocol.valid_reply(list(reply)) or reply[4] != 8):
        return None
    return tuple(reply)


def identify(reply):
    """Return a known full-response label; unknown replies keep raw fallback."""
    if (type(reply) not in (list, tuple) or not 8 <= len(reply) <= 256
            or any(type(value) is not int or not 0 <= value <= 127 for value in reply)):
        return None
    previous = fw33_profile.identity_key(reply)
    if previous is not None:
        return previous
    if hashlib.sha256(bytes(reply)).hexdigest() == BETA5_IDENTITY_SHA256:
        return BETA5_KEY
    return None

"""Name captured firmware replies for display only, never write permission.

These fingerprints were measured on a Mark II. A matching label does not
identify the chassis or qualify a writer, parameter, model or shared memory.
"""
import hashlib

from . import protocol


OBSERVED_BUILDS = {
    '15e9277d25e2180599d6d8a9d1fda73373ee592cdc0ce8682a1f7c007b67a616':
        '33.00-beta5.20261026',
    '946a6b36256826887d72b6f5e3263996bab058cdf8144479762e5136115799a3':
        '33.00.20261030',
    '5cb7d1d51cfd96ce65058e10f33e2e3c9722d57ff0b3c41b07ee7b63d05fb2d7':
        '33.01.20261031',
}


def parse_reply(reply):
    """Retain valid unknown replies; ignore malformed or unrelated packets."""
    if (type(reply) not in (list, tuple) or not 8 <= len(reply) <= 256
            or any(type(b) is not int or not 0 <= b <= 127 for b in reply)
            or not protocol.valid_reply(list(reply)) or reply[4] != 8):
        return None
    return tuple(reply)


def observed_build(reply):
    """A full-packet fingerprint, not a version/date prefix or beta alias."""
    parsed = parse_reply(reply)
    return OBSERVED_BUILDS.get(hashlib.sha256(bytes(parsed)).hexdigest()) if parsed else None


def display_label(reply):
    parsed = parse_reply(reply)
    if parsed is None:
        return ''
    # Keep the old raw fallback for builds not measured here. In particular,
    # raw 97.00 is not silently relabelled as an observed beta release.
    return observed_build(parsed) or f'{parsed[5]}.{parsed[6]:02d}'

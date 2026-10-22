"""Measured MK2/FW33 NAM addresses. No implicit installation permission.

Name GETs were captured for all256 addresses. Memory export headers/GETs were
independently captured at001,250,256. Occupancy requires explicit device data;
timeouts, blank names and malformed replies never mean a free slot.
"""
from dataclasses import dataclass

from fm9 import protocol as shared
from . import protocol, fw33_profile


def number(slot):
    if type(slot) is not int or not 1 <= slot <= 256:
        raise ValueError('Choose NAM slot001-256, one-based')
    return slot


def header(slot):
    return [0, *shared.encode14(number(slot)-1), 0, 0, 1]


def memory_request(slot):
    return protocol.envelope(0x1c, [0, *shared.encode14(number(slot)-1)])


def name_request(slot):
    return protocol.envelope(1, [8,1,0,0,0,0,*shared.encode14(number(slot)-1),0,0,0,0,0,0,0])


def is_name_request(frame):
    if len(frame) != 23 or not protocol.valid_reply(list(frame[1:-1])):
        return False
    slot = 1 + shared.decode14(frame[12], frame[13])
    return 1 <= slot <= 256 and list(frame) == name_request(slot)


@dataclass(frozen=True)
class Slot:
    slot: int
    name: str
    occupied: bool


def parse_name(data, slot):
    number(slot)
    # This measured reply does not echo the requested ordinal. The transport
    # MUST serialize one GET at a time and abort the scan on a missing reply.
    if (not protocol.valid_reply(data) or len(data) != 332
            or data[4:11] != [1,8,1,0,0,0,0]
            or data[18:20] != [16,2]):
        return None
    # Bytes11:18 are opaque editor/preset context, not the NAM slot address.
    # Live empty-preset replies contain0 where populated-preset replies had42.
    # Only the fixed name payload length272 and its contents identify a name.
    bits = ''.join(f'{b:07b}' for b in data[20:292])
    raw = bytes(int(bits[i:i+8],2) for i in range(0,len(bits)-7,8))[:28]
    if b'\0' not in raw:
        return None
    raw = raw.split(b'\0',1)[0]
    if not raw or any(not 32 <= b <= 126 for b in raw):
        return None
    name = raw.decode('ascii')
    return Slot(slot, name, name != '<EMPTY>')


def scan(dev):
    with dev._lock:
        if (getattr(dev.reg,'hardware_variant',None) != 'mk2'
                or dev.reg.firmware != fw33_profile.KEY
                or dev.firmware_label() != fw33_profile.KEY):
            raise ValueError('NAM inventory requires the measured MK2/FW33 profile')
        rows = []
        for slot in range(1,257):
            found = dev._request(name_request(slot), lambda data: parse_name(data,slot), .8)
            if found is None:
                raise ValueError(f'NAM slot{slot:03d} could not be read; inventory incomplete, nothing installed')
            rows.append(found)
        if dev.firmware_label() != fw33_profile.KEY:
            raise ValueError('Device changed while reading NAM inventory')
        return rows

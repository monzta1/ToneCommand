"""Official Gen 3 reads only, with the Axe-Fx III product byte 0x10.

Envelope/name/status codecs come from fm9.protocol, whose attribution to
Fractal's Third-Party MIDI specification remains there. No editor opcode,
parameter getter implemented as a setter, memory transfer or navigation.
"""
from fm9 import protocol as shared
from .chassis import MODEL_BYTE, PRESET_COUNTS, declared

MODEL = MODEL_BYTE
FUNCTIONS = frozenset({0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x13})


def preset_count(chassis):
    return declared(chassis).presets


def envelope(function, payload):
    return shared.envelope(function, payload, model=MODEL)


def valid_reply(data):
    return (len(data) >= 6 and tuple(data[:3]) == shared.MFR
            and data[3] == MODEL
            and all(type(b) is int and 0 <= b <= 127 for b in data)
            and shared.checksum(data[:-1]) == data[-1])


def allowed(frame, chassis='mk1'):
    """Exact read forms, including checksum, ranges and payload lengths."""
    limit = preset_count(chassis)
    if (len(frame) < 8 or frame[0] != 0xF0 or frame[-1] != 0xF7
            or not valid_reply(frame[1:-1])):
        return False
    function, payload = frame[5], frame[6:-2]
    if function in (0x08, 0x13):
        return payload == []
    if function == 0x0C:
        return payload == [127]
    if function == 0x0D:
        return len(payload) == 2 and (payload == [127, 127]
                                     or shared.decode14(*payload) < limit)
    if function == 0x0E:
        return len(payload) == 1 and payload[0] in (*range(8), 127)
    if function in (0x0A, 0x0B):
        return len(payload) == 3 and payload[2] == 127
    return False

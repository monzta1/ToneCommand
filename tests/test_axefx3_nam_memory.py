"""No model weights or personal capture files in regression fixtures."""
import struct
from unittest.mock import Mock

import pytest
from devices.axefx3 import nam_memory
from fm9 import protocol as p
from fm9.device import FM9


def export(name=b'Example A2'):
    payload = bytearray(65536)
    payload[:len(name)] = name
    payload[256:260] = struct.pack('<I', 0xffed1234)
    words = struct.unpack('<16384I', payload)
    frames = [p.envelope(0x54, [0,0,0,0,0,1], model=16)]
    for start in range(0, len(words), 256):
        data = [0,2]
        for word in words[start:start+256]:
            data.extend((word >> (7*i)) & 127 for i in range(5))
        frames.append(p.envelope(0x55, data, model=16))
    checksum = 0
    for word in words:
        checksum ^= word
    frames.append(p.envelope(0x56, [(checksum >> (7*i)) & 127 for i in range(5)], model=16))
    return frames


def test_complete_memory_read_and_unsigned_footer():
    capture = nam_memory.parse_export(export())
    assert capture.name == 'Example A2' and capture.slot == 1
    assert capture.byte_count == 65536 and len(capture.payload_sha256) == 64


@pytest.mark.parametrize('fault', ['head_tail','drop','duplicate','checksum','model','slot','xor','empty'])
def test_never_accept_incomplete_or_wrong_memory(fault):
    frames = export(b'EMPTY' if fault == 'empty' else b'Example A2')
    if fault == 'head_tail': frames = [frames[0],frames[-1]]
    if fault == 'drop': frames.pop(4)
    if fault == 'duplicate': frames.insert(2,frames[2])
    if fault == 'checksum': frames[1][-2] ^= 1
    if fault == 'model': frames[0] = p.envelope(0x54,frames[0][6:-2],model=17)
    if fault == 'slot': frames[0] = p.envelope(0x54,[1,0,0,0,0,1],model=16)
    if fault == 'xor': frames[-1] = p.envelope(0x56,[0]*5,model=16)
    with pytest.raises(ValueError):
        nam_memory.parse_export(frames)


def test_memory_read_guard_has_no_install_or_firmware_functions():
    nam_memory.READ_GUARD.check(0x1c)
    for fn in (0x54,0x55,0x56,0x77,0x7a,0x01,0x7f):
        with pytest.raises(Exception):
            nam_memory.READ_GUARD.check(fn)

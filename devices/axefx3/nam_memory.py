"""Read-only, bounded NAM slot001-256 export on the measured MK2/FW33 build.

This is NOT a .nam converter, installer or general slot-address decoder.
Addresses follow independently captured Axe-Edit requests/exports. Large native
WinMM buffers are necessary: python-rtmidi's Windows input drops these bodies.
The caller must close its ordinary MIDI input first and serialize the read.
"""
from dataclasses import dataclass
import hashlib
import struct

from fm9 import protocol as p
from fm9.safety import sysex_guard
from . import nam_slots

READ_GUARD = sysex_guard('NAM memory read only', {0x1c})


@dataclass(frozen=True)
class Capture:
    name: str
    slot: int
    payload_sha256: str
    byte_count: int
    empty: bool = False


def parse_export(frames, *, slot=1, allow_empty=False) -> Capture:
    """Validate every frame, count, slot header and full-payload XOR.

    No musical/device compatibility inference follows from this structure.
    Header flags, architecture and calibration fields remain opaque.
    """
    nam_slots.number(slot)
    frames = [bytes(f) for f in frames]
    if len(frames) < 3:
        raise ValueError('Incomplete NAM export')
    for f in frames:
        checksum = 0
        for byte in f[:-2]:
            checksum ^= byte
        if (len(f) < 8 or f[:5] != bytes([0xf0, 0, 1, 116, 16])
                or f[-1] != 0xf7 or any(b > 127 for b in f[1:-1])
                or checksum & 127 != f[-2]):
            raise ValueError('Invalid NAM envelope or checksum')
    if (len(frames[0]) != 14 or frames[0][5:12] != bytes([0x54,*nam_slots.header(slot)])
            or len(frames[-1]) != 13 or frames[-1][5] != 0x56):
        raise ValueError('Unmeasured NAM slot/header/footer')
    words = []
    for f in frames[1:-1]:
        if f[5] != 0x55 or len(f) < 8:
            raise ValueError('Unexpected NAM export body')
        count = f[6] | f[7] << 7
        if count not in (128, 256) or len(f) != 10 + 5*count:
            raise ValueError('Unmeasured NAM body word count')
        for off in range(8, len(f)-2, 5):
            words.append(sum(f[off+i] << (7*i) for i in range(5)) & 0xffffffff)
        if len(words) > 16384:
            raise ValueError('NAM export exceeds measured memory size')
    if len(words) != 16384:
        raise ValueError('Truncated NAM export; head/tail alone is not readback')
    checksum = 0
    for word in words:
        checksum ^= word
    expected = sum(frames[-1][6+i] << (7*i) for i in range(5)) & 0xffffffff
    if checksum != expected:
        raise ValueError('NAM payload XOR mismatch')
    payload = struct.pack('<16384I', *words)
    # The independently exported EMPTY images on250/256 are entirely erased.
    # No name-only/partial-header heuristic can classify a full image as empty.
    if payload == b'\xff' * 65536:
        if not allow_empty:
            raise ValueError('NAM slot is empty')
        return Capture('<EMPTY>',slot,hashlib.sha256(payload).hexdigest(),len(payload),True)
    raw_name = payload[:28].split(b'\0', 1)[0]
    try:
        name = raw_name.decode('ascii').strip()
    except UnicodeDecodeError as exc:
        raise ValueError('Unmeasured NAM name encoding') from exc
    if not name or name.upper() in {'EMPTY', '<EMPTY>'} or any(ord(c)<32 for c in name):
        raise ValueError('NAM slot is unnamed or has an unverified empty representation')
    return Capture(name, slot, hashlib.sha256(payload).hexdigest(), len(payload))


def _export_slot(outp, slot, timeout=5, *, allow_empty=True):
    """Own the native input exclusively; use the caller's existing output.

    Fixed bounded pool, no driver calls inside callbacks, no permanent writes.
    """
    nam_slots.number(slot)
    import ctypes as c
    import os
    import queue
    import time
    import mido
    if os.name != 'nt':
        raise RuntimeError('Measured NAM memory read currently requires Windows')

    class Caps(c.Structure):
        _fields_ = [('mid',c.c_uint16),('pid',c.c_uint16),('version',c.c_uint32),
                    ('name',c.c_wchar*32),('support',c.c_uint32)]

    class Header(c.Structure):
        _fields_ = [('data',c.c_void_p),('length',c.c_uint32),('recorded',c.c_uint32),
                    ('user',c.c_size_t),('flags',c.c_uint32),('next',c.c_void_p),
                    ('reserved',c.c_size_t),('offset',c.c_uint32),
                    ('reserved_array',c.c_size_t*8)]

    win = c.WinDLL('winmm')
    win.midiInGetDevCapsW.argtypes = [c.c_size_t,c.POINTER(Caps),c.c_uint]
    win.midiInOpen.argtypes = [c.POINTER(c.c_void_p),c.c_uint,c.c_size_t,c.c_size_t,c.c_uint32]
    for op in ('midiInPrepareHeader','midiInAddBuffer','midiInUnprepareHeader'):
        getattr(win,op).argtypes = [c.c_void_p,c.POINTER(Header),c.c_uint]
    for op in ('midiInStart','midiInStop','midiInReset','midiInClose'):
        getattr(win,op).argtypes = [c.c_void_p]

    def checked(result):
        if result:
            raise OSError(f'NAM read: WinMM error {result}')

    candidates = []
    for i in range(win.midiInGetNumDevs()):
        caps = Caps()
        checked(win.midiInGetDevCapsW(i,c.byref(caps),c.sizeof(caps)))
        if 'axe-fx iii' in caps.name.lower():
            candidates.append(i)
    if len(candidates) != 1:
        raise RuntimeError('NAM read requires exactly one Axe-Fx III input')
    messages, errors = queue.Queue(), queue.Queue()
    callback_type = c.WINFUNCTYPE(None,c.c_void_p,c.c_uint,c.c_size_t,c.c_size_t,c.c_size_t)

    def callback(handle, kind, instance, param, stamp):
        if kind in (0x3c4,0x3c6):
            header = c.cast(param,c.POINTER(Header)).contents
            if kind == 0x3c6:
                errors.put(True)
            elif header.recorded:
                messages.put(c.string_at(header.data,header.recorded))

    cb = callback_type(callback)
    handle = c.c_void_p()
    buffers = []
    checked(win.midiInOpen(c.byref(handle),candidates[0],c.cast(cb,c.c_void_p).value,0,0x30000))
    try:
        for _ in range(256):
            raw = c.create_string_buffer(4096)
            header = Header(data=c.addressof(raw),length=len(raw))
            checked(win.midiInPrepareHeader(handle,c.byref(header),c.sizeof(header)))
            buffers.append((raw,header))
            checked(win.midiInAddBuffer(handle,c.byref(header),c.sizeof(header)))
        checked(win.midiInStart(handle))
        request = nam_slots.memory_request(slot)
        READ_GUARD.check(request[5])
        outp.send(mido.Message('sysex',data=request[1:-1]))
        frames = []
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                f = messages.get(timeout=.05)
            except queue.Empty:
                continue
            if f[:5] == bytes([0xf0,0,1,116,16]) and len(f)>5 and f[5] in (0x54,0x55,0x56):
                frames.append(f)
                if f[5] == 0x56:
                    break
        if not errors.empty():
            raise RuntimeError('NAM read: long-message driver error')
        return parse_export(frames,slot=slot,allow_empty=allow_empty), tuple(bytes(f) for f in frames)
    finally:
        # All buffers must be returned before closing; even a failed read
        # must release ownership so the normal device session can reconnect.
        try:
            win.midiInStop(handle)
            win.midiInReset(handle)
            for raw,header in buffers:
                win.midiInUnprepareHeader(handle,c.byref(header),c.sizeof(header))
        finally:
            checked(win.midiInClose(handle))


def read_slot1(outp, timeout=5):
    return _export_slot(outp,1,timeout,allow_empty=False)[0]


def export_slot1(outp, timeout=5):
    """Full validated frames for private recovery, never returned to the UI/AI."""
    return _export_slot(outp,1,timeout,allow_empty=False)


def read_slot(outp,slot,timeout=5):
    return _export_slot(outp,slot,timeout)[0]


def export_slot(outp,slot,timeout=5):
    return _export_slot(outp,slot,timeout)

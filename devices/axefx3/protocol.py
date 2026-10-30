"""Explicit Axe-Fx III frames and captured SET domains.

Shared Gen-3 packing functions are reused, but their default FM9 product byte
is never changed globally. SET units and read paths are device-specific.
"""
from __future__ import annotations

import math
import struct
from numbers import Real

from fm9 import protocol as shared
from . import audio_safety, fw33_profile
from .evidence import (AXE_FX_III_32_06_ZERO_NORMALIZED,
                       AXE_FX_III_32_06_ZERO_TYPED,
                       AXE_FX_III_CAB_MIX_PARAMS)
from .registry import ParamSpec, Registry


MODEL = 0x10
NUMERIC_ZERO_EFFECTS = frozenset({46,50,54})


def envelope(fn: int, payload: list[int]) -> list[int]:
    return shared.envelope(fn, payload, model=MODEL)


def valid_reply(data: list[int]) -> bool:
    """Mido payload only: reject foreign models and damaged frames."""
    return (len(data) >= 6 and data[:3] == list(shared.MFR)
            and data[3] == MODEL
            and all(type(b) is int and 0 <= b <= 127 for b in data)
            and shared.checksum(data[:-1]) == data[-1])


def param_frame(effect_id: int, param_id: int, value: float, *, opcode: int) -> list[int]:
    if opcode not in (0x09, 0x52) or not math.isfinite(value):
        raise ValueError("Unsupported Axe-Fx III parameter encoding")
    if (type(effect_id) is not int or type(param_id) is not int
            or not 0 <= effect_id < 16384 or not 0 <= param_id < 16384):
        raise ValueError("Parameter address outside the Gen-3 frame")
    return envelope(shared.FN_PARAM, [opcode, 0, *shared.encode14(effect_id),
                    *shared.encode14(param_id), *shared.encode_f32_septets(value),
                    0, 0, 0, 0])


def set_parameter(registry: Registry, spec: ParamSpec, value: float) -> list[int]:
    """Validate and encode a display value. Does not authorize transmission.

    The caller still checks live firmware, channel, modifiers, external mute,
    tempo dependency and independent display readback. No silent clamping.
    """
    registry.validate_spec(spec)
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError("Parameter value must be a finite number")
    if not spec.dmin <= value <= spec.dmax:
        raise ValueError("Parameter value outside the verified display range")
    if spec.kind == "enum" and value != int(value):
        raise ValueError("Discrete parameter value must be an integer")
    error = audio_safety.parameter_error(spec, value)
    if error:
        raise ValueError(error)
    if spec.set_divisor is None:
        wire = shared.display_to_normalized(value, spec.dmin, spec.dmax, spec.scale)
        return param_frame(spec.effect_id, spec.param_id, wire, opcode=int(spec.set_opcode, 16))
    if value == 0:
        if registry.firmware == fw33_profile.KEY:
            if fw33_profile.LEGACY_ZERO_RELEASED:
                if spec.name in fw33_profile.LEGACY_ZERO_TYPED:
                    return param_frame(spec.effect_id,spec.param_id,0,opcode=0x09)
                if spec.name in fw33_profile.LEGACY_ZERO_NORMALIZED:
                    return param_frame(spec.effect_id,spec.param_id,0,opcode=0x52)
            if fw33_profile.FX_ZERO_RELEASED and spec.name in fw33_profile.FX_ZERO_NAMES:
                return param_frame(spec.effect_id,spec.param_id,0,opcode=0x09)
            if (fw33_profile.AMP_ZERO_RELEASED and spec.family=='DISTORT'
                    and spec.name in fw33_profile.NAMES['DISTORT'][:-1]):
                return param_frame(spec.effect_id,spec.param_id,0,opcode=0x09)
            if spec.name in fw33_profile.effect_controls.AUTO_OFF:
                return param_frame(spec.effect_id,spec.param_id,0,opcode=0x52)
            if spec.name not in fw33_profile.ZERO_TYPED:
                raise ValueError('No measured FW33 exact-zero setter')
            return param_frame(spec.effect_id, spec.param_id, 0, opcode=0x09)
        if spec.name in AXE_FX_III_32_06_ZERO_TYPED or spec.name in AXE_FX_III_CAB_MIX_PARAMS:
            return param_frame(spec.effect_id, spec.param_id, 0, opcode=0x09)
        if spec.name not in AXE_FX_III_32_06_ZERO_NORMALIZED:
            raise ValueError("No independently verified zero SET for this parameter")
        return param_frame(spec.effect_id, spec.param_id,
                           AXE_FX_III_32_06_ZERO_NORMALIZED[spec.name], opcode=0x52)
    if registry.firmware==fw33_profile.KEY and spec.name in fw33_profile.effect_controls.AUTO_OFF:
        raise ValueError('Only independently captured automatic-mode OFF is supported')
    if (registry.firmware == fw33_profile.KEY and spec.family == 'DISTORT'
            and spec.name in fw33_profile.NAMES['DISTORT'][:-1]):
        # Editor batch10 first rounds the display value to float32. Dividing
        # a Python double instead differs by one packed ULP for some knobs.
        value = struct.unpack('<f',struct.pack('<f',value))[0]
    return param_frame(spec.effect_id, spec.param_id, value / spec.set_divisor,
                       opcode=int(spec.set_opcode, 16))


def parse_grid_layout(data):
    """FX3 full eight-bit IDs, preserving NAM206 separately from Chorus78."""
    if (not valid_reply(data) or len(data) < 8 or data[4:6] != [1, shared.SUB_GRID_LAYOUT]):
        return None
    region_bytes = -(-(46 + shared.GRID_COLS * shared.GRID_ROWS * 32) // 7)
    offset = len(data) - 1 - region_bytes
    if offset < 349:
        return None
    region, cells = data[offset:-1], []
    for col in range(shared.GRID_COLS):
        for row in range(shared.GRID_ROWS):
            base = 46 + col * shared.GRID_ROWS * 32 + row * 32
            eid = shared._read_bits_msb(region, base - 1, 8)
            shunt = shared._read_bits_msb(region, base + 8, 8) == 8
            if eid or shunt:
                cells.append(shared.GridCell(row, col, None if shunt else eid,
                    shunt, shared._read_bits_msb(region, base + 16, 8)))
    return cells


def display_query(effect_id: int, param_id: int) -> list[int]:
    """Passive 01 10 query, never an active zero SET used as a GET.

    Model selectors are bulk-only. Numeric pid 0 is separately captured for
    Compressor threshold, GEQ band 1 and PEQ frequency 1, first blocks only.
    """
    if (type(effect_id) is not int or type(param_id) is not int
            or not 0 <= effect_id < 16384 or not 0 <= param_id < 16384
            or (param_id==0 and effect_id not in NUMERIC_ZERO_EFFECTS)):
        raise ValueError("Model selector display queries are not permitted")
    return envelope(shared.FN_PARAM, [0x10, 0, *shared.encode14(effect_id),
                    *shared.encode14(param_id)])


def _unpack_display_text(wire: list[int]) -> str:
    """Decode the AFX3 7-bit-MSB-first display-text payload."""
    bits = "".join(f"{b & 0x7F:07b}" for b in wire)
    raw = bytes(int(bits[i:i + 8], 2)
                for i in range(0, len(bits) - 7, 8))
    text = []
    for b in raw:
        if b == 0 or not 0x20 <= b <= 0x7E:
            break
        text.append(chr(b))
    return "".join(text).strip()


def parse_display_text_response(data: list[int]) -> tuple[int, int, str] | None:
    """Parse an AFX3 passive 01 10 reply (mido data, no F0/F7)."""
    if (not valid_reply(data) or data[4] != shared.FN_PARAM or len(data) < 22
            or data[5:7] != [0x10, 0]):
        return None
    effect_id = shared.decode14(data[7], data[8])
    param_id = shared.decode14(data[9], data[10])
    packed_len = shared.decode14(data[18], data[19])
    if not packed_len:
        return (effect_id, param_id, "")
    available = data[20:-1]  # omit checksum
    if len(available) < packed_len:
        return None
    return (effect_id, param_id,
            _unpack_display_text(available[:packed_len]))

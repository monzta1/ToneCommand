"""Fractal FM9 SysEx protocol layer.

Origin and attribution:
- Official commands are from Fractal's "Axe-Fx III MIDI for Third-Party
  Devices" Rev 1.4 PDF (FM9 model byte 0x12).
- The editor-protocol surface (fn 0x01 parameter set, grid, names, store;
  fn 0x1F bulk read) is ported to Python and modified from the TypeScript
  and SYSEX-MAP.md documentation of mcp-midi-control,
  https://github.com/TheAndrewStaker/mcp-midi-control,
  Copyright 2026 Stephen Staker, Apache License 2.0.
- The modifier model is re-implemented from forgefx-midi (Apache-2.0,
  https://github.com/sKuhLight/forgefx-midi).
- See THIRD_PARTY_NOTICES.md for full notices, and the README for
  corrections this project contributes back (select-before-insert on grid
  placement, grid-read id aliasing, FM9 Pedal 2 source ordinal).

Firmware-sensitive. Developed against FM9 firmware 11.x; the parameter
get/set paths re-verified on 12.00 (hardware_regression.py, 2026-08-19).
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass

MFR = (0x00, 0x01, 0x74)
MODEL_FM9 = 0x12

# Official (Rev 1.4 PDF)
FN_BYPASS = 0x0A          # id id dd; dd: 0 engaged, 1 bypassed, 7F query
FN_CHANNEL = 0x0B         # id id dd; dd: 0..3 = A..D, 7F query
FN_SCENE = 0x0C           # dd; 7F query
FN_PATCH_NAME = 0x0D      # dd dd preset LS-first; 7F 7F = current
FN_SCENE_NAME = 0x0E      # dd; 7F = current
FN_TEMPO_TAP = 0x10
FN_TUNER = 0x11
FN_STATUS_DUMP = 0x13
FN_TEMPO_BPM = 0x14
# Community-verified
FN_FIRMWARE = 0x08        # Axe-Fx II heritage, works on III generation
FN_PARAM = 0x01           # editor protocol: parameter set/get
FN_MULTIPURPOSE = 0x64    # ack/nack responses
FN_BULK_READ = 0x1F       # whole-block read poll; reply is 0x74/0x75/0x76 burst
FN_BCAST_HEAD = 0x74      # blockId + itemCount
FN_BCAST_BODY = 0x75      # positional 3-septet wire16 values (index == paramId)
FN_BCAST_END = 0x76

SUB_SET_TYPED = (0x09, 0x00)       # discrete select: float32(ordinal)
SUB_SET_CONTINUOUS = (0x52, 0x00)  # knob: float32(normalized 0..1)
SUB_GET_TYPE_NAME = (0x1F, 0x00)   # read current type/model name


def checksum(body: list[int]) -> int:
    x = 0xF0
    for b in body:
        x ^= b
    return x & 0x7F


def envelope(fn: int, payload: list[int], model: int = MODEL_FM9) -> list[int]:
    """Full message byte list including F0/F7, ready for mido sysex data[1:-1]."""
    body = [*MFR, model, fn, *payload]
    return [0xF0, *body, checksum(body), 0xF7]


def encode14(v: int) -> tuple[int, int]:
    return (v & 0x7F, (v >> 7) & 0x7F)


def decode14(lo: int, hi: int) -> int:
    return (lo & 0x7F) | ((hi & 0x7F) << 7)


def encode_f32_septets(value: float) -> list[int]:
    bits = struct.unpack("<I", struct.pack("<f", value))[0]
    return [(bits >> (7 * i)) & 0x7F for i in range(5)]


def decode_f32_septets(s: list[int]) -> float:
    bits = 0
    for i, b in enumerate(s[:5]):
        bits |= (b & 0x7F) << (7 * i)
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


# --- builders: official commands ---

def build_get_scene() -> list[int]:
    return envelope(FN_SCENE, [0x7F])


def build_set_scene(scene_1based: int) -> list[int]:
    if not 1 <= scene_1based <= 8:
        raise ValueError(f"scene must be 1..8, got {scene_1based}")
    return envelope(FN_SCENE, [scene_1based - 1])


def build_get_patch_name(preset: int | None = None) -> list[int]:
    if preset is None:
        return envelope(FN_PATCH_NAME, [0x7F, 0x7F])
    return envelope(FN_PATCH_NAME, list(encode14(preset)))


def build_get_scene_name(scene_1based: int | None = None) -> list[int]:
    return envelope(FN_SCENE_NAME, [0x7F if scene_1based is None else scene_1based - 1])


def build_get_bypass(effect_id: int) -> list[int]:
    return envelope(FN_BYPASS, [*encode14(effect_id), 0x7F])


def build_set_bypass(effect_id: int, bypassed: bool) -> list[int]:
    return envelope(FN_BYPASS, [*encode14(effect_id), 1 if bypassed else 0])


def build_get_channel(effect_id: int) -> list[int]:
    return envelope(FN_CHANNEL, [*encode14(effect_id), 0x7F])


def build_set_channel(effect_id: int, channel_0based: int) -> list[int]:
    if not 0 <= channel_0based <= 3:
        raise ValueError("channel must be 0..3 (A..D)")
    return envelope(FN_CHANNEL, [*encode14(effect_id), channel_0based])


def build_status_dump() -> list[int]:
    return envelope(FN_STATUS_DUMP, [])


def build_get_firmware() -> list[int]:
    return envelope(FN_FIRMWARE, [])


def build_get_tempo() -> list[int]:
    return envelope(FN_TEMPO_BPM, [0x7F, 0x7F])


def build_set_tempo(bpm: int) -> list[int]:
    return envelope(FN_TEMPO_BPM, list(encode14(bpm)))


# --- builders: editor protocol (community, fw-11.x pinned) ---

def _build_param_frame(sub: tuple[int, int], effect_id: int, param_id: int,
                       value_f32: float) -> list[int]:
    return envelope(FN_PARAM, [
        *sub,
        *encode14(effect_id),
        *encode14(param_id),
        *encode_f32_septets(value_f32),
        0x00, 0x00, 0x00, 0x00,
    ])


def build_set_param_continuous(effect_id: int, param_id: int, normalized: float) -> list[int]:
    return _build_param_frame(SUB_SET_CONTINUOUS, effect_id, param_id,
                              min(1.0, max(0.0, normalized)))


def build_set_param_discrete(effect_id: int, param_id: int, ordinal: int) -> list[int]:
    return _build_param_frame(SUB_SET_TYPED, effect_id, param_id, float(ordinal))


def build_get_param(effect_id: int, param_id: int) -> list[int]:
    return _build_param_frame(SUB_SET_TYPED, effect_id, param_id, 0.0)


def build_get_type_name(effect_id: int, type_param_id: int) -> list[int]:
    return _build_param_frame(SUB_GET_TYPE_NAME, effect_id, type_param_id, 0.0)


# --- name writes (editor protocol: sub 0x28 preset, sub 0x2B scene) ---

def pack_value_8to7(raw: bytes) -> list[int]:
    """Sliding-window 8-to-7 pack: N raw bytes -> N+1 septets."""
    out = []
    carry = 0
    for i, b in enumerate(raw):
        k = i + 1
        out.append((((b >> k) & 0x7F) | carry) & 0x7F)
        carry = (((~(0x7F << k) & 0xFF) & b) << (7 - k)) & 0x7F
    out.append(carry)
    return out


def pack_chunked(raw: bytes) -> list[int]:
    """Chunked 8-to-7 pack: window restarts every 7 raw bytes."""
    out = []
    for off in range(0, len(raw), 7):
        out.extend(pack_value_8to7(raw[off:off + 7]))
    return out


def _name32(name: str) -> bytes:
    name = "".join(c if 0x20 <= ord(c) <= 0x7E else " " for c in name)[:32]
    return name.ljust(32).encode("ascii")


def _build_name_frame(sub: int, param_id: int, name: str) -> list[int]:
    return envelope(FN_PARAM, [
        sub, 0x00,
        0x00, 0x00,
        *encode14(param_id),
        0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00,
        *encode14(32),
        *pack_chunked(_name32(name)),
    ])


def build_rename_preset(name: str) -> list[int]:
    """Rename the working-buffer preset (fn 0x01 sub 0x28). Edit buffer only."""
    return _build_name_frame(0x28, 0, name)


def build_set_scene_name(scene_index_0based: int, name: str) -> list[int]:
    """Rename a scene (fn 0x01 sub 0x2B). Edit buffer only."""
    if not 0 <= scene_index_0based <= 7:
        raise ValueError("scene index 0..7")
    return _build_name_frame(0x2B, scene_index_0based, name)


def unpack_value_7to8(wire: list[int], raw_len: int) -> bytes:
    out = bytearray(raw_len)
    for i in range(min(len(wire), raw_len + 1)):
        k = i + 1
        b = wire[i] & 0x7F
        if i > 0 and i - 1 < raw_len:
            out[i - 1] |= ((~(0x7F >> k) & 0xFF) & b) >> (8 - k) & 0xFF
        if i < raw_len:
            out[i] = (b << k) & 0xFF
    return bytes(out)


def unpack_chunked(wire: list[int], raw_len: int) -> bytes:
    out = bytearray()
    raw_pos = wire_pos = 0
    while raw_pos < raw_len:
        chunk_raw = min(7, raw_len - raw_pos)
        chunk_wire = 8 if chunk_raw == 7 else chunk_raw + 1
        out += unpack_value_7to8(wire[wire_pos:wire_pos + chunk_wire], chunk_raw)
        raw_pos += chunk_raw
        wire_pos += chunk_wire
    return bytes(out)


def parse_type_name_response(data: list[int]) -> tuple[int, int, str] | None:
    """Parse a fn=0x01 GET/type-name response carrying a length-prefixed,
    8-to-7 packed display string. Returns (effect_id, param_id, name)."""
    if not is_fractal(data, FN_PARAM):
        return None
    payload = data[5:-1]
    if len(payload) < 17 or (payload[0] == 0x04 and payload[1] == 0x01):
        return None
    str_len = (payload[13] & 0x7F) | ((payload[14] & 0x7F) << 7)
    if str_len <= 0 or len(payload) < 15 + str_len:
        return None
    raw = unpack_chunked(payload[15:], str_len)
    name = raw.decode("ascii", "replace").rstrip("\x00 ")
    return (decode14(payload[2], payload[3]), decode14(payload[4], payload[5]), name)


# --- modifier binding (community; FM9 slot N = effect id 3 + N-1) ---

MOD_SLOT_BASE = 3
MOD_SLOT_COUNT = 32
MOD_PID_SOURCE = 0
MOD_PID_MIN = 1
MOD_PID_MAX = 2
MOD_PID_TARGET_EFFECT = 8
MOD_PID_TARGET_PARAM = 9

#: The slot's own fields, in the order finding 17 verified. Everything in
#: 1..14 except the two target pids, which are written afterwards and
#: discretely. Writing past pid 14 corrupted a slot and triggered the device's
#: load-time clear, so the range is a boundary, not a guess.
MOD_FIELD_PIDS = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14)

#: The subset of those fields this project has defaults for: a linear transfer
#: curve. Pids 7 and 10-12 are absent deliberately. Nobody here knows what
#: they mean, and a continuous write of 0.0 is the zeroed-GET (a read, not a
#: write), so they cannot even be zeroed on purpose. That gap IS finding 12:
#: a slot built from these alone is the from-scratch case with the reversed or
#: dead sweeps. Clone a working slot instead wherever the preset has one.
MOD_DEFAULT_FIELDS = {1: 0.0, 2: 1.0, 3: 0.0, 4: 0.5, 5: 1.0, 6: 0.5,
                      13: 0.5, 14: 0.5}


def mod_slot_eid(slot_1based: int) -> int:
    if not 1 <= slot_1based <= MOD_SLOT_COUNT:
        raise ValueError("modifier slot 1..32")
    return MOD_SLOT_BASE + slot_1based - 1


def pack5_uint(v: int) -> list[int]:
    return [(v >> (7 * i)) & 0x7F for i in range(5)]


# --- store (guarded; see device.SAFE_STORE_SLOTS) ---

def build_store_preset(preset_number: int) -> list[int]:
    """fn 0x01 sub 0x26: persist the working buffer to a preset slot.
    DESTRUCTIVE for that slot. Callers must go through FM9.store_preset,
    which enforces the safe-slot whitelist."""
    return envelope(FN_PARAM, [
        0x26,
        0x00, 0x00, 0x00, 0x00, 0x00,
        *encode14(preset_number),
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ])


# --- grid protocol (community, FM9 6 rows x 14 cols) ---

GRID_ROWS = 6
GRID_COLS = 14
SUB_GRID_LAYOUT = 0x2E   # live grid read
SUB_GRID_INSERT = 0x32   # place block in cell (blockId 0 clears)
SUB_GRID_ROUTING = 0x35  # draw/remove cable between adjacent columns
ROUTING_CONNECT = 0x01
ROUTING_DISCONNECT = 0x02


def build_request_grid_layout() -> list[int]:
    return envelope(FN_PARAM, [SUB_GRID_LAYOUT, 0x00] + [0x00] * 13)


def build_select_grid_cell(row: int, col: int) -> list[int]:
    """Move the editor cursor to a cell (fn 0x01 sub 0x30, raw uint32 pos).
    Must precede build_set_grid_cell for the insert to honor its target."""
    grid_pos = (col - 1) * GRID_ROWS + (row - 1)
    return envelope(FN_PARAM, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00,
                               *pack5_uint(grid_pos), 0x00, 0x00, 0x00, 0x00])


def build_set_grid_cell(row: int, col: int, block_id: int) -> list[int]:
    """Place block_id at 1-based (row, col); block_id 0 clears the cell."""
    if not (1 <= row <= GRID_ROWS and 1 <= col <= GRID_COLS):
        raise ValueError("row/col out of range")
    grid_pos = (col - 1) * GRID_ROWS + (row - 1)
    return envelope(FN_PARAM, [
        SUB_GRID_INSERT, 0x00,
        *encode14(block_id), 0x00, 0x00,
        *encode14(grid_pos),
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    ])


def build_set_grid_routing(src_row: int, src_col: int, dest_row: int,
                           op: int = ROUTING_CONNECT) -> list[int]:
    """Cable from (src_row, src_col) to (dest_row, src_col+1). 6-row formula.
    Source row 1 with an even column is not decoded yet and raises."""
    if src_row == 1 and src_col % 2 == 0:
        raise ValueError("cable from row 1 of an even column is not decoded yet")
    src_gp = (src_col - 1) * GRID_ROWS + (src_row - 1)
    b21 = src_gp // 2
    col_term = (3 * (src_col - 1)) // 2 + 1
    if dest_row == src_row == 2:
        # same-row draws on row 2 use their own encoding, decoded by probe
        # on hardware fw 11.00 (2026-08-20): odd source column -> sign 0,
        # b23 3; even -> sign 1, b23 1. The general formula below is wrong
        # for this case (verified: it draws nothing).
        dest_sign, b23_val = (0, 3) if src_col % 2 else (1, 1)
    else:
        dest_sign = 1 if dest_row >= 3 else 0
        b23_val = (abs(dest_row - 3) + (2 if src_col % 2 == 0 else 0)) % 4
    b22 = ((src_gp & 1) << 6) | (col_term + dest_sign)
    b23 = b23_val << 5
    return envelope(FN_PARAM, [
        SUB_GRID_ROUTING, 0x00,
        0x00, 0x00, 0x00, 0x00,
        op,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x02, 0x00,
        b21, b22, b23,
    ])


def _read_bits_msb(data: list[int], bit: int, n: int) -> int:
    v = 0
    for i in range(n):
        b = bit + i
        v = (v << 1) | ((data[b // 7] >> (6 - (b % 7))) & 1)
    return v


@dataclass
class GridCell:
    row: int              # 0-based
    col: int              # 0-based
    effect_id: int | None
    is_shunt: bool
    cable_in_mask: int    # bits = source rows of the previous column


def parse_grid_layout(data: list[int]) -> list[GridCell] | None:
    """Decode a fn=0x01 sub=0x2E reply (mido data: no F0/F7, checksum last).
    The grid is a tail-anchored 7-bit-packed bitstream."""
    if not is_fractal(data, FN_PARAM) or len(data) < 8 or data[5] != SUB_GRID_LAYOUT:
        return None
    base_bit, row_stride = 46, 32
    col_stride = GRID_ROWS * row_stride
    region_bytes = -(-(base_bit + GRID_COLS * col_stride) // 7)
    region_offset = len(data) - 1 - region_bytes  # checksum is the last byte
    if region_offset < 349:
        return None
    region = data[region_offset:len(data) - 1]
    cells = []
    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            base = base_bit + col * col_stride + row * row_stride
            id_field = _read_bits_msb(region, base, 8) >> 1
            block_type = _read_bits_msb(region, base + 8, 8)
            is_shunt = block_type == 0x08
            if id_field == 0 and not is_shunt:
                continue
            cells.append(GridCell(row, col,
                                  None if is_shunt else id_field, is_shunt,
                                  _read_bits_msb(region, base + 16, 8)))
    return cells


def build_bulk_read_poll(effect_id: int) -> list[int]:
    """fn=0x1F whole-block read. Read-only; reply is a 0x74/0x75/0x76 burst."""
    return envelope(FN_BULK_READ, list(encode14(effect_id)))


def unpack_value16(lo: int, mid: int, top2: int) -> int:
    return (lo & 0x7F) | ((mid & 0x7F) << 7) | ((top2 & 0x03) << 14)


def parse_bcast_head(data: list[int]) -> tuple[int, int] | None:
    """(block_id, item_count) from a fn=0x74 head frame."""
    if not is_fractal(data, FN_BCAST_HEAD) or len(data) < 9:
        return None
    return (decode14(data[5], data[6]), decode14(data[7], data[8]))


def parse_bcast_body(data: list[int]) -> list[int] | None:
    """Positional wire16 values from a fn=0x75 body frame."""
    if not is_fractal(data, FN_BCAST_BODY) or len(data) < 9:
        return None
    body = data[7:-1]  # after sectionId + reserved, strip checksum
    return [unpack_value16(body[i], body[i + 1], body[i + 2])
            for i in range(0, len(body) - 2, 3)]


# --- display <-> wire scaling (linear / log10 onto 0..65534) ---

def display_to_normalized(display: float, dmin: float, dmax: float,
                          scale: str = "linear") -> float:
    display = min(dmax, max(dmin, display))
    if scale == "log10":
        ratio = math.log10(display / dmin) / math.log10(dmax / dmin)
    else:
        ratio = (display - dmin) / (dmax - dmin)
    return round(ratio * 65534) / 65534


def normalized_to_display(normalized: float, dmin: float, dmax: float,
                          scale: str = "linear") -> float:
    normalized = min(1.0, max(0.0, normalized))
    if scale == "log10":
        return dmin * (dmax / dmin) ** normalized
    return dmin + normalized * (dmax - dmin)


# --- parsers ---

@dataclass
class ParamEcho:
    effect_id: int
    param_id: int
    normalized: float
    display_name: str | None


def is_fractal(data: list[int], fn: int | None = None) -> bool:
    ok = len(data) >= 5 and tuple(data[:3]) == MFR
    return ok and (fn is None or data[4] == fn)


def parse_param_echo(data: list[int]) -> ParamEcho | None:
    """Parse an inbound fn=0x01 frame (mido data: no F0/F7). Returns None if
    the frame is not a value echo for a param (wrong fn or too short)."""
    if not is_fractal(data, FN_PARAM) or len(data) < 16:
        return None
    effect_id = decode14(data[7], data[8])
    param_id = decode14(data[9], data[10])
    normalized = decode_f32_septets(data[11:16])
    # Long GET responses carry a display string; scan tail for a printable run
    name = None
    tail = data[16:-1]
    run: list[str] = []
    best: list[str] = []
    for b in tail:
        if 0x20 <= b <= 0x7E:
            run.append(chr(b))
        else:
            if len(run) > len(best):
                best = run
            run = []
    if len(run) > len(best):
        best = run
    if len(best) >= 3:
        name = "".join(best).strip() or None
    return ParamEcho(effect_id, param_id, normalized, name)


def parse_multipurpose(data: list[int]) -> tuple[int, int] | None:
    """Returns (echoed_fn, result_code) for fn=0x64 ack/nack frames."""
    if not is_fractal(data, FN_MULTIPURPOSE) or len(data) < 8:
        return None
    return (data[5], data[6])


# --- name fields (fixed width, NUL padded) ---

NAME_FIELD_LEN = 32
EMPTY_SLOT_NAME = "<EMPTY>"     # the FM9's own marker for an unused slot

# The wire numbers presets 0..511. FM9-Edit and the unit's front panel number
# the same 512 slots 1..512, so anything a human reads needs +1. Verified on
# hardware: wire 0 is '59 Bassguy', which FM9-Edit lists as 001, and a chain
# built at wire 386 appears in FM9-Edit as 387.
PRESET_COUNT = 512


def editor_number(wire_preset: int) -> int:
    """Wire preset number as FM9-Edit and the front panel show it."""
    return wire_preset + 1


def slot_label(wire_preset: int) -> str:
    """Both numbers, the owner's first, for anything a person reads.

    Printing the wire number alone invites clearing the wrong preset: the
    owner checks the editor, sees a different number, and has to work out
    which of us is off by one.

    The EDITOR number leads. It is the number on the front panel, in
    FM9-Edit, and in the header pill, so it is the one every other number
    gets compared against. Leading with the wire number had the header
    saying 159 while the panel below said "158 (FM9-Edit 159)", which reads
    as the app disagreeing with itself about which preset is loaded
    (Moncy, 2026-09-01). The wire number rides in the bracket, named for
    what it is, because configs and MIDI tools still speak it.
    """
    return f"{editor_number(wire_preset)} (wire {wire_preset})"


def slot_set_label(slots) -> str:
    """A configured slot whitelist as it actually is, runs collapsed.

    Printing lowest-to-highest describes a contiguous set that may not be
    one: with 133,150-155 configured, "133-155" names every refused slot in
    between as allowed, which sends the reader off to fix the wrong thing.
    """
    runs: list[list[int]] = []
    for slot in sorted(set(slots)):
        if runs and slot == runs[-1][-1] + 1:
            runs[-1].append(slot)
        else:
            runs.append([slot])
    parts = []
    for run in runs:
        if len(run) == 1:
            parts.append(slot_label(run[0]))
        else:
            # Editor numbers lead, same as slot_label: every number a person
            # compares this against comes from the front panel.
            parts.append(f"{editor_number(run[0])}-{editor_number(run[-1])} "
                         f"(wire {run[0]}-{run[-1]})")
    return ", ".join(parts)


def is_empty_slot_name(name: str) -> bool:
    """True for the marker the FM9 itself writes into a cleared slot."""
    return name.strip() == EMPTY_SLOT_NAME


def decode_name_field(raw) -> tuple[str, str]:
    """Split a NUL-padded name field into (name, ghost).

    Clearing a preset writes "<EMPTY>\\0" over the FIRST 8 BYTES of the
    32-byte name field and leaves the rest of the previous name in flash, so
    the field must be cut at the FIRST NUL rather than merely right-stripped.
    What follows that NUL is a ghost: the tail (byte 8 onward) of whatever
    name used to occupy the slot. Diagnostic only - never a current name.
    """
    head, _, tail = bytes(raw).partition(b"\x00")
    name = head.decode("ascii", "replace").rstrip("\x00 ")
    ghost = tail.replace(b"\x00", b" ").decode("ascii", "replace").strip()
    return (name, ghost)


@dataclass
class SlotName:
    """A preset slot's stored name, with any ghost kept out of the name."""
    number: int
    name: str
    ghost: str = ""

    @property
    def empty(self) -> bool:
        return is_empty_slot_name(self.name)

    @property
    def editor(self) -> int:
        """This slot's number as FM9-Edit and the front panel show it."""
        return editor_number(self.number)

    @property
    def label(self) -> str:
        return slot_label(self.number)


def parse_patch_name_full(data: list[int]) -> SlotName | None:
    if not is_fractal(data, FN_PATCH_NAME) or len(data) < 40:
        return None
    name, ghost = decode_name_field(data[7:7 + NAME_FIELD_LEN])
    return SlotName(decode14(data[5], data[6]), name, ghost)


def parse_patch_name(data: list[int]) -> tuple[int, str] | None:
    got = parse_patch_name_full(data)
    return (got.number, got.name) if got else None


def parse_scene(data: list[int]) -> int | None:
    if not is_fractal(data, FN_SCENE) or len(data) < 6:
        return None
    return data[5] + 1


def parse_scene_name(data: list[int]) -> tuple[int, str] | None:
    if not is_fractal(data, FN_SCENE_NAME) or len(data) < 39:
        return None
    # Same fixed-width NUL-padded encoding as the preset name field. No ghost
    # has been observed here (an empty preset's scene names read as all-NUL),
    # so this shares decode_name_field for consistency, not as a fix.
    name, _ = decode_name_field(data[6:6 + NAME_FIELD_LEN])
    return (data[5] + 1, name)


def parse_bypass(data: list[int]) -> tuple[int, bool] | None:
    if not is_fractal(data, FN_BYPASS) or len(data) < 8:
        return None
    return (decode14(data[5], data[6]), bool(data[7]))


def parse_channel(data: list[int]) -> tuple[int, int] | None:
    if not is_fractal(data, FN_CHANNEL) or len(data) < 8:
        return None
    return (decode14(data[5], data[6]), data[7])


@dataclass
class BlockStatus:
    effect_id: int
    bypassed: bool
    channel: int          # 0..3 = A..D
    channels_supported: int


def parse_status_dump(data: list[int]) -> list[BlockStatus] | None:
    if not is_fractal(data, FN_STATUS_DUMP):
        return None
    out = []
    body = data[5:-1]
    for i in range(0, len(body) - 2, 3):
        eid = decode14(body[i], body[i + 1])
        dd = body[i + 2]
        out.append(BlockStatus(eid, bool(dd & 1), (dd >> 1) & 0x07, (dd >> 4) & 0x07))
    return out

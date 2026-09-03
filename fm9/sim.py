"""Virtual FM9: a frame-level simulator for hardware-free testing.

Speaks the same SysEx surface as fm9/protocol.py against in-memory state,
faithfully modeling the quirks learned on real hardware (fw 11.00):

- grid insert without a preceding cell-select lands on the internal cursor
- placing an already-placed block at another cell is IGNORED
- clearing a grid cell destroys its cables
- fresh modifier slots are all-zero (a bind without curve init is dead)
- sub 09 00 with value 0 on a continuous param is a no-op (the zeroed GET)
- display-name reads (sub 1F) never track the amp type (they return
  the roster's first entry), return NONE for modifier sources, and a
  stale constant elsewhere - plausible wrong values, never errors
- bulk reads are channel-blocked

- writes are ASYNC: reads within the settle window (80ms) see the old
  state, exactly like hardware; unsettled read-after-write races fail here
- undecoded territory is TRACKED, not silently simulated: touching
  anything hardware never verified (modifier curve writes, unproven cable
  geometries) lands in sim_core.undecoded for the run to report

HARD RULE: this is a REGRESSION tool, never verification. New protocol
claims are proven on hardware first, then taught to the sim. A sim pass
plus an EMPTY undecoded report means the script only used decoded,
hardware-proven operations; a non-empty report names exactly what still
needs ears on the real device (lesson of 2026-08-20).

Usage:
    from fm9.sim import SimFM9
    fm9 = SimFM9()            # an FM9 instance backed by the simulator
"""
from __future__ import annotations

import copy
import struct
from types import SimpleNamespace

from . import protocol as p
from .device import FM9
from .registry import Registry, EFFECT_ID_BASE

GRID_ROWS, GRID_COLS = 6, 14
STALE_NAME = "Quad-Tap Delay"   # the constant returned by non-amp 1F reads


def _f32_from_septets(s):
    bits = 0
    for i, b in enumerate(s[:5]):
        bits |= (b & 0x7F) << (7 * i)
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


class _Cell:
    def __init__(self, effect_id=None, is_shunt=False):
        self.effect_id = effect_id
        self.is_shunt = is_shunt
        self.cable_in_mask = 0   # bit n = fed from display row n of prev col


# Slots the simulated unit reports as empty, mirroring the layout observed on
# the reference FM9: a cleared slot keeps a ghost of its previous name, and
# some carry none (old name was <= 8 characters, or the slot was never used).
SIM_EMPTY_SLOTS = {386: "Phat Time", 387: "Live FM9+", 449: "", 511: ""}


def _copy_buffer(buf: dict) -> dict:
    """A preset buffer copy, without walking every integer in it.

    The settle window is modelled by snapshotting the whole buffer before each
    write, and `copy.deepcopy` was 16 of the 23 seconds of a single splice:
    fifteen MILLION calls, because a preset holds thousands of parameter ints
    and deepcopy memoises its way through each one. The shape here is known
    and entirely plain data, so slicing the lists does the same job at C
    speed.

    Unrecognised keys fall back to deepcopy rather than being aliased in,
    because a snapshot that shares mutable state with the live buffer would
    silently stop modelling the settle window at all, which is the one thing
    this copy exists for.
    """
    out = {}
    for k, v in buf.items():
        if k in ("number", "name", "tempo"):
            out[k] = v
        elif k == "scene_names":
            out[k] = dict(v)
        elif k == "grid":
            out[k] = {pos: copy.copy(cell) for pos, cell in v.items()}
        elif k == "scenes":
            out[k] = {sc: {eid: dict(st) for eid, st in blocks.items()}
                      for sc, blocks in v.items()}
        elif k == "params":
            out[k] = {eid: [chan[:] for chan in chans] for eid, chans in v.items()}
        elif k == "modifiers":
            out[k] = {slot: fields[:] for slot, fields in v.items()}
        else:
            out[k] = copy.deepcopy(v)
    return out


def _empty_preset(number: int) -> dict:
    """A cleared slot: no blocks, no grid, no cables, blank scene names.
    Hardware reads an empty preset's scene-name fields as all-NUL."""
    return {
        "number": number,
        "name": p.EMPTY_SLOT_NAME,
        "scene_names": {s: "" for s in range(1, 9)},
        "grid": {},
        "scenes": {s: {} for s in range(1, 9)},
        "params": {},
        "modifiers": {s: [0] * 25 for s in range(1, 33)},
        "tempo": 120,
    }


def _default_preset(number: int, reg: Registry) -> dict:
    """A minimal but realistic preset: In -> Amp -> Cab -> Delay -> Out on
    display row 2, with shunts, plus 8 scenes of per-block state."""
    grid = {}
    chain = [(2, 1, 37), (2, 2, None), (2, 3, 58), (2, 4, 62), (2, 5, None),
             (2, 6, 70), (2, 7, None), (2, 8, 118), (2, 9, 46), (2, 10, 66),
             (2, 11, 42), (2, 12, 50)]
    # ...fuzz, comp, reverb: realistic recipe targets. The graphic EQ (50) is
    # here because it is the one block the UI draws differently, as faders
    # rather than rows, and a renderer nothing exercises is a renderer nobody
    # notices breaking.
    prev_row = None
    for row, col, eid in chain:
        c = _Cell(eid if eid else None, is_shunt=eid is None)
        if col > 1:
            c.cable_in_mask = 1 << 2   # fed from display row 2 of prev col
        grid[(row, col)] = c
    blocks = sorted({c.effect_id for c in grid.values() if c.effect_id})
    scenes = {s: {eid: {"bypassed": False, "channel": 0} for eid in blocks}
              for s in range(1, 9)}
    params = {}
    for eid in blocks:
        fam_inst = None
        for fam, (base, count) in EFFECT_ID_BASE.items():
            if base <= eid < base + count:
                fam_inst = fam
                break
        n_params = 1 + max((pid for (f, pid) in reg.params if f == fam_inst),
                           default=0)
        chans = 4 if eid not in (37, 42) else 1
        params[eid] = [[0] * n_params for _ in range(chans)]
    return {
        "number": number,
        "name": f"Sim Preset {number}",
        "scene_names": {s: f"Scene {s}" for s in range(1, 9)},
        "grid": grid,
        "scenes": scenes,
        "params": params,                     # per block: [channel][pid] wire16
        "modifiers": {s: [0] * 25 for s in range(1, 33)},   # all-zero slots!
        "tempo": 120,
    }


class SimState:
    def __init__(self, reg: Registry | None = None):
        self.reg = reg or Registry()
        self.presets: dict[int, dict] = {}
        # slot -> ghost of the name it used to hold
        self.empty_slots: dict[int, str] = dict(SIM_EMPTY_SLOTS)
        self.buffer = self._load(0)
        self.scene = 1
        self.cursor = 0          # internal grid cursor (cell index)
        self.selected = False    # was a cell-select received since last insert

    def _load(self, number: int) -> dict:
        if number not in self.presets:
            self.presets[number] = (
                _empty_preset(number) if number in self.empty_slots
                else _default_preset(number, self.reg))
        return _copy_buffer(self.presets[number])

    def select_preset(self, number: int):
        self.buffer = self._load(number)     # discards edit buffer
        self.scene = 1

    # -- helpers --
    def block_param(self, eid, pid, ch=None):
        ch = self.buffer["scenes"][self.scene].get(eid, {}).get("channel", 0) if ch is None else ch
        rows = self.buffer["params"].get(eid)
        if rows is None or pid >= len(rows[0]):
            return None
        return rows[min(ch, len(rows) - 1)][pid]

    def set_block_param(self, eid, pid, wire, ch=None):
        ch = self.buffer["scenes"][self.scene].get(eid, {}).get("channel", 0) if ch is None else ch
        rows = self.buffer["params"].get(eid)
        if rows is not None and pid < len(rows[0]):
            rows[min(ch, len(rows) - 1)][pid] = max(0, min(65534, int(wire)))


class SimFM9Core:
    """Consumes protocol frames, mutates SimState, emits response frames."""

    def __init__(self, state: SimState | None = None):
        self.st = state or SimState()

    def handle(self, frame: list[int]) -> list[list[int]]:
        d = frame[1:-1]                        # strip F0/F7 -> mido-style data
        if list(d[:3]) != list(p.MFR) or d[3] != p.MODEL_FM9:
            return []
        fn = d[4]
        body = d[5:-1]                          # strip checksum
        h = getattr(self, f"_fn_{fn:02x}", None)
        return h(body) if h else []

    # ---- preset install (0x77/0x78/0x79 dump receive) --------------------
    # The write direction is hardware-unverified everywhere, this simulator
    # included, so it reports itself as undecoded territory while still
    # modeling the documented behavior: a header names the slot, chunks
    # carry the body, the footer commits, and the slot then reads back
    # under the file's embedded name.
    def _fn_77(self, b):
        # BIG-endian septets, unlike the little-endian ids elsewhere: the
        # dump header is the one place the wire flips (SYSEX-MAP, confirmed
        # on captured FM9 requests).
        self._install = {"slot": ((b[0] & 0x7F) << 7) | (b[1] & 0x7F),
                         "chunks": []}
        return []

    def _fn_78(self, b):
        if getattr(self, "_install", None) is not None:
            self._install["chunks"].append(list(b))
        return []

    def _fn_79(self, b):
        pending = getattr(self, "_install", None)
        self._install = None
        if not pending or not pending["chunks"]:
            return []
        from fm9 import presetfile
        chunk0 = pending["chunks"][0]
        chars = []
        for i in range(presetfile.NAME_MAX_WORDS):
            off = presetfile.CHUNK_BODY_OFFSET \
                + (presetfile.NAME_FIRST_WORD + i) * 3
            w = (chunk0[off] | (chunk0[off + 1] << 7)
                 | (chunk0[off + 2] << 14)) & 0xFFFF
            lo, hi = w & 0xFF, (w >> 8) & 0xFF
            if lo == 0:
                break
            chars.append(chr(lo))
            if hi == 0:
                break
            chars.append(chr(hi))
        slot = pending["slot"]
        self.st.presets.setdefault(slot, {})["name"] = "".join(chars).rstrip()
        self.st.empty_slots.pop(slot, None)
        self.undecoded.add(
            "preset install (0x77/0x78/0x79 write direction) is not "
            "hardware-verified; verify the slot name on a real unit")
        return []

    # ---- official surface ----
    def _fn_0c(self, b):
        if b and b[0] != 0x7F:
            self.st.scene = b[0] + 1
        return [p.envelope(p.FN_SCENE, [self.st.scene - 1])]

    @staticmethod
    def _name_field(name: str, ghost: str = "") -> list[int]:
        """32-byte NUL-padded name field. A cleared slot has "<EMPTY>\\0"
        written over its first 8 bytes with the old name's tail left behind,
        which is what makes cutting at the first NUL mandatory."""
        raw = name.encode("ascii", "replace")
        if p.is_empty_slot_name(name):
            raw += b"\x00" + ghost.encode("ascii", "replace")
        return list(raw.ljust(p.NAME_FIELD_LEN, b"\x00")[:p.NAME_FIELD_LEN])

    def _fn_0d(self, b):
        """Answers for ANY slot by number, read from "flash": the loaded
        preset and the edit buffer are untouched (hardware behaves this way,
        verified over all 512 slots)."""
        if len(b) >= 2 and not (b[0] == 0x7F and b[1] == 0x7F):
            num = p.decode14(b[0], b[1])
            if num in self.st.empty_slots:
                field = self._name_field(p.EMPTY_SLOT_NAME,
                                         self.st.empty_slots[num])
            else:
                name = self.st.presets.get(num, {}).get("name") or \
                    _default_preset(num, self.st.reg)["name"]
                field = self._name_field(name)
        else:
            num, name = self.st.buffer["number"], self.st.buffer["name"]
            field = self._name_field(name, self.st.empty_slots.get(num, ""))
        return [p.envelope(p.FN_PATCH_NAME, [*p.encode14(num)] + field)]

    def _fn_0e(self, b):
        s = self.st.scene if (not b or b[0] == 0x7F) else b[0] + 1
        name = self.st.buffer["scene_names"].get(s, f"Scene {s}")
        # an empty preset reads as an all-NUL scene-name field
        field = ([0] * 32 if not name
                 else [ord(c) for c in name.ljust(32)[:32]])
        return [p.envelope(p.FN_SCENE_NAME, [s - 1] + field)]

    def _fn_0a(self, b):
        eid = p.decode14(b[0], b[1])
        st = self.st.buffer["scenes"][self.st.scene].setdefault(
            eid, {"bypassed": False, "channel": 0})
        if b[2] != 0x7F:
            st["bypassed"] = bool(b[2])
        return [p.envelope(p.FN_BYPASS, [*p.encode14(eid), 1 if st["bypassed"] else 0])]

    def _fn_0b(self, b):
        eid = p.decode14(b[0], b[1])
        st = self.st.buffer["scenes"][self.st.scene].setdefault(
            eid, {"bypassed": False, "channel": 0})
        if b[2] != 0x7F:
            st["channel"] = b[2]
        return [p.envelope(p.FN_CHANNEL, [*p.encode14(eid), st["channel"]])]

    def _fn_13(self, b):
        out = []
        for eid, st in sorted(self.st.buffer["scenes"][self.st.scene].items()):
            chans = len(self.st.buffer["params"].get(eid, [[0]]))
            dd = (1 if st["bypassed"] else 0) | (st["channel"] << 1) | (chans << 4)
            out += [*p.encode14(eid), dd]
        return [p.envelope(p.FN_STATUS_DUMP, out)]

    def _fn_14(self, b):
        if len(b) >= 2 and not (b[0] == 0x7F and b[1] == 0x7F):
            self.st.buffer["tempo"] = p.decode14(b[0], b[1])
        return [p.envelope(p.FN_TEMPO_BPM, list(p.encode14(self.st.buffer["tempo"])))]

    def _fn_08(self, b):
        return [p.envelope(p.FN_FIRMWARE, [11, 0, 0, 1])]

    # ---- bulk read ----
    def _fn_1f(self, b):
        eid = p.decode14(b[0], b[1])
        if 3 <= eid <= 34:                       # modifier slots are readable
            flat = list(self.st.buffer["modifiers"][eid - 2])
        else:
            rows = self.st.buffer["params"].get(eid)
            if rows is None:
                return [p.envelope(p.FN_MULTIPURPOSE, [0x1F, 0x08, 0x00])]
            flat = [v for row in rows for v in row]
        frames = [p.envelope(p.FN_BCAST_HEAD, [*p.encode14(eid), *p.encode14(len(flat))])]
        CHUNK = 128
        for off in range(0, len(flat), CHUNK):
            payload = [0x00, 0x00]
            for v in flat[off:off + CHUNK]:
                payload += [v & 0x7F, (v >> 7) & 0x7F, (v >> 14) & 0x03]
            frames.append(p.envelope(p.FN_BCAST_BODY, payload))
        frames.append(p.envelope(p.FN_BCAST_END, []))
        return frames

    # ---- editor protocol ----
    def _fn_01(self, b):
        sub = (b[0], b[1])
        if sub == (0x09, 0x00):
            return self._set_discrete(b)
        if sub == (0x52, 0x00):
            return self._set_continuous(b)
        if sub == (0x1F, 0x00):
            return self._type_name(b)
        if sub == (0x30, 0x00):
            self.st.cursor = b[6] | (b[7] << 7)   # raw uint32 low septets
            self.st.selected = True
            return []
        if sub == (0x32, 0x00):
            return self._grid_insert(b)
        if sub == (0x35, 0x00):
            return self._cable(b)
        if sub == (0x2E, 0x00):
            return self._grid_read(b)
        if sub == (0x28, 0x00):
            self.st.buffer["name"] = self._unpack_name(b)
            return []
        if sub == (0x2B, 0x00):
            self.st.buffer["scene_names"][b[4] + 1] = self._unpack_name(b)
            return []
        if sub == (0x26, 0x00):
            slot = p.decode14(b[6], b[7])
            snap = _copy_buffer(self.st.buffer)
            snap["number"] = slot
            self.st.presets[slot] = snap
            self.st.buffer = _copy_buffer(snap)
            return []
        return []

    def _target(self, b):
        return p.decode14(b[2], b[3]), p.decode14(b[4], b[5])

    def _set_discrete(self, b):
        eid, pid = self._target(b)
        val = _f32_from_septets(b[6:11])
        if 3 <= eid <= 34:                       # modifier slot params
            slots = self.st.buffer["modifiers"]
            slots[eid - 2][pid] = int(round(val)) if pid < 25 else 0
            return []
        # A discrete write stores the integer, and NOT only for parameters the
        # reference calls enum. CABINET_TYPE1 declares float while holding a
        # cab ordinal in its wire value, and on hardware a discrete write of
        # 200 to it read back as exactly 200 (2026-08-29). Restricting this to
        # enums made cab auditioning untestable here while it worked on the
        # unit, which is the wrong way round for a test double.
        #
        # Value 0 is the exception, and it is not a special case we invented:
        # sub 09 00 carrying zero IS the device's zeroed GET, so it reads
        # rather than writes. It does that for EVERY parameter, not only the
        # continuous ones. Narrowing it by parameter kind invents a
        # distinction the device does not make, and the proof is in
        # device.set_param_ordinal: ordinal 0 is sent as a CONTINUOUS 0.0
        # precisely because the discrete path cannot carry it. So there is no
        # such thing as a discrete write of zero that lands, and a simulator
        # that lets one land is more permissive than the hardware, which is
        # the wrong direction for a test double to be wrong in.
        if val:
            self.st.set_block_param(eid, pid, int(round(val)))
        return [self._echo(eid, pid)]

    def _set_continuous(self, b):
        eid, pid = self._target(b)
        norm = max(0.0, min(1.0, _f32_from_septets(b[6:11])))
        if 3 <= eid <= 34:
            self.st.buffer["modifiers"][eid - 2][pid] = int(round(norm * 65534))
            return []
        self.st.set_block_param(eid, pid, round(norm * 65534))
        return [self._echo(eid, pid)]

    def _echo(self, eid, pid):
        wire = self.st.block_param(eid, pid) or 0
        norm = wire / 65534
        bits = struct.unpack("<I", struct.pack("<f", norm))[0]
        sept = [(bits >> (7 * i)) & 0x7F for i in range(5)]
        return p.envelope(p.FN_PARAM, [0x09, 0x00, *p.encode14(eid),
                                       *p.encode14(pid), *sept, 0, 0, 0, 0])

    def _type_name(self, b):
        eid, pid = self._target(b)
        if 58 <= eid <= 61:
            # The 0x1F name query does NOT track DISTORT_TYPE: it returns
            # the roster's FIRST entry regardless of the actual amp, before
            # and after writes, through >=3s of settle. Proven on fw 12.00
            # by @bschmalz81401 (PR #15) and reproduced exactly on the
            # fw 11.00 reference unit 2026-08-21. The earlier "fresh for
            # amp" model here was a misread of an early session.
            name = self.st.reg.amp_roster.get("0", "Unknown")
        elif 3 <= eid <= 34:
            name = "NONE"                        # mod sources: stale NONE
        else:
            name = STALE_NAME                    # everything else: stale
        raw = name.encode("ascii", "replace")
        payload = [0x1F, 0x00, *p.encode14(eid), *p.encode14(pid),
                   0, 0, 0, 0, 0, 0, 0, *p.encode14(len(raw)),
                   *p.pack_chunked(raw)]
        return [p.envelope(p.FN_PARAM, payload)]

    def _grid_insert(self, b):
        block_id = p.decode14(b[2], b[3])
        grid_pos = p.decode14(b[6], b[7])
        # QUIRK: without a preceding select, insert lands on the cursor cell
        pos = grid_pos if self.st.selected else self.st.cursor
        self.st.selected = False
        col, row = divmod(pos, GRID_ROWS)
        key = (row + 1, col + 1)
        grid = self.st.buffer["grid"]
        if block_id == 0:
            grid.pop(key, None)                  # QUIRK: clear kills cables too
            return []
        # QUIRK: placing an already-placed block elsewhere is IGNORED
        placed = {c.effect_id for c in grid.values() if c.effect_id}
        if block_id in placed:
            return []
        cell = grid.get(key) or _Cell()
        cell.effect_id, cell.is_shunt = block_id, False
        grid[key] = cell
        if block_id not in self.st.buffer["params"]:
            fam = self.st.reg.family_of_effect_id(block_id)
            n = 1 + max((pid for (f, pid) in self.st.reg.params if fam and f == fam[0]), default=0)
            self.st.buffer["params"][block_id] = [[0] * n for _ in range(4)]
        self.st.buffer["scenes"][self.st.scene].setdefault(
            block_id, {"bypassed": False, "channel": 0})
        for s in range(1, 9):
            self.st.buffer["scenes"][s].setdefault(
                block_id, {"bypassed": False, "channel": 0})
        return []

    _CABLE_LUT = None

    @classmethod
    def _cable_lut(cls):
        if cls._CABLE_LUT is None:
            lut = {}
            # same-row draws go in LAST: their hardware-decoded bytes collide
            # with what the general formula predicts for some cross-row draws
            # (the formula is only verified where hardware confirmed it), and
            # the hardware-verified meaning must win the collision.
            for same_row_pass in (False, True):
                for sc in range(1, 14):
                    for sr in range(1, 7):
                        if sr == 1 and sc % 2 == 0:
                            continue
                        for dr in range(1, 7):
                            if (dr == sr) != same_row_pass:
                                continue
                            f = p.build_set_grid_routing(sr, sc, dr)
                            lut[tuple(f[1:-1][5:][15:18])] = (sr, sc, dr)
            cls._CABLE_LUT = lut
        return cls._CABLE_LUT

    def _cable(self, b):
        op = b[6]
        key = tuple(b[15:18])
        hit = self._cable_lut().get(key)
        if not hit:
            return [p.envelope(p.FN_MULTIPURPOSE, [0x01, 0x16, 0x00])]
        sr, sc, dr = hit
        cell = self.st.buffer["grid"].setdefault((dr, sc + 1), _Cell(is_shunt=False))
        if op == p.ROUTING_CONNECT:
            cell.cable_in_mask |= (1 << sr)
        else:
            cell.cable_in_mask &= ~(1 << sr)
        return []

    def _grid_read(self, b):
        base_bit, row_stride = 46, 32
        region_bytes = -(-(base_bit + GRID_COLS * GRID_ROWS * row_stride) // 7)
        region = [0] * region_bytes

        def put(bit, n, val):
            for i in range(n):
                if (val >> (n - 1 - i)) & 1:
                    region[(bit + i) // 7] |= 1 << (6 - ((bit + i) % 7))

        for (row1, col1), cell in self.st.buffer["grid"].items():
            base = base_bit + (col1 - 1) * GRID_ROWS * row_stride + (row1 - 1) * row_stride
            ident = 0x08 if cell.is_shunt else ((cell.effect_id or 0) & 0x7F)
            put(base, 8, (ident << 1) & 0xFF)
            put(base + 8, 8, 0x08 if cell.is_shunt else 0x00)
            put(base + 16, 8, cell.cable_in_mask & 0xFF)
        payload = [0x2E, 0x00] + [0] * 354 + region
        return [p.envelope(p.FN_PARAM, payload)]

    def _unpack_name(self, b):
        return p.unpack_chunked(list(b[15:]), 32).decode("ascii", "replace").rstrip("\x00 ")


class _SimIn:
    def __init__(self):
        self.queue = []

    def iter_pending(self):
        q, self.queue = self.queue, []
        yield from q

    def close(self):
        pass


WRITE_SUBS = {0x09, 0x52, 0x28, 0x2B, 0x26, 0x30, 0x32, 0x35}
READ_SUBS = {0x2E, 0x1F}
SETTLE = 0.08          # hardware settle window: reads inside it see OLD state


def _classify(d):
    """'write' | 'read' | None for a mido-style frame body."""
    fn, body = d[4], d[5:-1]
    if fn == 0x01 and body:
        if body[0] in WRITE_SUBS:
            return "write"
        if body[0] in READ_SUBS:
            return "read"
        return None
    if fn in (0x0A, 0x0B):
        return "write" if len(body) >= 3 else "read"
    if fn == 0x0C:
        return "write" if (body and body[0] != 0x7F) else "read"
    if fn == p.FN_TEMPO_BPM:
        return "write" if len(body) >= 2 else "read"
    if fn in (0x0D, 0x0E, 0x13, 0x1F):     # 0x1F = bulk param read
        return "read"
    return None


class _SimOut:
    def __init__(self, core: SimFM9Core, inp: _SimIn):
        self.core, self.inp = core, inp
        core.undecoded = set()
        core._snapshot = None
        core._snapshot_expire = 0.0

    def _note_undecoded(self, d):
        body = d[5:-1]
        if d[4] == 0x01 and body and body[0] in (0x09, 0x52) and len(body) >= 4:
            eid = p.decode14(body[2], body[3])
            if 3 <= eid <= 34:
                self.core.undecoded.add(
                    f"modifier slot {eid - 2} written: curve semantics are "
                    f"undecoded on hardware (issue #11) - EAR-VERIFY the sweep")
        if d[4] == 0x01 and body and body[0] == 0x35:
            hit = SimFM9Core._cable_lut().get(tuple(body[15:18]))
            if hit:
                sr, sc, dr = hit
                # same-row runs confirmed on hardware for rows 2-5: row 2 by
                # its own encoding (finding 6), rows 4 and 5 in the 2026-08-21
                # session, row 3 while building a preset from scratch
                # (finding 20). Rows 1 and 6 are untried.
                verified = (dr == sr and sr in (2, 3, 4, 5)) or abs(dr - sr) == 1
                if not verified:
                    self.core.undecoded.add(
                        f"cable r{sr}c{sc}->r{dr}c{sc + 1}: geometry not "
                        f"hardware-verified; confirm on device before trusting")

    def send(self, msg):
        if msg.type == "sysex":
            import time as _time
            frame = [0xF0, *msg.data, 0xF7]
            d = frame[1:-1]
            kind = _classify(d) if len(d) > 5 else None
            now = _time.monotonic()
            if kind == "write":
                self._note_undecoded(d)
                # hardware applies writes asynchronously: snapshot the
                # pre-write state so reads inside the settle window see it
                if now >= self.core._snapshot_expire:
                    self.core._snapshot = _copy_buffer(self.core.st.buffer)
                self.core._snapshot_expire = now + SETTLE
                for resp in self.core.handle(frame):
                    self.inp.queue.append(SimpleNamespace(type="sysex", data=resp[1:-1]))
                return
            if kind == "read" and self.core._snapshot is not None                     and now < self.core._snapshot_expire:
                live = self.core.st.buffer
                self.core.st.buffer = self.core._snapshot
                try:
                    for resp in self.core.handle(frame):
                        self.inp.queue.append(SimpleNamespace(type="sysex", data=resp[1:-1]))
                finally:
                    self.core.st.buffer = live
                return
            for resp in self.core.handle(frame):
                self.inp.queue.append(SimpleNamespace(type="sysex", data=resp[1:-1]))
        elif msg.type == "program_change":
            bank = getattr(self.core, "_bank", 0)
            self.core.st.select_preset(bank * 128 + msg.program)
        elif msg.type == "control_change" and msg.control == 0:
            self.core._bank = msg.value

    def close(self):
        pass


def SimFM9(registry: Registry | None = None) -> FM9:
    """An FM9 device instance backed by the simulator."""
    core = SimFM9Core(SimState(registry))
    inp = _SimIn()
    outp = _SimOut(core, inp)
    dev = FM9(registry=core.st.reg, ports=(inp, outp))
    dev.sim_core = core   # exposed for test assertions
    return dev

"""Parse, validate and retarget user-cab (IR) files (.syx). Issue #42 ph4.

A cab export is the 0x7A/0x7B/0x7C dump family (requested from a device
with fn 0x19): one head, a run of body chunks, one tail. Verified against
a real artist export (Wes Hauch, Gift of Tone 2023): 12 B head + 8 x
1290 B chunks + 13 B tail, every frame passing the family XOR checksum.

Two facts of life this module owns honestly:

- IRs are family-shared, so artists export them with whatever model byte
  their editor had (the Wes file says Axe-Fx III). Installing to an FM9
  rewrites the model byte on every frame, checksums recomputed. This
  rewrite is UNVERIFIED on hardware until the first live install.
- The head carries a 0x7F 0x7F no-slot sentinel on exports, so the file
  cannot say which user-cab slot it belongs in. Fractal's own editors
  name exports "U{n}-...", and that filename convention is the artist
  stating the slot their presets reference: it is offered as the default
  destination, which is precisely the step players get wrong by hand.

The name embedded in the body is packed among IR data and is not decoded
here; the filename is the human label and is presented as exactly that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import protocol as p

FN_HEAD, FN_CHUNK, FN_FOOT = 0x7A, 0x7B, 0x7C
CAB_DUMP_FNS = frozenset({FN_HEAD, FN_CHUNK, FN_FOOT})

#: Fractal editors name cab exports U{slot}-... ; the artist's own filing.
_SLOT_RE = re.compile(r"^U(\d{1,4})[-_ ]", re.IGNORECASE)


class CabFileError(ValueError):
    """Written for the person who dragged the file in."""


@dataclass
class CabFile:
    frames: list[list[int]]
    source_model: int
    label: str                     # from the filename; the body name is
                                   # packed among IR data and not decoded

    @property
    def chunks(self) -> int:
        return len(self.frames) - 2


def default_slot(filename: str) -> int | None:
    """The user-cab slot the artist filed this for, per the U{n} naming
    convention, as a 0-based wire index. None when the name does not say."""
    m = _SLOT_RE.match(filename.rsplit("/", 1)[-1])
    if not m:
        return None
    n = int(m.group(1))
    return n - 1 if n >= 1 else None


def parse(raw: bytes, filename: str = "") -> CabFile:
    frames, cur = [], None
    for b in raw:
        if b == 0xF0:
            cur = [0xF0]
        elif cur is not None:
            cur.append(b)
            if b == 0xF7:
                frames.append(cur)
                cur = None
    if cur is not None:
        raise CabFileError("the file ends mid-message; it looks truncated")
    if not frames:
        raise CabFileError("no MIDI messages in the file at all")
    models = set()
    for i, f in enumerate(frames):
        if len(f) < 9 or f[1:4] != list(p.MFR):
            raise CabFileError(
                f"message {i + 1} is not a Fractal message; this does not "
                "look like a Fractal cab file")
        if p.checksum(f[1:-2]) != f[-2]:
            raise CabFileError(
                f"message {i + 1} fails its checksum; the file is corrupt")
        models.add(f[4])
    if len(models) != 1:
        raise CabFileError("the file mixes device model bytes; refusing it")
    fns = [f[5] for f in frames]
    if fns[0] != FN_HEAD or fns[-1] != FN_FOOT or len(frames) < 3 \
            or any(fn != FN_CHUNK for fn in fns[1:-1]):
        raise CabFileError(
            "not a user-cab dump: expected one 0x7A head, a run of 0x7B "
            f"chunks and a 0x7C tail, found {['0x%02X' % f for f in fns]}")
    base = filename.rsplit("/", 1)[-1]
    label = re.sub(r"^U\d{1,4}[-_ ]*(Cab[-_ ]*)?", "", base,
                   flags=re.IGNORECASE)
    label = re.sub(r"\.syx$", "", label, flags=re.IGNORECASE) \
        .replace("_", " ").strip() or base
    return CabFile(frames=frames, source_model=models.pop(), label=label)


#: The head's fourth payload byte on a captured export. Reads and the
#: bank encoding are probed against the device before any write, so this
#: is a starting point, never an assumption sent blind.
DEFAULT_TAG = 0x10


def retarget(cf: CabFile, slot: int, model: int = p.MODEL_FM9,
             tag: int = DEFAULT_TAG) -> list[list[int]]:
    """The file's frames aimed at user-cab index `slot` on `model`.

    Model byte rewritten on every frame (IRs are family-shared; the frames
    must claim the device they are entering), the head's index field set
    big-endian like the preset head, the head's tag byte set to the value
    the device itself confirmed for the destination (see the device
    layer's probe), every touched frame re-checksummed. The write
    direction is UNVERIFIED on hardware until the first live install, and
    callers must verify by reading the slot back.
    """
    if not 0 <= slot <= 0x3FFF:
        raise CabFileError(f"user cab slot {slot} is out of range")
    out = []
    for i, f in enumerate(cf.frames):
        g = list(f)
        g[4] = model
        if i == 0:
            g[6] = (slot >> 7) & 0x7F
            g[7] = slot & 0x7F
            if len(g) > 10:
                g[9] = tag & 0x7F
        g[-2] = p.checksum(g[1:-2])
        out.append(g)
    return out

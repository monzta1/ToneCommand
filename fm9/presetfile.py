"""Parse, validate and retarget Fractal gen-3 preset files (.syx).

A preset file is the device's own dump stream saved to disk: one fn=0x77
header frame, a run of fn=0x78 chunk frames, one fn=0x79 footer frame.
Wire layout per mcp-midi-control's gen-3 SYSEX-MAP and presetDump.ts
(descriptor-table mined from the official editor, structurally validated
against 384 Axe-Fx III factory presets and an FM9 export, and wire-confirmed
on FM9 fw 11.00 in the read direction on 2026-06-04):

    header  13 B    fn 0x77  payload [preset#Hi, preset#Lo, 0x00, 0x40, 0x00]
    chunk   3082 B  fn 0x78  payload [2B discriminator][3072B body]
    footer  11 B    fn 0x79  payload [3B xor-fold of body words, septet-split]

Chunk bodies are 1024 little-endian 16-bit words packed three septets each
(b0 | b1<<7 | b2<<14). Word 1 of chunk 0 is the 0xAA55 magic; the ASCII
preset name lives at words 4..19, two chars per word, low byte first.
Frame checksum is the family-standard XOR (0xF0 through the last payload
byte, masked 0x7F).

INSTALLING is the Ghidra-decoded recipe from the official editor's own
store path: re-emit the file's frames verbatim, patch only the header's
preset-index field (and that one frame's checksum), leave the footer
untouched. The host->device direction is NOT yet hardware-verified
anywhere, upstream included, so an install is only ever reported done
after the slot's name is read back and matches this file's embedded name.

Rule zero: nothing here widens what the transport may send. The device
layer's install path takes only the frames this module has validated, and
its guard admits only the three dump functions. A file that does not parse
as a preset dump for the right model byte is refused with the reason,
never sent to see what happens.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import protocol as p

HEADER_LEN, CHUNK_LEN, FOOTER_LEN = 13, 3082, 11
FN_HEAD, FN_CHUNK, FN_FOOT = 0x77, 0x78, 0x79
PRESET_DUMP_FNS = frozenset({FN_HEAD, FN_CHUNK, FN_FOOT})

#: Chunk payload: 2 discriminator bytes, then the packed words.
CHUNK_BODY_OFFSET = 2
NAME_MAGIC, NAME_MAGIC_WORD = 0xAA55, 1
NAME_FIRST_WORD, NAME_MAX_WORDS = 4, 16

#: Gen-3 model bytes, for a refusal that names the actual device instead
#: of saying "wrong byte".
MODEL_NAMES = {0x10: "Axe-Fx III", 0x11: "FM3", 0x12: "FM9", 0x14: "VP4"}


class PresetFileError(ValueError):
    """The file is not a valid preset dump for this device. The message is
    written for the person who dragged the file in, not for a log."""


@dataclass
class PresetFile:
    frames: list[list[int]]      # full F0..F7 byte lists, header first
    model: int
    source_slot: int             # the preset number baked into the header
    name: str

    @property
    def chunks(self) -> int:
        return len(self.frames) - 2


def _split_frames(raw: bytes) -> list[list[int]]:
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
        raise PresetFileError("the file ends mid-message; it looks truncated")
    return frames


def _word(chunk_payload: list[int], index: int) -> int:
    off = CHUNK_BODY_OFFSET + index * 3
    b = chunk_payload[off:off + 3]
    if len(b) < 3:
        return 0
    return (b[0] | (b[1] << 7) | (b[2] << 14)) & 0xFFFF


def parse(raw: bytes, model: int = p.MODEL_FM9) -> PresetFile:
    """Validate `raw` as a preset file for `model`, or raise PresetFileError.

    Every frame is length-checked, header-checked and checksum-checked
    before anything is trusted; the sequence must be exactly one header, at
    least one chunk, one footer, in order; and the name magic must be
    present. Everything the install path will send has passed through here.
    """
    frames = _split_frames(raw)
    if not frames:
        raise PresetFileError("no MIDI messages in the file at all")
    seen_models = set()
    for i, f in enumerate(frames):
        if len(f) < 9 or f[1:4] != list(p.MFR):
            raise PresetFileError(
                f"message {i + 1} is not a Fractal message; this does not "
                "look like a Fractal preset file")
        if p.checksum(f[1:-2]) != f[-2]:
            raise PresetFileError(
                f"message {i + 1} fails its checksum; the file is corrupt")
        seen_models.add(f[4])
    if seen_models != {model}:
        got = ", ".join(sorted(MODEL_NAMES.get(m, f"model 0x{m:02X}")
                               for m in seen_models))
        raise PresetFileError(
            f"this is a preset file for the {got}, not the "
            f"{MODEL_NAMES.get(model, 'target device')}; preset files are "
            "device-specific and cannot be converted here")
    fns = [f[5] for f in frames]
    if fns[0] != FN_HEAD or fns[-1] != FN_FOOT or len(frames) < 3 \
            or any(fn != FN_CHUNK for fn in fns[1:-1]):
        raise PresetFileError(
            "not a preset dump: expected one header, a run of chunks and a "
            f"footer, found functions {['0x%02X' % f for f in fns]}")
    if len(frames[0]) != HEADER_LEN or len(frames[-1]) != FOOTER_LEN \
            or any(len(f) != CHUNK_LEN for f in frames[1:-1]):
        raise PresetFileError(
            "a frame has the wrong length for a preset dump; the file may "
            "be damaged or from an unsupported firmware")
    chunk0 = frames[1][6:-2]
    if _word(chunk0, NAME_MAGIC_WORD) != NAME_MAGIC:
        raise PresetFileError(
            "the preset body is missing its magic word; refusing to send a "
            "blob this tool cannot recognise")
    name_chars = []
    for i in range(NAME_MAX_WORDS):
        w = _word(chunk0, NAME_FIRST_WORD + i)
        lo, hi = w & 0xFF, (w >> 8) & 0xFF
        if lo == 0:
            break
        name_chars.append(chr(lo))
        if hi == 0:
            break
        name_chars.append(chr(hi))
    source_slot = ((frames[0][6] & 0x7F) << 7) | (frames[0][7] & 0x7F)
    return PresetFile(frames=frames, model=model,
                      source_slot=source_slot,
                      name="".join(name_chars).rstrip())


def _set_word(payload: list[int], index: int, value: int) -> None:
    off = CHUNK_BODY_OFFSET + index * 3
    payload[off] = value & 0x7F
    payload[off + 1] = (value >> 7) & 0x7F
    payload[off + 2] = (value >> 14) & 0x03


def _body_words(pf: PresetFile) -> list[int]:
    """Every de-framed 16-bit word across the chunk bodies, in order.

    The footer is a XOR-fold of exactly these (upstream: a separate layer
    from the inner raw-patch CRC), so recomputing it after a name edit
    means folding this list.
    """
    words = []
    for f in pf.frames[1:-1]:
        payload = f[6:-2]
        n = (len(payload) - CHUNK_BODY_OFFSET) // 3
        for i in range(n):
            words.append(_word(payload, i))
    return words


def set_name(pf: PresetFile, name: str) -> PresetFile:
    """Return a copy with the embedded preset name replaced.

    The name lives in plaintext at chunk-0 words 4..19 (two chars per word,
    NUL-terminated); the footer is refolded over the whole body afterward,
    because a real device checks the 0x79 XOR on receive and rejects a
    mismatch. The name region is patched, the footer recomputed, both
    frames re-checksummed. Verified by parse round-trip; the footer's
    acceptance on hardware is unproven like the rest of the write path.
    """
    clean = "".join(c for c in name if 32 <= ord(c) < 127)[:32]
    frames = [list(f) for f in pf.frames]
    chunk0 = frames[1][6:-2]
    for i in range(NAME_MAX_WORDS):
        lo = ord(clean[2 * i]) if 2 * i < len(clean) else 0
        hi = ord(clean[2 * i + 1]) if 2 * i + 1 < len(clean) else 0
        _set_word(chunk0, NAME_FIRST_WORD + i, lo | (hi << 8))
    frames[1] = [*frames[1][:6], *chunk0, 0, 0xF7]
    frames[1][-2] = p.checksum(frames[1][1:-2])
    patched = PresetFile(frames=frames, model=pf.model,
                         source_slot=pf.source_slot, name=clean.rstrip())
    fold = 0
    for w in _body_words(patched):
        fold ^= w
    foot = frames[-1]
    foot[6] = fold & 0x7F
    foot[7] = (fold >> 7) & 0x7F
    foot[8] = (fold >> 14) & 0x03
    foot[-2] = p.checksum(foot[1:-2])
    return patched


def retarget(pf: PresetFile, slot: int) -> list[list[int]]:
    """The file's frames, aimed at `slot`: the official editor's own store
    recipe, header index patched, checksum recomputed, footer untouched."""
    if not 0 <= slot <= 0x3FFF:
        raise PresetFileError(f"slot {slot} is out of range")
    head = list(pf.frames[0])
    head[6] = (slot >> 7) & 0x7F
    head[7] = slot & 0x7F
    head[-2] = p.checksum(head[1:-2])
    return [head, *[list(f) for f in pf.frames[1:]]]

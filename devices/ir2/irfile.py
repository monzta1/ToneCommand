"""Turning a cabinet IR into what the BOSS IR-2 stores.

THE FORMAT, decoded on hardware 2026-09-29 and proven by writing it
(kb/IR2_PROTOCOL.md). Each IRDATA slot holds four regions, and the one
that matters here is DATA: big-endian float32 samples, eight nibbles each.
The first 1632 words are what the DSP convolves. Everything after them is
a pair of quantised tables that the pedal does NOT recompute when the
samples change, and does not need to: a cab written with another cab's
tables played correctly, and silence written into the samples played as no
cab at all. So this writes the samples and leaves the tables alone.

THE PEDAL CACHES. Writes land in flash and are invisible until the unit
reloads, which it does at power-on. Every test before that looks like
nothing happened, which is a trap worth naming loudly rather than
discovering twice; `install` says so in its result and the caller is
expected to pass it on.

SAMPLE RATE. 44,100, which is what the device itself reports as its
default. That is evidence rather than documentation, and it is the best
available: BOSS publishes no specification for this. If it is ever shown
to be wrong, the IRs written before the correction are slightly
transposed rather than broken, and rewriting them fixes it.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path

#: Samples the DSP convolves. Measured: the oscillating region of every
#: factory IR ends at 1631, and a sign change never occurs after it.
SAMPLES = 1632

#: What the device reports for itself. See the module docstring.
RATE = 44100

#: The pedal stores normalised IRs: every factory cab peaks at exactly 1.0
#: in the sample region. Writing a hotter one would clip inside the DSP.
PEAK = 1.0


class IRFileError(ValueError):
    """One line, written for the person at the rig."""


def read_wav(path: Path) -> tuple[list[float], int]:
    """Mono float samples and the file's rate, from a PCM wav.

    stdlib `wave` only, because adding a dependency to read the one format
    every IR vendor ships would be silly. A float wav (format 3) is not
    handled and says so rather than returning noise.
    """
    with wave.open(str(path), "rb") as w:
        channels, width, rate, frames = (w.getnchannels(), w.getsampwidth(),
                                         w.getframerate(), w.getnframes())
        raw = w.readframes(frames)
    if width not in (2, 3, 4):
        raise IRFileError(f"{path.name} is {width * 8}-bit; this reads 16, "
                          "24 or 32-bit PCM wav")
    scale = float(1 << (width * 8 - 1))
    out = []
    step = width * channels
    for i in range(0, len(raw) - step + 1, step):
        b = raw[i:i + width]
        v = int.from_bytes(b, "little", signed=True)
        out.append(v / scale)
    if not out:
        raise IRFileError(f"{path.name} has no audio in it")
    return out, rate


def resample(samples: list[float], src_rate: int, dst_rate: int) -> list[float]:
    """Linear resampling.

    Honest about what it is: linear interpolation, not a windowed sinc. For
    a cabinet IR being truncated to 37 ms anyway, the error sits far below
    what the truncation itself does, and it keeps this file dependency-free.
    If that ever stops being true, this is the one function to replace.
    """
    if src_rate == dst_rate:
        return list(samples)
    ratio = dst_rate / src_rate
    n = int(len(samples) * ratio)
    out = []
    for i in range(n):
        x = i / ratio
        j = int(x)
        frac = x - j
        a = samples[j]
        b = samples[j + 1] if j + 1 < len(samples) else a
        out.append(a + (b - a) * frac)
    return out


def prepare(path: Path) -> list[float]:
    """A wav as the pedal's 1632 samples: mono, 44.1 kHz, peak-normalised.

    Truncation is the lossy step and it is deliberate, because the device
    has room for 37 ms and nothing else. A long tail is faded over the last
    64 samples rather than cut square, since a hard cut puts a step in the
    impulse and that is audible as a click on every note.
    """
    samples, rate = read_wav(Path(path))
    samples = resample(samples, rate, RATE)
    if len(samples) < SAMPLES:
        samples = samples + [0.0] * (SAMPLES - len(samples))
    else:
        samples = samples[:SAMPLES]
        fade = min(64, SAMPLES)
        for k in range(fade):
            samples[SAMPLES - fade + k] *= (fade - 1 - k) / (fade - 1)
    peak = max(abs(x) for x in samples)
    if peak == 0:
        raise IRFileError("that file is silent")
    return [x * (PEAK / peak) for x in samples]


def to_nibbles(samples: list[float]) -> list[int]:
    """The pedal's wire form: big-endian float32, eight nibbles each."""
    out = []
    for v in samples:
        w = struct.unpack(">I", struct.pack(">f", float(v)))[0]
        for k in range(8):
            out.append((w >> (28 - 4 * k)) & 0xF)
    return out


def from_nibbles(nib: list[int]) -> list[float]:
    """The inverse, for reading an IR back off the pedal."""
    out = []
    for i in range(0, len(nib) - 7, 8):
        w = 0
        for n in nib[i:i + 8]:
            w = (w << 4) | n
        out.append(struct.unpack(">f", w.to_bytes(4, "big"))[0])
    return out


def name_nibbles(text: str, length: int) -> list[int]:
    """ASCII, space-padded, as the pedal stores names and filenames.

    NAME is one byte per position; FILE is nibble pairs. Both are capped
    rather than raising, because a long filename is not a reason to refuse
    an install the player asked for.
    """
    data = text.encode("ascii", "replace")[:length].ljust(length, b" ")
    return [b & 0x7F for b in data]


def file_nibbles(text: str, length: int = 128) -> list[int]:
    data = text.encode("ascii", "replace")[:length // 2]
    out = []
    for b in data:
        out.append((b >> 4) & 0xF)
        out.append(b & 0xF)
    return out + [0] * (length - len(out))

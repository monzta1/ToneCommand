"""Render an audible preview of a cab IR, so cabs can be A/B'd without the rig.

Why this exists: nobody can judge a cab IR from its filename. This convolves a
deterministic synthetic DI with the IR and hands back a WAV the browser can
play, so a handful of candidates can be compared side by side in the review.

The signal chain deliberately matches tone_rules 3a:

    test DI  ->  saturation (the "amp")  ->  convolution (the cab IR)

Saturation happens BEFORE the cab because distortion is nonlinear and an IR
cannot contain it. Auditioning a high-gain cab with a clean source would
misrepresent it: the baked-in high-cut that tames fizz only makes sense once
there is fizz to tame.

Only WAV IRs can be previewed. Fractal .syx cab dumps are an encoded device
format whose IR body is not decoded anywhere in this codebase, so they are
refused here rather than guessed at; those are auditioned on the rig instead.

numpy is used for the FFT convolution. Everything else is stdlib.
"""
from __future__ import annotations

import io
import struct
import wave
from pathlib import Path

import numpy as np

SR = 48000
MAX_IR_SECONDS = 2.0        # past this it is not a cab IR (see IRCommand)
MAX_RENDER_SECONDS = 8.0

#: How a candidate was rendered, worst to best. Issue #59: the UI must say
#: which of these it is, because "heard in your rig" and "a generic amp stage
#: through this cab" are very different claims and only one of them is true
#: here. Anything that overstates its grade is how a tool starts lying.
FIDELITY = {
    "target_in_chain": "Heard in your rig",
    "captured_pre_cab": "Heard from your amp path",
    "representative_amp": "Representative preview",
    "metadata_only": "Not auditioned",
}

#: What this renderer can honestly claim. It uses a fixed synthetic DI and a
#: generic saturation stage, so it is representative: good for ranking
#: candidates against each other, not a prediction of the player's rig.
#: Raising this requires capturing the real pre-cab amp output, which is
#: gated on the hardware spike in issue #56.
RENDER_GRADE = "representative_amp"

#: The conditions that make a set of previews a fair COMPARISON rather than a
#: collection of unrelated auditions. Every one of these is true of this
#: renderer by construction, which is why it may claim them.
COMPARISON_CONTRACT = {
    "same_source": "the identical synthetic DI for every candidate",
    "same_drive": "the same saturation stage and setting",
    "same_level": "every render normalised to the same peak",
    "same_length": "the same region of the same phrase",
    "deterministic": "the DI is seeded, so repeat renders are identical",
}


def integrity(drive: str, seconds: float) -> dict:
    """What may honestly be claimed about a set of renders at these settings.

    A comparison is only a comparison when one variable moves. Everything here
    holds the source, the drive and the level fixed, so the cab is the only
    difference. If a caller ever varies drive or length between candidates,
    this is where that stops being true and the label has to change.
    """
    return {
        "grade": RENDER_GRADE,
        "label": FIDELITY[RENDER_GRADE],
        "is_comparison": True,
        "holds": dict(COMPARISON_CONTRACT),
        "drive": drive,
        "seconds": seconds,
        "caveat": "Not your amp path: a generic saturation stage stands in for "
                  "the amp, so this ranks cabs rather than predicting your rig.",
    }

# Saturation presets. The number is pre-gain into a tanh; higher = more
# compressed and more harmonics, i.e. further up the amp's gain structure.
DRIVES = {"clean": 1.2, "crunch": 8.0, "lead": 30.0, "high-gain": 60.0}


# --- WAV reading -------------------------------------------------------

def _read_wav(path: Path):
    """(samples float32 mono, sample_rate). Handles PCM 16/24/32 and float32,
    which the stdlib wave module cannot do on its own."""
    raw = Path(path).read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            afmt, nch, sr, _br, _ba, bits = struct.unpack("<HHIIHH", body[:16])
            fmt = (afmt, nch, sr, bits)
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if not fmt or data is None:
        raise ValueError("WAV is missing its fmt or data chunk")
    afmt, nch, sr, bits = fmt
    if afmt == 3 and bits == 32:
        x = np.frombuffer(data, dtype="<f4").astype(np.float32)
    elif afmt == 1 and bits == 16:
        x = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    elif afmt == 1 and bits == 32:
        x = np.frombuffer(data, dtype="<i4").astype(np.float32) / 2147483648.0
    elif afmt == 1 and bits == 24:
        b = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = (b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float32) / 8388608.0
    else:
        raise ValueError(f"unsupported WAV encoding (format {afmt}, {bits} bit)")
    if nch > 1:                      # sum to mono; an IR pair is near-identical
        n = (len(x) // nch) * nch
        x = x[:n].reshape(-1, nch).mean(axis=1)
    return x.astype(np.float32), sr


def _resample(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Linear resample. Ample for a preview; this is not a mastering path."""
    if src_sr == dst_sr or len(x) == 0:
        return x
    n = int(round(len(x) * dst_sr / src_sr))
    return np.interp(np.linspace(0, len(x) - 1, n),
                     np.arange(len(x)), x).astype(np.float32)


# --- the test DI -------------------------------------------------------

def test_di(seconds: float = 3.0, sr: int = SR) -> np.ndarray:
    """A deterministic synthetic DI: three plucked notes with a full harmonic
    stack and a pick transient.

    Deliberately harmonically rich, because a cab IR is a filter: the preview
    can only reveal what the source actually excites. A pure sine would tell
    you nothing about a 4x12's upper-mid bite.
    """
    rng = np.random.default_rng(0)          # deterministic: same DI every time
    n = int(seconds * sr)
    out = np.zeros(n, dtype=np.float32)
    notes = [82.41, 110.0, 164.81]          # E2, A2, E3
    step = n // len(notes)
    for i, f0 in enumerate(notes):
        start = i * step
        length = min(int(sr * 1.4), n - start)
        if length <= 0:
            break
        t = np.arange(length) / sr
        note = np.zeros(length, dtype=np.float32)
        for h in range(1, 25):              # harmonics up to ~4 kHz for E2
            if f0 * h > sr / 2:
                break
            note += (np.sin(2 * np.pi * f0 * h * t) / h).astype(np.float32)
        note *= np.exp(-t * 3.0).astype(np.float32)
        pick = rng.standard_normal(min(int(sr * 0.006), length)).astype(np.float32)
        note[:len(pick)] += pick * 0.5 * np.exp(
            -np.arange(len(pick)) / (sr * 0.001))
        out[start:start + length] += note
    peak = float(np.max(np.abs(out))) or 1.0
    return (out / peak * 0.7).astype(np.float32)


def saturate(x: np.ndarray, drive: str = "crunch") -> np.ndarray:
    """The 'amp'. Nonlinear, and upstream of the cab, per tone_rules 3a."""
    g = DRIVES.get(drive, DRIVES["crunch"])
    y = np.tanh(x * g).astype(np.float32)
    peak = float(np.max(np.abs(y))) or 1.0
    return (y / peak).astype(np.float32)


# --- render ------------------------------------------------------------

def load_ir(path: str | Path, sr: int = SR) -> np.ndarray:
    p = Path(path)
    if p.suffix.lower() == ".syx":
        raise ValueError(
            "that is a Fractal .syx cab dump, an encoded device format whose "
            "IR body this codebase does not decode. Audition it on the rig.")
    ir, ir_sr = _read_wav(p)
    if len(ir) / ir_sr > MAX_IR_SECONDS:
        raise ValueError(
            f"that file is {len(ir)/ir_sr:.1f}s long, which is not an impulse "
            "response (a cab IR is well under a second)")
    ir = _resample(ir, ir_sr, sr)
    peak = float(np.max(np.abs(ir))) or 1.0
    return (ir / peak).astype(np.float32)


def render(ir_path: str | Path, drive: str = "crunch",
           seconds: float = 3.0, sr: int = SR) -> bytes:
    """DI -> saturation -> cab IR, returned as 16-bit PCM WAV bytes."""
    seconds = max(0.5, min(float(seconds), MAX_RENDER_SECONDS))
    ir = load_ir(ir_path, sr)
    di = saturate(test_di(seconds, sr), drive)
    wet = np.convolve(di, ir)[:len(di)]     # numpy picks an FFT path when it pays
    peak = float(np.max(np.abs(wet))) or 1.0
    wet = (wet / peak * 0.89).astype(np.float32)
    pcm = (wet * 32767.0).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()

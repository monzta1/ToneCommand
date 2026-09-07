"""IR audition: rendering, the .syx refusal, and the path security boundary."""
from __future__ import annotations

import io
import struct
import wave

import pytest

# numpy is an OPTIONAL extra (the audition preview). Skip rather than
# error where it is absent, so a core install still reports a clean suite.
np = pytest.importorskip("numpy")
from fastapi.testclient import TestClient

import server
from fm9 import ir_audition, ir_service


def write_wav(path, samples, sr=48000, bits=16):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(bits // 8)
        w.setframerate(sr)
        w.writeframes((np.asarray(samples) * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "IR-Library"
    (root / "IRs").mkdir(parents=True)
    monkeypatch.setenv("TONECOMMAND_IR_LIBRARY", str(root))
    return root


# --- the DI and the renderer ------------------------------------------

def test_test_di_is_deterministic_and_broadband():
    a, b = ir_audition.test_di(), ir_audition.test_di()
    assert np.array_equal(a, b), "the DI must be identical every render"
    S = np.abs(np.fft.rfft(a))
    f = np.fft.rfftfreq(len(a), 1 / ir_audition.SR)
    # a cab IR is a filter; the source has to excite the range it shapes
    assert S[(f > 1000) & (f < 4000)].mean() > 0, "DI has no upper-mid content"


def test_saturation_adds_harmonics():
    t = np.arange(int(0.2 * ir_audition.SR)) / ir_audition.SR
    sine = np.sin(2 * np.pi * 220 * t).astype(np.float32)

    def harmonic_energy(x):
        S = np.abs(np.fft.rfft(x))
        f = np.fft.rfftfreq(len(x), 1 / ir_audition.SR)
        return S[(f > 400)].sum() / S.sum()

    assert harmonic_energy(ir_audition.saturate(sine, "high-gain")) > \
        harmonic_energy(ir_audition.saturate(sine, "clean")), \
        "more drive must produce more harmonic content"


def test_render_returns_playable_wav(library):
    ir = write_wav(library / "IRs" / "cab.wav", np.random.default_rng(1)
                   .standard_normal(2048) * 0.2)
    out = ir_audition.render(ir, drive="lead", seconds=1.0)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        assert w.getnframes() > 0


def test_different_irs_give_different_tone(library):
    """A dark IR must render darker than a bright one, or the convolution is
    not actually doing anything."""
    n = 2048
    bright = np.zeros(n); bright[0] = 1.0; bright[1] = -0.9   # high-pass-ish
    dark = np.exp(-np.arange(n) / 40.0)                        # low-pass-ish
    pb = write_wav(library / "IRs" / "bright.wav", bright)
    pd = write_wav(library / "IRs" / "dark.wav", dark)

    def centroid(b):
        with wave.open(io.BytesIO(b)) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
        S = np.abs(np.fft.rfft(x))
        f = np.fft.rfftfreq(len(x), 1 / ir_audition.SR)
        return (S * f).sum() / S.sum()

    assert centroid(ir_audition.render(pb)) > centroid(ir_audition.render(pd))


def test_syx_is_refused(library):
    syx = library / "IRs" / "cab.syx"
    syx.write_bytes(b"\xf0\x00\x01t\x10\x7a\xf7")
    with pytest.raises(ValueError, match="syx"):
        ir_audition.load_ir(syx)


def test_long_file_is_refused(library):
    """Parity with IRCommand's guard: a 3s file is not an impulse response."""
    long = write_wav(library / "IRs" / "long.wav",
                     np.zeros(3 * ir_audition.SR) + 0.1)
    with pytest.raises(ValueError, match="not an impulse response"):
        ir_audition.load_ir(long)


def test_reads_24_bit_and_float_wav(library):
    """IR packs ship 24-bit and float32; the stdlib wave module reads neither."""
    n = 512
    x = (np.sin(np.arange(n) / 5) * 0.5).astype(np.float32)
    for bits, fmt, data in (
            (24, 1, b"".join(int(v * 8388607).to_bytes(3, "little", signed=True)
                             for v in x)),
            (32, 3, x.tobytes())):
        p = library / "IRs" / f"w{bits}_{fmt}.wav"
        block = 1 * bits // 8
        hdr = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
               + b"fmt " + struct.pack("<IHHIIHH", 16, fmt, 1, 48000,
                                       48000 * block, block, bits)
               + b"data" + struct.pack("<I", len(data)) + data)
        p.write_bytes(hdr)
        got, sr = ir_audition._read_wav(p)
        assert sr == 48000 and len(got) == n


# --- the security boundary --------------------------------------------

def test_path_outside_library_is_rejected(library, tmp_path):
    outside = write_wav(tmp_path / "secret.wav", np.zeros(64))
    assert ir_service.safe_ir_path(str(outside)) is None
    assert ir_service.safe_ir_path("/etc/passwd") is None
    assert ir_service.safe_ir_path("") is None


def test_traversal_out_of_library_is_rejected(library, tmp_path):
    write_wav(tmp_path / "secret.wav", np.zeros(64))
    assert ir_service.safe_ir_path(
        str(library / "IRs" / ".." / ".." / "secret.wav")) is None


def test_path_inside_library_is_accepted(library):
    good = write_wav(library / "IRs" / "ok.wav", np.zeros(64))
    assert ir_service.safe_ir_path(str(good)) == good.resolve()


def test_audition_endpoint_rejects_outside_path(library, tmp_path):
    outside = write_wav(tmp_path / "nope.wav", np.zeros(64))
    c = TestClient(server.app)
    r = c.get("/api/ir/audition", params={"path": str(outside)})
    assert r.status_code == 400 and "outside the IR library" in r.json()["error"]


def test_ir_context_is_empty_when_service_off(monkeypatch):
    """With IRCommand off the planner must see nothing extra at all."""
    monkeypatch.setattr(ir_service, "enabled", lambda: False)
    assert server.ir_context("soldano lead") == ""


def test_ir_context_lists_the_library_hits(monkeypatch):
    monkeypatch.setattr(ir_service, "enabled", lambda: True)
    monkeypatch.setattr(ir_service, "recommend", lambda *a, **k: [
        {"name": "Soldano SLO30.wav", "pack": "t3k", "why": ["Soldano"]}])
    got = server.ir_context("soldano lead")
    assert "Soldano SLO30.wav" in got and "t3k" in got and "set_cab" in got


def test_ir_context_survives_a_broken_service(monkeypatch):
    """A failing IR lookup must never take a build down."""
    monkeypatch.setattr(ir_service, "enabled", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("service exploded")

    monkeypatch.setattr(ir_service, "recommend", boom)
    assert server.ir_context("anything") == ""


def test_audition_endpoint_serves_wav(library):
    ir = write_wav(library / "IRs" / "cab.wav",
                   np.random.default_rng(2).standard_normal(1024) * 0.2)
    c = TestClient(server.app)
    r = c.get("/api/ir/audition", params={"path": str(ir), "seconds": 1.0})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getnframes() > 0


# --- #59 fidelity grades, #57 audition integrity ------------------------

def test_the_renderer_does_not_overstate_its_grade():
    """It uses a synthetic DI and a generic saturation stage, so the strongest
    honest claim is 'representative', never 'heard in your rig'."""
    assert ir_audition.RENDER_GRADE == "representative_amp"
    assert ir_audition.integrity("lead", 3.0)["label"] == "Representative preview"


def test_every_grade_has_player_facing_copy():
    for grade, copy in ir_audition.FIDELITY.items():
        assert copy and copy[0].isupper(), grade


def test_integrity_states_what_is_held_constant():
    got = ir_audition.integrity("crunch", 3.0)
    assert got["is_comparison"] is True
    for key in ("same_source", "same_drive", "same_level", "same_length"):
        assert key in got["holds"], key
    assert "not your amp path" in got["caveat"].lower()


def test_the_grade_travels_with_the_audio(library):
    ir = write_wav(library / "IRs" / "cab.wav",
                   np.random.default_rng(3).standard_normal(1024) * 0.2)
    r = TestClient(server.app).get("/api/ir/audition",
                                   params={"path": str(ir), "seconds": 1.0})
    assert r.headers["X-Audition-Grade"] == "representative_amp"
    assert r.headers["X-Audition-Label"] == "Representative preview"


def test_the_integrity_endpoint_answers_without_rendering():
    d = TestClient(server.app).get("/api/ir/audition/integrity").json()
    assert d["grade"] == "representative_amp" and d["is_comparison"] is True


def test_the_same_di_is_used_for_every_candidate(library):
    """The core of #57: if the source moved between candidates, the comparison
    would be measuring the source, not the cab."""
    a = ir_audition.test_di(3.0)
    b = ir_audition.test_di(3.0)
    assert np.array_equal(a, b)

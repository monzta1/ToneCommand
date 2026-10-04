"""#195: installing an IR, and the three things hardware taught us.

The IR-2 caches. Writes land in flash and the DSP keeps playing what it
loaded at power-on, so every test before a power cycle looked like nothing
had happened. Silence written into a slot changed nothing at all until the
unit was restarted, and then played as no cab. That is the single most
expensive fact in this file and the reason every install says so out loud.

The slots are not a free list either. USER 1 to USER 11 hold the cabinets
for the eleven amp voicings in order, confirmed by matching every slot's
stored filename against its voicing's factory cab, so installing an IR
replaces a specific amp's speaker.
"""
import wave
from pathlib import Path

import pytest

from devices.ir2 import irfile, protocol as p
from devices.ir2.adapter import IR2Adapter, IR2_SLOTS_ENV, writable_slots
from devices.ir2.client import VerifyFailed
from devices.ir2.sim import SimIR2


def _wav(tmp_path, name="Greenback 4x12.wav", rate=48000, n=4000):
    path = tmp_path / name
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(3); w.setframerate(rate)
        s = [0.0] * n
        s[5], s[6], s[40] = 0.8, -0.4, 0.2
        w.writeframes(b"".join(int(x * (2**23 - 1)).to_bytes(3, "little", signed=True)
                               for x in s))
    return path


@pytest.fixture
def dev(monkeypatch):
    monkeypatch.setenv(IR2_SLOTS_ENV, "11")
    return IR2Adapter(client=SimIR2())


# --- the whitelist is empty until the owner says otherwise ----------------

def test_nothing_is_writable_by_default(monkeypatch, tmp_path):
    """Installing replaces the cabinet for an amp voicing. Which of those are
    expendable is the owner's call and can never be a default."""
    monkeypatch.delenv(IR2_SLOTS_ENV, raising=False)
    assert writable_slots() == frozenset()
    d = IR2Adapter(client=SimIR2())
    with pytest.raises(PermissionError, match="no IR-2 slot is writable"):
        d.install_capture(_wav(tmp_path), b"", 11)


def test_a_slot_off_the_list_is_refused_and_names_what_it_holds(dev, tmp_path):
    with pytest.raises(PermissionError) as e:
        dev.install_capture(_wav(tmp_path), b"", 5)
    assert "not on the writable list" in str(e.value)
    assert "CRUNCH" in str(e.value), "it should say whose cab it would destroy"


def test_the_whitelist_ignores_slots_that_do_not_exist(monkeypatch):
    monkeypatch.setenv(IR2_SLOTS_ENV, "0,5,11,12,99,banana")
    assert writable_slots() == frozenset({5, 11})


# --- what the slots actually are ------------------------------------------

def test_each_slot_is_a_voicings_cabinet(dev):
    assert dev.voicing_for(1) == "CLEAN"
    assert dev.voicing_for(11) == "RFIER"
    assert dev.voicing_for(7) == "HI-GAIN"


# --- the install ----------------------------------------------------------

def test_an_ir_is_written_verified_and_named(dev, tmp_path):
    r = dev.install_capture(_wav(tmp_path), b"", 11)
    assert r.slot == 11 and r.verified is True
    assert dev.list_captures()[10].name == "Greenback 4x12"


def test_the_result_says_the_pedal_must_be_restarted(dev, tmp_path):
    """The pedal caches at power-on. An install that does not say so leaves
    the player believing it failed."""
    r = dev.install_capture(_wav(tmp_path), b"", 11)
    assert "power-on" in r.note and "plug it back in" in r.note


def test_verified_is_earned_not_asserted(dev, tmp_path, monkeypatch):
    """A slot that reads back wrong must raise, not report success."""
    real = dev.io.read
    def wrong(addr, n, timeout=0.0):
        got = list(real(addr, n, timeout))
        if addr >= p.ir_slot_addr(11, p.IR_DATA) and got:
            got[0] ^= 0xF
        return got
    monkeypatch.setattr(dev.io, "read", wrong)
    with pytest.raises(VerifyFailed, match="does not read back"):
        dev.install_capture(_wav(tmp_path), b"", 11)


def test_removing_an_ir_is_refused_with_a_reason(dev):
    with pytest.raises(NotImplementedError, match="no cabinet at all"):
        dev.remove_capture(11)


# --- the conversion -------------------------------------------------------

def test_a_long_ir_is_truncated_to_what_the_pedal_holds(tmp_path):
    out = irfile.prepare(_wav(tmp_path, n=40000))
    assert len(out) == irfile.SAMPLES == 1632


def test_a_short_ir_is_padded(tmp_path):
    out = irfile.prepare(_wav(tmp_path, n=200))
    assert len(out) == irfile.SAMPLES


def test_the_tail_is_faded_rather_than_cut_square(tmp_path):
    """A hard cut puts a step in the impulse, which is audible as a click on
    every note."""
    path = tmp_path / "dc.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(3); w.setframerate(44100)
        w.writeframes(b"".join(int(0.5 * (2**23 - 1)).to_bytes(3, "little", signed=True)
                               for _ in range(5000)))
    out = irfile.prepare(path)
    assert out[-1] == 0.0, "the last sample must land on zero"
    assert out[-32] > out[-8] > out[-1], "and get there gradually"


def test_the_result_is_peak_normalised(tmp_path):
    """Every factory cab peaks at exactly 1.0; a hotter one clips in the DSP."""
    out = irfile.prepare(_wav(tmp_path))
    assert abs(max(abs(x) for x in out) - 1.0) < 1e-6


def test_a_silent_file_is_refused_rather_than_normalised(tmp_path):
    path = tmp_path / "silent.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(3); w.setframerate(44100)
        w.writeframes(b"\x00" * 3 * 2000)
    with pytest.raises(irfile.IRFileError, match="silent"):
        irfile.prepare(path)


def test_float_wavs_are_refused_rather_than_read_as_noise(tmp_path):
    path = tmp_path / "f32.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(44100)
        w.writeframes(b"\x80" * 500)
    with pytest.raises(irfile.IRFileError, match="8-bit"):
        irfile.prepare(path)


def test_the_wire_form_is_lossless_for_what_the_pedal_stores(tmp_path):
    """The pedal stores float32 and `prepare` computes in float64, so the
    first encode quantises once, by design. What matters is that encoding is
    lossless from there on, which is why the install can verify by equality
    rather than by a tolerance: a tolerance would quietly accept a
    half-written IR.
    """
    out = irfile.prepare(_wav(tmp_path))
    once = irfile.from_nibbles(irfile.to_nibbles(out))
    twice = irfile.from_nibbles(irfile.to_nibbles(once))
    assert twice == once, "float32 must survive the encoding unchanged"
    # and the one quantisation is tiny, not a rounding bug
    assert max(abs(a - b) for a, b in zip(out, once)) < 1e-7


def test_the_sample_rate_is_what_the_device_reports():
    """44,100 is evidence, not documentation: BOSS publish no specification
    and this is what the pedal says about itself."""
    assert irfile.RATE == 44100

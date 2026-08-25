"""ToneX frame decoding, against synthetic frames.

The real captures are preset content and stay local (kb/ is gitignored), so
these build frames to the documented grammar instead. That also makes the
grammar itself the thing under test.
"""
import importlib.util
import struct
import sys
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parent.parent / "tools" / "tonex_decode.py"
_spec = importlib.util.spec_from_file_location("tonex_decode", _path)
tonex = importlib.util.module_from_spec(_spec)
# Register before exec: @dataclass resolves annotations via sys.modules, and
# the module uses `from __future__ import annotations`.
sys.modules["tonex_decode"] = tonex
_spec.loader.exec_module(tonex)


def s(text: str, width: int | None = None) -> bytes:
    width = width if width is not None else len(text)
    body = text.encode("ascii").ljust(width, b"\x00")
    return bytes([tonex.TAG_STR, width]) + body


def f(value: float) -> bytes:
    return bytes([tonex.TAG_F32]) + struct.pack("<f", value)


def frame(name="Test Preset", category="DRIVE", floats=(1.0, 5.0, 0.0)):
    out = bytes([tonex.FRAME_LEAD, 0xB9, 0x03])
    out += s(name, 33) + s("") + s("2026-04-20") + s(category)
    out += b"".join(s("None") for _ in range(4))
    out += bytes([0xBA, 0x02]) + b"".join(f(v) for v in floats)
    return out


def test_the_name_is_read_from_slot_zero():
    assert tonex.decode(frame(name="MES LS I Clean BAL CAB")).name == "MES LS I Clean BAL CAB"


def test_zero_padding_is_stripped():
    """Names are padded to the declared width; the padding is not the name."""
    d = tonex.decode(frame(name="Heavy Load"))
    assert d.name == "Heavy Load"
    assert "\x00" not in d.name


@pytest.mark.parametrize("category", ["CLEAN", "DRIVE", "HI-GAIN"])
def test_the_category_is_read_from_slot_three(category):
    assert tonex.decode(frame(category=category)).category == category


def test_floats_are_little_endian_ieee754():
    """Spot values verified against real captures: 1.0, 5.0, 300.0, 0.7."""
    d = tonex.decode(frame(floats=(1.0, 5.0, 300.0, 0.7)))
    assert d.floats == pytest.approx([1.0, 5.0, 300.0, 0.7])


def test_undecoded_bytes_are_counted_not_guessed():
    d = tonex.decode(frame())
    assert d.structural > 0


def test_identical_control_state_reports_no_diff():
    """Real behaviour: programs 2 and 5 are different amps with identical
    floats, because the tone lives in the capture."""
    a = tonex.decode(frame(name="5150 Aggression", floats=(1.0, 5.0)))
    b = tonex.decode(frame(name="MES LS I Lead", floats=(1.0, 5.0)))
    assert a.name != b.name
    assert tonex.diff(a, b) == []


def test_a_changed_slot_is_located():
    a = tonex.decode(frame(floats=(1.0, 5.0, 0.0)))
    b = tonex.decode(frame(floats=(1.0, 7.5, 0.0)))
    assert tonex.diff(a, b) == [(1, pytest.approx(5.0), pytest.approx(7.5))]

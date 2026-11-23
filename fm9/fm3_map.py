"""The FM3's own settings map (#40): where each measured setting lives.

The FM3 answers the FM9's block read and knob write, but it numbers a
block's settings its own way: the amp's Gain is the FM9's parameter 11 and
the FM3's 7, the reverb's Mix the FM9's 0 and the FM3's 13. Every entry here
was measured on a real FM3 (fw 13.00, a tester's unit, 2026-11-22) by
turning one knob on the unit and finding the one value that moved
(tools/fm3_knob_map.py), with the screen's reading to fix the scale. The
first write (tools/fm3_param_write.py) then proved the FM3 takes a knob write
addressed by these numbers: reverb Mix to 30% and back, read back each way,
and seen moving in FM3-Edit.

Only instance 1 of each block was measured, on one amp model (USA JP IIC+
Green). Nothing outside this table is read or written on an FM3.

Keys are the FM9 registry's (family, parameter id), so the rest of
ToneCommand keeps one vocabulary; values say where the FM3 keeps that
setting and on what scale. Pure data: protocol.fm3_allowed imports it, so it
must not import anything from fm9.
"""
from __future__ import annotations

from typing import NamedTuple


class Fm3Param(NamedTuple):
    word: int            # the FM3's parameter id = its place in the block read
    label: str
    dmin: float
    dmax: float
    scale: str = "linear"   # or "log10"


#: The blocks measured, by the FM9 registry's effect id for instance 1. The
#: FM3 answered these ids in every read and write (58 amp, 66 reverb, 70 delay).
EFFECT_IDS = {"DISTORT": 58, "REVERB": 66, "DELAY": 70}

PARAMS: dict[tuple[str, int], Fm3Param] = {
    # Amp. Words 0-3 match the FM9; from the amp model on, the FM3 is four
    # places earlier (FM9 10 = FM3 6). Knobs are the FM9's 0-10 scale.
    ("DISTORT", 1): Fm3Param(1, "Level", -80, 20),            # 52427 = 0.0 dB, 45874 = -10.0
    ("DISTORT", 2): Fm3Param(2, "Balance", -100, 100),        # 32767 = 0, 0 = -100
    ("DISTORT", 11): Fm3Param(7, "Gain", 0, 10),              # 55507 = 8.47
    ("DISTORT", 12): Fm3Param(8, "Bass", 0, 10),              # 48888 = 7.46
    ("DISTORT", 13): Fm3Param(9, "Mid", 0, 10),               # 42532 = 6.49
    ("DISTORT", 14): Fm3Param(10, "Treble", 0, 10),           # 62388 = 9.52
    ("DISTORT", 15): Fm3Param(11, "Master", 0, 10),           # 65534 = 10.00
    ("DISTORT", 30): Fm3Param(26, "Presence", 0, 10),         # 62323 = 9.51
    # Reverb. The sound settings are ten places earlier than on the FM9
    # (type 0, Time 1); Mix, Level and Balance sit after them, at 13-15.
    ("REVERB", 0): Fm3Param(13, "Mix", 0, 100),               # 35782 = 54.6%; the write test
    ("REVERB", 1): Fm3Param(14, "Level", -80, 20),            # 33881 = -28.3 dB
    ("REVERB", 2): Fm3Param(15, "Balance", -100, 100),        # 65534 = 100
    ("REVERB", 11): Fm3Param(1, "Time", 0.1, 100),            # 22921 = 35.04 s, 656 = 1.10
    ("REVERB", 12): Fm3Param(2, "High Cut", 200, 20000, "log10"),  # 45860 = 5018.9, 22948 = 1003.1
    ("REVERB", 19): Fm3Param(9, "Predelay", 0, 1000),         # 29654 = 452.5 ms, 65534 = 1000
    # Delay. Mix, Level and Balance at 0-2 as on the FM9; from the type on,
    # four places earlier (FM9 12 Time = FM3 8).
    ("DELAY", 0): Fm3Param(0, "Mix", 0, 100),                 # 29687 = 45.3%
    ("DELAY", 1): Fm3Param(1, "Level", -80, 20),              # 25689 = -40.8 dB
    ("DELAY", 2): Fm3Param(2, "Balance", -100, 100),          # 54328 = 65.8
    ("DELAY", 12): Fm3Param(8, "Time", 0, 16000),             # 33445 = 8166 ms, 65534 = 16000
    ("DELAY", 14): Fm3Param(10, "Feedback", -100, 100),       # 58784 = 79.4%, 39320 = 20.0
}

#: effect id -> the FM3 words that may be written there. protocol.fm3_allowed
#: lets a knob write through only for one of these.
WRITABLE_WORDS: dict[int, frozenset[int]] = {
    eid: frozenset(m.word for (fam, _pid), m in PARAMS.items() if fam == family)
    for family, eid in EFFECT_IDS.items()
}


def lookup(family: str, param_id: int, instance: int = 1) -> Fm3Param | None:
    """Where the FM3 keeps the FM9 registry's (family, param_id), or None
    when that setting has not been measured on an FM3."""
    if instance != 1:
        return None
    return PARAMS.get((family, param_id))

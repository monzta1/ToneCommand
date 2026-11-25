"""The ToneX One's 109 preset settings, by index.

Index order, names, ranges and kinds from Builty/TonexOneController
(source/main/tonex_params.c and web/script.js), Copyright (c) Greg Smith,
Apache License 2.0 (see NOTICE). Checked against all twenty presets read
from a real One (fw 1.3.17, 2026-11-25): every observed value sits inside
its range except VIR_CABINET_MODEL, which is therefore never written.

`blocked` names a reason a setting is shown but never written.
"""
from __future__ import annotations

from typing import NamedTuple


class Param(NamedTuple):
    index: int
    name: str
    short: str
    lo: float
    hi: float
    kind: str            # "range", "switch" or "select"
    options: tuple | None = None
    blocked: str | None = None


PARAMS: tuple[Param, ...] = (
    Param(0, 'GATE_POST', 'NG POST', 0.0, 1.0, 'switch', None, None),
    Param(1, 'GATE_ENABLE', 'NG POWER', 0.0, 1.0, 'switch', None, None),
    Param(2, 'GATE_THRESHOLD', 'NG THRESH', -100.0, 0.0, 'range', None, None),
    Param(3, 'GATE_RELEASE', 'NG REL', 5.0, 500.0, 'range', None, None),
    Param(4, 'GATE_DEPTH', 'NG DEPTH', -100.0, -20.0, 'range', None, None),
    Param(5, 'COMP_POST', 'COMP POST', 0.0, 1.0, 'switch', None, None),
    Param(6, 'COMP_ENABLE', 'COMP POWER', 0.0, 1.0, 'switch', None, None),
    Param(7, 'COMP_THRESHOLD', 'COMP THRESH', -40.0, 0.0, 'range', None, None),
    Param(8, 'COMP_MAKE_UP', 'COMP GAIN', -30.0, 10.0, 'range', None, None),
    Param(9, 'COMP_ATTACK', 'COMP ATTACK', 1.0, 51.0, 'range', None, None),
    Param(10, 'EQ_POST', 'EQ POST', 0.0, 1.0, 'switch', None, None),
    Param(11, 'EQ_BASS', 'EQ BASS', 0.0, 10.0, 'range', None, None),
    Param(12, 'EQ_BASS_FREQ', 'EQ BFREQ', 75.0, 600.0, 'range', None, None),
    Param(13, 'EQ_MID', 'EQ MID', 0.0, 10.0, 'range', None, None),
    Param(14, 'EQ_MIDQ', 'EQ MIDQ', 0.2, 3.0, 'range', None, None),
    Param(15, 'EQ_MID_FREQ', 'EQ MFREQ', 150.0, 5000.0, 'range', None, None),
    Param(16, 'EQ_TREBLE', 'EQ TREBLE', 0.0, 10.0, 'range', None, None),
    Param(17, 'EQ_TREBLE_FREQ', 'EQ TFREQ', 1000.0, 4000.0, 'range', None, None),
    Param(18, 'MODEL_AMP_ENABLE', 'MDL AMP', 0.0, 1.0, 'switch', None, 'turning the amp off sends the bare guitar; not offered'),
    Param(19, 'MODEL_SW1', 'MDL SW1', 0.0, 1.0, 'switch', None, 'Builty: results in silence; function unknown'),
    Param(20, 'MODEL_GAIN', 'MDL GAIN', 0.0, 10.0, 'range', None, None),
    Param(21, 'MODEL_VOLUME', 'MDL VOL', 0.0, 10.0, 'range', None, None),
    Param(22, 'MODEL_MIX', 'MDL MIX', 0.0, 100.0, 'range', None, None),
    Param(23, 'MODEL_CABINET_UNKNOWN', 'MDL CABU', 0.0, 1.0, 'switch', None, 'function unknown (always 1)'),
    Param(24, 'CABINET_TYPE', 'MDL CAB', 0.0, 2.0, 'select', None, 'documented two different ways (0 = tone model cab or VIR); not checked on this pedal'),
    Param(25, 'VIR_CABINET_MODEL', 'VIR_CMDL', 0.0, 10.0, 'select', None, 'an index into a cab list longer than its documented 0..10 (17, 25, 28 seen); undecoded'),
    Param(26, 'VIR_RESO', 'VIR_RESO', 0.0, 10.0, 'range', None, None),
    Param(27, 'VIR_MIC_1', 'VIR M1', 0.0, 2.0, 'select', ('CONDENSER', 'DYNAMIC', 'RIBBON'), None),
    Param(28, 'VIR_MIC_1_X', 'VIR M1X', 0.0, 10.0, 'range', None, None),
    Param(29, 'VIR_MIC_1_Z', 'VIR M1Z', 0.0, 10.0, 'range', None, None),
    Param(30, 'VIR_MIC_2', 'VIR M2', 0.0, 2.0, 'select', ('CONDENSER', 'DYNAMIC', 'RIBBON'), None),
    Param(31, 'VIR_MIC_2_X', 'VIR M2X', 0.0, 2.0, 'range', None, None),
    Param(32, 'VIR_MIC_2_Z', 'VIR M2Z', 0.0, 10.0, 'range', None, None),
    Param(33, 'VIR_BLEND', 'VIR BLEND', -100.0, 100.0, 'range', None, None),
    Param(34, 'MODEL_PRESENCE', 'MDL PRE', 0.0, 10.0, 'range', None, None),
    Param(35, 'MODEL_DEPTH', 'MDL DEP', 0.0, 10.0, 'range', None, None),
    Param(36, 'REVERB_POSITION', 'RVB POS', 0.0, 1.0, 'switch', None, None),
    Param(37, 'REVERB_ENABLE', 'RVB POWER', 0.0, 1.0, 'switch', None, None),
    Param(38, 'REVERB_MODEL', 'RVB MODEL', 0.0, 5.0, 'select', ('SPRING 1', 'SPRING 2', 'SPRING 3', 'SPRING 4', 'ROOM', 'PLATE'), None),
    Param(39, 'REVERB_SPRING1_TIME', 'RVB S1 T', 0.0, 10.0, 'range', None, None),
    Param(40, 'REVERB_SPRING1_PREDELAY', 'RVB S1 P', 0.0, 500.0, 'range', None, None),
    Param(41, 'REVERB_SPRING1_COLOR', 'RVB S1 C', -10.0, 10.0, 'range', None, None),
    Param(42, 'REVERB_SPRING1_MIX', 'RVB S1 M', 0.0, 100.0, 'range', None, None),
    Param(43, 'REVERB_SPRING2_TIME', 'RVB S2 T', 0.0, 10.0, 'range', None, None),
    Param(44, 'REVERB_SPRING2_PREDELAY', 'RVB S2 P', 0.0, 500.0, 'range', None, None),
    Param(45, 'REVERB_SPRING2_COLOR', 'RVB S2 C', -10.0, 10.0, 'range', None, None),
    Param(46, 'REVERB_SPRING2_MIX', 'RVB S2 M', 0.0, 100.0, 'range', None, None),
    Param(47, 'REVERB_SPRING3_TIME', 'RVB S3 T', 0.0, 10.0, 'range', None, None),
    Param(48, 'REVERB_SPRING3_PREDELAY', 'RVB S3 P', 0.0, 500.0, 'range', None, None),
    Param(49, 'REVERB_SPRING3_COLOR', 'RVB S3 C', -10.0, 10.0, 'range', None, None),
    Param(50, 'REVERB_SPRING3_MIX', 'RVB S3 M', 0.0, 100.0, 'range', None, None),
    Param(51, 'REVERB_SPRING4_TIME', 'RVB S4 T', 0.0, 10.0, 'range', None, None),
    Param(52, 'REVERB_SPRING4_PREDELAY', 'RVB S4 P', 0.0, 500.0, 'range', None, None),
    Param(53, 'REVERB_SPRING4_COLOR', 'RVB S4 C', -10.0, 10.0, 'range', None, None),
    Param(54, 'REVERB_SPRING4_MIX', 'RVB S4 M', 0.0, 100.0, 'range', None, None),
    Param(55, 'REVERB_ROOM_TIME', 'RVB RM T', 0.0, 10.0, 'range', None, None),
    Param(56, 'REVERB_ROOM_PREDELAY', 'RVB RM P', 0.0, 500.0, 'range', None, None),
    Param(57, 'REVERB_ROOM_COLOR', 'RVB RM C', -10.0, 10.0, 'range', None, None),
    Param(58, 'REVERB_ROOM_MIX', 'RVB RM M', 0.0, 100.0, 'range', None, None),
    Param(59, 'REVERB_PLATE_TIME', 'RVB PL T', 0.0, 10.0, 'range', None, None),
    Param(60, 'REVERB_PLATE_PREDELAY', 'RVB PL P', 0.0, 500.0, 'range', None, None),
    Param(61, 'REVERB_PLATE_COLOR', 'RVB PL C', -10.0, 10.0, 'range', None, None),
    Param(62, 'REVERB_PLATE_MIX', 'RVB PL M', 0.0, 100.0, 'range', None, None),
    Param(63, 'MOD_POST', 'MOD POST', 0.0, 1.0, 'switch', None, None),
    Param(64, 'MOD_ENABLE', 'MOD POWER', 0.0, 1.0, 'switch', None, None),
    Param(65, 'MOD_MODEL', 'MOD MODEL', 0.0, 4.0, 'select', ('CHORUS', 'TREMOLO', 'PHASER', 'FLANGER', 'ROTARY'), None),
    Param(66, 'MOD_CHORUS_SYNC', 'MOD CH S', 0.0, 1.0, 'switch', None, None),
    Param(67, 'MOD_CHORUS_TS', 'MOD CH T', 0.0, 17.0, 'select', None, None),
    Param(68, 'MOD_CHORUS_RATE', 'MOD CH R', 0.1, 10.0, 'range', None, None),
    Param(69, 'MOD_CHORUS_DEPTH', 'MOD CH D', 0.0, 100.0, 'range', None, None),
    Param(70, 'MOD_CHORUS_LEVEL', 'MOD CH L', 0.0, 10.0, 'range', None, None),
    Param(71, 'MOD_TREMOLO_SYNC', 'MOD TR S', 0.0, 1.0, 'switch', None, None),
    Param(72, 'MOD_TREMOLO_TS', 'MOD TR T', 0.0, 17.0, 'select', None, None),
    Param(73, 'MOD_TREMOLO_RATE', 'MOD TR R', 0.1, 10.0, 'range', None, None),
    Param(74, 'MOD_TREMOLO_SHAPE', 'MOD TR P', 0.0, 10.0, 'range', None, None),
    Param(75, 'MOD_TREMOLO_SPREAD', 'MOD TR D', 0.0, 100.0, 'range', None, None),
    Param(76, 'MOD_TREMOLO_LEVEL', 'MOD TR L', 0.0, 10.0, 'range', None, None),
    Param(77, 'MOD_PHASER_SYNC', 'MOD PH S', 0.0, 1.0, 'switch', None, None),
    Param(78, 'MOD_PHASER_TS', 'MOD PH T', 0.0, 17.0, 'select', None, None),
    Param(79, 'MOD_PHASER_RATE', 'MOD PH R', 0.1, 10.0, 'range', None, None),
    Param(80, 'MOD_PHASER_DEPTH', 'MOD PH D', 0.0, 100.0, 'range', None, None),
    Param(81, 'MOD_PHASER_LEVEL', 'MOD PH L', 0.0, 10.0, 'range', None, None),
    Param(82, 'MOD_FLANGER_SYNC', 'MOD FL S', 0.0, 1.0, 'switch', None, None),
    Param(83, 'MOD_FLANGER_TS', 'MOD FL T', 0.0, 17.0, 'select', None, None),
    Param(84, 'MOD_FLANGER_RATE', 'MOD FL R', 0.1, 10.0, 'range', None, None),
    Param(85, 'MOD_FLANGER_DEPTH', 'MOD FL D', 0.0, 100.0, 'range', None, None),
    Param(86, 'MOD_FLANGER_FEEDBACK', 'MOD FL F', 0.0, 100.0, 'range', None, None),
    Param(87, 'MOD_FLANGER_LEVEL', 'MOD FL L', 0.0, 10.0, 'range', None, None),
    Param(88, 'MOD_ROTARY_SYNC', 'MOD RO S', 0.0, 1.0, 'switch', None, None),
    Param(89, 'MOD_ROTARY_TS', 'MOD RO T', 0.0, 17.0, 'select', None, None),
    Param(90, 'MOD_ROTARY_SPEED', 'MOD RO S', 0.0, 400.0, 'range', None, None),
    Param(91, 'MOD_ROTARY_RADIUS', 'MOD RO R', 0.0, 300.0, 'range', None, None),
    Param(92, 'MOD_ROTARY_SPREAD', 'MOD RO D', 0.0, 100.0, 'range', None, None),
    Param(93, 'MOD_ROTARY_LEVEL', 'MOD RO L', 0.0, 10.0, 'range', None, None),
    Param(94, 'DELAY_POST', 'DLY POST', 0.0, 1.0, 'switch', None, None),
    Param(95, 'DELAY_ENABLE', 'DLY POWER', 0.0, 1.0, 'switch', None, None),
    Param(96, 'DELAY_MODEL', 'DLY MODEL', 0.0, 1.0, 'select', ('DIGITAL', 'TAPE'), None),
    Param(97, 'DELAY_DIGITAL_SYNC', 'DLY DG S', 0.0, 1.0, 'switch', None, None),
    Param(98, 'DELAY_DIGITAL_TS', 'DLY DG T', 0.0, 17.0, 'select', None, None),
    Param(99, 'DELAY_DIGITAL_TIME', 'DLY DT M', 0.0, 1000.0, 'range', None, None),
    Param(100, 'DELAY_DIGITAL_FEEDBACK', 'DLY DT F', 0.0, 100.0, 'range', None, None),
    Param(101, 'DELAY_DIGITAL_MODE', 'DLY DT O', 0.0, 1.0, 'switch', None, None),
    Param(102, 'DELAY_DIGITAL_MIX', 'DLY DT X', 0.0, 100.0, 'range', None, None),
    Param(103, 'DELAY_TAPE_SYNC', 'DLY TA S', 0.0, 1.0, 'switch', None, None),
    Param(104, 'DELAY_TAPE_TS', 'DLY TA T', 0.0, 17.0, 'select', None, None),
    Param(105, 'DELAY_TAPE_TIME', 'DLY TA M', 0.0, 1000.0, 'range', None, None),
    Param(106, 'DELAY_TAPE_FEEDBACK', 'DLY TA F', 0.0, 100.0, 'range', None, None),
    Param(107, 'DELAY_TAPE_MODE', 'DLY TA O', 0.0, 1.0, 'switch', None, None),
    Param(108, 'DELAY_TAPE_MIX', 'DLY TA X', 0.0, 100.0, 'range', None, None),
)

BY_NAME = {p.name: p for p in PARAMS}

#: index -> (lo, hi) for every setting the send gate lets through.
WRITABLE = {p.index: (p.lo, p.hi) for p in PARAMS if not p.blocked}

assert len(PARAMS) == 109 and all(p.index == i for i, p in enumerate(PARAMS))

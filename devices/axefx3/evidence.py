"""Axe-Fx III parameter evidence, isolated from the FM9 catalog.

Ported from local checkpoint 18f8eac (2026-09-29). Original Axe-Edit
captures and device checks were made on FW 32.06; this port still
requires its own hardware acceptance. Metadata is not acoustic proof.
See docs/AFX3-PARITY-2026-09-19.md for provenance and limits.
"""
from fm9.protocol import normalized_to_display
from .tone_controls import DEFINITIONS as EXTRA_CONTROLS, ZERO_TYPED as EXTRA_ZERO_TYPED

AXE_FX_III_PARAM_DEFINITIONS = {
    # Axe-Edit III + independent FW32.06 display/bulk reads on test 323,
    # 2026-10-06. SET floats are Hz, fractional depth/mix and literal dB.
    "CHORUS": {
        "CHORUS_RATE": {"pid": 2, "label": "Rate", "unit": "Hz",
                        "min": .1, "max": 10.0, "scale": "log10",
                        "set_opcode": "09", "set_divisor": 1.0,
                        "display_tolerance": .00051, "tempo_param_id": 3,
                        "firmware_versions": ("32.06",)},
        "CHORUS_DEPTH": {"pid": 4, "label": "Depth", "unit": "%",
                         "min": 0.0, "max": 100.0, "set_opcode": "09",
                         "set_divisor": 100.0, "display_tolerance": .051,
                         "firmware_versions": ("32.06",)},
        "CHORUS_MIX": {"pid": 10, "label": "Mix", "unit": "%",
                       "min": 0.0, "max": 100.0, "set_opcode": "09",
                       "set_divisor": 100.0, "display_tolerance": .051,
                       "firmware_versions": ("32.06",)},
        "CHORUS_LEVEL": {"pid": 11, "label": "Level", "unit": "dB",
                         "min": -80.0, "max": 20.0, "set_opcode": "09",
                         "set_divisor": 1.0, "display_tolerance": .051,
                         "firmware_versions": ("32.06",)},
    },
    "DISTORT": {
        "DISTORT_DRIVE": {"pid": 1, "label": "Gain", "unit": "0-10",
                           "min": 0.0, "max": 10.0, "set_opcode": "09"},
        "DISTORT_MID": {"pid": 3, "label": "Mid", "unit": "0-10",
                         "min": 0.0, "max": 10.0, "set_opcode": "09"},
        # AFX3 32p4/32p6 Axe-Edit metadata + pinned 32.02 capture map.
        # Not copied from FM9; independent display read-back on each write.
        "DISTORT_BASS": {"pid": 2, "label": "Bass", "unit": "0-10",
                          "min": 0.0, "max": 10.0, "set_opcode": "09", "hardware_verified": False},
        "DISTORT_TREBLE": {"pid": 4, "label": "Treble", "unit": "0-10",
                            "min": 0.0, "max": 10.0, "set_opcode": "09", "hardware_verified": False},
        "DISTORT_MASTER": {"pid": 5, "label": "Master", "unit": "0-10",
                            "min": 0.0, "max": 10.0, "set_opcode": "09", "hardware_verified": False},
        "DISTORT_DEPTH": {"pid": 16, "label": "Depth", "unit": "0-10",
                           "min": 0.0, "max": 10.0, "set_opcode": "09", "hardware_verified": False},
        "DISTORT_PRESENCE": {"pid": 20, "label": "Presence", "unit": "0-10",
                              "min": 0.0, "max": 10.0, "set_opcode": "09", "hardware_verified": False},
        # SET is raw dB; bulk is linear [-80, 20], independently evidenced.
        # See docs/AFX3-CORE-CONTROLS.md (including the zero/GET ambiguity).
        "DISTORT_LEVEL": {"pid": 21, "label": "Level", "unit": "dB",
                          "min": -80.0, "max": 20.0, "scale": "linear",
                          "set_opcode": "09", "set_divisor": 1.0,
                          "display_tolerance": 0.051,
                          "firmware_versions": ("32.04", "32.06"),
                          "hardware_verified": False},
    },
    "REVERB": {
        "REVERB_MIX": {"pid": 13, "label": "Mix", "unit": "%",
                       "min": 0.0, "max": 100.0, "scale": "linear",
                       "set_opcode": "09", "set_divisor": 100.0,
                       "display_tolerance": 0.051,
                       "firmware_versions": ("32.04", "32.06"),
                       "hardware_verified": False},
        "REVERB_TIME": {"pid": 1, "label": "Time", "unit": "seconds",
                         "min": 0.1, "max": 100.0, "scale": "linear",
                         "set_opcode": "09", "set_divisor": 1.0,
                         "display_tolerance": 0.011,
                         "firmware_versions": ("32.04", "32.06"),
                         "hardware_verified": False},
        # Direct-dB SET is evidenced; the bulk law has no per-control anchor.
        # Main must honor bulk_restore_supported in all raw restore paths.
        "REVERB_LEVEL": {"pid": 14, "label": "Level", "unit": "dB",
                          "min": -80.0, "max": 20.0,
                          "set_opcode": "09", "set_divisor": 1.0,
                          "display_tolerance": 0.051,
                          "firmware_versions": ("32.04", "32.06"),
                          "bulk_restore_supported": False,
                          "hardware_verified": False},
    },
    "DELAY": {
        "DELAY_MIX": {"pid": 17, "label": "Mix", "unit": "%",
                      "min": 0.0, "max": 100.0, "scale": "linear",
                      "set_opcode": "09", "set_divisor": 100.0,
                      "display_tolerance": 0.051,
                      "firmware_versions": ("32.04", "32.06"),
                      "hardware_verified": False},
        # Axe-Edit III 32p4/32p6 metadata + pinned 32.02 captures:
        # SET uses seconds / signed fraction, NOT the normalized bulk word.
        # Evidence and the tempo dependency: docs/AFX3-DELAY.md.
        "DELAY_TIME": {"pid": 2, "label": "Time", "unit": "ms",
                       "min": 1.0, "max": 16000.0, "wire_min": 0.0,
                       "set_opcode": "09", "set_divisor": 1000.0,
                       "display_tolerance": 0.51, "tempo_param_id": 9,
                       "firmware_versions": ("32.04", "32.06"),
                       "hardware_verified": False},
        "DELAY_FEED": {"pid": 4, "label": "Feedback", "unit": "%",
                       "min": -100.0, "max": 100.0,
                       "set_opcode": "09", "set_divisor": 100.0,
                       "display_tolerance": 0.11,
                       "firmware_versions": ("32.04", "32.06"),
                       "hardware_verified": False},
        "DELAY_LEVEL": {"pid": 18, "label": "Level", "unit": "dB",
                         "min": -80.0, "max": 20.0,
                         "set_opcode": "09", "set_divisor": 1.0,
                         "display_tolerance": 0.051,
                         "firmware_versions": ("32.04", "32.06"),
                         "bulk_restore_supported": False,
                         "hardware_verified": False},
    },
    "PITCH": {
        "PITCH_LEVEL": {"pid": 39, "label": "Level", "unit": "dB",
                         "min": -80.0, "max": 20.0,
                         "set_opcode": "09", "set_divisor": 1.0,
                         "display_tolerance": 0.051,
                         "firmware_versions": ("32.04", "32.06"),
                         "bulk_restore_supported": False,
                         "hardware_verified": False},
    },
    "WAH": {
        # Actual Axe-Edit 1.14.34 output + local FW32p6 definitions, 2026-09-18.
        # Q/Drive display the 0..10 knob, NOT the nonlinear internal cache units.
        # Frequency fields send literal Hz via 09; Q/Drive send knob/10 via 52.
        "WAH_FREQMIN": {"pid": 1, "label": "Frequency Min", "unit": "Hz",
                        "min": 100.0, "max": 1000.0, "scale": "log10",
                        "set_opcode": "09", "set_divisor": 1.0,
                        "display_tolerance": 0.51, "firmware_versions": ("32.06",)},
        "WAH_FREQMAX": {"pid": 2, "label": "Frequency Max", "unit": "Hz",
                        "min": 500.0, "max": 5000.0, "scale": "log10",
                        "set_opcode": "09", "set_divisor": 1.0,
                        "display_tolerance": 0.51, "firmware_versions": ("32.06",)},
        "WAH_RESONANCE": {"pid": 3, "label": "Resonance Q", "unit": "0-10",
                          "min": 0.0, "max": 10.0,
                          "set_opcode": "52", "set_divisor": 10.0,
                          "display_tolerance": 0.011, "firmware_versions": ("32.06",)},
        "WAH_QTRACKING": {"pid": 4, "label": "Q Tracking", "unit": "0-10",
                          "min": 0.0, "max": 10.0,
                          "set_opcode": "09", "set_divisor": 10.0,
                          "display_tolerance": 0.011, "firmware_versions": ("32.06",)},
        "WAH_FAT": {"pid": 9, "label": "Fat", "unit": "0-10",
                    "min": 0.0, "max": 10.0,
                    "set_opcode": "09", "set_divisor": 10.0,
                    "display_tolerance": 0.011, "firmware_versions": ("32.06",)},
        "WAH_DRIVE": {"pid": 10, "label": "Drive", "unit": "0-10",
                      "min": 0.0, "max": 10.0,
                      "set_opcode": "52", "set_divisor": 10.0,
                      "display_tolerance": 0.011, "firmware_versions": ("32.06",)},
        "WAH_INDUCTOR_BIAS": {"pid": 13, "label": "Inductor Bias", "unit": "0-10",
                              "min": 0.0, "max": 10.0,
                              "set_opcode": "09", "set_divisor": 10.0,
                              "display_tolerance": 0.011, "firmware_versions": ("32.06",)},
        "WAH_LOWCUT": {"pid": 14, "label": "Low Cut Frequency", "unit": "Hz",
                       "min": 20.0, "max": 2000.0, "scale": "log10",
                       "set_opcode": "09", "set_divisor": 1.0,
                       "display_tolerance": 0.051, "firmware_versions": ("32.06",)},
        # Preserve the established 01 52 normalized path explicitly. Cache
        # metadata establishes ranges, not SET opcode; see legacy-domain docs.
        "WAH_LEVEL": {"pid": 6, "label": "Level", "unit": "dB",
                       "min": -80.0, "max": 20.0, "set_opcode": "52"},
        "WAH_CONTROL": {"pid": 5, "label": "Control", "unit": "0-10",
                         "min": 0.0, "max": 10.0, "set_opcode": "52"},
    },
    "OUTPUT": {
        "OUTPUT_LEVEL": {"pid": 12, "label": "Level", "unit": "dB",
                          "min": -80.0, "max": 20.0,
                          "set_opcode": "09", "set_divisor": 1.0,
                          "display_tolerance": 0.051,
                          "firmware_versions": ("32.04", "32.06"),
                          "bulk_restore_supported": False,
                          "hardware_verified": False},
    },
}

# Cab Legacy mixer: exact Axe-Edit captures + independent FW32.06 readback,
# 2026-09-19. These are IR slots, not block instances or stereo sides.
AXE_FX_III_CAB_MIX_PARAMS = {
    **{f"CABINET_LEVEL{i}": {"pid": 7+i, "label": f"IR {i} Level", "unit": "dB",
        "min": -40.0, "max": 0.0, "set_opcode": "09", "set_divisor": 1.0,
        "display_tolerance": .011, "firmware_versions": ("32.06",)} for i in range(1, 5)},
    **{f"CABINET_PAN{i}": {"pid": 11+i, "label": f"IR {i} Pan", "unit": "%",
        "min": -100.0, "max": 100.0, "set_opcode": "09", "set_divisor": 100.0,
        "display_tolerance": .051, "firmware_versions": ("32.06",)} for i in range(1, 5)},
    **{f"CABINET_MUTE{i}": {"pid": 23+i, "label": f"IR {i} Mode (0=normal, 1=mute, 2=solo)",
        "unit": "IR mode", "kind": "enum", "enum_count": 3,
        "min": 0.0, "max": 2.0, "set_opcode": "09", "set_divisor": 1.0,
        "display_tolerance": 0, "firmware_versions": ("32.06",)} for i in range(1, 5)},
}
AXE_FX_III_PARAM_DEFINITIONS["CABINET"] = AXE_FX_III_CAB_MIX_PARAMS
AXE_FX_III_PARAM_DEFINITIONS.update(EXTRA_CONTROLS)

AXE_FX_III_VERIFIED_PARAMS = frozenset(
    name for params in AXE_FX_III_PARAM_DEFINITIONS.values()
    for name in params
)

# Hardware captures, 2026-09-18, Axe-Fx III FW 32.06, muted test preset 321.
# These are explicit per-control measurements, NOT a general opcode fallback.
# See docs/AFX3-HARDWARE-2026-09-18.md. Older firmware keeps its restrictions.
AXE_FX_III_32_06_ZERO_NORMALIZED = {
    "DELAY_MIX": 0.0, "REVERB_MIX": 0.0, "DELAY_FEED": 0.5,
    "DISTORT_LEVEL": 0.8, "DELAY_LEVEL": 0.8, "REVERB_LEVEL": 0.8,
    "PITCH_LEVEL": 0.8, "OUTPUT_LEVEL": 0.8,
    "WAH_RESONANCE": 0.0, "WAH_DRIVE": 0.0,
}

# Actual typed-zero SETs from Axe-Edit: Wah confirmed 2026-09-19,
# Chorus confirmed 2026-10-06. See docs/AFX3-CHORUS-INSERTION.md.
# Distinct from the normalized alternate setters above; no general fallback.
AXE_FX_III_32_06_ZERO_TYPED = frozenset({
    'WAH_INDUCTOR_BIAS', 'WAH_QTRACKING', 'WAH_FAT',
    'CHORUS_DEPTH', 'CHORUS_MIX', 'CHORUS_LEVEL',
}) | EXTRA_ZERO_TYPED


def afx3_zero_set_supported(spec, firmware: str) -> bool:
    """Value-level capability for an otherwise validated AFX3 parameter.

    Raw display-domain SETs need a separately evidenced zero encoder. A range
    starting at zero or a successful nonzero capture does not supply one.
    Existing normalized controls are outside this raw-SET restriction. This
    does not replace address/range/firmware checks in the device executor.
    """
    return (getattr(spec, 'set_divisor', None) is None
            or (firmware == '32.06' and spec.family == 'CABINET'
                and spec.name in AXE_FX_III_CAB_MIX_PARAMS)
            or (firmware == '32.06' and spec.family in ('WAH', 'CHORUS', *EXTRA_CONTROLS)
                and spec.name in AXE_FX_III_32_06_ZERO_TYPED)
            or (firmware == '32.06' and spec.name in AXE_FX_III_32_06_ZERO_NORMALIZED))


AXE_FX_III_32_06_LEVEL_BULK = frozenset({
    "DISTORT_LEVEL", "DELAY_LEVEL", "REVERB_LEVEL", "PITCH_LEVEL", "OUTPUT_LEVEL",
    "CHORUS_LEVEL",
})
AXE_FX_III_32_06_TESTED_CONTROLS = frozenset({
    "CHORUS_RATE", "CHORUS_DEPTH", "CHORUS_MIX", "CHORUS_LEVEL",
    "DISTORT_DRIVE", "DISTORT_BASS", "DISTORT_MID", "DISTORT_TREBLE",
    "DISTORT_MASTER", "DISTORT_DEPTH", "DISTORT_PRESENCE", "DISTORT_LEVEL",
    "REVERB_TIME", "REVERB_MIX", "REVERB_LEVEL", "DELAY_TIME", "DELAY_FEED",
    "DELAY_MIX", "DELAY_LEVEL", "PITCH_LEVEL", "OUTPUT_LEVEL", "WAH_CONTROL", "WAH_LEVEL",
    "WAH_FREQMIN", "WAH_FREQMAX", "WAH_RESONANCE", "WAH_QTRACKING", "WAH_FAT",
    "WAH_DRIVE", "WAH_INDUCTOR_BIAS", "WAH_LOWCUT",
}) | frozenset(name for definitions in EXTRA_CONTROLS.values() for name in definitions)


def afx3_bulk_restore_supported(spec, firmware: str) -> bool:
    definition = AXE_FX_III_PARAM_DEFINITIONS.get(spec.family, {}).get(spec.name, {})
    return (definition.get("bulk_restore_supported") is not False
            or (firmware == "32.06" and spec.name in AXE_FX_III_32_06_LEVEL_BULK))


def param_normalized_to_display(spec, normalized: float, firmware: str = "") -> float:
    """Decode bulk with firmware-specific anchors; preserve the FM9 path.

    The measured 0 dB word rounds to 52427, not an exactly representable 80%.
    Canonicalize ONLY that exact word, never relax the positive-gain guard.
    """
    lo = spec.wire_min if spec.wire_min is not None else spec.dmin
    if spec.verify_display_text and firmware == "32.06":
        if spec.family == 'CABINET' and spec.name in AXE_FX_III_CAB_MIX_PARAMS:
            if spec.kind == 'enum':
                return normalized * 65534  # mode words are ordinals, not normalized knobs
        if spec.name == "DELAY_TIME" and spec.family == "DELAY":
            lo = 1.0  # 1ms -> word 0; 16000ms -> 65534 on this firmware.
        if (spec.name in AXE_FX_III_32_06_LEVEL_BULK
                and normalized == 52427 / 65534):
            return 0.0
    return normalized_to_display(normalized, lo, spec.dmax, spec.scale)

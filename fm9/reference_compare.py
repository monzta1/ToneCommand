"""Local-only, read-only frequency-balance reference comparison."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .audio_metrics import (
    ALGORITHM_VERSION,
    DC_OFFSET_MAX_ABS,
    FREQUENCY_BANDS,
    _audio,
    _db,
    _full_cross_correlation,
    _np,
    _validate_sample_rate,
)


REFERENCE_QUALITY = {
    "golden_same_di": {"rank": 1, "correction": True, "label": "player-approved golden preset, same DI"},
    "isolated_guitar": {"rank": 2, "correction": True, "label": "isolated guitar stem"},
    "solo_guitar_excerpt": {"rank": 3, "correction": True, "label": "solo guitar excerpt with unknown processing"},
    "mastered_mix": {"rank": 4, "correction": False, "label": "full mastered mix; broad estimate only"},
}


def _spectrum(samples, sample_rate: int):
    np = _np()
    windowed = samples * np.hanning(len(samples))
    power = np.abs(np.fft.rfft(windowed)) ** 2
    frequencies = np.fft.rfftfreq(len(samples), 1.0 / sample_rate)
    return frequencies, power


def _band_levels(samples, sample_rate: int) -> tuple[dict[str, float], list[str]]:
    np = _np()
    frequencies, power = _spectrum(samples, sample_rate)
    total = float(power[frequencies >= 20.0].sum())
    values: dict[str, float] = {}
    unsupported: list[str] = []
    for name, (low, high) in FREQUENCY_BANDS.items():
        upper = sample_rate / 2.0 if high is None else min(float(high), sample_rate / 2.0)
        mask = (frequencies >= low) & (frequencies < upper)
        if upper <= low or not mask.any():
            unsupported.append(name)
        else:
            values[name] = _db(float(power[mask].sum()) / max(total, 1e-20))
    return values, unsupported


def _resolve_control(control_map: Mapping[str, Any] | None, band: str) -> dict[str, Any] | None:
    if not control_map or band not in control_map:
        return None
    candidates = control_map[band]
    if isinstance(candidates, Mapping):
        candidates = [candidates]
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or len(candidates) != 1:
        return None
    candidate = candidates[0]
    if not isinstance(candidate, Mapping) or not candidate.get("block") or not candidate.get("parameter"):
        return None
    if candidate.get("ambiguous") or candidate.get("shared_across_scenes"):
        return None
    return dict(candidate)


def compare_reference(
    subject: Sequence[float],
    reference: Sequence[float],
    sample_rate: int,
    *,
    reference_quality: str,
    control_map: Mapping[str, Any] | None = None,
    subject_region: tuple[int, int] | None = None,
    reference_region: tuple[int, int] | None = None,
    proposal_threshold_db: float = 1.5,
) -> dict[str, Any]:
    """Compare two local clips and optionally propose one directional EQ move.

    The proposal is inert data: it is confirmation-required and this module has
    no device action path.  Raw levels are measured before alignment/normalizing.
    """

    _validate_sample_rate(sample_rate)
    if (
        isinstance(proposal_threshold_db, bool)
        or not isinstance(proposal_threshold_db, (int, float))
        or not math.isfinite(float(proposal_threshold_db))
        or proposal_threshold_db < 0
    ):
        raise ValueError("proposal_threshold_db must be a finite non-negative number")
    np = _np()
    if reference_quality not in REFERENCE_QUALITY:
        raise ValueError(f"unknown reference_quality: {reference_quality}")
    subject_data, reference_data = _audio(subject), _audio(reference)
    if subject_region:
        subject_data = subject_data[slice(*subject_region)]
    if reference_region:
        reference_data = reference_data[slice(*reference_region)]
    if min(len(subject_data), len(reference_data)) < 32:
        raise ValueError("comparable regions must contain at least 32 frames")
    subject_mono, reference_mono = subject_data.mean(axis=1), reference_data.mean(axis=1)

    subject_raw_rms = float(np.sqrt(np.mean(subject_mono * subject_mono)))
    reference_raw_rms = float(np.sqrt(np.mean(reference_mono * reference_mono)))
    report: dict[str, Any] = {
        "metric": "reference_frequency_balance",
        "status": "unknown",
        "coverage": {
            "sample_rate_hz": int(sample_rate),
            "subject_region_frames": int(len(subject_mono)),
            "reference_region_frames": int(len(reference_mono)),
        },
        "evidence": [{"source": "local_clips", "method": "aligned, RMS-normalized Hann spectral comparison"}],
        "missing_facts": [],
        "findings": [],
        "limitations": ["Frequency balance cannot recreate amp dynamics, production, or playing feel."],
        "algorithm_version": f"{ALGORITHM_VERSION}+reference/1.0",
        "measurement_boundary": "local_audio_fixture",
        "hardware_verified": False,
        "sound_checked": False,
        "live_fm9": False,
        "reference_quality": {"id": reference_quality, **REFERENCE_QUALITY[reference_quality]},
        "raw_levels": {
            "subject_rms_dbfs": 20.0 * math.log10(max(subject_raw_rms, 1e-8)),
            "reference_rms_dbfs": 20.0 * math.log10(max(reference_raw_rms, 1e-8)),
        },
        "proposal": None,
        "sent": False,
    }
    dc_offsets = {
        "subject": [float(value) for value in np.mean(subject_data, axis=0)],
        "reference": [float(value) for value in np.mean(reference_data, axis=0)],
    }
    if any(abs(value) > DC_OFFSET_MAX_ABS for values in dc_offsets.values() for value in values):
        report["status"] = "invalid"
        report["technical_defects"] = [
            {
                "kind": "dc_offset",
                "offsets_full_scale": dc_offsets,
                "threshold_full_scale": DC_OFFSET_MAX_ABS,
            }
        ]
        report["findings"].append(
            {"kind": "dc_offset", "severity": "invalid", "reason": "DC-offset audio cannot establish a reference comparison."}
        )
        return report
    subject_ac = subject_mono - subject_mono.mean()
    reference_ac = reference_mono - reference_mono.mean()
    subject_ac_rms = float(np.sqrt(np.mean(subject_ac * subject_ac)))
    reference_ac_rms = float(np.sqrt(np.mean(reference_ac * reference_ac)))
    if subject_raw_rms < 1e-8 or reference_raw_rms < 1e-8:
        report["missing_facts"].append("non-silent subject and reference regions")
        return report
    if subject_ac_rms < 1e-8 or reference_ac_rms < 1e-8:
        report["missing_facts"].append("usable non-DC spectral energy in both regions")
        report["limitations"].append("DC-only material cannot establish frequency balance.")
        return report

    # Normalize only working copies; raw measurements above remain untouched.
    subject_norm = subject_ac / subject_ac_rms
    reference_norm = reference_ac / reference_ac_rms
    max_lag = min(int(sample_rate * 0.25), len(subject_norm) - 1, len(reference_norm) - 1)
    correlation = _full_cross_correlation(subject_norm, reference_norm)
    center = len(reference_norm) - 1
    window = correlation[center - max_lag : center + max_lag + 1]
    lag = int(np.argmax(np.abs(window)) - max_lag)
    if lag >= 0:
        subject_aligned, reference_aligned = subject_norm[lag:], reference_norm[: len(subject_norm) - lag]
    else:
        subject_aligned, reference_aligned = subject_norm[: len(subject_norm) + lag], reference_norm[-lag:]
    length = min(len(subject_aligned), len(reference_aligned))
    subject_aligned, reference_aligned = subject_aligned[:length], reference_aligned[:length]
    report["alignment"] = {"lag_samples": lag, "lag_ms": lag * 1000.0 / sample_rate, "compared_frames": length}

    subject_bands, subject_unsupported = _band_levels(subject_aligned, sample_rate)
    reference_bands, reference_unsupported = _band_levels(reference_aligned, sample_rate)
    common = sorted(set(subject_bands) & set(reference_bands))
    deltas = {band: subject_bands[band] - reference_bands[band] for band in common}
    report["spectral_delta"] = {
        "band_delta_db": deltas,
        "smoothing": "named log-frequency bands",
        "normalization": "independent RMS normalization after raw-level measurement",
    }
    unsupported = sorted(set(subject_unsupported + reference_unsupported))
    report["unsupported_regions"] = unsupported
    if unsupported:
        report["limitations"].append(f"Unsupported at this sample rate: {', '.join(unsupported)}.")
    if not deltas:
        report["missing_facts"].append("overlapping spectral regions")
        return report
    report["status"] = "verified"

    quality = REFERENCE_QUALITY[reference_quality]
    if not quality["correction"]:
        report["limitations"].append("A mastered mix is a broad estimate and cannot justify an EQ action.")
        return report
    strongest_band, strongest_delta = max(deltas.items(), key=lambda item: abs(item[1]))
    if abs(strongest_delta) < proposal_threshold_db:
        report["findings"].append({"result": "within_directional_threshold", "threshold_db": proposal_threshold_db})
        return report
    control = _resolve_control(control_map, strongest_band)
    if control is None:
        report["missing_facts"].append(f"one unambiguous injected control for {strongest_band}")
        report["limitations"].append("No confirmable action is produced from a missing, shared, or ambiguous control map.")
        return report
    direction = "decrease" if strongest_delta > 0 else "increase"
    report["proposal"] = {
        "kind": "directional_eq",
        "band": strongest_band,
        "measured_delta_db": strongest_delta,
        "direction": direction,
        "size": "small",
        "block": control["block"],
        "parameter": control["parameter"],
        "requires_confirmation": True,
        "sent": False,
    }
    return report


compare_frequency_balance = compare_reference

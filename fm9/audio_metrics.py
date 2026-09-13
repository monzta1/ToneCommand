"""Pure, optional-dependency audio measurements.

The functions in this module accept in-memory samples and never open an audio
or MIDI device.  Importing the module does not require NumPy; a helpful error is
raised only if a measurement is requested without the optional ``audio`` extra.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .sound_policy import POLICY_VERSION, SceneLoudnessPolicy, evaluate_band_policy


ALGORITHM_VERSION = "offline-audio-metrics/1.0"
MEASUREMENT_BOUNDARY = "local_audio_fixture"
# A mean offset above one percent of digital full scale (-40 dBFS) is treated
# as a technical acquisition defect.  This intentionally conservative fixture
# threshold must be hardware-calibrated before live FM9 claims are possible.
DC_OFFSET_MAX_ABS = 0.01

# Descriptive evidence regions, not universal good/bad ranges.
FREQUENCY_BANDS: dict[str, tuple[float, float | None]] = {
    "low_end": (20.0, 120.0),
    "body": (180.0, 500.0),
    "presence": (1500.0, 4000.0),
    "upper_bite": (6000.0, 8000.0),
    "fizz_potential": (8000.0, 10000.0),
    "air_noise": (10000.0, None),
}


def _np():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised by no-extra install checks
        raise RuntimeError(
            "Offline audio analysis requires the optional 'audio' extra "
            "(pip install tonecommand[audio])."
        ) from exc
    return np


def _audio(samples: Sequence[float], *, minimum_frames: int = 32):
    np = _np()
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2 or data.shape[1] not in (1, 2):
        raise ValueError("audio must be mono or stereo with shape (frames, channels)")
    if data.shape[0] < minimum_frames:
        raise ValueError(f"audio must contain at least {minimum_frames} frames")
    if not np.isfinite(data).all():
        raise ValueError("audio contains NaN or infinite samples")
    return data


def _validate_sample_rate(sample_rate: int) -> int:
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive integer")
    return sample_rate


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _finite_limit_rule(rule: Any, minimum_key: str, maximum_key: str) -> bool:
    if not isinstance(rule, Mapping):
        return False
    supplied = [rule[key] for key in (minimum_key, maximum_key) if rule.get(key) is not None]
    return bool(supplied) and all(_finite_number(value) for value in supplied)


def _reject_dc_offset(report: dict[str, Any], data, *, scope: str = "capture") -> bool:
    """Mark a report invalid when any input channel exceeds the DC threshold."""

    np = _np()
    offsets = np.mean(data, axis=0)
    affected = [int(index) for index, value in enumerate(offsets) if abs(float(value)) > DC_OFFSET_MAX_ABS]
    if not affected:
        return False
    report["status"] = "invalid"
    report["technical_defects"] = [
        {
            "kind": "dc_offset",
            "scope": scope,
            "channels": affected,
            "offsets_full_scale": [float(value) for value in offsets],
            "threshold_full_scale": DC_OFFSET_MAX_ABS,
        }
    ]
    report["findings"].append(
        {
            "kind": "dc_offset",
            "severity": "invalid",
            "reason": "Meaningful DC offset invalidates uncentered audio measurements.",
        }
    )
    return True


def _base_report(metric: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "status": "unknown",
        "coverage": {},
        "evidence": [],
        "missing_facts": [],
        "findings": [],
        "limitations": [],
        "algorithm_version": ALGORITHM_VERSION,
        "policy_version": None,
        "measurement_boundary": MEASUREMENT_BOUNDARY,
        "hardware_verified": False,
        "sound_checked": False,
        "live_fm9": False,
    }


def _db(value: float, *, floor: float = -160.0) -> float:
    if value <= 0.0:
        return floor
    return max(floor, 10.0 * math.log10(value))


def _mono(data):
    return data.mean(axis=1)


def _full_cross_correlation(left, right):
    """Return ``correlate(left, right, 'full')`` without quadratic work."""

    np = _np()
    output_length = len(left) + len(right) - 1
    fft_length = 1 << (output_length - 1).bit_length()
    circular = np.fft.irfft(
        np.fft.rfft(left, fft_length) * np.conj(np.fft.rfft(right, fft_length)),
        fft_length,
    )
    return np.concatenate((circular[-(len(right) - 1) :], circular[: len(left)]))


def analyze_frequency_balance(
    samples: Sequence[float],
    sample_rate: int,
    *,
    baseline: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    source: str = "local_fixture",
) -> dict[str, Any]:
    """Report named-band energy and spectral centroid.

    ``policy`` must name itself and supply a ``bands`` mapping.  Alternatively,
    a prior report may be supplied as ``baseline``.  Without either comparator,
    the measurements remain descriptive and the status is ``unknown``.
    """

    _validate_sample_rate(sample_rate)
    np = _np()
    data = _audio(samples)
    mono = _mono(data)
    report = _base_report("frequency_balance")
    report["coverage"] = {
        "frames": int(data.shape[0]),
        "channels": int(data.shape[1]),
        "sample_rate_hz": int(sample_rate),
        "duration_seconds": data.shape[0] / float(sample_rate),
    }
    report["evidence"].append({"source": source, "method": "Hann-windowed one-sided power spectrum"})
    if _reject_dc_offset(report, data, scope="frequency_balance"):
        return report
    rms = float(np.sqrt(np.mean(mono * mono)))
    if rms < 1e-8:
        report["missing_facts"].append("finite excited audio")
        report["limitations"].append("Silence or near-silence cannot establish frequency balance.")
        return report

    windowed = mono * np.hanning(len(mono))
    spectrum = np.abs(np.fft.rfft(windowed)) ** 2
    frequencies = np.fft.rfftfreq(len(mono), 1.0 / sample_rate)
    usable = frequencies >= 20.0
    total = float(spectrum[usable].sum())
    if total <= 1e-20:
        report["missing_facts"].append("usable spectral excitation above 20 Hz")
        return report

    centroid = float((frequencies[usable] * spectrum[usable]).sum() / total)
    bands: dict[str, dict[str, Any]] = {}
    band_values: dict[str, float] = {}
    nyquist = sample_rate / 2.0
    for name, (low, high) in FREQUENCY_BANDS.items():
        upper = nyquist if high is None else min(high, nyquist)
        covered = upper > low
        mask = (frequencies >= low) & (frequencies < upper) if covered else np.zeros_like(frequencies, bool)
        energy = float(spectrum[mask].sum()) if covered else 0.0
        relative_db = _db(energy / total)
        bands[name] = {
            "range_hz": [low, high],
            "covered": bool(covered and mask.any()),
            "energy_fraction": energy / total,
            "db_relative_total": relative_db,
            "unit": "dB relative to covered spectral energy",
        }
        if bands[name]["covered"]:
            band_values[name] = relative_db

    report["values"] = {
        "bands": bands,
        "spectral_centroid": {
            "value": centroid,
            "unit": "Hz",
            "method": "power-weighted centroid over finite bins at or above 20 Hz",
        },
    }
    unsupported = [name for name, result in bands.items() if not result["covered"]]
    if unsupported:
        report["limitations"].append(f"Sample rate does not cover bands: {', '.join(unsupported)}.")

    if baseline is not None:
        base_bands = baseline.get("values", {}).get("bands", {})
        deltas: dict[str, float] = {}
        invalid_baseline = False
        if isinstance(base_bands, Mapping):
            for name, value in band_values.items():
                entry = base_bands.get(name)
                if not isinstance(entry, Mapping) or not entry.get("covered"):
                    continue
                baseline_value = entry.get("db_relative_total")
                if not _finite_number(baseline_value):
                    invalid_baseline = True
                    continue
                deltas[name] = value - float(baseline_value)
        report["comparison"] = {"baseline": baseline.get("baseline_id", "named_baseline"), "band_delta_db": deltas}
        if invalid_baseline:
            report["missing_facts"].append("finite numeric values for every overlapping baseline band")
        if not deltas:
            report["missing_facts"].append("overlapping baseline band coverage")
        elif not invalid_baseline:
            report["status"] = "verified"
    elif policy is not None and policy.get("id") and isinstance(policy.get("bands"), Mapping):
        report["policy_version"] = str(policy.get("version", "unversioned"))
        evaluated = {
            name: rule
            for name, rule in policy["bands"].items()
            if name in band_values
            and _finite_limit_rule(rule, "min_db", "max_db")
        }
        malformed = [
            name
            for name, rule in policy["bands"].items()
            if name in band_values
            and not _finite_limit_rule(rule, "min_db", "max_db")
        ]
        report["coverage"]["evaluated_policy_bands"] = sorted(evaluated)
        report["coverage"]["invalid_policy_bands"] = sorted(malformed)
        if malformed:
            report["missing_facts"].append(f"finite policy limits for bands: {', '.join(sorted(malformed))}")
        if not evaluated:
            report["missing_facts"].append("at least one covered band with an explicit policy limit")
            report["limitations"].append("An empty or unsupported policy cannot establish a pass.")
        elif not malformed:
            report["findings"] = evaluate_band_policy(band_values, evaluated)
            report["status"] = "concern" if report["findings"] else "verified"
    else:
        report["missing_facts"].append("explicit named baseline or frequency policy")
        report["limitations"].append("Named bands are descriptive evidence, not universal tone targets.")
    return report


def _biquad(signal, b: tuple[float, float, float], a: tuple[float, float, float]):
    np = _np()
    output = np.zeros_like(signal)
    for channel in range(signal.shape[1]):
        x1 = x2 = y1 = y2 = 0.0
        for index, x0 in enumerate(signal[:, channel]):
            y0 = b[0] * x0 + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
            output[index, channel] = y0
            x2, x1, y2, y1 = x1, float(x0), y1, float(y0)
    return output


def _integrated_lufs_48k(data) -> float | None:
    """BS.1770-style K weighting and absolute/relative block gating at 48 kHz."""

    np = _np()
    weighted = _biquad(
        data,
        (1.53512485958697, -2.69169618940638, 1.19839281085285),
        (1.0, -1.69065929318241, 0.73248077421585),
    )
    weighted = _biquad(
        weighted,
        (1.0, -2.0, 1.0),
        (1.0, -1.99004745483398, 0.99007225036621),
    )
    block, hop = 19_200, 4_800
    if len(weighted) < block:
        return None
    energies = np.asarray(
        [float(np.sum(np.mean(weighted[start : start + block] ** 2, axis=0))) for start in range(0, len(weighted) - block + 1, hop)]
    )
    with np.errstate(divide="ignore"):
        levels = -0.691 + 10.0 * np.log10(energies)
    absolute_mask = levels > -70.0
    absolute = energies[absolute_mask]
    if not len(absolute):
        return None
    preliminary = -0.691 + 10.0 * math.log10(float(absolute.mean()))
    # BS.1770's relative gate is applied to the set that already survived the
    # absolute gate.  Applying it to every block can accidentally re-admit very
    # quiet blocks when the preliminary loudness is close to -70 LUFS.
    relative = energies[absolute_mask & (levels > preliminary - 10.0)]
    if not len(relative):
        return None
    return -0.691 + 10.0 * math.log10(float(relative.mean()))


def analyze_loudness(
    samples: Sequence[float], sample_rate: int, *, source: str = "local_fixture"
) -> dict[str, Any]:
    _validate_sample_rate(sample_rate)
    np = _np()
    data = _audio(samples)
    report = _base_report("loudness")
    report["coverage"] = {
        "frames": int(data.shape[0]), "channels": int(data.shape[1]), "sample_rate_hz": int(sample_rate)
    }
    report["values"] = {"rms_dbfs": None, "integrated_lufs": None}
    report["evidence"].append({"source": source, "method": "BS.1770 K-weighted 400 ms blocks with absolute and relative gates"})
    if _reject_dc_offset(report, data, scope="loudness"):
        return report
    rms = float(np.sqrt(np.mean(data * data)))
    report["values"]["rms_dbfs"] = _db(rms * rms)
    if rms < 1e-8:
        report["status"] = "invalid"
        report["missing_facts"].append("non-silent audio")
        return report
    if sample_rate != 48_000:
        report["missing_facts"].append("48 kHz input required by the validated coefficient set")
        report["limitations"].append("Integrated loudness is withheld at other sample rates; RMS remains supporting evidence.")
        return report
    lufs = _integrated_lufs_48k(data)
    if lufs is None:
        report["missing_facts"].append("at least 400 ms above the absolute loudness gate")
        return report
    report["values"]["integrated_lufs"] = lufs
    report["status"] = "verified"
    return report


def compare_scene_loudness(
    captures: Mapping[str, Sequence[float]],
    sample_rate: int,
    *,
    roles: Mapping[str, str],
    baseline_scene: str,
    manifests: Mapping[str, Mapping[str, Any]],
    policy: SceneLoudnessPolicy | None = None,
) -> dict[str, Any]:
    """Compare scene loudness only under an identical controlled stimulus."""

    _validate_sample_rate(sample_rate)
    policy = policy or SceneLoudnessPolicy()
    report = _base_report("scene_loudness")
    report["policy_version"] = policy.version
    report["coverage"] = {"scenes": sorted(captures), "baseline_scene": baseline_scene}
    policy_numbers: list[Any] = [*policy.lead_target_lu, policy.lead_concern_above_lu]
    if policy.clean_target_lu is not None:
        policy_numbers.extend(policy.clean_target_lu)
    if not all(_finite_number(value) for value in policy_numbers):
        report["missing_facts"].append("finite numeric scene-loudness policy values")
        return report
    required_manifest = ("stimulus_id", "active_region", "pre_roll", "tail", "measurement_boundary")
    if baseline_scene not in captures or roles.get(baseline_scene, "").lower() != "rhythm":
        report["missing_facts"].append("named rhythm baseline capture")
        return report
    if any(scene not in manifests or any(key not in manifests[scene] for key in required_manifest) for scene in captures):
        report["missing_facts"].append("complete stimulus and measurement manifest for every scene")
        return report
    signatures = {tuple(repr(manifests[scene][key]) for key in required_manifest) for scene in captures}
    if len(signatures) != 1:
        report["missing_facts"].append("identical stimulus, active region, pre-roll, tail, and boundary")
        report["limitations"].append("Different performances or measurement windows are not comparable.")
        return report

    sliced_captures: dict[str, Any] = {}
    for scene, audio in captures.items():
        region = manifests[scene]["active_region"]
        if (
            not isinstance(region, (list, tuple))
            or len(region) != 2
            or not all(isinstance(value, int) and not isinstance(value, bool) for value in region)
            or region[0] < 0
            or region[1] <= region[0]
            or region[1] > len(audio)
        ):
            report["missing_facts"].append(f"valid in-bounds active_region for {scene}")
            return report
        if region[1] - region[0] < 32:
            report["missing_facts"].append(f"active_region with at least 32 frames for {scene}")
            report["limitations"].append("The declared active region is too short for an audio measurement.")
            return report
        # Pre-roll and tail are deliberately excluded from the measurement.
        # Their declared policies are still part of the equality signature
        # above, preventing captures with different boundaries being compared.
        sliced_captures[scene] = audio[region[0] : region[1]]
    report["coverage"]["active_region"] = list(manifests[baseline_scene]["active_region"])
    report["coverage"]["pre_roll_policy"] = manifests[baseline_scene]["pre_roll"]
    report["coverage"]["tail_policy"] = manifests[baseline_scene]["tail"]
    metrics = {
        scene: analyze_loudness(audio, sample_rate, source=f"scene:{scene}:active_region")
        for scene, audio in sliced_captures.items()
    }
    report["scene_metrics"] = metrics
    invalid_scenes = sorted(scene for scene, item in metrics.items() if item["status"] == "invalid")
    if invalid_scenes:
        report["status"] = "invalid"
        report["missing_facts"].append(f"valid active-region audio for scenes: {', '.join(invalid_scenes)}")
        report["findings"].append(
            {"kind": "invalid_scene_capture", "severity": "invalid", "scenes": invalid_scenes}
        )
        return report
    if any(item["values"].get("integrated_lufs") is None for item in metrics.values()):
        report["missing_facts"].append("validated integrated loudness for every scene")
        return report
    baseline_lufs = metrics[baseline_scene]["values"]["integrated_lufs"]
    relationships: dict[str, Any] = {}
    unknown = False
    concern = False
    for scene, item in metrics.items():
        role = roles.get(scene)
        target = policy.target_for_role(role or "")
        delta = item["values"]["integrated_lufs"] - baseline_lufs
        relation = {"role": role, "delta_lu": delta, "target_lu": list(target) if target else None, "status": "unknown"}
        if role is None or target is None:
            unknown = True
            relation["missing_fact"] = "explicit scene role/relationship"
        elif role.lower() == "lead" and delta > policy.lead_concern_above_lu:
            concern = True
            relation["status"] = "concern"
            relation["finding"] = f"Lead is {delta:.2f} LU above the named rhythm baseline."
        elif target[0] <= delta <= target[1]:
            relation["status"] = "verified"
        else:
            concern = True
            relation["status"] = "concern"
        relationships[scene] = relation
    report["relationships"] = relationships
    report["status"] = "unknown" if unknown else ("concern" if concern else "verified")
    if unknown:
        report["missing_facts"].append("explicit role-relative target for every scene")
    return report


def analyze_stereo_dynamics(
    samples: Sequence[float],
    sample_rate: int,
    *,
    source: str = "local_fixture",
    baseline: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_sample_rate(sample_rate)
    np = _np()
    data = _audio(samples)
    report = _base_report("stereo_and_dynamics")
    report["coverage"] = {
        "frames": int(data.shape[0]), "channels": int(data.shape[1]), "sample_rate_hz": int(sample_rate)
    }
    report["evidence"].append({"source": source, "method": "sample energy, windowed RMS, correlation, and cross-correlation"})
    if _reject_dc_offset(report, data, scope="stereo_and_dynamics"):
        report["stereo"] = {"status": "invalid", "reason": "Capture contains DC offset above the technical-defect threshold."}
        return report

    peak = float(np.max(np.abs(data)))
    rms = float(np.sqrt(np.mean(data * data)))
    short_calibration = data.shape[0] / float(sample_rate) < 60.0
    report["dynamics"] = {
        "peak_dbfs": 20.0 * math.log10(max(peak, 1e-8)),
        "rms_dbfs": 20.0 * math.log10(max(rms, 1e-8)),
        "crest_factor_db": 20.0 * math.log10(max(peak, 1e-8) / max(rms, 1e-8)),
        "short_term_spread_db": None,
        "loudness_range_lu": None,
        "loudness_range_status": "not_applicable" if short_calibration else "unknown",
        "loudness_range_reason": (
            "Standards-style LRA is not claimed for short calibration material."
            if short_calibration
            else "LRA was not calculated by this offline metrics version."
        ),
    }
    if rms < 1e-8:
        report["status"] = "invalid"
        report["missing_facts"].append("non-silent audio")
        report["stereo"] = {"status": "invalid"}
        return report

    window = max(1, int(round(0.4 * sample_rate)))
    hop = max(1, int(round(0.1 * sample_rate)))
    levels = []
    for start in range(0, max(1, len(data) - window + 1), hop):
        chunk = data[start : start + window]
        if len(chunk):
            levels.append(20.0 * math.log10(max(float(np.sqrt(np.mean(chunk * chunk))), 1e-8)))
    if levels:
        report["dynamics"]["short_term_spread_db"] = float(np.percentile(levels, 95) - np.percentile(levels, 10))

    if data.shape[1] == 1:
        report["stereo"] = {"status": "not_applicable", "reason": "Mono input has no inter-channel stereo evidence."}
        report["missing_facts"].append("stereo baseline or named stereo/dynamics policy")
        return report

    left, right = data[:, 0], data[:, 1]
    left_rms = float(np.sqrt(np.mean(left * left)))
    right_rms = float(np.sqrt(np.mean(right * right)))
    if min(left_rms, right_rms) < 1e-8:
        report["status"] = "invalid"
        report["stereo"] = {"status": "invalid", "reason": "A stereo channel is silent or dead."}
        report["missing_facts"].append("two active channels")
        return report
    centered_l, centered_r = left - left.mean(), right - right.mean()
    if float(np.sqrt(np.mean(centered_l * centered_l))) < 1e-8 or float(np.sqrt(np.mean(centered_r * centered_r))) < 1e-8:
        report["status"] = "invalid"
        report["stereo"] = {"status": "invalid", "reason": "A channel contains DC but no usable varying signal."}
        report["missing_facts"].append("finite non-DC signal in both channels")
        return report
    correlation = float(np.corrcoef(centered_l, centered_r)[0, 1])
    if not math.isfinite(correlation):
        report["status"] = "invalid"
        report["stereo"] = {"status": "invalid", "reason": "Inter-channel correlation is non-finite."}
        report["missing_facts"].append("finite inter-channel correlation")
        return report
    mid, side = (left + right) / 2.0, (left - right) / 2.0
    mid_energy, side_energy = float(np.mean(mid * mid)), float(np.mean(side * side))
    mono_rms = float(np.sqrt(np.mean(mid * mid)))
    stereo_reference = math.sqrt((left_rms * left_rms + right_rms * right_rms) / 2.0)
    max_lag = min(len(left) - 1, int(round(0.05 * sample_rate)))
    corr = _full_cross_correlation(centered_l, centered_r)
    center = len(left) - 1
    restricted = corr[center - max_lag : center + max_lag + 1]
    delay_samples = int(np.argmax(np.abs(restricted)) - max_lag)
    report["stereo"] = {
        "status": "measured",
        "correlation": correlation,
        "mid_side_energy_ratio_db": _db(mid_energy / max(side_energy, 1e-16)),
        "left_level_dbfs": 20.0 * math.log10(left_rms),
        "right_level_dbfs": 20.0 * math.log10(right_rms),
        "inter_channel_level_delta_db": 20.0 * math.log10(left_rms / right_rms),
        "inter_channel_delay_samples": delay_samples,
        "inter_channel_delay_ms": delay_samples * 1000.0 / sample_rate,
        "mono_fold_down_loss_db": 20.0 * math.log10(max(mono_rms, 1e-8) / max(stereo_reference, 1e-8)),
    }
    report["limitations"].append("Stereo width is descriptive; wider is not better without an explicit baseline.")
    comparable_values = {
        "correlation": report["stereo"]["correlation"],
        "mid_side_energy_ratio_db": report["stereo"]["mid_side_energy_ratio_db"],
        "inter_channel_level_delta_db": report["stereo"]["inter_channel_level_delta_db"],
        "inter_channel_delay_ms": report["stereo"]["inter_channel_delay_ms"],
        "mono_fold_down_loss_db": report["stereo"]["mono_fold_down_loss_db"],
        "peak_dbfs": report["dynamics"]["peak_dbfs"],
        "rms_dbfs": report["dynamics"]["rms_dbfs"],
        "crest_factor_db": report["dynamics"]["crest_factor_db"],
        "short_term_spread_db": report["dynamics"]["short_term_spread_db"],
    }
    if baseline is not None:
        baseline_values = {
            **baseline.get("stereo", {}),
            **baseline.get("dynamics", {}),
        }
        deltas: dict[str, float] = {}
        invalid_baseline = False
        for name, value in comparable_values.items():
            if value is None or name not in baseline_values:
                continue
            if not _finite_number(baseline_values[name]):
                invalid_baseline = True
                continue
            deltas[name] = value - float(baseline_values[name])
        report["comparison"] = {"baseline": baseline.get("baseline_id", "named_baseline"), "metric_deltas": deltas}
        if invalid_baseline:
            report["missing_facts"].append("finite numeric values for every overlapping baseline metric")
        if deltas and not invalid_baseline:
            report["status"] = "verified"
        elif not deltas:
            report["missing_facts"].append("overlapping finite stereo/dynamics baseline metrics")
    elif policy is not None and policy.get("id") and isinstance(policy.get("metrics"), Mapping):
        evaluated = {
            name: rule
            for name, rule in policy["metrics"].items()
            if name in comparable_values
            and comparable_values[name] is not None
            and _finite_limit_rule(rule, "min", "max")
        }
        malformed = [
            name
            for name, rule in policy["metrics"].items()
            if name in comparable_values
            and not _finite_limit_rule(rule, "min", "max")
        ]
        report["policy_version"] = str(policy.get("version", "unversioned"))
        report["coverage"]["evaluated_policy_metrics"] = sorted(evaluated)
        report["coverage"]["invalid_policy_metrics"] = sorted(malformed)
        for name, rule in evaluated.items():
            value = float(comparable_values[name])
            if rule.get("min") is not None and value < float(rule["min"]):
                report["findings"].append({"metric": name, "direction": "below", "value": value, "limit": float(rule["min"])})
            if rule.get("max") is not None and value > float(rule["max"]):
                report["findings"].append({"metric": name, "direction": "above", "value": value, "limit": float(rule["max"])})
        if malformed:
            report["missing_facts"].append(f"finite policy limits for metrics: {', '.join(sorted(malformed))}")
        if evaluated and not malformed:
            report["status"] = "concern" if report["findings"] else "verified"
        elif not evaluated:
            report["missing_facts"].append("at least one covered metric with an explicit policy limit")
    else:
        report["missing_facts"].append("explicit named baseline or stereo/dynamics policy")
    return report


# Compact public aliases for callers that name the measurement rather than the report.
frequency_balance = analyze_frequency_balance
loudness = analyze_loudness
scene_loudness = compare_scene_loudness
stereo_dynamics = analyze_stereo_dynamics

import math

import numpy as np
import pytest

from fm9.audio_metrics import (
    DC_OFFSET_MAX_ABS,
    analyze_frequency_balance,
    analyze_loudness,
    analyze_stereo_dynamics,
    compare_scene_loudness,
)
from fm9.sound_policy import SceneLoudnessPolicy


RATE = 48_000


def tone(frequency, *, seconds=1.0, amplitude=0.1):
    time = np.arange(int(RATE * seconds)) / RATE
    return amplitude * np.sin(2 * np.pi * frequency * time)


def assert_fixture_boundary(report):
    assert report["hardware_verified"] is False
    assert report["sound_checked"] is False
    assert report["live_fm9"] is False
    assert report["algorithm_version"]
    assert "coverage" in report
    assert "missing_facts" in report


def test_frequency_balance_reports_named_bands_and_policy_status():
    audio = tone(80, amplitude=0.03) + tone(300, amplitude=0.05) + tone(2_000, amplitude=0.1)
    report = analyze_frequency_balance(
        audio,
        RATE,
        policy={
            "id": "fixture-presence-limit",
            "version": "fixture/1",
            "bands": {"presence": {"max_db": -3.0}},
        },
    )

    assert set(report["values"]["bands"]) == {
        "low_end",
        "body",
        "presence",
        "upper_bite",
        "fizz_potential",
        "air_noise",
    }
    assert report["values"]["spectral_centroid"]["unit"] == "Hz"
    assert report["status"] == "concern"
    assert report["findings"][0]["band"] == "presence"
    assert report["policy_version"] == "fixture/1"
    assert_fixture_boundary(report)


def test_frequency_balance_without_baseline_is_truthfully_unknown():
    report = analyze_frequency_balance(tone(300), RATE)
    assert report["status"] == "unknown"
    assert "explicit named baseline or frequency policy" in report["missing_facts"]


def test_frequency_balance_silence_cannot_pass():
    report = analyze_frequency_balance(np.zeros(RATE), RATE, policy={"id": "anything", "bands": {}})
    assert report["status"] == "unknown"
    assert report["values"] if "values" in report else True
    assert "finite excited audio" in report["missing_facts"]


def test_frequency_balance_empty_or_unsupported_policy_cannot_pass():
    audio = tone(2_000)
    empty = analyze_frequency_balance(audio, RATE, policy={"id": "empty", "version": "1", "bands": {}})
    unsupported = analyze_frequency_balance(
        audio,
        RATE,
        policy={"id": "wrong-band", "version": "1", "bands": {"ultrasound": {"max_db": -3}}},
    )
    for report in (empty, unsupported):
        assert report["status"] == "unknown"
        assert report["coverage"]["evaluated_policy_bands"] == []
        assert "at least one covered band with an explicit policy limit" in report["missing_facts"]


def test_frequency_and_loudness_reject_per_channel_dc_before_measurement():
    signal = tone(997, amplitude=0.01)
    cancelling_stereo = np.column_stack((0.5 + signal, -0.5 + signal))
    frequency = analyze_frequency_balance(
        cancelling_stereo,
        RATE,
        policy={"id": "would-pass", "bands": {"presence": {"max_db": 1.0}}},
    )
    loudness = analyze_loudness(0.5 + signal, RATE)
    for report in (frequency, loudness):
        assert report["status"] == "invalid"
        assert report["technical_defects"][0]["kind"] == "dc_offset"
        assert report["hardware_verified"] is False
    assert "values" not in frequency
    assert loudness["values"] == {"rms_dbfs": None, "integrated_lufs": None}


def test_integrated_loudness_and_rms_are_reported_for_48k_audio():
    report = analyze_loudness(tone(997, amplitude=0.1), RATE)
    assert report["status"] == "verified"
    assert math.isfinite(report["values"]["integrated_lufs"])
    assert report["values"]["rms_dbfs"] == pytest_approx(-23.0103, abs=0.03)
    assert_fixture_boundary(report)


def test_integrated_loudness_matches_bs1770_golden_sine_fixture():
    # Analytic -23 dBFS peak, 1 kHz sine.  The expected gated value was
    # established with the BS.1770 48 kHz coefficient/gating reference path.
    time = np.arange(RATE * 2) / RATE
    fixture = (10 ** (-23.0 / 20.0)) * np.sin(2 * np.pi * 1_000 * time)
    report = analyze_loudness(fixture, RATE)
    assert report["values"]["integrated_lufs"] == pytest_approx(-26.004, abs=0.03)


def pytest_approx(value, **kwargs):
    # Keeps pytest out of the product module while retaining readable assertions.
    import pytest

    return pytest.approx(value, **kwargs)


def test_scene_loudness_uses_rhythm_baseline_and_unknowns():
    rhythm_active = tone(997, amplitude=0.08)
    lead_active = rhythm_active * (10 ** (2.5 / 20.0))
    pre_roll = np.zeros(RATE // 10)
    # Deliberately different tails prove that only the declared active region
    # contributes to the comparison.
    rhythm = np.concatenate((pre_roll, rhythm_active, tone(200, seconds=0.1, amplitude=0.01)))
    lead = np.concatenate((pre_roll, lead_active, tone(200, seconds=0.1, amplitude=0.9)))
    clean = np.concatenate((pre_roll, rhythm_active, tone(200, seconds=0.1, amplitude=0.3)))
    captures = {"scene_1": rhythm, "scene_2": lead, "scene_3": clean}
    common = {
        "stimulus_id": "same-di-sha256",
        "active_region": [RATE // 10, RATE // 10 + RATE],
        "pre_roll": {"frames": RATE // 10, "excluded": True},
        "tail": {"frames": RATE // 10, "excluded": True},
        "measurement_boundary": "local_audio_fixture",
    }
    manifests = {scene: dict(common) for scene in captures}
    report = compare_scene_loudness(
        captures,
        RATE,
        roles={"scene_1": "rhythm", "scene_2": "lead", "scene_3": "clean"},
        baseline_scene="scene_1",
        manifests=manifests,
        policy=SceneLoudnessPolicy(clean_target_lu=(-0.5, 0.5)),
    )

    assert report["status"] == "verified"
    assert report["relationships"]["scene_2"]["delta_lu"] == pytest_approx(2.5, abs=0.03)
    assert report["relationships"]["scene_2"]["target_lu"] == [2.0, 3.0]
    assert_fixture_boundary(report)

    manifests["scene_2"] = {**common, "stimulus_id": "different-performance"}
    unknown = compare_scene_loudness(
        captures,
        RATE,
        roles={"scene_1": "rhythm", "scene_2": "lead", "scene_3": "clean"},
        baseline_scene="scene_1",
        manifests=manifests,
    )
    assert unknown["status"] == "unknown"
    assert "identical stimulus, active region, pre-roll, tail, and boundary" in unknown["missing_facts"]


def test_scene_loudness_missing_role_is_unknown_and_large_lead_is_concern():
    rhythm = tone(997, amplitude=0.05)
    captures = {"rhythm": rhythm, "lead": rhythm * (10 ** (4.5 / 20)), "mystery": rhythm}
    common = {
        "stimulus_id": "same",
        "active_region": [0, RATE],
        "pre_roll": 0,
        "tail": 0,
        "measurement_boundary": "local_audio_fixture",
    }
    report = compare_scene_loudness(
        captures,
        RATE,
        roles={"rhythm": "rhythm", "lead": "lead"},
        baseline_scene="rhythm",
        manifests={scene: dict(common) for scene in captures},
    )
    assert report["status"] == "unknown"
    assert report["relationships"]["lead"]["status"] == "concern"
    assert report["relationships"]["mystery"]["status"] == "unknown"


def test_scene_loudness_structures_short_regions_and_dc_contamination():
    rhythm = tone(997, amplitude=0.05)
    common = {
        "stimulus_id": "same",
        "active_region": [0, 16],
        "pre_roll": 0,
        "tail": 0,
        "measurement_boundary": "local_audio_fixture",
    }
    short = compare_scene_loudness(
        {"rhythm": rhythm, "lead": rhythm},
        RATE,
        roles={"rhythm": "rhythm", "lead": "lead"},
        baseline_scene="rhythm",
        manifests={"rhythm": dict(common), "lead": dict(common)},
    )
    assert short["status"] == "unknown"
    assert "active_region with at least 32 frames for rhythm" in short["missing_facts"]

    full = {**common, "active_region": [0, RATE]}
    dc = compare_scene_loudness(
        {"rhythm": rhythm, "lead": rhythm + 0.5},
        RATE,
        roles={"rhythm": "rhythm", "lead": "lead"},
        baseline_scene="rhythm",
        manifests={"rhythm": dict(full), "lead": dict(full)},
    )
    assert dc["status"] == "invalid"
    assert dc["scene_metrics"]["lead"]["technical_defects"][0]["kind"] == "dc_offset"
    assert dc["findings"][0]["kind"] == "invalid_scene_capture"


def test_stereo_and_dynamics_metrics_are_coverage_aware():
    left = tone(997, amplitude=0.1)
    right = np.roll(left, 12) * 0.8
    report = analyze_stereo_dynamics(
        np.column_stack((left, right)),
        RATE,
        policy={
            "id": "fixture-stereo-safety",
            "version": "fixture/1",
            "metrics": {"correlation": {"min": 0.0}, "mono_fold_down_loss_db": {"min": -3.0}},
        },
    )

    assert report["status"] == "verified"
    assert set(report["stereo"]) >= {
        "correlation",
        "mid_side_energy_ratio_db",
        "inter_channel_level_delta_db",
        "inter_channel_delay_samples",
        "mono_fold_down_loss_db",
    }
    assert set(report["dynamics"]) >= {
        "peak_dbfs",
        "rms_dbfs",
        "crest_factor_db",
        "short_term_spread_db",
    }
    assert report["dynamics"]["loudness_range_status"] == "not_applicable"
    assert_fixture_boundary(report)

    mono = analyze_stereo_dynamics(left, RATE)
    assert mono["status"] == "unknown"
    assert mono["stereo"]["status"] == "not_applicable"

    dead_right = analyze_stereo_dynamics(np.column_stack((left, np.zeros_like(left))), RATE)
    assert dead_right["status"] == "invalid"
    assert "two active channels" in dead_right["missing_facts"]


def test_stereo_without_policy_is_descriptive_and_dc_is_invalid():
    left = tone(997, amplitude=0.1)
    descriptive = analyze_stereo_dynamics(np.column_stack((left, left)), RATE)
    assert descriptive["status"] == "unknown"
    assert descriptive["stereo"]["status"] == "measured"
    assert "explicit named baseline or stereo/dynamics policy" in descriptive["missing_facts"]

    dc = analyze_stereo_dynamics(np.full((RATE, 2), 0.1), RATE)
    assert dc["status"] == "invalid"
    assert dc["technical_defects"][0]["kind"] == "dc_offset"


def test_dc_offset_threshold_invalidates_stereo_and_mono_before_dynamics():
    signal = tone(997, amplitude=0.01)
    stereo = analyze_stereo_dynamics(np.column_stack((0.5 + signal, 0.5 + signal)), RATE)
    mono = analyze_stereo_dynamics(0.5 + signal, RATE)
    for report in (stereo, mono):
        assert report["status"] == "invalid"
        assert report["technical_defects"][0]["kind"] == "dc_offset"
        assert report["technical_defects"][0]["threshold_full_scale"] == DC_OFFSET_MAX_ABS
        assert "dynamics" not in report
        assert report["findings"][0]["severity"] == "invalid"

    below_threshold = analyze_stereo_dynamics(0.009 + signal, RATE)
    assert below_threshold["status"] == "unknown"
    assert "technical_defects" not in below_threshold


def test_lra_is_only_not_applicable_for_short_calibration_audio():
    short = analyze_stereo_dynamics(np.ones(5_000) * np.sin(np.arange(5_000)), 100)
    long = analyze_stereo_dynamics(np.ones(6_100) * np.sin(np.arange(6_100)), 100)
    assert short["dynamics"]["loudness_range_status"] == "not_applicable"
    assert long["dynamics"]["loudness_range_status"] == "unknown"


def test_nonfinite_policy_and_baseline_values_never_verify():
    audio = tone(2_000)
    bad_frequency_policy = analyze_frequency_balance(
        audio,
        RATE,
        policy={"id": "bad", "bands": {"presence": {"max_db": float("nan")}}},
    )
    assert bad_frequency_policy["status"] == "unknown"
    assert bad_frequency_policy["coverage"]["evaluated_policy_bands"] == []

    baseline = analyze_frequency_balance(audio, RATE, policy={"id": "ok", "bands": {"presence": {"max_db": 1}}})
    baseline["values"]["bands"]["presence"]["db_relative_total"] = float("inf")
    bad_frequency_baseline = analyze_frequency_balance(audio, RATE, baseline=baseline)
    assert bad_frequency_baseline["status"] == "unknown"
    assert all(math.isfinite(value) for value in bad_frequency_baseline["comparison"]["band_delta_db"].values())

    stereo = np.column_stack((tone(997, amplitude=0.1), tone(997, amplitude=0.08)))
    bad_stereo_policy = analyze_stereo_dynamics(
        stereo,
        RATE,
        policy={"id": "bad", "metrics": {"correlation": {"min": float("-inf")}}},
    )
    assert bad_stereo_policy["status"] == "unknown"
    assert bad_stereo_policy["coverage"]["evaluated_policy_metrics"] == []

    bad_stereo_baseline = analyze_stereo_dynamics(
        stereo,
        RATE,
        baseline={"baseline_id": "bad", "stereo": {"correlation": float("nan")}},
    )
    assert bad_stereo_baseline["status"] == "unknown"
    assert bad_stereo_baseline["comparison"]["metric_deltas"] == {}

    common = {
        "stimulus_id": "same",
        "active_region": [0, RATE],
        "pre_roll": 0,
        "tail": 0,
        "measurement_boundary": "local_audio_fixture",
    }
    bad_scene_policy = compare_scene_loudness(
        {"rhythm": audio, "lead": audio},
        RATE,
        roles={"rhythm": "rhythm", "lead": "lead"},
        baseline_scene="rhythm",
        manifests={"rhythm": dict(common), "lead": dict(common)},
        policy=SceneLoudnessPolicy(lead_target_lu=(2.0, float("inf"))),
    )
    assert bad_scene_policy["status"] == "unknown"
    assert "finite numeric scene-loudness policy values" in bad_scene_policy["missing_facts"]


@pytest.mark.parametrize("bad_rule", [None, {}, "not-a-rule", {"max_db": "loud"}, {"max_db": float("nan")}, {"max_db": float("inf")}])
def test_any_malformed_applicable_frequency_rule_blocks_verified(bad_rule):
    report = analyze_frequency_balance(
        tone(2_000),
        RATE,
        policy={
            "id": "mixed",
            "bands": {
                "presence": {"max_db": 1.0},
                "body": bad_rule,
            },
        },
    )
    assert report["status"] == "unknown"
    assert report["coverage"]["evaluated_policy_bands"] == ["presence"]
    assert report["coverage"]["invalid_policy_bands"] == ["body"]
    assert "finite policy limits for bands: body" in report["missing_facts"]


@pytest.mark.parametrize("bad_rule", [None, {}, "not-a-rule", {"max": "wide"}, {"max": float("nan")}, {"max": float("inf")}])
def test_any_malformed_applicable_stereo_rule_blocks_verified(bad_rule):
    signal = tone(997, amplitude=0.1)
    report = analyze_stereo_dynamics(
        np.column_stack((signal, signal * 0.9)),
        RATE,
        policy={
            "id": "mixed",
            "metrics": {
                "correlation": {"min": 0.5},
                "crest_factor_db": bad_rule,
            },
        },
    )
    assert report["status"] == "unknown"
    assert report["coverage"]["evaluated_policy_metrics"] == ["correlation"]
    assert report["coverage"]["invalid_policy_metrics"] == ["crest_factor_db"]
    assert "finite policy limits for metrics: crest_factor_db" in report["missing_facts"]


@pytest.mark.parametrize("sample_rate", [0, -48_000])
def test_all_public_audio_metrics_reject_nonpositive_sample_rates(sample_rate):
    audio = np.ones(64) * 0.01
    calls = (
        lambda: analyze_frequency_balance(audio, sample_rate),
        lambda: analyze_loudness(audio, sample_rate),
        lambda: analyze_stereo_dynamics(audio, sample_rate),
        lambda: compare_scene_loudness(
            {}, sample_rate, roles={}, baseline_scene="rhythm", manifests={}
        ),
    )
    for call in calls:
        with pytest.raises(ValueError, match="sample_rate must be a positive integer"):
            call()

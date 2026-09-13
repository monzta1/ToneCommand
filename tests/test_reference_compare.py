import numpy as np
import pytest

from fm9.reference_compare import REFERENCE_QUALITY, compare_reference


RATE = 48_000


def tone(frequency, amplitude):
    time = np.arange(RATE) / RATE
    return amplitude * np.sin(2 * np.pi * frequency * time)


def control_map():
    return {
        "low_end": {"block": "PEQ 1", "parameter": "Band 1 Gain"},
        "body": {"block": "PEQ 1", "parameter": "Band 2 Gain"},
        "presence": {"block": "PEQ 1", "parameter": "Band 3 Gain"},
        "upper_bite": {"block": "PEQ 1", "parameter": "Band 4 Gain"},
        "fizz_potential": {"block": "PEQ 1", "parameter": "Band 5 Gain"},
        "air_noise": {"block": "PEQ 1", "parameter": "Band 5 Gain"},
    }


def clips():
    reference = tone(300, 0.10) + tone(2_000, 0.025)
    subject = tone(300, 0.025) + tone(2_000, 0.10)
    return subject, reference


def assert_never_send(report):
    assert report["sent"] is False
    assert report["hardware_verified"] is False
    assert report["sound_checked"] is False
    assert report["live_fm9"] is False
    if report["proposal"]:
        assert report["proposal"]["requires_confirmation"] is True
        assert report["proposal"]["sent"] is False


def test_local_golden_reference_aligns_preserves_levels_and_offers_one_small_proposal():
    subject, reference = clips()
    subject = np.concatenate((np.zeros(24), subject[:-24]))
    report = compare_reference(
        subject,
        reference,
        RATE,
        reference_quality="golden_same_di",
        control_map=control_map(),
    )

    assert report["status"] == "verified"
    assert report["reference_quality"]["rank"] == 1
    assert report["raw_levels"]["subject_rms_dbfs"] != report["raw_levels"]["reference_rms_dbfs"]
    assert report["spectral_delta"]["normalization"].startswith("independent RMS")
    assert len(report["spectral_delta"]["band_delta_db"]) >= 4
    assert report["alignment"]["compared_frames"] > RATE - 100
    assert report["proposal"]["kind"] == "directional_eq"
    assert report["proposal"]["size"] == "small"
    assert_never_send(report)


def test_mastered_mix_is_broad_estimate_and_never_creates_action():
    subject, reference = clips()
    report = compare_reference(
        subject,
        reference,
        RATE,
        reference_quality="mastered_mix",
        control_map=control_map(),
    )
    assert report["reference_quality"] == {"id": "mastered_mix", **REFERENCE_QUALITY["mastered_mix"]}
    assert report["proposal"] is None
    assert any("broad estimate" in item for item in report["limitations"])
    assert_never_send(report)


def test_missing_or_ambiguous_control_map_produces_no_confirmable_action():
    subject, reference = clips()
    no_map = compare_reference(subject, reference, RATE, reference_quality="isolated_guitar")
    assert no_map["proposal"] is None
    assert any("unambiguous injected control" in fact for fact in no_map["missing_facts"])

    ambiguous = {band: [entry, dict(entry)] for band, entry in control_map().items()}
    result = compare_reference(
        subject,
        reference,
        RATE,
        reference_quality="solo_guitar_excerpt",
        control_map=ambiguous,
    )
    assert result["proposal"] is None
    assert_never_send(result)


def test_silence_or_unknown_quality_cannot_become_a_reference_claim():
    subject, reference = clips()
    silent = compare_reference(np.zeros_like(subject), reference, RATE, reference_quality="golden_same_di")
    assert silent["status"] == "unknown"
    assert silent["proposal"] is None

    import pytest

    with pytest.raises(ValueError, match="unknown reference_quality"):
        compare_reference(subject, reference, RATE, reference_quality="mystery")


def test_dc_only_reference_has_no_usable_spectral_evidence():
    subject, _ = clips()
    report = compare_reference(
        subject,
        np.full_like(subject, 0.1),
        RATE,
        reference_quality="golden_same_di",
        control_map=control_map(),
    )
    assert report["status"] == "invalid"
    assert report["proposal"] is None
    assert report["technical_defects"][0]["kind"] == "dc_offset"
    assert_never_send(report)


def test_dc_offset_plus_audio_is_invalid_not_silently_centered():
    subject, reference = clips()
    report = compare_reference(
        subject + 0.5,
        reference,
        RATE,
        reference_quality="golden_same_di",
        control_map=control_map(),
    )
    assert report["status"] == "invalid"
    assert report["proposal"] is None
    assert report["technical_defects"][0]["kind"] == "dc_offset"
    assert_never_send(report)

    # Opposite channel offsets cancel in a mono downmix but remain acquisition
    # defects, so validation must inspect channels before averaging.
    cancelling_stereo = np.column_stack((subject + 0.5, subject - 0.5))
    stereo_report = compare_reference(
        cancelling_stereo,
        reference,
        RATE,
        reference_quality="golden_same_di",
        control_map=control_map(),
    )
    assert stereo_report["status"] == "invalid"
    assert stereo_report["technical_defects"][0]["offsets_full_scale"]["subject"] == pytest.approx([0.5, -0.5])
    assert_never_send(stereo_report)


def test_reference_rejects_invalid_rates_and_nonfinite_thresholds():
    import pytest

    subject, reference = clips()
    for sample_rate in (0, -RATE):
        with pytest.raises(ValueError, match="sample_rate must be a positive integer"):
            compare_reference(subject, reference, sample_rate, reference_quality="golden_same_di")
    for threshold in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="proposal_threshold_db"):
            compare_reference(
                subject,
                reference,
                RATE,
                reference_quality="golden_same_di",
                proposal_threshold_db=threshold,
            )

"""Reference windows are bounded metadata, not listening or MIDI authority."""
from copy import deepcopy
import math
import pytest
from devices.axefx3.tone_ui import Measurements


def reading():
    return dict(sample_seconds=20.,rms_dbfs=-18.,peak_dbfs=-3.,crest_db=15.,
                centroid_hz=1800.,band_energy=[.2]*5)


def test_older_measurements_default_to_start_zero():
    m=Measurements.model_validate(reading())
    assert m.start_seconds==0 and m.source_seconds is None


def test_explicit_window_is_preserved_in_ai_evidence():
    m=Measurements.model_validate(dict(**reading(),start_seconds=30.,source_seconds=300.))
    result=m.model_dump()
    assert result['start_seconds']==30 and result['sample_seconds']==20
    assert result['source_seconds']==300


@pytest.mark.parametrize('patch',[{'start_seconds':-1},{'start_seconds':math.nan},
    {'start_seconds':math.inf},{'start_seconds':86401},{'source_seconds':0},
    {'source_seconds':86401},{'source_seconds':10},{'source_seconds':30,'start_seconds':20},
    {'sample_seconds':61},{'sample_seconds':0}])
def test_bad_or_out_of_source_window_is_rejected(patch):
    data=reading();data.update(patch)
    with pytest.raises(ValueError):Measurements.model_validate(data)


def test_v2_provenance_is_explicit_and_legacy_defaults_stay_compatible():
    assert Measurements.model_validate(reading()).analysis_method=='legacy-v1'
    data=dict(**reading(),analysis_method='channel-power-v2',analysis_rate_hz=16000,analysis_cutoff_hz=7000.,analysis_channels=2,analysis_frames=157)
    assert Measurements.model_validate(data).model_dump()['analysis_frames']==157


@pytest.mark.parametrize('patch',[
    {'analysis_method':'channel-power-v2'},
    {'analysis_method':'channel-power-v2','analysis_rate_hz':44100,'analysis_channels':2,'analysis_frames':10},
    {'analysis_method':'channel-power-v2','analysis_rate_hz':16000,'analysis_channels':0,'analysis_frames':10},
    {'analysis_method':'channel-power-v2','analysis_rate_hz':16000,'analysis_channels':9,'analysis_frames':10},
    {'analysis_method':'channel-power-v2','analysis_rate_hz':16000,'analysis_channels':2,'analysis_frames':513},
    {'analysis_method':'channel-power-v2','analysis_rate_hz':16000,'analysis_channels':True,'analysis_frames':10},
    {'analysis_method':'legacy-v1','analysis_rate_hz':16000},
    {'analysis_method':'unmeasured-v3'},
])
def test_invalid_or_mislabelled_provenance_is_rejected(patch):
    with pytest.raises(ValueError):Measurements.model_validate(dict(**reading(),**patch))


@pytest.mark.parametrize('patch',[
    {'analysis_rate_hz':44100},{'analysis_channels':0},{'analysis_channels':9},
    {'analysis_channels':True},{'analysis_frames':513},{'analysis_frames':0},
    {'analysis_cutoff_hz':8000.},{'analysis_cutoff_hz':None},{'analysis_cutoff_hz':math.nan},
    {'analysis_method':'legacy-v1'},
])
def test_individual_v2_provenance_fields_cannot_bypass_validation(patch):
    valid=dict(**reading(),analysis_method='channel-power-v2',analysis_rate_hz=16000,analysis_cutoff_hz=7000.,analysis_channels=2,analysis_frames=157)
    with pytest.raises(ValueError):Measurements.model_validate({**valid,**patch})

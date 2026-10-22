"""Comparison is descriptive, private numeric evidence with no unit authority."""
import math
import pytest
from devices.axefx3 import audio_measurements as audio


def reading(**patch):
    return dict(sample_seconds=1.,rms_dbfs=-18.,peak_dbfs=-3.,crest_db=15.,
        centroid_hz=440.,band_energy=[0.,1.,0.,0.,0.],analysis_method='channel-power-v2',
        analysis_rate_hz=16000,analysis_cutoff_hz=7000.,analysis_channels=1,
        analysis_frames=8,**patch)


def test_equal_metrics_are_not_a_sound_match_claim():
    result=audio.compare(audio.Comparison(reference=reading(),recording=reading()))
    assert result['differences']['rms_db']==0
    assert result['differences']['band_energy'][0]['relative_db'] is None
    assert result['differences']['band_energy'][1]['relative_db']==0
    for field in ('hardware_written','audible_match_verified','isolated_guitar_verified',
                  'performance_alignment_verified','unit_recording_verified'):
        assert result[field] is False
    assert 'score' not in result and 'actions' not in result


def test_differences_have_explicit_recording_minus_reference_direction():
    recording={**reading(),'rms_dbfs':-20.,'peak_dbfs':-5.,'centroid_hz':880.,
               'band_energy':[.25,.5,.25,0.,0.]}
    got=audio.compare(audio.Comparison(reference=reading(),recording=recording))['differences']
    assert got['rms_db']==-2 and got['peak_db']==-2 and got['crest_db']==0
    assert got['centroid_hz']==440
    assert got['band_energy'][1]['relative_db']==pytest.approx(10*math.log10(.5))
    assert got['band_energy'][1]['delta_fraction']==-.5


def test_private_evidence_drops_urls_and_local_names():
    data=reading(url='https://example.com/?token=private',file_name='personal.wav')
    evidence=audio.private_evidence(data)
    assert 'url' not in evidence and 'file_name' not in evidence
    result=audio.compare(audio.Comparison(reference=data,recording=data))
    assert 'private' not in str(result) and 'personal' not in str(result)


@pytest.mark.parametrize('patch',[
    {'rms_dbfs':0},{'crest_db':5},{'band_energy':[0.]*5},
    {'band_energy':[math.nan,1.,0.,0.,0.]},{'centroid_hz':9000},
])
def test_inconsistent_v2_metrics_refused(patch):
    with pytest.raises(ValueError):audio.Measurements.model_validate({**reading(),**patch})


def test_unlike_filters_legacy_and_silence_are_not_comparable():
    with pytest.raises(ValueError,match='cutoff'):
        audio.compare(audio.Comparison(reference=reading(),recording={**reading(),'analysis_cutoff_hz':6000.}))
    with pytest.raises(ValueError,match='silent'):
        audio.compare(audio.Comparison(reference=reading(),recording={**reading(),'rms_dbfs':-150.,'peak_dbfs':-135.}))
    legacy={k:v for k,v in reading().items() if not k.startswith('analysis_')}
    with pytest.raises(ValueError,match='again'):
        audio.compare(audio.Comparison(reference=legacy,recording=reading()))


def test_comparison_route_is_available_without_device_or_ai(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from devices.axefx3 import tone_ui
    app=FastAPI()
    tone_ui.register(app,SimpleNamespace(device_context=lambda:pytest.fail('Comparison reached a device')))
    client=TestClient(app)
    got=client.post('/api/axefx3/audio/compare',json=dict(reference=reading(),recording=reading()))
    assert got.status_code==200 and got.json()['hardware_written'] is False

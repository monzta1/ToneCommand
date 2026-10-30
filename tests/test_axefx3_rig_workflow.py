"""Rig source passes through the existing FX3-only review, never FM9 SEND."""
import pytest
from devices.axefx3 import rig_source
from tests.test_axefx3_nam_workflow import api, dev, design, BODY
from tests.test_axefx3_rig_source import source


def test_rig_source_uses_existing_review_and_no_automatic_send(api,dev,monkeypatch):
    client,ask=api
    assert client.get('/api/axefx3/state').json()['source_support']['rig_reader']
    monkeypatch.setattr(rig_source,'read',lambda prompt:source())
    result=client.post('/api/axefx3/plan',json={**BODY,'source_kind':'rig'})
    assert result.status_code==200,result.text
    data=result.json()
    assert data['token'] and data['rig_report']['planned_route']==data['required_route']
    assert data['source']['spec']['found']
    assert 'SOURCE EVIDENCE' in ask.call_args.args[0]
    assert data['mode']=='nam' and data['target']['preset']==133
    dev.set_param_display.assert_not_called()
    dev.install_nam_slot.assert_not_called();dev.store_preset.assert_not_called()


def test_rig_link_not_required_to_have_audio_measurements(api,dev,monkeypatch):
    client,_=api
    monkeypatch.setattr(rig_source,'read',lambda prompt:source())
    result=client.post('/api/axefx3/plan',json={**BODY,'prompt':'Bouw https://youtu.be/Plwb_gfmSc4','source_kind':'rig'})
    assert result.status_code==200,result.text
    dev._write.assert_not_called()


def test_faithful_unsupported_wah_stops_before_design(api,dev,monkeypatch):
    client,ask=api
    monkeypatch.setattr(rig_source,'read',lambda prompt:source(('instrument','wah','amp','cab')))
    result=client.post('/api/axefx3/plan',json={**BODY,'source_kind':'rig','rig_mode':'faithful'})
    assert result.status_code==409,result.text
    ask.assert_not_called();dev._write.assert_not_called()


def test_read_failure_releases_settings_and_planning_locks(api,dev,monkeypatch):
    client,ask=api
    def fail(prompt):raise ValueError('No explained rig')
    monkeypatch.setattr(rig_source,'read',fail)
    assert client.post('/api/axefx3/plan',json={**BODY,'source_kind':'rig'}).status_code==409
    ask.assert_not_called()
    assert client.post('/api/axefx3/plan',json=BODY).status_code==200
    dev.set_param_display.assert_not_called()


def test_tone_link_still_requires_measurements_and_cannot_silently_become_rig(api,monkeypatch):
    client,ask=api
    reader=[];monkeypatch.setattr(rig_source,'read',lambda prompt:reader.append(prompt))
    assert client.post('/api/axefx3/plan',json={**BODY,'prompt':'Bouw https://youtu.be/Plwb_gfmSc4'}).status_code==409
    assert not reader;ask.assert_not_called()

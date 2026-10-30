"""Synthetic route comparison is read-only, never capability promotion."""
from unittest.mock import Mock
import copy
import pytest
import server
from devices.axefx3 import route_options,fw33_profile,tone3000
from devices.axefx3.registry import Registry
from tests.test_axefx3_text_planning import api,dev,design

COMPARISON=dict(recommended='either',reason='Both can approximate warm crunch.',
    amp_direction='British crunch amp with a warm cab',nam_query='Whole Lotta Love',
    pedals=['short delay','room reverb'])


@pytest.mark.parametrize('firmware,variant,amp,nam',[
    ('32.06',None,True,False),(fw33_profile.KEY,'mk2',True,True),
    (fw33_profile.KEY,'mk1',False,False),('33.01','mk2',False,False)])
def test_capabilities_do_not_force_or_promote_nam(firmware,variant,amp,nam):
    reg=Registry(firmware);reg.hardware_variant=variant
    reg.import_cab_names('U1.0028 Test','user')
    choices=route_options.capabilities(reg)
    expected=dict(amp=amp,nam=nam)
    if firmware==fw33_profile.KEY and variant=='mk2':expected['serial']=True
    assert {x['mode']:x['enabled'] for x in choices}==expected
    assert choices[0]['label']==('AMP / CAB: 1-8 scenes with tone goals' if firmware==fw33_profile.KEY and variant=='mk2' else 'AMP / CAB + pedals')


def request(api,dev,monkeypatch):
    client,ask=api
    ask.side_effect=lambda *a,**k:dict(**k['validate'](copy.deepcopy(COMPARISON)),backend='cli',model='test')
    monkeypatch.setattr(tone3000.client,'status',lambda:dict(connected=True))
    search=Mock(return_value={'data':[dict(id=5132,title='Whole Lotta Love',gear='amp-cab')]})
    monkeypatch.setattr(tone3000.client,'search',search)
    return client,ask,search


def test_http_explores_both_and_searches_without_selection_or_write(api,dev,monkeypatch):
    client,ask,search=request(api,dev,monkeypatch)
    select=Mock();monkeypatch.setattr(tone3000.client,'select_tone',select)
    r=client.post('/api/axefx3/options',json=dict(prompt='Warm Whole Lotta Love blues rock',expected_preset=324))
    assert r.status_code==200,r.text
    result=r.json()
    assert result['readonly'] and not result['hardware_written']
    assert result['comparison']['recommended']=='either'
    assert result['nam_candidates'][0]['id']==5132
    assert [x['mode'] for x in result['routes']]==['amp','nam']
    search.assert_called_once_with('Whole Lotta Love');select.assert_not_called()
    dev._write.assert_not_called();dev.edit_session.assert_not_called();dev.install_nam_slot.assert_not_called()
    assert 'token' not in result and 'actions' not in result


def test_no_account_does_not_hide_amp_route(api,dev,monkeypatch):
    client,ask,search=request(api,dev,monkeypatch)
    monkeypatch.setattr(tone3000.client,'status',lambda:dict(connected=False))
    r=client.post('/api/axefx3/options',json=dict(prompt='Warm crunch',expected_preset=324))
    assert r.status_code==200
    assert r.json()['routes'][0]['enabled']
    assert not r.json()['nam_candidates'] and r.json()['nam_search_warning']
    search.assert_not_called()


def test_catalog_failure_keeps_comparison_without_claiming_capture(api,dev,monkeypatch):
    client,ask,search=request(api,dev,monkeypatch)
    search.side_effect=tone3000.ToneError('Catalog unavailable.',502)
    r=client.post('/api/axefx3/options',json=dict(prompt='Warm crunch',expected_preset=324))
    assert r.status_code==200 and not r.json()['nam_candidates']
    assert r.json()['nam_search_warning']=='Catalog unavailable.'


def test_empty_literal_search_reports_no_match_without_hiding_amp(api,dev,monkeypatch):
    client,ask,search=request(api,dev,monkeypatch)
    search.return_value={'data':[]}
    result=client.post('/api/axefx3/options',json=dict(prompt='Warm crunch',expected_preset=324)).json()
    assert result['routes'][0]['enabled'] and not result['nam_candidates']
    assert 'No catalog match' in result['nam_search_warning']
    assert 'literal text match' in ask.call_args.kwargs['system']
    dev._write.assert_not_called()


def test_wrong_target_and_unknown_ai_output_cannot_reach_writes(api,dev,monkeypatch):
    client,ask,_=request(api,dev,monkeypatch)
    body=dict(prompt='Warm crunch',expected_preset=325)
    assert client.post('/api/axefx3/options',json=body).status_code==409
    ask.assert_not_called()
    body['expected_preset']=324
    ask.side_effect=lambda *a,**k:k['validate'](dict(COMPARISON,actions=[{'kind':'store'}]))
    assert client.post('/api/axefx3/options',json=body).status_code==409
    dev._write.assert_not_called()


def test_changed_target_during_ai_declines_options(api,dev,monkeypatch):
    client,ask,_=request(api,dev,monkeypatch)
    dev.current_preset.side_effect=[(324,'Empty'),(325,'Other')]
    assert client.post('/api/axefx3/options',json=dict(prompt='Warm crunch',expected_preset=324)).status_code==409
    dev._write.assert_not_called()


def test_unanalysed_or_mismatched_link_refused_before_ai(api,dev,monkeypatch):
    client,ask,_=request(api,dev,monkeypatch)
    body=dict(prompt='Klank https://youtu.be/reference',expected_preset=324)
    assert client.post('/api/axefx3/options',json=body).status_code==409
    body['audio_reference']=dict(url='https://youtu.be/other',sample_seconds=2,rms_dbfs=-18,
        peak_dbfs=-3,crest_db=15,centroid_hz=1500,band_energy=[.2]*5)
    assert client.post('/api/axefx3/options',json=body).status_code==409
    body['source_kind']='rig'
    assert client.post('/api/axefx3/options',json=body).status_code==422
    ask.assert_not_called();dev._write.assert_not_called()
    del body['audio_reference']
    assert client.post('/api/axefx3/options',json=body).status_code==200


def test_firmware_change_during_exploration_refused(api,dev,monkeypatch):
    client,ask,_=request(api,dev,monkeypatch)
    dev.firmware_label.side_effect=['32.06','33.01']
    assert client.post('/api/axefx3/options',json=dict(prompt='Warm crunch',expected_preset=324)).status_code==409
    dev._write.assert_not_called()

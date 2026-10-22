"""Storage protection and reference intake must never bypass device verification."""
import json
import socket
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest

from devices.axefx3 import profile, tone_search, reference_audio, tone_ui
from devices.axefx3.registry import Registry
from tests.test_axefx3_text_planning import api, dev, design, BODY


@pytest.mark.parametrize('firmware,variant,user2,storage', [
    ('32.06',None,True,'unverified'),('32.06','mk1',True,'unverified'),
    ('33.00','mk1',False,'user2'),('97.00','mk1',False,'user2'),
    ('33.00','mk2',True,'separate'),('97.00',None,False,'unverified')])
def test_memory_policy_does_not_enable_new_firmware(firmware,variant,user2,storage):
    reg=Registry(firmware); result=profile.apply(reg,variant)
    assert result['user2_cabs'] is user2 and result['nam_storage']==storage
    assert not result['nam_writes'] and not result['variant_verified']
    reg.import_cab_names('U1.0001 First','user')
    if user2:reg.import_cab_names('U2.0001 Second','user')
    else:
        before=dict(reg.cab_catalog.names)
        with pytest.raises(ValueError,match='reserved'):reg.import_cab_names('U1.0002 New\nU2.0001 Second','user')
        assert before==reg.cab_catalog.names
    if firmware!='32.06':assert not reg.params and not reg.amp_roster


def test_switching_to_mk1_removes_stale_user2_names():
    reg=Registry('33.00');profile.apply(reg,'mk2')
    reg.import_cab_names('U1.0001 First\nU2.0001 Second','user')
    profile.apply(reg,'mk1')
    assert reg.cab_catalog.names=={(2,0):'First'}
    assert reg.cab_rosters['2']=={'0':'First'}


def test_search_uses_current_a2_parameter_and_never_echoes_secret():
    http=Mock(return_value=(200,json.dumps({'data':[{'id':42,'title':'Plexi','user':{'username':'creator'}}]}).encode()))
    result=tone_search.search('Led Zeppelin','nam',http=http,key='PRIVATE')
    query=parse_qs(urlparse(http.call_args.args[1]).query)
    assert query['architecture']==['2'] and query['format']==['nam']
    assert query['page_size']==['8']
    assert 'PRIVATE' not in json.dumps(result)
    assert result['candidates'][0]['url']=='https://www.tone3000.com/tones/42'
    assert not result['hardware_written'] and not result['nam_install_supported']


@pytest.mark.parametrize('status',[401,403,429,503])
def test_search_failures_do_not_invent_results(status):
    with pytest.raises(ValueError,match='HTTP'):
        tone_search.search('Plexi',http=lambda *a:(status,b''),key='PRIVATE')


def test_ir_search_does_not_apply_nam_architecture():
    http=Mock(return_value=(200,b'{"data":[]}'))
    tone_search.search('Greenback','ir',http=http,key='PRIVATE')
    assert 'architecture' not in parse_qs(urlparse(http.call_args.args[1]).query)


@pytest.mark.parametrize('url',['http://example.com/x.wav','file:///C:/secret','https://user:pass@example.com/x.wav','https://example.com:123/x.wav'])
def test_audio_url_rejects_non_public_schemes_before_dns(url,monkeypatch):
    dns=Mock(side_effect=AssertionError('DNS must not run'));monkeypatch.setattr(socket,'getaddrinfo',dns)
    with pytest.raises(ValueError):reference_audio.public_url(url)
    dns.assert_not_called()


@pytest.mark.parametrize('address',['127.0.0.1','10.0.0.1','169.254.169.254','::1','192.168.1.1'])
def test_audio_private_targets_blocked(address,monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(address,443))])
    with pytest.raises(ValueError,match='private'):reference_audio.public_url('https://example.com/x.wav')


def test_markdown_audio_link_is_unwrapped():
    assert reference_audio.links('Maak [sound](https://youtu.be/abc), graag')==['https://youtu.be/abc']


def test_new_profile_endpoint_does_not_write_and_invalidates_plan(api,dev):
    client,_=api
    proposal=client.post('/api/axefx3/plan',json=BODY).json()
    response=client.post('/api/axefx3/profile',json={'variant':'mk2'})
    assert response.status_code==200 and not response.json()['hardware_written']
    assert client.post('/api/axefx3/send',json=dict(token=proposal['token'],target_confirmed=True,external_audio_muted=True)).status_code==409
    dev._write.assert_not_called();dev.edit_session.assert_not_called()


def test_new_firmware_can_show_identity_without_guessing_grid(api,dev):
    client,_=api;dev.reg=Registry('97.00')
    data=client.get('/api/axefx3/state').json()
    assert data['connected'] and not data['profile']['write_supported']
    assert not data['profile']['user2_cabs']
    dev.read_grid.assert_not_called();dev._write.assert_not_called()


MEASUREMENTS=dict(url='https://youtu.be/example',sample_seconds=20,rms_dbfs=-17,
                  peak_dbfs=-2,crest_db=15,centroid_hz=1700,band_energy=[.3,.2,.3,.1,.1])


def test_gui_loads_the_actual_fm9_stylesheet_without_device_writes(api,dev):
    from fm9.paths import resource_path
    client,_=api
    response=client.get('/axefx3.css')
    source=resource_path('ui','index.html').read_text(encoding='utf-8')
    assert response.status_code==200
    assert response.text==source.split('<style>',1)[1].split('</style>',1)[0]
    assert response.headers['content-type'].startswith('text/css')
    html=client.get('/axefx3').text
    for component in ('hwbar','rail','context','workspace','canvas','rightrail','shelf','pane-request','pane-plan','pane-review','pane-confirm','pane-send'):
        assert 'id="'+component+'"' in html
    dev._write.assert_not_called();dev.edit_session.assert_not_called()


def test_measurements_and_capture_metadata_reach_selected_planner_only(api,dev,monkeypatch):
    client,ask=api
    monkeypatch.setattr(tone_search,'search',lambda *a,**k:{'candidates':[{'id':42,'title':'Plexi'}]})
    response=client.post('/api/axefx3/plan',json={**BODY,'prompt':'Gebruik https://youtu.be/example',
                        'audio_reference':MEASUREMENTS,'nam_query':'Marshall Plexi'})
    assert response.status_code==200,response.text
    text=ask.call_args.args[0]
    assert '1700' in text and 'NOT supported' in text and 'not instructions' in text
    assert response.json()['capture_search']['candidates'][0]['id']==42
    dev._write.assert_not_called();dev.edit_session.assert_not_called()


def test_audio_failure_and_cross_origin_do_not_call_ai(api,monkeypatch):
    client,ask=api
    monkeypatch.setattr(reference_audio,'fetch_audio',Mock(side_effect=ValueError('No audio')))
    assert client.post('/api/axefx3/audio',json={'url':'https://youtu.be/example'}).status_code==409
    assert client.post('/api/axefx3/search',json={'query':'Plexi'},headers={'Origin':'https://evil.test'}).status_code==403
    ask.assert_not_called()


def test_measurements_reject_freeform_instructions_and_nan():
    with pytest.raises(ValueError):tone_ui.Measurements(**{**MEASUREMENTS,'actions':'store preset'})
    with pytest.raises(ValueError):tone_ui.Measurements(**{**MEASUREMENTS,'centroid_hz':float('nan')})

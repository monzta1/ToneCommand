"""Metadata refresh never changes verified rosters, plans, presets or permissions."""
from copy import deepcopy
import struct
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
import server
from devices.axefx3 import amp_cache,amp_refresh,amp_inventory,fw33_profile,album_planning,tone_review
from devices.axefx3.registry import Registry


def cache(names=None):
    labels=list((names or amp_inventory.roster(fw33_profile.KEY)).values())
    header=struct.pack('<III',97,0,4)+bytes(30)+struct.pack('<I',2)
    encoded=struct.pack('<I',len(labels))+b''.join(struct.pack('<I',len(n))+n.encode('ascii') for n in labels)
    enum=struct.pack('<HHHffff',0,0,0,0,len(labels)-1,0,1)+encoded+struct.pack('<IH',0,0)
    numeric=struct.pack('<HHHffffIIH',1,0,0,0,10,0,1,0,0,0)
    # A different table containing an IR name must not escape the parser.
    table=struct.pack('<HHHffff',0xfff0,0,0,0,1,0,1)+struct.pack('<II',1,10)+b'PRIVATE IR'+struct.pack('<HII',0,1,123)
    return header+struct.pack('<II',10,2)+enum+numeric+struct.pack('<II',11,1)+table


def reg():
    result=Registry(fw33_profile.KEY);result.hardware_variant='mk2';return result


def source(tmp_path,monkeypatch,data):
    monkeypatch.setattr(amp_refresh,'cache_directory',lambda:tmp_path)
    path=tmp_path/'effectDefinitions_10_97p0.cache';path.write_bytes(data);return path


def test_exact_cache_to_eof_returns_only_amplifiers():
    assert amp_cache.amp_names(cache())==amp_inventory.roster(fw33_profile.KEY)
    assert 'PRIVATE IR' not in str(amp_cache.amp_names(cache()))


@pytest.mark.parametrize('fault',['short','header','count','trailing','oversize','nonascii','duplicate','numeric','noamp'])
def test_malformed_metadata_is_rejected(fault):
    data=bytearray(cache())
    if fault=='short':data=data[:50]
    if fault=='header':data[8]=5
    if fault=='count':data[42]=3
    if fault=='trailing':data.extend(b'bad')
    if fault=='oversize':data=bytes(amp_cache.MAX_BYTES+1)
    if fault=='nonascii':data[80]=255
    if fault=='duplicate':
        names=amp_inventory.roster(fw33_profile.KEY);names[1]=names[0];data=cache(names)
    if fault=='numeric':data[-(len(b'PRIVATE IR')+14+22+8+32):-1]=b'bad'
    if fault=='noamp':data[46:50]=struct.pack('<I',9)
    with pytest.raises(ValueError):amp_cache.amp_names(bytes(data))


def test_refresh_matching_cache_is_read_only(tmp_path,monkeypatch):
    source(tmp_path,monkeypatch,cache());registry=reg();before=deepcopy(album_planning.MODELS)
    result=amp_refresh.refresh(registry)
    assert result['status']=='up_to_date' and result['source_count']==336
    assert result['inventory']['count']==336 and not result['live_list_fetched']
    assert not result['hardware_written'] and not result['permissions_changed']
    assert result['added']==result['changed']==result['removed']==[]
    assert album_planning.MODELS==before and not registry.selectable_amp_models()
    assert 'PRIVATE IR' not in str(result)


def test_changed_bundled_file_cannot_desynchronize_active_planner(monkeypatch):
    names=dict(album_planning.MODELS);names[100]='Different bundled name'
    monkeypatch.setattr(amp_inventory,'roster',lambda _:names)
    with pytest.raises(ValueError,match='Restart TC'):amp_refresh.refresh(reg())


def test_existing_review_still_sends_after_metadata_refresh(api,monkeypatch):
    from test_axefx3_album_build import plan
    dev,client=api;reviews=server._afx3_tone_reviews
    monkeypatch.setattr(reviews,'pending',None)
    prepared=reviews.prepare(dev,plan(dev),tone_review.snapshot(dev,include_nam=False))
    pending=reviews.pending
    response=client.post('/api/axefx3/amps/refresh',json=dict(expected_firmware=fw33_profile.KEY))
    assert response.status_code==200 and reviews.pending is pending
    dev._write.assert_not_called()
    sent=reviews.send(dev,prepared['token'],target_confirmed=True,external_audio_muted=True)
    assert sent['ok'] and not sent['skipped']
    dev.store_preset.assert_not_called()


def test_new_changed_and_missing_models_remain_blocked(tmp_path,monkeypatch):
    names=amp_inventory.roster(fw33_profile.KEY);names[0]='Renamed amplifier';names[336]='New amplifier'
    source(tmp_path,monkeypatch,cache(names));before=deepcopy(album_planning.MODELS)
    result=amp_refresh.refresh(reg())
    assert result['status']=='verification_required'
    assert result['added']==[dict(ordinal=336,name='New amplifier')]
    assert result['changed'][0]['verified_name']=='59 Bassguy Bright'
    assert result['inventory']['count']==336 and album_planning.MODELS==before
    with pytest.raises(ValueError):amp_inventory.ordinal(fw33_profile.KEY,'New amplifier')
    names=amp_inventory.roster(fw33_profile.KEY);names.pop(335)
    source(tmp_path,monkeypatch,cache(names))
    assert amp_refresh.refresh(reg())['removed']==[dict(ordinal=335,name='Brit JVM Crunch Red')]


def test_missing_and_invalid_source_preserve_bundled_inventory(tmp_path,monkeypatch):
    monkeypatch.setattr(amp_refresh,'cache_directory',lambda:tmp_path)
    assert amp_refresh.refresh(reg())['status']=='bundled_only'
    source(tmp_path,monkeypatch,b'bad')
    result=amp_refresh.refresh(reg())
    assert result['status']=='source_unreadable' and result['inventory']['count']==336


def test_pick_highest_product10_cache_and_do_not_fall_back_on_bad_latest(tmp_path,monkeypatch):
    source(tmp_path,monkeypatch,cache())
    (tmp_path/'effectDefinitions_11_999p0.cache').write_bytes(cache())
    (tmp_path/'effectDefinitions_10_98p0.cache').write_bytes(b'bad')
    assert amp_refresh.latest_cache().name=='effectDefinitions_10_98p0.cache'
    assert amp_refresh.refresh(reg())['status']=='source_unreadable'


@pytest.mark.parametrize('firmware,variant',[('33.00','mk2'),(fw33_profile.KEY,'mk1')])
def test_unverified_profile_never_gains_selection(tmp_path,monkeypatch,firmware,variant):
    source(tmp_path,monkeypatch,cache());registry=Registry(firmware);registry.hardware_variant=variant
    result=amp_refresh.refresh(registry)
    assert result['status']=='verification_required' and result['inventory'] is None
    assert not result['permissions_changed']


@pytest.fixture
def api(monkeypatch,tmp_path):
    from test_axefx3_album_build import device
    dev=device(monkeypatch);dev.firmware_label=Mock(return_value=fw33_profile.KEY)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',dev.reg,dev,'Axe-Fx III'))
    source(tmp_path,monkeypatch,cache())
    return dev,TestClient(server.app)


def test_registered_refresh_preserves_pending_review_and_hardware(api,monkeypatch):
    dev,client=api;before=tone_review.snapshot(dev,include_nam=False)
    clear=Mock();monkeypatch.setattr(server._afx3_tone_reviews,'clear',clear)
    response=client.post('/api/axefx3/amps/refresh',json=dict(expected_firmware=fw33_profile.KEY))
    assert response.status_code==200 and response.json()['status']=='up_to_date'
    assert tone_review.snapshot(dev,include_nam=False)==before
    clear.assert_not_called();dev._write.assert_not_called();dev.set_param_display.assert_not_called()
    dev.store_preset.assert_not_called();dev.read_nam_slot.assert_not_called()


def test_refresh_origin_stale_identity_and_bad_schema_fail_closed(api):
    dev,client=api;path='/api/axefx3/amps/refresh';body=dict(expected_firmware=fw33_profile.KEY)
    assert client.post(path,json=body,headers={'Origin':'https://evil.test'}).status_code==403
    assert client.post(path,json={**body,'path':'C:/private'}).status_code==422
    dev.firmware_label.return_value='33.00'
    assert client.post(path,json=body).status_code==409
    dev.firmware_label.side_effect=[fw33_profile.KEY,'33.00']
    assert client.post(path,json=body).status_code==409
    dev._write.assert_not_called();dev.set_param_display.assert_not_called()

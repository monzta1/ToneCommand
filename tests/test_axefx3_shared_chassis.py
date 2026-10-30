"""One DSP implementation, separate storage policy. No native write approval."""
from dataclasses import FrozenInstanceError

import pytest

from devices.axefx3 import chassis, profile, fw33_profile, cab_inventory, cab_metadata
from devices.axefx3 import readonly_protocol, firmware_identity, protocol
from devices.axefx3.registry import Registry, SUPPORTED_FIRMWARE
from tests.test_axefx3_text_planning import api, dev, design


@pytest.mark.parametrize('name,count,fullres', [('mk1',512,0),('mk2',1024,64),('turbo',1024,64)])
def test_declared_capacity_has_one_source_for_both_adapters(name,count,fullres):
    value=chassis.declared(name)
    assert value.control_family=='axe-fx-iii'
    assert value.presets==readonly_protocol.preset_count(name)==count
    assert value.persistent_fullres==fullres
    assert readonly_protocol.PRESET_COUNTS is chassis.PRESET_COUNTS
    with pytest.raises(FrozenInstanceError):value.presets=9999
    with pytest.raises(TypeError):chassis.PRESET_COUNTS[name]=9999


@pytest.mark.parametrize('bad', [None,False,True,512,{},[],['mk1'],'auto','MK1','mk3',''])
def test_invalid_declaration_does_not_become_mk2_or_change_ranges(bad):
    with pytest.raises(ValueError):chassis.declared(bad)
    with pytest.raises(ValueError):readonly_protocol.preset_count(bad)
    if bad is not None:
        with pytest.raises(ValueError):profile.memory_policy(fw33_profile.KEY,bad)


@pytest.mark.parametrize('firmware', ['32.06',fw33_profile.KEY,firmware_identity.BETA5_KEY,'97.00'])
def test_mk1_mk2_share_registry_and_encoding_not_storage(firmware):
    first,second=Registry(firmware),Registry(firmware)
    mk1,mk2=profile.apply(first,'mk1'),profile.apply(second,'mk2')
    assert mk1['control_family']==mk2['control_family']=='axe-fx-iii'
    assert first.params==second.params and first.amp_roster==second.amp_roster
    assert first.effect_type_models==second.effect_type_models
    for family,pid in first.params:
        assert first.spec(family,pid)==second.spec(family,pid)
    assert mk1['preset_count']==512 and mk2['preset_count']==1024
    assert not mk1['variant_verified'] and not mk2['variant_verified']
    assert mk1['write_supported']==mk2['write_supported']==(firmware in SUPPORTED_FIRMWARE)
    if firmware not in SUPPORTED_FIRMWARE:
        assert not first.params and not second.params
        assert not mk1['nam_writes'] and not mk2['nam_writes']


@pytest.mark.parametrize('firmware', ['32.06',fw33_profile.KEY])
@pytest.mark.parametrize('family,name,value', [('DISTORT','DISTORT_MID',6.),('DELAY','DELAY_TIME',280.),('REVERB','REVERB_TIME',1.2),('WAH','WAH_FREQMIN',350.)])
def test_shared_knob_bytes_do_not_fork_per_chassis(firmware,family,name,value):
    frames=[]
    for variant in ('mk1','mk2'):
        reg=Registry(firmware);profile.apply(reg,variant)
        frames.append(protocol.set_parameter(reg,reg.find_param(family,name),value))
    assert frames[0]==frames[1] and frames[0][4]==0x10


@pytest.mark.parametrize('firmware', [fw33_profile.KEY,firmware_identity.BETA5_KEY])
def test_mk2_to_mk1_preserves_upper_user1_and_removes_reserved_storage(firmware):
    reg=Registry(firmware);profile.apply(reg,'mk2')
    reg.import_cab_names('U1.1024 Upper User1\nU2.1024 User2\nU3.0064 FullRes','user')
    assert reg.cab_catalog.names=={(2,1023):'Upper User1',(3,1023):'User2',(6,63):'FullRes'}
    profile.apply(reg,'mk1')
    assert reg.cab_catalog.names=={(2,1023):'Upper User1'}
    for text in ('U1.0001 Replacement\nU2.0001 Reserved','U1.0001 Replacement\nU3.0001 No persistent bank'):
        with pytest.raises(ValueError):reg.import_cab_names(text,'user',replace=True)
        assert reg.cab_catalog.names=={(2,1023):'Upper User1'}
    profile.apply(reg,'mk2')
    assert reg.cab_catalog.names=={(2,1023):'Upper User1'}


def test_fullres_inventory_and_direct_selection_refuse_mk1_even_if_names_are_injected():
    reg=Registry(fw33_profile.KEY);profile.apply(reg,'mk1')
    reg.cab_catalog.names[6,0]='Stale MK2 FullRes'
    assert all(c['bank']!=6 for c in cab_inventory.choices(reg,include_fullres=True))
    with pytest.raises(ValueError):cab_inventory.selection(reg,6,0,3)


def test_beta5_name_cache_is_separate_and_has_no_selector_or_firmware_approval():
    def make(firmware,variant):
        reg=Registry(firmware);profile.apply(reg,variant);return reg
    before=make(fw33_profile.KEY,'mk2')
    before.import_cab_names('U1.0001 Older build name','user');assert cab_metadata.save(before)
    beta=make(firmware_identity.BETA5_KEY,'mk2')
    assert not beta.cab_catalog.names and cab_metadata.path_for(beta)!=cab_metadata.path_for(before)
    beta.import_cab_names('U1.1024 Upper User1\nU2.1024 Upper User2','user')
    assert cab_metadata.save(beta)
    assert make(firmware_identity.BETA5_KEY,'mk2').cab_catalog.names==beta.cab_catalog.names
    assert not make(firmware_identity.BETA5_KEY,'mk1').cab_catalog.names
    assert not beta.params and not beta.selectable_amp_models()
    assert cab_inventory.factory_roster(beta.firmware)=={} and cab_inventory.choices(beta)==[]
    assert not profile.memory_policy(beta.firmware,'mk2')['nam_writes']


@pytest.mark.parametrize('writer_module', ['amp_writer','beta5_amp_writer'])
def test_shared_storage_policy_does_not_silently_enable_unmeasured_writers(writer_module,monkeypatch):
    from importlib import import_module
    from fm9.device import ReadOnly
    from fm9 import midi_transport
    monkeypatch.setattr(midi_transport,'open_ports',lambda *a:pytest.fail('Native MIDI opened'))
    module=import_module('devices.axefx3.'+writer_module)
    writer=module.Beta5AmpWriter if writer_module.startswith('beta5') else module.AmpWriter
    with pytest.raises(ReadOnly):writer(chassis='mk1')


def test_unknown_chassis_retains_conservative_storage_without_auto_detection():
    reg=Registry(firmware_identity.BETA5_KEY)
    result=profile.memory_policy(reg.firmware,None)
    assert result['preset_count']==512 and result['persistent_fullres_slots']==0
    assert not result['user2_cabs'] and result['nam_storage']=='unverified'
    assert not result['nam_writes'] and not result['write_supported']


@pytest.mark.parametrize('bank', [3,6])
def test_validly_checksummed_reserved_cache_cannot_partially_reload_on_mk1(bank):
    import json
    import hashlib
    firmware=firmware_identity.BETA5_KEY
    reg=Registry(firmware);profile.apply(reg,'mk1')
    reg.import_cab_names('U1.1024 Good','user');assert cab_metadata.save(reg)
    path=cab_metadata.path_for(reg)
    payload=json.loads(path.read_text(encoding='utf-8'))
    payload['data']['entries'].append([bank,0,'Stale reserved bank'])
    payload['checksum']=hashlib.sha256(cab_metadata.canonical(payload['data']).encode('ascii')).hexdigest()
    path.write_text(cab_metadata.canonical(payload),encoding='utf-8')
    original=path.read_bytes()
    fresh=Registry(firmware);result=profile.apply(fresh,'mk1')
    assert result['cab_names_restored']==0 and not fresh.cab_catalog.names
    assert path.read_bytes()==original


def test_mk1_does_not_receive_the_mk2_nam_install_instructions():
    assert 'installation in slots 001-256' in profile.memory_policy(fw33_profile.KEY,'mk2')['warning']
    for variant in ('mk1',None):
        result=profile.memory_policy(fw33_profile.KEY,variant)
        assert 'installation in slots 001-256' not in result['warning']
        assert not result['nam_writes']


def test_normal_http_profile_and_cab_import_share_storage_policy_without_ai_or_midi(api,dev):
    client,ask=api
    dev.reg=Registry(firmware_identity.BETA5_KEY)
    dev.firmware_label.return_value=firmware_identity.BETA5_KEY
    response=client.post('/api/axefx3/profile',json={'variant':'mk1'})
    assert response.status_code==200 and not response.json()['hardware_written']
    assert response.json()['profile']['control_family']=='axe-fx-iii'
    response=client.post('/api/axefx3/cabs',json={'kind':'user','text':'U1.1024 Upper User1'})
    assert response.status_code==200,response.text
    assert response.json()['imported']==1 and not response.json()['hardware_written']
    assert response.json()['locally_saved']
    for text in ('U2.0001 Reserved NAM bank','U3.0001 Unsupported persistent FullRes'):
        response=client.post('/api/axefx3/cabs',json={'kind':'user','text':text})
        assert response.status_code==409 and dev.reg.cab_catalog.names=={(2,1023):'Upper User1'}
    state=client.get('/api/axefx3/state').json()
    assert state['connected'] and not state['profile']['write_supported'] and state['cab_count']==1
    assert client.post('/api/axefx3/profile',json={'variant':'mk2'}).status_code==200
    response=client.post('/api/axefx3/cabs',json={'kind':'user','text':'U2.1024 Upper User2\nU3.0064 FullRes'})
    assert response.status_code==200 and response.json()['imported']==2
    assert not response.json()['hardware_written']
    assert client.post('/api/axefx3/profile',json={'variant':'mk1'}).status_code==200
    assert dev.reg.cab_catalog.names=={(2,1023):'Upper User1'}
    dev._write.assert_not_called();ask.assert_not_called()

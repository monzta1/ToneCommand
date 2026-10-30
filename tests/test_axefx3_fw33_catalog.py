"""FW33 name addressing is metadata, not a selector-write permission."""
import pytest
from devices.axefx3 import fw33_profile, profile
from devices.axefx3 import cab_inventory
from devices.axefx3.catalog import wire_address
from devices.axefx3.registry import Registry


@pytest.mark.parametrize('bank,slot,expected', [(1,1,(2,0)), (1,513,(2,512)),
    (1,1024,(2,1023)), (2,1,(3,0)), (2,1024,(3,1023)), (3,1,(6,0)), (3,64,(6,63))])
def test_fw33_bank_boundaries(bank,slot,expected):
    assert wire_address('user',bank,slot,firmware=fw33_profile.KEY) == expected


def test_full_import_keeps_banks_separate_and_fullres_explicit():
    reg=Registry(fw33_profile.KEY)
    profile.apply(reg,'mk2')
    reg.import_cab_names('U1.0513 Upper User1\nU1.1024 Last1\nU2.0001 First2\nU2.1024 Last2\nU3.0064 FullRes','user')
    assert reg.cab_rosters['2'] == {'512':'Upper User1','1023':'Last1'}
    assert reg.cab_rosters['3'] == {'0':'First2','1023':'Last2'}
    assert reg.cab_rosters['6'] == {'63':'FullRes'}
    assert reg.cab_catalog.position(2,512) == 'USER 1 slot 513'
    assert reg.cab_catalog.position(3,0) == 'USER 2 slot 1'
    assert reg.cab_catalog.position(6,63) == 'USER 3 (FullRes) slot 64'


@pytest.mark.parametrize('variant',[None,'mk1'])
def test_nam_protection_removes_whole_user2_not_upper_user1(variant):
    reg=Registry(fw33_profile.KEY)
    profile.apply(reg,'mk2')
    reg.import_cab_names('U1.1024 Upper1\nU2.0001 First2\nU2.1024 Last2','user')
    profile.apply(reg,variant)
    assert reg.cab_catalog.names == {(2,1023):'Upper1'}
    before=dict(reg.cab_catalog.names)
    with pytest.raises(ValueError,match='reserved for NAM'):
        reg.import_cab_names('U1.0001 New1\nU2.0001 New2','user',replace=True)
    assert reg.cab_catalog.names == before


@pytest.mark.parametrize('text',['U1.1025 Bad','U2.1025 Bad','U3.0065 Bad','U4.0001 Bad'])
def test_invalid_import_remains_atomic(text):
    reg=Registry(fw33_profile.KEY)
    profile.apply(reg,'mk2')
    reg.import_cab_names('U1.1024 Original','user')
    before=dict(reg.cab_catalog.names)
    with pytest.raises(ValueError):
        reg.import_cab_names('U1.0001 New\n'+text,'user',replace=True)
    assert reg.cab_catalog.names == before


def test_replace_user_does_not_remove_factory_names():
    reg=Registry(fw33_profile.KEY)
    profile.apply(reg,'mk2')
    reg.import_cab_names('F1.0001 Factory','factory')
    reg.import_cab_names('U1.1024 One\nU2.0001 Two\nU3.0064 Three','user')
    reg.import_cab_names('U1.0001 Replacement','user',replace=True)
    assert reg.cab_catalog.names == {(0,0):'Factory',(2,0):'Replacement'}


def test_factory_roster_is_complete_and_firmware_pinned():
    names=cab_inventory.factory_roster(fw33_profile.KEY)
    assert len(names)==2048
    assert names[0,0]=='1x4 Pig 57'
    assert names[1,1023]=='TOTALLY-FLAT'
    assert not cab_inventory.factory_roster('32.06')
    assert not cab_inventory.factory_roster('33.01')


def test_choices_exclude_empty_reserved_and_fullres_by_default():
    reg=Registry(fw33_profile.KEY)
    profile.apply(reg,'mk2')
    reg.import_cab_names('U1.1024 Upper1\nU2.1024 Upper2\nU3.0063 <EMPTY> (*)\nU3.0064 FullRes','user')
    choices=cab_inventory.choices(reg)
    assert len(choices)==2050
    assert all(c['bank']!=6 for c in choices)
    full=cab_inventory.choices(reg,include_fullres=True)
    assert len(full)==2051 and full[-1]['eligible_ir_slots']==[3,4]
    profile.apply(reg,'mk1')
    assert len(cab_inventory.choices(reg))==2049

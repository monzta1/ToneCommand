"""Name persistence is isolated by firmware/chassis and never installs IRs."""
import json
import pytest
from devices.axefx3 import cab_metadata,fw33_profile,profile
from devices.axefx3.registry import Registry


def registry(variant='mk2'):
    reg=Registry(fw33_profile.KEY);profile.apply(reg,variant)
    return reg


def test_names_reload_on_a_new_connection_without_reimport():
    first=registry()
    first.import_cab_names('U1.1024 Upper1\nU2.0001 First2\nU3.0064 <EMPTY>','user')
    assert cab_metadata.save(first)
    second=registry()
    assert second.cab_catalog.names==first.cab_catalog.names
    assert second.cab_rosters==first.cab_rosters
    assert 'geen live inventarisatie' in second.cab_catalog.cache_note


def test_mk1_never_reloads_mk2_user2_cache():
    first=registry();first.import_cab_names('U1.1024 One\nU2.0001 Two','user');cab_metadata.save(first)
    mk1=registry('mk1')
    assert not mk1.cab_catalog.names and not mk1.cab_catalog.user2_enabled
    assert cab_metadata.path_for(mk1)!=cab_metadata.path_for(first)


def test_existing_live_metadata_is_not_overwritten_by_old_cache():
    first=registry();first.import_cab_names('U1.0001 Old','user');cab_metadata.save(first)
    first.import_cab_names('U1.0001 New','user');profile.apply(first,'mk2')
    assert first.cab_catalog.names[2,0]=='New'


def test_corrupt_cache_does_not_partially_import_or_delete():
    first=registry();first.import_cab_names('U1.0001 Old','user');cab_metadata.save(first)
    path=cab_metadata.path_for(first);data=json.loads(path.read_text(encoding='utf-8'))
    data['data']['entries'].append([3,0,'Corrupt'])
    path.write_text(json.dumps(data),encoding='utf-8')
    second=registry()
    assert not second.cab_catalog.names and path.exists()
    assert 'again' in second.cab_catalog.cache_note


@pytest.mark.parametrize('firmware',['32.06','33.01','unknown'])
def test_other_firmware_does_not_inherit_cache(firmware):
    first=registry();first.import_cab_names('U1.0001 Old','user');cab_metadata.save(first)
    reg=Registry(firmware);profile.apply(reg,'mk2')
    assert not reg.cab_catalog.names and not cab_metadata.save(reg)


def test_simulator_without_isolated_path_never_reads_real_cache(monkeypatch):
    monkeypatch.delenv('TONECOMMAND_AXEFX3_STATE_DIR')
    reg=registry()
    assert cab_metadata.path_for(reg) is None and not reg.cab_catalog.names

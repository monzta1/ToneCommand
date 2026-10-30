"""A new firmware may not silently discard accepted legacy functionality."""
from copy import deepcopy
from types import SimpleNamespace

from devices.axefx3 import firmware_parity as parity,fw33_profile
from devices.axefx3.registry import Registry


def test_every_legacy_parameter_is_retained_or_has_an_explicit_migration():
    current=Registry(fw33_profile.KEY)
    rows=parity.parameters(current.definitions)
    missing={r['parameter'] for r in rows if r['status']=='pending'}
    assert missing==set(parity.PENDING)
    assert all(r['reason']!='Unaccounted firmware regression' for r in rows)
    assert len(rows)==75
    changed={r['parameter'] for r in rows if r['changed_fields']}
    assert changed==parity.ENCODER_MIGRATIONS
    assert {r['parameter'] for r in rows if r['status']=='retained_definition'} | changed | missing == {
        name for family in parity.LEGACY.values() for name in family}


def test_unaccounted_removal_is_detectable_not_a_fallback_to_legacy_metadata():
    reg=Registry(fw33_profile.KEY)
    actual=deepcopy(reg.definitions)
    del actual['DELAY']['DELAY_TIME']
    rows=parity.parameters(actual)
    missing={r['parameter'] for r in rows if r['status']=='pending'}
    assert missing-set(parity.PENDING)=={'DELAY_TIME'}
    assert next(r for r in rows if r['parameter']=='DELAY_TIME')['reason']=='Unaccounted firmware regression'
    assert 'DELAY_TIME' not in actual['DELAY']


def test_extra_instances_are_accounted_for_separately_from_parameter_names():
    old,new=Registry('32.06'),Registry(fw33_profile.KEY)
    missing=set()
    for family, controls in old.definitions.items():
        for name, value in controls.items():
            if name not in new.definitions.get(family,{}):continue
            for instance in range(1,5):
                try:old.spec(family,value['pid'],instance)
                except (ValueError,KeyError):continue
                try:new.spec(family,value['pid'],instance)
                except (ValueError,KeyError):missing.add((family,instance))
    assert missing==parity.INSTANCE_MIGRATIONS


def test_report_counts_actual_definitions_and_never_promotes_writes():
    reg=Registry(fw33_profile.KEY)
    before=deepcopy(reg.definitions)
    result=parity.report(reg)
    assert result['retained_parameters']==75
    assert len(result['added_parameters'])==8
    assert len(result['pending_parameters'])==0
    assert result['automatically_enables_writes'] is False
    assert not result['functionality_complete']
    assert any(r['function']=='flexible_serial_insertion' and r['status']=='pending' for r in result['operation_migrations'])
    assert result['wah_in_fw33_tone_planner'] is False
    assert reg.definitions==before
    assert not result['wah_controller_workspace']
    reg.hardware_variant='mk2'
    assert parity.report(reg)['wah_controller_workspace']
    reg.hardware_variant='mk1'
    assert not parity.report(reg)['wah_controller_workspace']
    assert parity.report(Registry('32.06'))['pending_parameters']==[]
    assert not parity.report(SimpleNamespace(firmware='33.01'))['recognized']

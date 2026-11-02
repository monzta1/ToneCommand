"""Synthetic observations only; this contract cannot open a device or provider."""
import ast
from copy import deepcopy
import inspect

import pytest

from devices.axefx3 import existing_contract as plan


@pytest.fixture
def context():
    return dict(declared_chassis='mk2', preset=323, name='Preserved reference', scene=2,
        observed_state=dict(grid=[[58, 62, 78]], bulk={'58': [0, 32767],
            '200': [117, 9], '201': [23, 4]}, opaque={'unqualified': [93, 2, 19]},
            modifiers=[[0, 0, 0, 0, 0, 0, 0, 0, 78, 21, *([0] * 15)]]),
        scene_maps=[dict(scene=n, name=f'Original {n}', blocks=[
            dict(effect_id=58, channel='A' if n % 2 else 'B', bypassed=False),
            dict(effect_id=62, channel='A', bypassed=False),
            dict(effect_id=78, channel='A', bypassed=True)]) for n in range(1, 9)],
        editable_parameters=[dict(effect_id=58, channel=ch, parameter='DISTORT_DRIVE',
            param_id=1, model='Existing qualified amp', current=5., minimum=0., maximum=8.,
            tolerance=.01, qualified=True) for ch in ('A', 'B')])


@pytest.fixture
def design():
    return dict(summary='Dark bluesrock, preserving the existing scene roles.',
        changes=[dict(effect_id=58, channel=ch, parameter='DISTORT_DRIVE', value=value,
                      reason='Increase saturation without replacing the amp model or trim.')
                 for ch, value in [('A', 5.6), ('B', 5.5)]],
        scene_goals=[dict(scene=n, target='Warmer bluesrock body, original arrangement retained.')
                     for n in range(1, 9)])


def test_shared_impact_and_detached_review_without_execution(context, design):
    original = deepcopy((context, design))
    out = plan.compile_design(design, context)
    assert out['target'] == dict(preset=323, name='Preserved reference', scene=2,
                                 declared_chassis='mk2')
    assert out['changes'][0]['affected_scenes'] == [1, 3, 5, 7]
    assert out['changes'][1]['active_scenes'] == [2, 4, 6, 8]
    assert out['changes'][0]['before'] == 5. and out['changes'][0]['after'] == 5.6
    assert len(out['scene_goals']) == 8 and not out['executable'] and not out['stored']
    assert 'actions' not in out and 'token' not in out
    assert (context, design) == original
    out['changes'][0]['affected_scenes'].clear()
    design['changes'][0]['value'] = 7.
    assert context == original[0]
    assert plan.compile_design(original[1], context)['changes'][0]['after'] == 5.6


@pytest.mark.parametrize('fault', ['duplicate', 'unknown', 'missing_channel', 'noop',
    'rounding', 'low', 'high', 'nan', 'inf', 'boolean', 'string', 'extra_action',
    'extra_context', 'one_scene_missing', 'reordered_goals', 'duplicate_goals'])
def test_ai_cannot_extend_surface_or_fake_changes(context, design, fault):
    first = design['changes'][0]
    if fault == 'duplicate': design['changes'].append(deepcopy(first))
    elif fault == 'unknown': first['parameter'] = 'DISTORT_LEVEL'
    elif fault == 'missing_channel': first['channel'] = 'C'
    elif fault in ('noop', 'rounding'): first['value'] = 5. if fault == 'noop' else 5.001
    elif fault in ('low', 'high'): first['value'] = -1. if fault == 'low' else 9.
    elif fault in ('nan', 'inf'): first['value'] = float(fault)
    elif fault == 'boolean': first['value'] = True
    elif fault == 'string': first['value'] = '5.6'
    elif fault == 'extra_action': design['actions'] = [{'kind': 'store'}]
    elif fault == 'extra_context': design['editable_parameters'] = context['editable_parameters']
    elif fault == 'one_scene_missing': design['scene_goals'].pop()
    elif fault == 'reordered_goals': design['scene_goals'].reverse()
    elif fault == 'duplicate_goals': design['scene_goals'][7]['scene'] = 1
    before = deepcopy(context)
    with pytest.raises(ValueError): plan.compile_design(design, context)
    assert context == before


@pytest.mark.parametrize('field', ['qualified', 'modifier_owned', 'timing_linked', 'wet_only'])
def test_host_ownership_and_qualification_are_fail_closed(context, design, field):
    context['editable_parameters'][0][field] = field != 'qualified'
    with pytest.raises(ValueError): plan.compile_design(design, context)
    if field == 'qualified':
        del context['editable_parameters'][0]['qualified']
        with pytest.raises(ValueError): plan.compile_design(design, context)


@pytest.mark.parametrize('parameter', ['DISTORT_LEVEL', 'WAH_CONTROL', 'VOLUME_CONTROL',
                                     'PITCH_CONTROL', 'OUTPUT_LEVEL', 'TYPE'])
def test_preserved_control_cannot_be_exposed_by_host_mistake(context, design, parameter):
    for item in [*context['editable_parameters'], *design['changes']]: item['parameter'] = parameter
    with pytest.raises(ValueError): plan.compile_design(design, context)


@pytest.mark.parametrize('eid', [37, 38, 39, 40, 41, 42, 43, 44, 45, 200, 201])
def test_io_and_system_surfaces_cannot_be_exposed(context, design, eid):
    for item in [*context['editable_parameters'], *design['changes']]: item['effect_id'] = eid
    for scene in context['scene_maps']: scene['blocks'][0]['effect_id'] = eid
    with pytest.raises(ValueError): plan.compile_design(design, context)


@pytest.mark.parametrize('fault', ['missing_change', 'bypassed', 'same_channel'])
def test_every_scene_needs_active_not_imagined_coverage(context, design, fault):
    if fault == 'missing_change': design['changes'].pop()
    if fault == 'bypassed': context['scene_maps'][1]['blocks'][0]['bypassed'] = True
    if fault == 'same_channel': design['changes'][1]['channel'] = 'A'
    with pytest.raises(ValueError): plan.compile_design(design, context)


def test_bypassed_scene_is_affected_but_not_claimed_active(context, design):
    context['scene_maps'][0]['blocks'][0]['bypassed'] = True
    context['editable_parameters'].append(dict(context['editable_parameters'][0],
        effect_id=62, parameter='CAB_TEST_SCALAR', param_id=2))
    design['changes'].append(dict(design['changes'][0], effect_id=62, parameter='CAB_TEST_SCALAR'))
    out = plan.compile_design(design, context)
    assert out['changes'][0]['affected_scenes'] == [1, 3, 5, 7]
    assert out['changes'][0]['active_scenes'] == [3, 5, 7]
    assert out['changes'][2]['active_scenes'] == list(range(1, 9))


@pytest.mark.parametrize('fault', ['empty_baseline', 'bad_json', 'nonfinite_baseline',
    'duplicate_parameter', 'aliased_address', 'duplicate_block', 'changed_inventory',
    'missing_scene', 'reordered_maps', 'wrong_channel', 'bool_preset', 'bool_scene',
    'bool_effect', 'bool_bypass', 'bad_range', 'huge_tolerance', 'negative_tolerance',
    'nonfinite_current', 'missing_model', 'extra_parameter_permission'])
def test_incomplete_context_is_not_silently_repaired(context, design, fault):
    p = context['editable_parameters'][0]
    if fault == 'empty_baseline': context['observed_state'] = {}
    elif fault == 'bad_json': context['observed_state']['bad'] = object()
    elif fault == 'nonfinite_baseline': context['observed_state']['bad'] = float('nan')
    elif fault == 'duplicate_parameter': context['editable_parameters'].append(deepcopy(p))
    elif fault == 'aliased_address': context['editable_parameters'].append(dict(p, parameter='ALIAS'))
    elif fault == 'duplicate_block': context['scene_maps'][0]['blocks'].append(deepcopy(context['scene_maps'][0]['blocks'][0]))
    elif fault == 'changed_inventory': context['scene_maps'][0]['blocks'].pop()
    elif fault == 'missing_scene': context['scene_maps'].pop()
    elif fault == 'reordered_maps': context['scene_maps'].reverse()
    elif fault == 'wrong_channel': p['channel'] = 'E'
    elif fault == 'bool_preset': context['preset'] = True
    elif fault == 'bool_scene': context['scene'] = True
    elif fault == 'bool_effect': p['effect_id'] = True
    elif fault == 'bool_bypass': context['scene_maps'][0]['blocks'][0]['bypassed'] = 1
    elif fault == 'bad_range': p['minimum'] = p['maximum']
    elif fault == 'huge_tolerance': p['tolerance'] = 100.
    elif fault == 'negative_tolerance': p['tolerance'] = -1.
    elif fault == 'nonfinite_current': p['current'] = float('inf')
    elif fault == 'missing_model': del p['model']
    elif fault == 'extra_parameter_permission': p['execute'] = True
    with pytest.raises((ValueError, TypeError)): plan.compile_design(design, context)


@pytest.mark.parametrize('chassis,slot,valid', [('mk1', 511, True), ('mk1', 512, False),
    ('mk2', 1023, True), ('turbo', 1023, True), ('mk2', 1024, False), ('mk2', -1, False)])
def test_declared_capacity_is_not_a_shared_write_grant(context, design, chassis, slot, valid):
    context.update(declared_chassis=chassis, preset=slot)
    if valid:
        out = plan.compile_design(design, context)
        assert out['target']['preset'] == slot and not out['executable']
    else:
        with pytest.raises(ValueError): plan.compile_design(design, context)


def test_opaque_or_scene_changes_affect_digest_without_leaking_payload(context, design):
    first = plan.compile_design(design, context)
    context['observed_state']['opaque']['unqualified'][0] += 1
    second = plan.compile_design(design, context)
    assert first['baseline_digest'] != second['baseline_digest']
    context['scene_maps'][0]['name'] = 'Different original name'
    assert second['baseline_digest'] != plan.compile_design(design, context)['baseline_digest']
    assert 'observed_state' not in first


def test_original_values_outside_new_build_caps_are_not_normalized(context, design):
    context['observed_state']['original_output_level'] = 0.
    context['editable_parameters'][0]['current'] = 9.
    before = deepcopy(context)
    out = plan.compile_design(design, context)
    assert out['changes'][0]['before'] == 9. and context == before
    assert all(c['parameter'] != 'OUTPUT_LEVEL' for c in out['changes'])


def test_module_cannot_import_transport_provider_or_executor():
    tree = ast.parse(inspect.getsource(plan))
    names = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert set(names) <= {'copy', 'hashlib', 'json', 'typing', 'pydantic'}
    assert not hasattr(plan, 'send') and not hasattr(plan, 'register')

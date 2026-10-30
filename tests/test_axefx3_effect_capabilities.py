"""Musical vocabulary is not an effect setter or firmware acceptance gate."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from devices.axefx3 import (album_planning, effect_capabilities as effects,
    effect_voicing, fw33_profile, nam_planning, route_options, scene_contract,
    scene_intent, serial_build, serial_planning, wah_voicing)
from devices.axefx3.registry import Registry, SUPPORTED_FIRMWARE
from tests.test_axefx3_album_build import device
from tests.test_axefx3_scene_counts import short_design
from tests.test_axefx3_scene_contract import brief, workspace, sequence, BODY


def registry(firmware=fw33_profile.KEY, chassis='mk2'):
    reg = Registry(firmware)
    reg.hardware_variant = chassis
    return reg


def rows(reg, mode='amp'):
    return {row['key']: row for row in effects.reference(reg, mode)['effects']}


def test_full_vocabulary_is_explicit_without_midi_addresses_or_fake_rights():
    report = effects.reference(registry())
    index = rows(registry())
    assert len(index) == len(effects.EFFECTS) == 40
    assert {'phaser', 'flanger', 'pitch', 'formant', 'enhancer', 'gate',
        'volume', 'rotary', 'dynamic_distortion', 'multitap_delay', 'send_return',
        'scene_midi', 'rta', 'vocoder', 'looper'} <= index.keys()
    assert not report['all_effects_executable'] and not report['hardware_write_authorized']
    assert report['requires_current_route_and_state_validation']
    assert 'baseline, not live inventory' in report['vocabulary_source']
    assert not {'pid', 'effect_id', 'opcode', 'actions', 'token'} & report.keys()
    assert all(row['purpose'] and row['label'] for row in index.values())
    assert 'feedback' in index['send_return']['purpose']


def test_support_is_route_specific_not_a_global_released_flag():
    reg = registry()
    assert effects.executable(reg, 'amp') == sorted([
        'drive', 'compressor', 'graphic_eq', 'post_eq', 'wah', 'wah_controller', 'delay', 'chorus'])
    assert effects.executable(reg, 'serial') == ['chorus', 'delay']
    assert effects.executable(reg, 'nam') == ['chorus', 'delay', 'reverb']
    assert not rows(reg)['reverb']['executable']
    assert rows(reg, 'nam')['reverb']['executable']
    assert not rows(reg)['parametric_eq']['executable']
    assert not rows(reg)['pitch']['executable']
    for key in ('enhancer', 'filter', 'flanger'):
        assert not rows(reg)[key]['executable']  # A reserve block is not voicing.
    assert rows(reg)['drive']['scope']['models'] == 'T808 Mod'
    assert 'A-D' in rows(reg)['drive']['scope']['channels']
    assert rows(reg)['delay']['scope']['channels'] == 'Shared A'


@pytest.mark.parametrize('firmware,chassis', [
    ('33.00-beta5.20261026', 'mk2'), ('33.01', 'mk2'), ('', 'mk2'),
    (fw33_profile.KEY, 'mk1'), (fw33_profile.KEY, None)])
def test_normal_builder_does_not_inherit_unaccepted_firmware_or_chassis(firmware, chassis):
    reg = registry(firmware, chassis)
    for mode in ('amp', 'nam', 'serial'):
        assert effects.executable(reg, mode) == []
        assert all(not r['executable'] and r['scope'] is None
            and r['limitation'] for r in rows(reg, mode).values())
    assert '33.00-beta5.20261026' not in SUPPORTED_FIRMWARE


def test_legacy_profile_retains_its_effects_without_inheriting_later_models():
    index = rows(registry('32.06'))
    assert index['parametric_eq']['executable']
    assert 'Existing' in index['parametric_eq']['scope']['models']
    assert 'Rat Distortion' in index['drive']['scope']['models']
    assert not index['flanger']['executable']


@pytest.mark.parametrize('module,flag,feature', [
    (fw33_profile, 'DRIVE_RELEASED', 'drive'),
    (effect_voicing, 'COMPRESSOR_RELEASED', 'compressor'),
    (effect_voicing, 'GEQ_RELEASED', 'graphic_eq'),
    (wah_voicing, 'RELEASED', 'wah_controller')])
def test_feature_acceptance_still_controls_planner_facts(monkeypatch, module, flag, feature):
    monkeypatch.setattr(module, flag, False)
    index = rows(registry())
    assert not index[feature]['executable']
    if feature == 'graphic_eq':
        assert not index['post_eq']['executable']


def test_reference_is_fresh_data_not_mutable_permission_state():
    reg = registry()
    report = effects.reference(reg)
    report['effects'][0]['executable'] = False
    report['effects'][0]['scope']['models'] = 'Any model'
    assert rows(reg)['drive']['executable']
    assert rows(reg)['drive']['scope']['models'] == 'T808 Mod'
    with pytest.raises(ValueError):
        effects.reference(reg, 'anything')


def test_concrete_designers_receive_the_same_route_scoped_catalog():
    reg = registry()
    for text, mode in ((album_planning.reference(reg), 'amp'),
            (serial_planning.reference(reg), 'serial'),
            (nam_planning.reference(reg, {'nam': None}), 'nam')):
        assert json.loads(text)['effect_catalog'] == effects.reference(reg, mode)


def test_album_reference_cannot_advertise_released_booleans_on_beta5_or_mk1():
    for reg in (registry('33.00-beta5.20261026'), registry(chassis='mk1')):
        facts = json.loads(album_planning.reference(reg))
        for key in ('drive_executable', 'compressor_executable', 'geq_executable',
                'wah_executable', 'tempo_none_executable', 'amp_exact_zero_executable'):
            assert facts[key] is False
        assert facts['models'] == [] and facts['controls'] == {}


def test_route_exploration_gets_catalog_and_independent_route_scopes():
    ask = Mock(side_effect=lambda *a, **k: k['validate'](dict(recommended='amp',
        reason='A useful amp approach', amp_direction='British clean',
        nam_query='British clean', pedals=['phaser'])))
    result = route_options.compare(ask, 'A clean phaser sound', registry())
    facts = json.loads(ask.call_args.args[2])
    assert not facts['write_authorized'] and result['readonly']
    assert len(facts['effect_catalog']['effects']) == 40
    assert 'reverb' in facts['executable_effects_by_route']['nam']
    assert 'reverb' not in facts['executable_effects_by_route']['amp']
    assert 'phaser' not in facts['executable_effects_by_route']['amp']
    assert effects.RULES in ask.call_args.kwargs['system']


@pytest.mark.parametrize('feature', list(effects.EFFECTS))
def test_every_effect_requirement_survives_both_schemas(feature):
    goal = dict(scene=1, target='A passage tone', role='Lead', realization='Purposeful effect',
        required_features=[feature])
    assert scene_intent.Goal.model_validate(goal).required_features == [feature]
    raw = brief(); raw['scenes'][0]['required_features'] = [feature]
    assert scene_contract.validate(raw, 4, 'Four scenes')['scenes'][0]['required_features'] == [feature]


@pytest.mark.parametrize('feature', ['unlisted', 'GLOBAL', 'store', 'set_param'])
def test_arbitrary_or_operational_keys_are_not_effect_requirements(feature):
    with pytest.raises(ValueError):
        scene_intent.Goal.model_validate(dict(scene=1, target='A passage tone',
            role='Lead', realization='Not executable', required_features=[feature]))


@pytest.mark.parametrize('feature', ['flanger', 'phaser', 'pitch', 'volume_controller',
    'send_return', 'scene_midi', 'enhancer', 'dynamic_distortion'])
def test_unsupported_effect_cannot_disappear_from_a_compiled_scene(monkeypatch, feature):
    dev = device(monkeypatch)
    raw = short_design(4)
    raw['scene_goals'][0]['required_features'] = [feature]
    with pytest.raises(scene_intent.MissingFeature, match=feature):
        album_planning.compile_design(dev.reg, raw, list(serial_build.ROUTE), 4)
    dev._write.assert_not_called()


@pytest.mark.parametrize('feature', ['delay', 'chorus', 'reverb', 'drive', 'compressor'])
def test_bypassed_or_dry_effect_is_not_realized(feature):
    sound = dict(effects={feature: dict(active=True, mix=20., depth=25.)})
    assert effects.realized(feature, sound, None)
    for change in (dict(active=False), dict(mix=0.)):
        copy = deepcopy(sound); copy['effects'][feature].update(change)
        assert not effects.realized(feature, copy, None)
    if feature == 'chorus':
        sound['effects'][feature]['depth'] = 0.
        assert not effects.realized(feature, sound, None)


@pytest.mark.parametrize('feature', ['delay', 'chorus'])
def test_supported_required_wet_effect_compiles_and_dry_mix_is_refused(monkeypatch, feature):
    dev = device(monkeypatch)
    raw = short_design(4)
    raw['scene_goals'][1]['required_features'] = [feature]
    plan = album_planning.compile_design(dev.reg, raw, list(serial_build.ROUTE), 4)
    assert plan['scene_intent']['goals'][1]['required_features'] == [feature]
    raw[feature]['mix'] = 0.
    with pytest.raises(scene_intent.MissingFeature, match=feature):
        album_planning.compile_design(dev.reg, raw, list(serial_build.ROUTE), 4)
    dev._write.assert_not_called()


def test_flat_eq_and_level_only_pitch_are_not_required_tonal_effects():
    sound = dict(effects=dict(geq=dict(active=True, gains=[0.]*10),
        pitch=dict(active=True, level=0.)))
    assert not effects.realized('graphic_eq', sound, None)
    assert not effects.realized('post_eq', sound, None)
    assert not effects.realized('pitch', sound, None)
    sound['effects']['geq']['gains'][2] = -2.
    assert effects.realized('graphic_eq', sound, None)
    assert effects.realized('post_eq', sound, None)
    sound = dict(effects=dict(peq=dict(active=True, bands=[dict(gain=-2.)])))
    assert effects.realized('parametric_eq', sound, None)


def test_registered_scene_brief_and_concrete_plan_share_catalog(workspace):
    client, dev, ask, raw = workspace
    sequence(ask, brief(), dict(proposal=raw, clarification=None))
    response = client.post('/api/axefx3/plan', json=BODY)
    assert response.status_code == 200, response.text
    first, second = [json.loads(call.args[2]) for call in ask.call_args_list]
    assert first['effect_catalog'] == second['effect_catalog']
    assert len(first['effect_catalog']['effects']) == 40
    dev._write.assert_not_called(); dev.store_preset.assert_not_called()


def test_registered_flow_keeps_missing_phaser_in_frozen_brief(workspace):
    client, dev, ask, raw = workspace
    contract = brief(); contract['scenes'][0]['required_features'] = ['phaser']
    question = dict(proposal=None, clarification=dict(message='Phaser execution is not available.',
        questions=[dict(id='phaser', text='Use chorus instead?',
            suggestions=['Use chorus', 'Keep the phaser requirement'])]))
    # Initial design and one bounded self-correction cannot discard the brief.
    sequence(ask, contract, raw, raw, question['clarification'])
    response = client.post('/api/axefx3/plan', json=BODY)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['needs_clarification'] and 'phaser' in json.dumps(result).lower()
    assert result['intake']['questions'][0]['kind'] == 'answer'
    assert 'phaser' in result['design_validation_issue'] and ask.call_count == 4
    assert not result.get('actions') and not result.get('token')
    dev._write.assert_not_called(); dev.store_preset.assert_not_called()

"""Eight-scene compilation proves channel safety, not FW33 hardware support."""
import copy
import json

import pytest
from pydantic import ValidationError

from devices.axefx3 import executor, fw33_profile, planning, scene_channels, tone_ui
from devices.axefx3.registry import Registry
from tests.test_axefx3_text_planning import api, dev, design


def albums(design):
    result = copy.deepcopy(design)
    result['name'] = 'Metallica albums'
    result['scenes'] = []
    for number, template in enumerate(design['scenes']):
        for role in ('Lead', 'Solo'):
            scene = copy.deepcopy(template)
            scene['name'] = f'Album {number+1} {role}'
            scene['wah'] = False
            scene['output_level'] = -9 if role == 'Lead' else -6
            scene['delay']['active'] = role == 'Solo'
            result['scenes'].append(scene)
    return result


def channel_values(plan, family):
    return [a['value'] for a in plan['actions']
            if a['kind'] == 'set_channel' and a.get('block') == family]


def test_album_pairs_compile_eight_scenes_with_four_amp_channels(dev, design):
    plan = planning.compile_design(dev.reg, albums(design), [], 8)
    assert plan['name'] == 'AI-Metallica albums'
    assert len(plan['scenes']) == 8
    assert channel_values(plan, 'DISTORT') == [0, 0, 1, 1, 2, 2, 3, 3]
    assert channel_values(plan, 'DELAY') == [0, 0, 1, 1, 2, 2, 3, 3]
    assert channel_values(plan, 'REVERB') == [0]*8
    assert channel_values(plan, 'OUTPUT') == [0, 1]*4
    assert channel_values(plan, 'CABINET') == [0]*8
    assert sum(a.get('param') == 'DISTORT_DRIVE' for a in plan['actions']) == 4
    assert sum(a['kind'] == 'set_type' and a.get('block') == 'DISTORT'
               for a in plan['actions']) == 4
    assert [a['value'] for a in plan['actions'] if a.get('param') == 'OUTPUT_LEVEL'] == [-9, -6]
    assert [a['bypassed'] for a in plan['actions']
            if a['kind'] == 'set_bypass' and a['block'] == 'DELAY'] == [True, True, True, False]*4
    assert [a['value'] for a in plan['actions'] if a['kind'] == 'set_scene'] == list(range(1, 9))
    assert not any(a['kind'] in ('store', 'select_preset') for a in plan['actions'])
    executor.prepare(dev, plan['actions'], plan['required_route'], 324)
    dev._write.assert_not_called()


def test_four_distinct_album_models_and_cabs_can_be_chosen(dev, design):
    raw = albums(design)
    names = list(dev.reg.selectable_amp_models().values())[:4]
    dev.reg.import_cab_names('\n'.join(f'U1.{i+1:04d} Album Cab {i+1}' for i in range(4)), 'user')
    for i, scene in enumerate(raw['scenes']):
        scene['amp_model'] = names[i//2]
        scene['cab_left'] = dict(bank=2, slot=i//2+1)
        scene['cab_right'] = None
    plan = planning.compile_design(dev.reg, raw, [], 8)
    assert [a['type_name'] for a in plan['actions']
            if a['kind'] == 'set_type' and a['block'] == 'DISTORT'] == names
    assert channel_values(plan, 'CABINET') == [0, 0, 1, 1, 2, 2, 3, 3]
    assert [a['value'] for a in plan['actions'] if a['kind'] == 'set_cab'] == [0, 1, 2, 3]
    assert [s['choices'][0]['name'] for s in plan['scene_cabs']] == [f'Album Cab {i//2+1}' for i in range(8)]
    dev._write.assert_not_called()


def test_shared_channel_has_one_consistent_stored_configuration(dev, design):
    plan = planning.compile_design(dev.reg, albums(design), [], 8)
    selected, writes = {}, {}
    for action in plan['actions']:
        if action['kind'] == 'set_scene':
            selected.clear()
        elif action['kind'] == 'set_channel':
            assert 0 <= action['value'] <= 3
            selected[action['block']] = action['value']
        elif action['kind'] in ('set_param', 'set_type'):
            key = (action['block'], selected[action['block']], action['kind'], action.get('param'))
            assert key not in writes
            writes[key] = action.get('value', action.get('type_name'))


@pytest.mark.parametrize('family,attr', [('Amp', 'amp'), ('Delay', 'delay'), ('Reverb', 'reverb')])
def test_fifth_unique_voice_is_rejected_not_silently_overwritten(dev, design, family, attr):
    raw = albums(design)
    field = {'amp': 'gain', 'delay': 'time_ms', 'reverb': 'time_s'}[attr]
    for i, scene in enumerate(raw['scenes']):
        scene[attr][field] = i+1
    with pytest.raises(ValueError, match=f'{family}: more than four'):
        planning.compile_design(dev.reg, raw, [], 8)
    dev._write.assert_not_called()


@pytest.mark.parametrize('family', ['CABINET', 'OUTPUT', 'CHORUS', 'FUZZ', 'COMP', 'GEQ', 'PEQ'])
def test_other_fifth_channel_configurations_are_refused(dev, design, family):
    raw = albums(design)
    dev.reg.import_cab_names('\n'.join(f'U1.{i+1:04d} Cab {i+1}' for i in range(8)), 'user')
    for i, scene in enumerate(raw['scenes']):
        if family == 'CABINET': scene['cab_left'] = dict(bank=2, slot=i+1)
        if family == 'OUTPUT': scene['output_level'] = -6-i
        if family == 'CHORUS': scene['chorus'] = dict(active=True, rate_hz=.2+i*.1, depth=25, mix=12)
        if family == 'FUZZ': scene['drive'] = dict(active=True, drive=i, tone=5, mix=100, level=2)
        if family == 'COMP': scene['compressor'] = dict(active=True, threshold=-30, ratio=i+1, attack_ms=5, release_ms=250, mix=75, level=-12)
        if family == 'GEQ': scene['geq'] = dict(active=True, gains=[-i]*10, level=-6)
        if family == 'PEQ': scene['peq'] = dict(active=True, bands=[dict(frequency_hz=f, gain=-i) for f in (200, 400, 800, 1600, 3200)], level=-6)
    label = {'CABINET': 'Cab', 'OUTPUT': 'Output', 'CHORUS': 'Chorus'}.get(family, family)
    with pytest.raises(ValueError, match=f'{label}: more than four'):
        planning.compile_design(dev.reg, raw, [37,58,62,50,54,70,66,42], 8)
    dev._write.assert_not_called()


@pytest.mark.parametrize('count', [5, 6, 7, 8])
def test_all_new_scene_counts_remain_within_four_channels(dev, design, count):
    raw = albums(design)
    raw['scenes'] = raw['scenes'][:count]
    plan = planning.compile_design(dev.reg, raw, [], count)
    assert len(plan['scenes']) == count
    assert all(0 <= value <= 3 for channels in plan['scene_channels'].values() for value in channels)
    executor.prepare(dev, plan['actions'], plan['required_route'], 324)


def test_optional_pedals_share_voicing_but_not_scene_bypass(dev, design):
    raw = albums(design)
    for i, scene in enumerate(raw['scenes']):
        scene['drive'] = dict(active=i%2 == 1, drive=4, tone=5, mix=100, level=2)
        scene['compressor'] = dict(active=i%2 == 1, threshold=-30, ratio=4,
                                   attack_ms=5, release_ms=250, mix=75, level=-12)
        scene['chorus'] = dict(active=i%2 == 1, rate_hz=.7, depth=25, mix=12)
    plan = planning.compile_design(dev.reg, raw, [], 8)
    for family in ('FUZZ', 'COMP', 'CHORUS'):
        assert channel_values(plan, family) == [0]*8
        assert sum(a['kind'] == 'set_type' and a.get('block') == family
                   for a in plan['actions']) == 1
    executor.prepare(dev, plan['actions'], plan['required_route'], 324)
    dev._write.assert_not_called()


def test_unrequested_new_effect_scenes_do_not_overwrite_its_channel(dev, design):
    raw = albums(design)
    raw['scenes'][7]['drive'] = dict(active=True, drive=4, tone=5, mix=100, level=2)
    plan = planning.compile_design(dev.reg, raw, [], 8)
    assert channel_values(plan, 'FUZZ') == [0]*8
    assert sum(a.get('param') == 'FUZZ_DRIVE' for a in plan['actions']) == 1
    executor.prepare(dev, plan['actions'], plan['required_route'], 324)


@pytest.mark.parametrize('bad', ['model', 'cab', 'right_only', 'volume', 'nan', 'nine'])
def test_invalid_album_designs_fail_without_writes(dev, design, bad):
    raw = albums(design)
    if bad == 'model': raw['scenes'][7]['amp_model'] = 'Imaginary model'
    if bad == 'cab': raw['scenes'][7]['cab_left'] = dict(bank=2, slot=999)
    if bad == 'right_only': raw['scenes'][7]['cab_right'] = dict(bank=2, slot=28)
    if bad == 'volume': raw['scenes'][7]['output_level'] = 3
    if bad == 'nan': raw['scenes'][7]['output_level'] = float('nan')
    if bad == 'nine': raw['scenes'].append(copy.deepcopy(raw['scenes'][0]))
    with pytest.raises(ValueError): planning.compile_design(dev.reg, raw, [], 8)
    dev._write.assert_not_called()


def test_request_schema_accepts_eight_but_not_nine_or_bool():
    assert tone_ui.Request(prompt='Metallica albums', expected_preset=326, mode='amp', scenes=8).scenes == 8
    for value in (0, 9, True, 8.0, '8'):
        with pytest.raises(ValidationError):
            tone_ui.Request(prompt='Metallica albums', expected_preset=326, scenes=value)


def test_allocator_ignores_dictionary_order_but_preserves_all_values():
    assert scene_channels.allocate([{'x': 1, 'y': 2}, {'y': 2, 'x': 1}], 'Amp') == [0, 0]
    assert scene_channels.allocate([None, {'x': 1}, None, {'x': 2}], 'Drive') == [0, 0, 0, 1]
    assert scene_channels.allocate([1, 1, 1, 1], 'Amp', independent=True) == [0, 1, 2, 3]
    with pytest.raises(ValueError): scene_channels.allocate([], 'Amp')
    with pytest.raises(ValueError): scene_channels.allocate([1]*9, 'Amp')


def test_eight_scenes_use_normal_review_send_in_simulation(api, dev, design):
    client, ask = api
    design.update(albums(design))
    response = client.post('/api/axefx3/plan', json=dict(prompt='Metallica albums', expected_preset=324, mode='amp', scenes=8))
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data['scenes']) == 8 and data['scene_channels']['DISTORT'] == [0, 0, 1, 1, 2, 2, 3, 3]
    assert 'Exactly 8 scenes' in ask.call_args.args[0]
    proposal=json.loads(ask.call_args.kwargs['shape'])['properties']['proposal']['anyOf'][0]
    assert proposal['properties']['scenes']['maxItems'] == 8
    sent = client.post('/api/axefx3/send', json=dict(token=data['token'], target_confirmed=True, external_audio_muted=True))
    assert sent.status_code == 200 and sent.json()['ok'], sent.text
    assert dev.set_scene.call_args_list[-1].args == (8,)
    dev.store_preset.assert_not_called()


def test_unreleased_fw33_scene_count_is_refused_before_ai(api, dev,monkeypatch):
    monkeypatch.setattr(fw33_profile,'ALBUM_SCENE_COUNTS',frozenset({8}))
    client, ask = api
    dev.reg = Registry(fw33_profile.KEY)
    dev.reg.hardware_variant = 'mk2'
    dev.firmware_label.return_value = fw33_profile.KEY
    response = client.post('/api/axefx3/plan', json=dict(prompt='Metallica albums', expected_preset=324, mode='amp', scenes=4))
    assert response.status_code == 409, response.text
    assert 'released scene counts' in response.text and 'no NAM/controller' in response.text
    ask.assert_not_called()
    dev.edit_session.assert_not_called()
    dev._write.assert_not_called()


def test_state_advertises_request_capacity_separately_from_firmware_support(api, dev):
    client, _ = api
    state = client.get('/api/axefx3/state').json()
    assert state['request_scene_limit'] == 8
    assert state['multiscene_planning_supported'] is True

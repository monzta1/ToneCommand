"""Synthetic complete observations, opaque data and injected read settling."""
import ast
from copy import deepcopy
import inspect
from unittest.mock import Mock

import pytest

from devices.axefx3 import preset_observation as obs, protocol
from devices.axefx3.observed_words import Broadcast, assemble
from tests.axefx3_beta5_identity import BETA5
from tests.test_axefx3_observed_words import burst


@pytest.fixture
def raw(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports', lambda *a, **k: pytest.fail('No physical MIDI'))
    ids = (58, 62, 203, 200, 201)
    counts = {58: 568, 62: 424, 203: 4, 200: 1525, 201: 350}
    bulk = {str(eid): assemble(burst(eid, (65535, *([eid] * (counts[eid] - 1)))), eid) for eid in ids}
    mods = [assemble(burst(eid, (0,) * 8 + (78, 77) + (999,) * 15), eid) for eid in range(3, 35)]
    return dict(identity=BETA5, variant='mk2', firmware='33.00-beta5.20261026',
        preset=[323, 'Original name '], scene=2, scenes=[[n, f'Original {n}'] for n in range(1, 9)],
        status=[dict(effect_id=e, channel=0, bypassed=False, channels_supported=1 if e >= 200 else 4) for e in ids],
        grid=[dict(row=3, col=col, effect_id=eid, is_shunt=False, cable_in_mask=0 if col == 0 else 16)
              for col, eid in enumerate((58, 62, 203))]
             + [dict(row=5, col=13, effect_id=None, is_shunt=True, cable_in_mask=126)],
        bulk=bulk, modifiers=mods)


def test_observation_preserves_every_opaque_word_and_original_structure(raw):
    initial = deepcopy(raw)
    value = obs.observe(raw)
    data = value.data()
    assert data['preset'] == [323, 'Original name '] and data['scene'] == 2
    assert data['bulk']['203'] == [65535, 203, 203, 203]
    assert len(data['bulk']['200']) == 1525 and len(data['bulk']['201']) == 350
    assert data['broadcast_counts']['58'] == 568
    assert data['modifiers'][0] == [0] * 8 + [78, 77] + [999] * 15
    assert data['grid'][-1]['is_shunt'] and data['grid'][-1]['cable_in_mask'] == 126
    assert raw == initial and len(value.digest) == 64
    assert 'Original name' not in repr(value) and '65535' not in repr(value)
    data['bulk']['203'][0] = 0
    raw['preset'][1] = 'Later name'
    assert value.data()['bulk']['203'][0] == 65535 and value.data()['preset'][1] == 'Original name '


def test_status_and_cell_order_are_not_parameter_or_modifier_order(raw):
    first = obs.observe(raw)
    raw['status'].reverse(); raw['grid'].reverse()
    assert obs.observe(raw) == first
    words = list(raw['modifiers'][0].words); words[10] += 1
    raw['modifiers'][0] = Broadcast(3, 25, tuple(words))
    assert obs.observe(raw).digest != first.digest


@pytest.mark.parametrize('surface', sorted(obs.FIELDS))
def test_missing_surface_is_not_default_filled(raw, surface):
    del raw[surface]
    with pytest.raises(ValueError): obs.observe(raw)


@pytest.mark.parametrize('fault', ['extra', 'identity', 'bad_checksum', 'preset_bool',
    'scene_bool', 'missing_name', 'reordered_names', 'unread_name', 'blank_firmware',
    'duplicate_block', 'no_system', 'channel', 'channel_count', 'bypass_int',
    'missing_grid', 'duplicate_position', 'duplicate_instance', 'bad_mask',
    'bool_mask', 'bad_row', 'bool_row', 'shunt_id', 'unknown_empty_cell',
    'no_bulk', 'extra_bulk', 'numeric_key', 'wrong_bulk_target', 'raw_words',
    'missing_modifier', 'modifier_order', 'short_modifier', 'raw_modifier'])
def test_incomplete_or_incoherent_observations_fail_closed(raw, fault):
    if fault == 'extra': raw['unknown_surface'] = 'not silently discarded'
    elif fault == 'identity': raw['identity'] = protocol.envelope(19, [33, 1])[1:-1]
    elif fault == 'bad_checksum': raw['identity'] = [*BETA5[:-1], BETA5[-1] ^ 1]
    elif fault == 'preset_bool': raw['preset'][0] = True
    elif fault == 'scene_bool': raw['scene'] = True
    elif fault == 'missing_name': raw['scenes'].pop()
    elif fault == 'reordered_names': raw['scenes'].reverse()
    elif fault == 'unread_name': raw['scenes'][0][1] = None
    elif fault == 'blank_firmware': raw['firmware'] = ''
    elif fault == 'duplicate_block': raw['status'].append(deepcopy(raw['status'][0]))
    elif fault == 'no_system': raw['status'].pop()
    elif fault == 'channel': raw['status'][0]['channel'] = 4
    elif fault == 'channel_count': raw['status'][0]['channels_supported'] = True
    elif fault == 'bypass_int': raw['status'][0]['bypassed'] = 0
    elif fault == 'missing_grid': raw['grid'].pop(0)
    elif fault == 'duplicate_position': raw['grid'][1]['col'] = 0
    elif fault == 'duplicate_instance': raw['grid'][1]['effect_id'] = 58
    elif fault == 'bad_mask': raw['grid'][0]['cable_in_mask'] = 1
    elif fault == 'bool_mask': raw['grid'][0]['cable_in_mask'] = True
    elif fault == 'bad_row': raw['grid'][0]['row'] = 6
    elif fault == 'bool_row': raw['grid'][0]['row'] = False
    elif fault == 'shunt_id': raw['grid'][-1]['effect_id'] = 58
    elif fault == 'unknown_empty_cell': raw['grid'][0]['effect_id'] = None
    elif fault == 'no_bulk': del raw['bulk']['203']
    elif fault == 'extra_bulk': raw['bulk']['204'] = Broadcast(204, 1, (1,))
    elif fault == 'numeric_key': raw['bulk'][203] = raw['bulk'].pop('203')
    elif fault == 'wrong_bulk_target': raw['bulk']['203'] = Broadcast(204, 1, (1,))
    elif fault == 'raw_words': raw['bulk']['203'] = [65535, 203, 203, 203]
    elif fault == 'missing_modifier': raw['modifiers'].pop()
    elif fault == 'modifier_order': raw['modifiers'].reverse()
    elif fault == 'short_modifier': raw['modifiers'][0] = Broadcast(3, 24, (0,) * 24)
    elif fault == 'raw_modifier': raw['modifiers'][0] = [0] * 25
    with pytest.raises(ValueError): obs.observe(raw)


@pytest.mark.parametrize('variant,slot,valid', [('mk1', 511, True), ('mk1', 512, False),
    ('mk2', 1023, True), ('turbo', 1023, True), ('mk2', 1024, False), ('mk2', -1, False)])
def test_declared_capacity_does_not_promote_writes(raw, variant, slot, valid):
    raw.update(variant=variant, preset=[slot, 'Read only'])
    if valid: assert obs.observe(raw).data()['preset'][0] == slot
    else:
        with pytest.raises(ValueError): obs.observe(raw)


def test_empty_preset_is_observed_not_rebuilt(raw):
    raw['status'] = [b for b in raw['status'] if b['effect_id'] in (200, 201)]
    raw['bulk'] = {k: v for k, v in raw['bulk'].items() if k in ('200', '201')}
    raw['grid'] = []
    assert obs.observe(raw).data()['grid'] == []


def test_two_equal_fresh_reads_are_required(raw):
    reader = Mock(side_effect=lambda: deepcopy(raw))
    result = obs.capture(reader)
    assert reader.call_count == 2 and result == obs.observe(raw)


def test_only_complete_unequal_readings_settle_again(raw):
    changed = deepcopy(raw)
    changed['bulk']['203'] = Broadcast(203, 4, (65535, 8, 9, 10))
    reader = Mock(side_effect=[raw, changed, deepcopy(changed)])
    assert obs.capture(reader).data()['bulk']['203'] == [65535, 8, 9, 10]
    assert reader.call_count == 3


@pytest.mark.parametrize('change', ['preset', 'scene', 'identity', 'variant'])
def test_target_drift_stops_without_settling_on_the_new_target(raw, change):
    changed = deepcopy(raw)
    if change == 'preset': changed['preset'][0] += 1
    elif change == 'scene': changed['scene'] = 3
    elif change == 'identity': changed['identity'] = protocol.envelope(8, [33, 1])[1:-1]
    else: changed['variant'] = 'mk1'
    reader = Mock(side_effect=[raw, changed, changed])
    with pytest.raises(ValueError, match='target changed'): obs.capture(reader)
    assert reader.call_count == 2


@pytest.mark.parametrize('error', [OSError('read failed'), ValueError('missing packet')])
def test_read_errors_are_not_hidden_by_cached_or_default_state(raw, error):
    reader = Mock(side_effect=[raw, error, raw])
    with pytest.raises(type(error)): obs.capture(reader)
    assert reader.call_count == 2


def test_unstable_complete_state_is_bounded(raw):
    def read():
        raw['preset'][1] += '.'
        return deepcopy(raw)
    reader = Mock(side_effect=read)
    with pytest.raises(ValueError, match='did not settle'): obs.capture(reader, max_reads=3)
    assert reader.call_count == 3


@pytest.mark.parametrize('bound', [True, 1, 9, 2., '4'])
def test_bad_read_bound_fails_before_the_callback(raw, bound):
    reader = Mock(return_value=raw)
    with pytest.raises(ValueError): obs.capture(reader, max_reads=bound)
    reader.assert_not_called()


def test_no_transport_or_model_permission_is_imported_or_released():
    tree = ast.parse(inspect.getsource(obs))
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert all(m not in ('server', 'mido', 'fm9.device', 'fm9.planner', 'amp_writer') for m in modules)
    assert not hasattr(obs, 'register') and not hasattr(obs, 'send')
    assert not protocol.allowed(protocol.envelope(31, [58, 0]))
    assert not protocol.allowed(protocol.envelope(1, [46]))

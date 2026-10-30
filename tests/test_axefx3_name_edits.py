"""Pure rename proposals plus proof the actual output guard still refuses them."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import mido
import pytest

from devices.axefx3 import readonly_protocol as protocol
from devices.axefx3.readonly_adapter import AxeFxIII, ReadOnlyOutput, snapshot
from devices.axefx3.name_edits import NameEdit
from fm9 import protocol as shared
from fm9.device import ReadOnly
from fm9.safety import BrickGuardRefusal
from tests.test_axefx3_readonly import FakePorts


@pytest.fixture
def state():
    return dict(connected=True, declared_chassis='mk2', preset_count=1024,
                firmware='97.00', preset=dict(number=323, editor=323, name='Old preset'),
                scene=dict(number=1, name='Scene 1'),
                scenes=[dict(number=n, name=f'Scene {n}') for n in range(1, 9)],
                blocks=[dict(effect_id=58, channel='A', bypassed=True)],
                read_only=True, values={}, params={}, mods=[], cab_sel=None,
                navigation_read_only=True, gig_mode=False)


@pytest.mark.parametrize('name', ['', ' ', ' Leading', 'Trailing ', 'x' * 32,
                                  'line\nfeed', 'nul\0name', 'tab\tname', 'Mötley',
                                  '\x7f', None, 12, True])
def test_invalid_names_are_refused_instead_of_silently_changed(name):
    with pytest.raises(ValueError):
        NameEdit(323, name)


@pytest.mark.parametrize('preset', [-1, 1024, True, 1.0, '323', None])
def test_invalid_preset_targets_are_not_coerced(preset):
    with pytest.raises(ValueError):
        NameEdit(preset, 'Name')


@pytest.mark.parametrize('scene', [0, 9, True, 1.0, '1', [], {}])
def test_scene_targets_are_one_based_integers(scene):
    with pytest.raises(ValueError):
        NameEdit(323, 'Name', scene)


@pytest.mark.parametrize('scene', [None, *range(1, 9)])
def test_only_product_byte_and_checksum_differ_from_shared_name_codec(scene):
    edit = NameEdit(323, 'Name with / and "quotes"', scene)
    original = (shared.build_rename_preset(edit.name) if scene is None else
                shared.build_set_scene_name(scene - 1, edit.name))
    frame = edit.frame()
    assert frame[4] == 0x10 and original[4] == 0x12
    assert frame[5:-2] == original[5:-2]
    assert frame[-2] == shared.checksum(frame[1:-2])
    assert frame[6] == (0x28 if scene is None else 0x2B)
    assert shared.decode14(*frame[10:12]) == (0 if scene is None else scene - 1)
    assert protocol.valid_reply(frame[1:-1])


@pytest.mark.parametrize('scene', [None, 1, 2, 8])
def test_every_compiled_name_write_is_still_refused_at_final_output(scene):
    edit = NameEdit(323, 'Name', scene)
    frame = edit.frame()
    for chassis in ('mk1', 'mk2', 'turbo'):
        assert not protocol.allowed(frame, chassis)
        raw = SimpleNamespace(send=lambda message: pytest.fail('A name SET reached MIDI'))
        with pytest.raises((ReadOnly, BrickGuardRefusal)):
            ReadOnlyOutput(raw, chassis).send(mido.Message('sysex', data=frame[1:-1]))


@pytest.mark.parametrize('scene', [None, 1, 2, 8])
def test_renaming_changes_only_the_requested_observable_name(state, scene):
    original = deepcopy(state)
    edit = NameEdit(323, 'AI-Name', scene)
    wanted = edit.expected_after(state)
    assert state == original
    assert edit.verify(state, wanted)
    assert edit.preview(state)['executable'] is False
    assert edit.preview(state)['stored'] is False
    assert edit.preview(wanted)['changes'] is False
    assert wanted['blocks'] == state['blocks']
    assert wanted['scene']['number'] == state['scene']['number']
    if scene is None:
        assert wanted['preset']['name'] == 'AI-Name'
        assert wanted['scenes'] == state['scenes']
    else:
        assert wanted['preset'] == state['preset']
        assert wanted['scenes'][scene - 1]['name'] == 'AI-Name'
        assert wanted['scene']['name'] == ('AI-Name' if scene == 1 else 'Scene 1')
    with pytest.raises(FrozenInstanceError):
        edit.name = 'Different'


@pytest.mark.parametrize('corruption', ['name', 'preset', 'scene', 'other_scene',
                                      'channel', 'bypass', 'firmware', 'chassis',
                                      'capacity', 'disconnected', 'missing_name'])
def test_incorrect_or_incomplete_readback_never_passes(state, corruption):
    edit = NameEdit(323, 'Name')
    after = edit.expected_after(state)
    if corruption == 'name': after['preset']['name'] = 'Wrong'
    elif corruption == 'preset': after['preset'].update(number=324, editor=324)
    elif corruption == 'scene': after['scene'].update(number=2, name='Scene 2')
    elif corruption == 'other_scene': after['scenes'][1]['name'] = 'Changed'
    elif corruption == 'channel': after['blocks'][0]['channel'] = 'B'
    elif corruption == 'bypass': after['blocks'][0]['bypassed'] = False
    elif corruption == 'firmware': after['firmware'] = 'Unknown'
    elif corruption == 'chassis': after['declared_chassis'] = 'mk1'
    elif corruption == 'capacity': after['preset_count'] = 512
    elif corruption == 'disconnected': after['connected'] = False
    elif corruption == 'missing_name': after['scenes'][3]['name'] = None
    with pytest.raises(ValueError):
        edit.verify(state, after)


def test_incomplete_before_state_and_wrong_target_fail_closed(state):
    edit = NameEdit(323, 'Name')
    for bad in (None, {}, {'connected': True}, dict(state, scenes=[])):
        with pytest.raises(ValueError):
            edit.preview(bad)
    with pytest.raises(ValueError):
        NameEdit(324, 'Name').preview(state)
    mk1 = deepcopy(state)
    mk1['declared_chassis'], mk1['preset_count'] = 'mk1', 512
    mk1['preset'].update(number=512, editor=512)
    with pytest.raises(ValueError):
        NameEdit(512, 'Name').preview(mk1)


def test_contract_works_on_a_real_adapter_snapshot_without_sending_any_set():
    ports = FakePorts()
    dev = AxeFxIII((ports.inp, ports.outp))
    try:
        before = snapshot(dev)
        sent = list(ports.sent)
        edit = NameEdit(320, 'AI-Test')
        assert edit.preview(before)['changes']
        assert edit.verify(before, edit.expected_after(before))
        assert ports.sent == sent
        assert not dev.capabilities().can_rename
        assert not dev.capabilities().can_verify
        assert not dev.capabilities().stores_presets
        with pytest.raises((ReadOnly, BrickGuardRefusal)):
            dev._send(edit.frame())
        assert ports.sent == sent
    finally:
        dev.close()


@pytest.mark.parametrize('blocks', [[{}], [None],
    [dict(effect_id=True, channel='A', bypassed=True)],
    [dict(effect_id=58, channel='X', bypassed=True)],
    [dict(effect_id=58, channel='A', bypassed=1)],
    [dict(effect_id=58, channel='A', bypassed=True)] * 2])
def test_incomplete_duplicate_or_invalid_blocks_do_not_make_a_baseline(state, blocks):
    state['blocks'] = blocks
    with pytest.raises(ValueError): NameEdit(323, 'New').preview(state)


@pytest.mark.parametrize('scene', range(1, 9))
def test_scene_name_can_be_explicitly_cleared_without_allowing_empty_preset(state, scene):
    edit = NameEdit(323, '', scene)
    assert edit.expected_after(state)['scenes'][scene - 1]['name'] == ''
    with pytest.raises(ValueError): NameEdit(323, '')

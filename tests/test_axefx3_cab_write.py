"""Editor-captured Cab writes, strict Legacy boundary and exact recovery."""
from dataclasses import replace
import threading
from types import MethodType
from unittest.mock import Mock

import pytest

from devices.axefx3 import cab_mix
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from fm9.protocol import decode_f32_septets


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(cab_mix.time, 'sleep', lambda _: None)
    dev = Mock(model=16)
    dev.reg = Registry('32.06')
    dev._lock = threading.RLock()
    dev.firmware_label.return_value = '32.06'
    dev.get_channel.return_value = 0
    words = ([0]*8 + [65534]*4 + [32767]*4 + [0]*8 + [0,1,1,1] + [0]*78)*4
    assert len(words) == 424
    dev.bulk_read.side_effect = lambda eid: words.copy()
    def shown(eid, pid):
        word = words[dev.get_channel(eid)*106+pid]
        if pid in range(8,12): return f'{-40+40*word/65534:.2f} dB'
        if pid in range(12,16): return f'{-100+200*word/65534:.1f}'
        return cab_mix.DISPLAY_MODES[word]
    dev.read_display_text.side_effect = shown
    def send(frame, eid, pid, **kwargs):
        assert frame[6:8] == [9, 0]
        value = decode_f32_septets(frame[12:17])
        word = (round((value+40)/40*65534) if pid in range(8,12) else
                round((value+1)/2*65534) if pid in range(12,16) else int(value))
        words[dev.get_channel(eid)*106+pid] = word
    dev._param_echo.side_effect = send
    dev._set_domain_guard = MethodType(AxeFxIII._set_domain_guard, dev)
    dev.set_param_display = MethodType(AxeFxIII.set_param_display, dev)
    dev.set_param_wire = MethodType(AxeFxIII.set_param_wire, dev)
    return dev, words


@pytest.mark.parametrize('channel', range(4))
@pytest.mark.parametrize('slot', range(1,5))
def test_level_pan_mode_and_zero_each_ir_and_channel(rig, channel, slot):
    dev, words = rig
    dev.get_channel.return_value = channel
    original = words.copy()
    for field, targets in [('LEVEL',[-6,-12,-40,0]), ('PAN',[-100,-35,35,100,0]),
                            ('MUTE',[1,0,2,0,original[channel*106+23+slot]])]:
        spec = dev.reg.find_param('CABINET', f'CABINET_{field}{slot}')
        for value in targets:
            result = dev.set_param_display(spec,value)
            assert result.ok, result
            assert abs(result.display_after-value) <= .01
    assert original == words


@pytest.mark.parametrize('slot', range(1,5))
@pytest.mark.parametrize('field,target', [('LEVEL',-6),('PAN',35),('MUTE',2)])
def test_exact_bulk_restore_is_not_a_cab_selection(rig, slot, field, target):
    dev, words = rig
    spec = dev.reg.find_param('CABINET', f'CABINET_{field}{slot}')
    held = words[spec.param_id]
    assert dev.set_param_display(spec,target).ok
    assert dev.set_param_wire(spec,held).ok
    assert words[spec.param_id] == held
    dev.set_param_ordinal.assert_not_called()


@pytest.mark.parametrize('change', [dict(param_id=18), dict(effect_id=58), dict(instance=5),
    dict(dmax=20), dict(set_divisor=100), dict(kind='enum'), dict(unit='numeric'),
    dict(enum_count=99), dict(verify_display_text=False), dict(firmware_versions=('33.00',))])
def test_malformed_spec_cannot_write(rig, change):
    dev, _ = rig
    spec = replace(dev.reg.find_param('CABINET','CABINET_LEVEL1'), **change)
    with pytest.raises((ValueError, KeyError)):
        dev.set_param_display(spec,-6)
    dev._param_echo.assert_not_called()


@pytest.mark.parametrize('issue', ['dynacab','firmware','layout','unknown_display','changed_channel'])
def test_wrong_or_unknown_state_refuses_before_send(rig, issue):
    dev, words = rig
    if issue == 'dynacab': words[31] = 1
    if issue == 'firmware': dev.firmware_label.return_value = '32.04'
    if issue == 'layout': words.pop()
    if issue == 'unknown_display': dev.read_display_text.side_effect = lambda *a: ''
    if issue == 'changed_channel': dev.get_channel.side_effect = [0,1]
    assert not dev.set_param_display(dev.reg.find_param('CABINET','CABINET_LEVEL1'),-6).ok
    dev._param_echo.assert_not_called()


@pytest.mark.parametrize('name,value', [('CABINET_LEVEL1',1), ('CABINET_LEVEL1',-41),
    ('CABINET_LEVEL1',float('nan')), ('CABINET_LEVEL1',True), ('CABINET_PAN1',101),
    ('CABINET_MUTE1',.5), ('CABINET_MUTE1',3), ('CABINET_MUTE1',-1)])
def test_invalid_value_not_sent(rig, name, value):
    dev, _ = rig
    with pytest.raises((ValueError, TypeError)):
        dev.set_param_display(dev.reg.find_param('CABINET',name),value)
    dev._param_echo.assert_not_called()


def test_no_success_on_echo_alone_or_other_channel_change(rig):
    dev, words = rig
    dev._param_echo.side_effect = lambda *a,**k: None
    spec = dev.reg.find_param('CABINET','CABINET_LEVEL1')
    assert not dev.set_param_display(spec,-6).ok
    def corrupt(*a,**k):
        words[8] = 55704
        words[106+8] = 55704
    dev._param_echo.side_effect = corrupt
    assert not dev.set_param_display(spec,-6).ok

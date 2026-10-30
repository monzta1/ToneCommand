"""Synthetic safety checks; hardware evidence is recorded separately."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from fm9.device import SetResult
from devices.axefx3 import nam_selector as selector, fw33, protocol, modifiers
from devices.axefx3.nam_memory import Capture
from tests.test_axefx3_fw33 import fake


@pytest.fixture(autouse=True)
def inactive_modifiers(monkeypatch):
    monkeypatch.setattr(modifiers, 'inspect', lambda _: [dict(active=False, words=[0]*25)]*32)


def device():
    dev = fake(True)
    words = [0]*72
    words[0] = 249
    dev.bulk_read.side_effect = lambda eid: list(words)
    dev.get_channel.return_value = 0
    dev.get_bypass.return_value = True
    dev.read_nam_slot.side_effect = lambda slot: Capture('Synthetic', slot, 'a'*64, 65536)
    def write(frame):
        assert dev._nam_select_permit == tuple(frame)
        fw33.check_frame(dev, frame)
        from fm9.protocol import decode_f32_septets
        words[0] = int(decode_f32_septets(frame[12:17]))
    dev._write.side_effect = write
    return dev, words


def test_frames_equal_independently_captured_editor_bytes():
    assert selector.frame(1) == list(bytes.fromhex('f0 00 01 74 10 01 09 00 4e 01 00 00 00 00 00 00 00 00 00 00 00 52 f7'))
    assert selector.frame(250) == list(bytes.fromhex('f0 00 01 74 10 01 09 00 4e 01 00 00 00 00 64 1b 04 00 00 00 00 29 f7'))
    assert selector.frame(256) == list(bytes.fromhex('f0 00 01 74 10 01 09 00 4e 01 00 00 00 00 7c 1b 04 00 00 00 00 31 f7'))


@pytest.mark.parametrize('slot', [0, 257, True, 250., '250'])
def test_invalid_selector_frame_refused(slot):
    with pytest.raises(ValueError): selector.frame(slot)


@pytest.mark.parametrize('slot', [1,250,256])
def test_raw_selector_needs_exact_scoped_permit(slot):
    dev, _ = device()
    dev._nam_select_permit = None
    with pytest.raises(PermissionError): fw33.check_frame(dev, selector.frame(slot))
    dev._nam_select_permit = tuple(selector.frame(slot))
    fw33.check_frame(dev, selector.frame(slot))
    with pytest.raises(PermissionError): fw33.check_frame(dev, selector.frame(250 if slot!=250 else 256))
    with pytest.raises(PermissionError): fw33.check_frame(dev, protocol.param_frame(206, 0, slot-1, opcode=0x52))


def test_only_full_four_channel_enum_bulk_is_accepted():
    words = [0]*72; words[0]=249; words[18]=255
    assert selector.slots(words) == [250,256,1,1]
    for invalid in (words[:18], [256]*72, [-1]*72, [True]*72, [0.]*72):
        with pytest.raises(ValueError): selector.slots(invalid)


@pytest.mark.parametrize('slot', [1,256])
def test_verified_slot_change_leaves_bypassed_quiet_and_never_installs(monkeypatch,slot):
    monkeypatch.setattr(selector.time, 'sleep', lambda _: None)
    dev, _ = device()
    assert selector.select(dev, slot).ok
    dev._write.assert_called_once_with(selector.frame(slot))
    assert dev._nam_select_permit is None
    dev.set_bypass.assert_called_once_with(206, True)
    assert [call.args[1] for call in dev.set_param_display.call_args_list] == [-18, -18]
    dev.install_nam_slot.assert_not_called(); dev.store_preset.assert_not_called()
    dev.install_nam_slot1.assert_not_called()


def test_same_slot_does_not_reset_voicing_or_stage():
    dev, _ = device()
    assert selector.select(dev, 250).ok
    dev._write.assert_not_called(); dev.set_param_display.assert_not_called()


@pytest.mark.parametrize('fault', ['empty','incomplete','wrong_slot','empty_zero','modifier','channel','variant'])
def test_bad_target_stops_before_staging_or_selector(fault, monkeypatch):
    dev, _ = device()
    target = 256
    got = Capture('Synthetic', 256, 'a'*64, 65536)
    if fault == 'empty': got = replace(got, empty=True)
    if fault == 'incomplete': got = replace(got, byte_count=100)
    if fault == 'wrong_slot': got = replace(got, slot=250)
    dev.read_nam_slot.side_effect = None; dev.read_nam_slot.return_value = got
    if fault == 'empty_zero':
        target = 1
        dev.read_nam_slot1.return_value = Capture('EMPTY',1,'a'*64,65536,True)
    if fault == 'modifier': monkeypatch.setattr(modifiers, 'inspect', lambda _: [dict(active=True, words=[0]*25)]*32)
    if fault == 'channel': dev.get_channel.return_value = 2
    if fault == 'variant': dev.reg.hardware_variant = 'mk1'
    with pytest.raises(ValueError): selector.select(dev, target)
    dev._write.assert_not_called(); dev.set_param_display.assert_not_called()


def test_readback_mismatch_never_retries_write_or_restores(monkeypatch):
    monkeypatch.setattr(selector.time, 'sleep', lambda _: None)
    dev, _ = device(); dev._write.side_effect = None
    assert not selector.select(dev, 256).ok
    dev._write.assert_called_once(); dev.install_nam_slot.assert_not_called()


def test_other_channel_change_stops(monkeypatch):
    monkeypatch.setattr(selector.time, 'sleep', lambda _: None)
    dev, words = device()
    dev._write.side_effect = lambda frame: words.__setitem__(18, 255)
    assert not selector.select(dev, 256).ok
    assert dev.set_param_display.call_count == 1


def test_empty_memory_cannot_be_verified_just_by_name():
    dev, _ = device()
    dev.read_nam_slot.side_effect = None
    dev.read_nam_slot.return_value = Capture('EMPTY',256,'a'*64,65536,False)
    with pytest.raises(ValueError): selector.capture(dev,256)

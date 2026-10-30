"""The AFX3 wire contract must not alter the FM9 or depend on process env.

These are offline protocol tests, not claims of hardware/audio acceptance.
Expected SET floats come from the prior captured/readback evidence, not
from round-tripping the new decoder.
"""
from dataclasses import replace
import math

import pytest

from fm9 import protocol as fm9_protocol
from fm9.registry import Registry as FM9Registry
from devices.axefx3 import protocol
from devices.axefx3.registry import Registry


def test_the_registry_is_not_an_fm9_catalog_with_a_new_product_byte(monkeypatch):
    before = fm9_protocol.build_get_scene()
    monkeypatch.setenv("TONECOMMAND_DEVICE", "axe-fx-iii")
    fm9 = FM9Registry()
    axe = Registry("32.06")
    assert len(axe.params) == 75
    assert axe.model_byte == 0x10
    assert fm9.model_byte == 0x12
    assert axe.find_param("DISTORT", "DISTORT_MID").param_id == 3
    assert fm9.find_param("DISTORT", "DISTORT_MID").param_id != 3
    assert fm9_protocol.build_get_scene() == before
    assert before[4] == 0x12
    assert protocol.envelope(0x0C, [127])[4] == 0x10


@pytest.mark.parametrize("firmware", ["", "unknown", "12.00", "32.04", "32.07", "99.00"])
def test_unverified_firmware_does_not_inherit_any_writes(firmware):
    reg = Registry(firmware)
    assert not reg.params
    assert not reg.selectable_amp_models()
    with pytest.raises(KeyError):
        reg.spec("DISTORT", 3)


@pytest.mark.parametrize("family,name,value,opcode,wire", [
    ("DISTORT", "DISTORT_MID", 6, 0x09, 39320 / 65534),
    ("DISTORT", "DISTORT_LEVEL", -15, 0x09, -15),
    ("DELAY", "DELAY_TIME", 280, 0x09, .280),
    ("DELAY", "DELAY_FEED", 24, 0x09, .24),
    ("DELAY", "DELAY_FEED", 0, 0x52, .5),
    ("DELAY", "DELAY_LEVEL", 0, 0x52, .8),
    ("REVERB", "REVERB_TIME", 1.2, 0x09, 1.2),
    ("REVERB", "REVERB_MIX", 8, 0x09, .08),
    ("WAH", "WAH_FREQMIN", 350, 0x09, 350),
    ("WAH", "WAH_RESONANCE", 4.5, 0x52, .45),
    ("WAH", "WAH_INDUCTOR_BIAS", 0, 0x09, 0),
    ("CABINET", "CABINET_PAN2", -100, 0x09, -1),
    ("CABINET", "CABINET_MUTE2", 1, 0x09, 1),
    ("CABINET", "CABINET_LEVEL1", 0, 0x09, 0),
    ("CHORUS", "CHORUS_RATE", .3, 0x09, .3),
    ("CHORUS", "CHORUS_DEPTH", 25, 0x09, .25),
    ("CHORUS", "CHORUS_DEPTH", 0, 0x09, 0),
    ("CHORUS", "CHORUS_MIX", 20, 0x09, .2),
    ("CHORUS", "CHORUS_MIX", 0, 0x09, 0),
    ("CHORUS", "CHORUS_LEVEL", -12, 0x09, -12),
    ("CHORUS", "CHORUS_LEVEL", 0, 0x09, 0),
])
def test_captured_display_units_are_not_fm9_normalized_knobs(family, name, value, opcode, wire):
    reg = Registry("32.06")
    spec = reg.find_param(family, name)
    frame = protocol.set_parameter(reg, spec, value)
    assert frame[:6] == [0xF0, 0, 1, 0x74, 0x10, 1]
    assert frame[6:8] == [opcode, 0]
    assert frame[8:12] == [spec.effect_id, 0, spec.param_id, 0]
    assert fm9_protocol.decode_f32_septets(frame[12:17]) == pytest.approx(wire)
    assert frame[-2] == fm9_protocol.checksum(frame[1:-2])
    assert frame[-1] == 0xF7


@pytest.mark.parametrize("field,value", [
    ("effect_id", 1), ("param_id", 3), ("name", "GLOBAL_INPUT_SOURCE"),
    ("dmax", 10000), ("set_opcode", "52"), ("set_divisor", 10),
    ("verify_display_text", False), ("firmware_versions", ()),
])
def test_an_action_cannot_forge_its_encoding_or_safety_reference(field, value):
    reg = Registry("32.06")
    spec = reg.find_param("DELAY", "DELAY_TIME")
    with pytest.raises((KeyError, ValueError)):
        protocol.set_parameter(reg, replace(spec, **{field: value}), 280)


@pytest.mark.parametrize("value", [True, "6", math.nan, math.inf, -1, 11])
def test_no_silent_clamp_or_nonfinite_parameter(value):
    reg = Registry("32.06")
    with pytest.raises(ValueError):
        protocol.set_parameter(reg, reg.find_param("DISTORT", "DISTORT_MID"), value)


@pytest.mark.parametrize("family,name,value", [
    ("DELAY", "DELAY_FEED", 61), ("DELAY", "DELAY_FEED", -61),
    ("DISTORT", "DISTORT_LEVEL", 1), ("OUTPUT", "OUTPUT_LEVEL", 6),
    ("CABINET", "CABINET_MUTE1", .5),
    ("CHORUS", "CHORUS_LEVEL", 1),
])
def test_static_audio_limits_are_not_bypassed_by_valid_device_ranges(family, name, value):
    reg = Registry("32.06")
    with pytest.raises(ValueError):
        protocol.set_parameter(reg, reg.find_param(family, name), value)


def test_display_read_is_the_short_captured_query_not_a_typed_zero_write():
    frame = protocol.display_query(58, 3)
    assert frame[1:-2] == [0, 1, 0x74, 0x10, 1, 0x10, 0, 58, 0, 3, 0]
    with pytest.raises(ValueError):
        protocol.display_query(58, 0)


def test_foreign_or_corrupt_replies_cannot_verify_a_write():
    frame = protocol.envelope(0x0C, [0])
    assert protocol.valid_reply(frame[1:-1])
    assert not protocol.valid_reply(fm9_protocol.envelope(0x0C, [0])[1:-1])
    frame[-2] ^= 1
    assert not protocol.valid_reply(frame[1:-1])
    assert not protocol.valid_reply([])


def test_fm9_spec_and_unknown_controls_cannot_enter_the_axe_writer():
    reg = Registry("32.06")
    with pytest.raises(ValueError):
        protocol.set_parameter(reg, FM9Registry().find_param("DISTORT", "DISTORT_MID"), 6)
    with pytest.raises(KeyError):
        reg.spec("GLOBAL", 72)
    assert reg.find_param("DISTORT", "unknown") is None
    with pytest.raises(ValueError):
        reg.spec("DISTORT", 3, 3)
    with pytest.raises(ValueError):
        reg.spec("CHORUS", 2, 2)


@pytest.mark.parametrize('variant,count', [(None,512),('mk1',512),('mk2',1024)])
def test_preset_capacity_is_separate_from_write_permission(variant,count):
    from devices.axefx3 import profile
    reg=Registry('32.06')
    result=profile.apply(reg,variant)
    assert profile.preset_count(reg)==count==result['preset_count']
    assert result['variant_verified'] is False
    for number in (0,511,count-1):assert profile.validate_preset(reg,number)==number
    for number in (-1,count,True,'512',None):
        with pytest.raises(ValueError):profile.validate_preset(reg,number)


@pytest.mark.parametrize('number',[511,512,1023])
def test_mk2_name_queries_use_full_fourteen_bit_address_without_wrap(number):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from devices.axefx3.adapter import AxeFxIII
    dev=object.__new__(AxeFxIII)
    dev.reg=Registry('32.06');dev.reg.hardware_variant='mk2'
    dev._request=Mock(return_value=None)
    dev.slot_name(number)
    frame=dev._request.call_args.args[0]
    assert frame==protocol.envelope(0x0d,list(fm9_protocol.encode14(number)))
    assert fm9_protocol.decode14(*frame[6:8])==number
    assert len(frame)==10 and frame[4]==0x10


@pytest.mark.parametrize('variant,count',[(None,512),('mk1',512),('mk2',1024)])
def test_default_name_scan_matches_chassis_and_invalid_slots_never_query(variant,count):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from devices.axefx3.adapter import AxeFxIII
    dev=object.__new__(AxeFxIII)
    dev.reg=Registry('32.06');dev.reg.hardware_variant=variant
    dev.slot_name=Mock(side_effect=lambda n:SimpleNamespace(number=n))
    assert [s.number for s in dev.scan_slots()]==list(range(count))
    dev.slot_name.reset_mock()
    for start,end in ((0,count),(-1,5),(True,5),(5,4)):
        with pytest.raises(ValueError):list(dev.scan_slots(start,end))
    dev.slot_name.assert_not_called()
    dev._request=Mock()
    with pytest.raises(ValueError):AxeFxIII.slot_name(dev,count)
    dev._request.assert_not_called()


def test_upper_preset_api_inputs_do_not_clip_to_the_lower_bank():
    from devices.axefx3 import tone_ui,nam_ui,navigation
    for number in (512,1023):
        assert tone_ui.Request(prompt='One lead scene',scenes=1,expected_preset=number).expected_preset==number
        assert nam_ui.StoreTarget(expected_preset=number).expected_preset==number
        assert navigation.Prepare(kind='preset',value=number,expected_preset=number,expected_scene=1).value==number
    for number in (-1,1024,True):
        with pytest.raises(ValueError):tone_ui.Request(prompt='One lead scene',scenes=1,expected_preset=number)


def test_one_checkout_menu_uses_existing_install_and_safety_paths():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    menu=(root/'ToneCommand.cmd').read_text(encoding='utf-8')
    assert 'packaging\\mk1-ai\\Install.ps1' in menu and '-Development' in menu
    assert 'packaging\\mk1-ai\\Development.ps1' in menu
    assert 'tools\\start_tonecommand.ps1' in menu
    assert '-Connect' not in menu and 'git reset' not in menu and 'pip install' not in menu

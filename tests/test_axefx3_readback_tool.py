from unittest.mock import Mock

import pytest

from tools import afx3_integration_readback as readback
from devices.axefx3.registry import Registry
from fm9 import midi_transport


def test_readback_without_explicit_hardware_flag_opens_nothing(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(readback, "AxeFxIII", factory)
    with pytest.raises(SystemExit):
        readback.main([])
    factory.assert_not_called()


def test_simulator_cannot_be_reported_as_hardware(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_SIM", "1")
    factory = Mock()
    monkeypatch.setattr(readback, "AxeFxIII", factory)
    with pytest.raises(SystemExit):
        readback.main(["--hardware-read-only"])
    factory.assert_not_called()


def test_report_never_enters_write_session_or_changes_selection():
    dev = Mock(device_name="Axe-Fx III")
    dev.reg = Registry("32.06")
    dev.current_preset.return_value = (322, "Test")
    dev.current_scene.return_value = 1
    dev.firmware_label.return_value = "32.06"
    dev.status_dump.return_value = []
    dev.read_grid.return_value = []
    dev.modifier_report.return_value = []
    report = readback.inspect(dev)
    assert report["same_preset"] and report["read_only"] and not report["stored"]
    assert not report["physical_pedal_verified"]
    dev.edit_session.assert_not_called()
    dev.set_scene.assert_not_called()
    dev.select_preset.assert_not_called()
    dev._write.assert_not_called()


def test_input_port_is_released_if_output_open_fails(monkeypatch):
    monkeypatch.setattr(midi_transport, "backend", lambda _: "mido")
    monkeypatch.setattr(midi_transport.mido, "get_input_names", lambda: ["Axe-Fx III"])
    monkeypatch.setattr(midi_transport.mido, "get_output_names", lambda: ["Axe-Fx III"])
    inp = Mock()
    monkeypatch.setattr(midi_transport.mido, "open_input", lambda _: inp)
    monkeypatch.setattr(midi_transport.mido, "open_output", Mock(side_effect=RuntimeError("busy")))
    with pytest.raises(RuntimeError, match="busy"):
        midi_transport.open_ports("axe-fx")
    inp.close.assert_called_once()


def test_supriya_input_is_released_if_output_open_fails(monkeypatch):
    monkeypatch.setattr(midi_transport, "backend", lambda _: "supriya")
    inp = Mock()
    monkeypatch.setattr(midi_transport.SupriyaIn, "open", Mock(return_value=inp))
    monkeypatch.setattr(midi_transport.SupriyaOut, "open", Mock(side_effect=RuntimeError("busy")))
    with pytest.raises(RuntimeError, match="busy"):
        midi_transport.open_ports("axe-fx", supriya_module=Mock())
    inp.close.assert_called_once()


def test_scene_change_during_readback_is_not_a_coherent_snapshot():
    dev = Mock(device_name="Axe-Fx III")
    dev.reg = Registry("32.06")
    dev.current_preset.return_value = (322, "Test")
    dev.current_scene.side_effect = [1, 2]
    dev.firmware_label.return_value = "32.06"
    dev.status_dump.return_value = []
    dev.read_grid.return_value = []
    dev.modifier_report.return_value = []
    report = readback.inspect(dev)
    assert report["same_preset"] and not report["same_scene_and_block_status"]
    dev.edit_session.assert_not_called()


@pytest.mark.parametrize("source,name", [(12, "External 1"), (13, "External 2")])
def test_zero_control_read_is_not_claimed_as_zero_pedal_position(source, name):
    blocks = [{"effect_id": 94, "parameters": {"WAH_CONTROL": 0}}]
    slots = {"readable": True, "slots": [
        {"slot": 1, "effect_id": 94, "param_id": 5, "active": True,
         "parameter": "WAH_CONTROL", "source": source, "source_name": name},
        {"slot": 2, "effect_id": 94, "active": False},
        {"slot": 3, "effect_id": 58, "active": True},
    ]}
    readback.annotate_modifier_reads(blocks, slots)
    observed = blocks[0]["modifier_controlled_parameters"]
    assert len(observed) == 1
    assert observed[0]["display_read"] == 0
    assert observed[0]["source_name"] == name
    assert observed[0]["effective_value_verified"] is False
    assert "CC" not in observed[0]  # No owner-specific CC mapping invented.


def test_unreadable_modifiers_are_not_reported_as_uncontrolled():
    blocks = [{"effect_id": 94, "parameters": {"WAH_CONTROL": 0}}]
    readback.annotate_modifier_reads(blocks, {"readable": False, "reason": "timeout"})
    assert blocks[0]["modifier_state_readable"] is False
    assert blocks[0]["modifier_controlled_parameters"] == []

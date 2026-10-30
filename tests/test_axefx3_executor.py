from contextlib import contextmanager
import threading
from unittest.mock import Mock

import pytest

from devices.axefx3.executor import prepare, execute, preset_name
from devices.axefx3.registry import Registry
from fm9.device import SetResult
from fm9.protocol import GridCell, BlockStatus

ROUTE = ["Input 1", "Wah 1", "Amp 1", "Cab 1", "Delay 1", "Reverb 1", "Output 1"]
IDS = [37, 94, 58, 62, 70, 66, 42]


@pytest.mark.parametrize('bad',['future_mode','layout','implicit_channel'])
def test_extra_effect_future_channels_are_preflighted_before_amp_write(dev,bad):
    ids=[37,46,58,62,42]
    route=['Input 1','Compressor 1','Amp 1','Cab 1','Output 1']
    dev.read_grid.side_effect=lambda:[GridCell(2,i,e,False,8 if i else 0) for i,e in enumerate(ids)]
    dev.status_dump.side_effect=lambda:[BlockStatus(e,True,0,4) for e in ids]
    data=[0]*(4*37)
    if bad=='future_mode':data[37+12]=1
    if bad=='layout':data.pop()
    dev.bulk_read.return_value=data
    actions=[dict(kind='set_param',block='amp',param='DISTORT_MID',value=6),
             dict(kind='set_scene',value=2),
             dict(kind='set_channel',block='COMP',value=1),
             dict(kind='set_param',block='COMP',param='COMP_THRESH',value=-30)]
    if bad=='implicit_channel':actions.pop(2)
    with pytest.raises(ValueError):
        execute(dev,actions,route,expected_preset=322,external_audio_muted=True)
    dev.edit_session.assert_not_called()
    dev.set_param_display.assert_not_called()
    dev.set_scene.assert_not_called()


@pytest.mark.parametrize('bad',['missing_model','missing_channel','orphan_modifier','unsupported_model'])
def test_new_drive_requires_complete_static_preflight_before_routing(dev,bad):
    from devices.axefx3 import modifiers
    from unittest.mock import patch
    ids=[37,58,62,42]
    dev.read_grid.side_effect=lambda:[GridCell(2,i,e,False,8 if i else 0) for i,e in enumerate(ids)]
    dev.status_dump.side_effect=lambda:[BlockStatus(e,True,0,4) for e in ids]
    actions=[dict(kind='add_block',block='FUZZ',position='pre'),
             dict(kind='set_channel',block='FUZZ',value=0),
             dict(kind='set_type',block='FUZZ',type_name='T808 OD'),
             dict(kind='set_param',block='FUZZ',param='FUZZ_LEVEL',value=2)]
    if bad=='missing_model':actions.pop(2)
    if bad=='missing_channel':actions.pop(1)
    if bad=='unsupported_model':actions[2]['type_name']='FAS Boost'
    slots=[dict(effect_id=118 if bad=='orphan_modifier' else 0,source=0)]
    with patch.object(modifiers,'preflight',return_value=slots):
        with pytest.raises(ValueError):prepare(dev,actions,['Input 1','Drive 1','Amp 1','Cab 1','Output 1'],322)
    dev.build_route.assert_not_called()
    dev.set_param_display.assert_not_called()


@pytest.fixture
def dev():
    rig = Mock()
    rig.reg = Registry("32.06")
    rig._lock = threading.RLock()
    rig.firmware_label.return_value = "32.06"
    rig.current_preset.return_value = (322, "Test")
    rig.read_grid.side_effect = lambda: [GridCell(2, i, eid, False, 8 if i else 0) for i, eid in enumerate(IDS)]
    rig.status_dump.side_effect = lambda: [BlockStatus(eid, False, 0, 4) for eid in IDS]
    rig.read_modifier.side_effect = lambda slot: [0]*15
    @contextmanager
    def session(**kwargs):
        assert kwargs == {"external_audio_muted": True, "expected_preset": 322}
        yield rig
    rig.edit_session.side_effect = session
    rig.set_scene.side_effect = lambda value: value
    rig.set_channel.side_effect = lambda eid, value: value
    rig.set_bypass.side_effect = lambda eid, value: value
    rig.set_param_display.return_value = SetResult(True, "verified", 5, 6)
    rig.set_model.return_value = SetResult(True, "verified", "Old", "New")
    return rig


def test_four_scene_channels_are_not_collapsed_to_one_amp_channel(dev):
    actions = []
    for scene in range(1, 5):
        actions.extend([{"kind": "set_scene", "value": scene},
                        {"kind": "set_channel", "block": "amp", "value": scene-1},
                        {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE", "value": scene+2}])
    result = execute(dev, actions, ROUTE, expected_preset=322, external_audio_muted=True)
    assert result["ok"] and not result["stored"] and not result["physical_volume_verified"]
    assert [c.args for c in dev.set_channel.call_args_list] == [(58, i) for i in range(4)]
    assert [c.args[1] for c in dev.set_param_display.call_args_list] == [3, 4, 5, 6]
    dev.store_preset.assert_not_called()
    dev.select_preset.assert_not_called()


def test_first_bad_readback_stops_following_actions(dev):
    dev.set_param_display.return_value = SetResult(False, "did not verify", 5, 5)
    actions = [{"kind": "set_param", "block": "amp", "param": "DISTORT_MID", "value": 6},
               {"kind": "rename_preset", "type_name": "New"}]
    result = execute(dev, actions, ROUTE, expected_preset=322, external_audio_muted=True)
    assert not result["ok"] and result["skipped"] == 1
    dev.rename_preset.assert_not_called()


@pytest.mark.parametrize("problem", ["invalid_last", "target", "firmware", "mute", "modifier"])
def test_entire_plan_preflight_refuses_before_any_edits(dev, problem):
    actions = [{"kind": "set_param", "block": "amp", "param": "DISTORT_MID", "value": 6}]
    if problem == "invalid_last": actions.append({"kind": "store"})
    if problem == "target": dev.current_preset.return_value = (321, "Different")
    if problem == "firmware": dev.firmware_label.return_value = "33.00"
    if problem == "modifier": dev.read_modifier.side_effect = lambda slot: None
    with pytest.raises((ValueError, PermissionError)):
        execute(dev, actions, ROUTE, expected_preset=322, external_audio_muted=problem != "mute")
    dev.edit_session.assert_not_called()
    dev.set_param_display.assert_not_called()
    dev.build_route.assert_not_called()


def test_missing_new_modifier_curve_blocks_before_constructing_empty_preset(dev):
    dev.read_grid.side_effect = lambda: []
    dev.status_dump.side_effect = lambda: []
    actions = [{"kind": "add_block", "block": b} for b in ("wah", "amp", "cab", "delay", "reverb")]
    actions.append({"kind": "bind_pedal", "block": "wah", "param": "WAH_CONTROL", "source": "External 1"})
    with pytest.raises(ValueError, match="device-built"):
        execute(dev, actions, ROUTE, expected_preset=322, external_audio_muted=True)
    dev.build_route.assert_not_called()
    dev.edit_session.assert_not_called()


def test_model_reset_needs_final_level_before_engagement(dev):
    actions = [{"kind": "set_channel", "block": "amp", "value": 0},
               {"kind": "set_type", "block": "amp", "type_name": "Brit 800 2204 High"},
               {"kind": "set_bypass", "block": "amp", "bypassed": False}]
    with pytest.raises(ValueError, match="final level"):
        prepare(dev, actions, ROUTE, 322)
    actions.insert(2, {"kind": "set_param", "block": "amp", "param": "DISTORT_LEVEL", "value": -15})
    assert execute(dev, actions, ROUTE, expected_preset=322, external_audio_muted=True)["ok"]


def test_ai_prefix_is_not_duplicated():
    assert preset_name("AI-AI-Whole Lotta Love") == "AI-Whole Lotta Love"
    assert preset_name("FM9AI-Test") == "AI-Test"


@pytest.mark.parametrize("problem", ["mismatch", "connection"])
def test_route_failure_reports_partial_edit_and_sends_no_voicing(dev, problem):
    dev.read_grid.side_effect = lambda: []
    dev.status_dump.side_effect = lambda: []
    dev.build_route.return_value = SetResult(False, "Cable mismatch", None, None)
    if problem == "connection":
        dev.build_route.side_effect = OSError("MIDI lost during placement")
    actions = [{"kind": "add_block", "block": b} for b in ("wah", "amp", "cab", "delay", "reverb")]
    actions.append({"kind": "set_param", "block": "amp", "param": "DISTORT_MID", "value": 6})
    result = execute(dev, actions, ROUTE, expected_preset=322, external_audio_muted=True)
    assert not result["ok"] and result["skipped"] == len(actions)
    assert result["phase"] == "build_route" and "Partial routing" in result["recovery"]
    assert not result["stored"] and not result["physical_volume_verified"]
    dev.set_param_display.assert_not_called()
    dev.store_preset.assert_not_called()

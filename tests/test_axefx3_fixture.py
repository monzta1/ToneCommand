"""Test-only structural permissions are not generic planner capabilities."""
from unittest.mock import Mock
import pytest
from devices.axefx3 import grid,protocol,insertion
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry
from fm9.protocol import GridCell


def fixture_device(frame,target=323,eid=118):
    dev=object.__new__(AxeFxIII)
    dev.reg=Registry('32.06');dev._approved_frame=tuple(frame)
    dev._grid_fixture_permit=tuple(frame);dev._grid_move_permit=tuple(frame)
    dev._edit_target=target;dev.outp=Mock();dev._check_edit_target=Mock()
    dev.read_grid=Mock(return_value=[GridCell(2,1,eid,False,8)])
    return dev


@pytest.mark.parametrize('col',[2,3])
def test_removal_frame_has_only_captured_position_field(col):
    frame=grid.fixture_remove_frame(col)
    assert protocol.valid_reply(frame[1:-1])
    assert frame[6:8]==[51,0]
    assert frame[12:17]==[(col-1)*6+2,0,0,0,0]
    assert not grid.valid_write(frame,Registry('32.06'))


@pytest.mark.parametrize('col',[True,1,4,14])
def test_fixture_cannot_remove_general_cells(col):
    with pytest.raises(ValueError):grid.fixture_remove_frame(col)


@pytest.mark.parametrize('target,eid,permit,ok',[(323,118,True,True),(323,46,True,True),
    (322,118,True,False),(324,118,True,False),(323,58,True,False),
    (323,118,False,False)])
def test_removal_scope_is_explicit_preset_and_effect(target,eid,permit,ok):
    frame=grid.fixture_remove_frame(2);dev=fixture_device(frame,target,eid)
    if not permit:dev._grid_fixture_permit=None
    if ok:
        dev._send(frame);dev.outp.send.assert_called_once()
    else:
        with pytest.raises(PermissionError):dev._send(frame)
        dev.outp.send.assert_not_called()


def test_left_movement_is_not_a_normal_insertion_permission():
    frame=grid.fixture_left_frame();dev=fixture_device(frame)
    dev._grid_fixture_permit=None
    with pytest.raises(PermissionError):dev._send(frame)
    dev.outp.send.assert_not_called()
    dev._grid_fixture_permit=tuple(frame);dev._send(frame)
    dev.outp.send.assert_called_once()

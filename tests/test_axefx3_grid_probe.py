"""Captured fixture is NOT a public builder or firmware-wide permission."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from devices.axefx3 import grid_probe,grid,fw33_profile,protocol,fw33
from devices.axefx3.registry import Registry
from devices.axefx3.adapter import AxeFxIII
from fm9 import protocol as shared


def device():
    return SimpleNamespace(reg=Registry(fw33_profile.KEY),_edit_target=324,
                           _grid_probe_permit=None)


@pytest.mark.parametrize('frame',grid_probe.captured_frames())
def test_fixture_requires_exact_permit_and_current_target(frame):
    dev=device()
    assert not grid_probe.allowed(dev,frame)
    dev._grid_probe_permit=tuple(frame)
    assert grid_probe.allowed(dev,frame)
    fw33.check_frame(dev,frame)
    assert protocol.valid_reply(frame[1:-1])
    assert not grid.valid_write(frame,dev.reg)
    dev._edit_target=323
    assert not grid_probe.allowed(dev,frame)
    dev._edit_target=324
    dev.reg=Registry('32.06')
    assert not grid_probe.allowed(dev,frame)


def test_insert_retains_captured_payload_not_assumed_cursor_position():
    assert grid_probe.INSERTS[46]!=grid.reframe(shared.build_set_grid_cell(5,1,46))
    assert grid_probe.INSERTS[118]!=grid.reframe(shared.build_set_grid_cell(5,2,118))


def test_unknown_fixture_write_rejected_and_permit_always_cleared():
    dev=device()
    dev._check_edit_target=lambda:None
    dev.read_grid=lambda:[]
    def fail(frame):
        assert grid_probe.allowed(dev,frame)
        raise RuntimeError('Stopped once, no write retry')
    dev._write=fail
    with pytest.raises(RuntimeError):
        grid_probe.write(dev,grid_probe.frames()[0])
    assert dev._grid_probe_permit is None
    with pytest.raises(PermissionError):
        grid_probe.write(dev,grid.reframe(shared.build_set_grid_cell(5,3,58)))


@pytest.mark.parametrize('col',[0,3,True,None])
def test_delete_other_cells_never_enabled(col):
    with pytest.raises(ValueError):grid_probe.delete(col)


def test_captured_cable_matches_shared_fm9_builder_exactly():
    assert bytes(grid_probe.frames()[4]).hex(' ')==(
        'f0 00 01 74 10 01 35 00 00 00 00 00 01 00 00 00 00 00 00 02 00 02 02 40 62 f7')
    assert bytes(grid_probe.frames()[5]).hex(' ')==(
        'f0 00 01 74 10 01 35 00 00 00 00 00 02 00 00 00 00 00 00 02 00 02 02 40 61 f7')


def test_captured_diagonal_matches_fm9_builder_without_new_insert_guess():
    assert grid_probe.frames()[1]==grid_probe.frames(6)[1]
    assert grid_probe.frames()[3]==grid_probe.frames(6)[3]
    assert bytes(grid_probe.frames(6)[4]).hex(' ')==(
        'f0 00 01 74 10 01 35 00 00 00 00 00 01 00 00 00 00 00 00 02 00 02 02 60 42 f7')
    assert bytes(grid_probe.frames(6)[5]).hex(' ')==(
        'f0 00 01 74 10 01 35 00 00 00 00 00 02 00 00 00 00 00 00 02 00 02 02 60 41 f7')


@pytest.mark.parametrize('row',[0,4,7,True,None])
def test_unmeasured_geometry_is_refused(row):
    with pytest.raises(ValueError):grid_probe.frames(row)
    with pytest.raises(ValueError):grid_probe.delete(2,row=row)


@pytest.mark.parametrize('fault',['unselected','occupied','duplicate','cable','other_block'])
def test_probe_rejects_unsafe_fixture_state_before_transport(fault):
    dev=device();dev._check_edit_target=lambda:None
    cells=[];written=[]
    dev.read_grid=lambda:cells
    dev._write=lambda frame:written.append(frame)
    frame=grid_probe.INSERTS[46]
    if fault=='occupied':cells.append(shared.GridCell(4,0,58,False,0))
    if fault=='duplicate':cells.append(shared.GridCell(1,7,46,False,0))
    if fault in ('cable','other_block'):
        frame=grid_probe.delete(1)
        cells.append(shared.GridCell(4,0,46 if fault=='cable' else 58,False,8 if fault=='cable' else 0))
    if fault!='unselected':dev._grid_probe_selection=((5,1),grid.snapshot(cells))
    with pytest.raises(PermissionError):grid_probe.write(dev,frame)
    assert not written
    assert dev._grid_probe_permit is None


@pytest.mark.parametrize('fault',['no_permit','raw','wrong_target','unmeasured'])
def test_transport_still_refuses_unreviewed_fixture_frames(fault):
    dev=device();frame=grid_probe.frames()[1]
    dev.guard=AxeFxIII.guard;dev.outp=Mock();dev._check_edit_target=lambda:None
    dev._approved_frame=tuple(frame);dev._grid_probe_permit=tuple(frame)
    if fault=='no_permit':dev._grid_probe_permit=None
    if fault=='raw':dev._approved_frame=None
    if fault=='wrong_target':dev._edit_target=325
    if fault=='unmeasured':
        frame=grid.reframe(shared.build_set_grid_cell(5,3,58))
        dev._approved_frame=dev._grid_probe_permit=tuple(frame)
    with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
    dev.outp.send.assert_not_called()


@pytest.mark.parametrize('dest_row',[5,6])
def test_complete_captured_sequence_consumes_selection_and_retains_other_cells(dest_row):
    dev=device();dev._check_edit_target=lambda:None
    # An unrelated existing cell must never be the target of a fixture write.
    original=shared.GridCell(2,8,58,False,0)
    cells=[original];selected=None;written=[]
    dev.read_grid=lambda:cells
    def write(frame):
        nonlocal selected
        assert grid_probe.allowed(dev,frame)
        written.append(frame)
        sub=frame[6]
        if sub==0x30:
            c,r=divmod(sum(v<<(7*i) for i,v in enumerate(frame[12:17])),6)
            selected=(r,c)
        elif sub==0x32:
            cells.append(shared.GridCell(*selected,frame[8],False,0))
        elif sub==0x35:
            target=next(c for c in cells if (c.row,c.col)==(dest_row-1,1))
            target.cable_in_mask=32 if frame[12]==1 else 0
        elif sub==0x33:
            cells[:]=[c for c in cells if (c.row,c.col)!=selected]
    dev._write=write
    for frame in grid_probe.frames(dest_row):
        grid_probe.write(dev,frame)
        assert dev._grid_probe_permit is None
    assert len(written)==10 and cells==[original]


def test_diagonal_delete_refuses_outgoing_row6_source_mask():
    dev=device();dev._check_edit_target=lambda:None
    cells=[shared.GridCell(5,1,118,False,0),shared.GridCell(2,2,58,False,64)]
    dev.read_grid=lambda:cells;dev._write=Mock()
    dev._grid_probe_selection=((6,2),grid.snapshot(cells))
    with pytest.raises(PermissionError,match='outgoing'):
        grid_probe.write(dev,grid_probe.delete(2,row=6))
    dev._write.assert_not_called()


@pytest.mark.parametrize('source,target,direction,checksum',[
    ((5,1),(5,2),1,'23'),((5,2),(6,2),3,'21'),
    ((6,2),(5,2),2,'20'),((5,2),(5,1),0,'22')])
def test_move_retains_each_independently_captured_literal(source,target,direction,checksum):
    assert bytes(grid_probe.move_frame(source,target)).hex(' ')==(
        f'f0 00 01 74 10 01 36 00 00 00 00 00 {direction:02x} 00 00 00 00 00 00 00 00 {checksum} f7')


@pytest.mark.parametrize('source,target',[
    ((5,1),(6,2)),((6,2),(6,1)),((5,1),(5,3)),((True,1),(5,2)),
    ([5,1],(5,2)),((5,1),None)])
def test_other_move_geometries_are_not_enabled(source,target):
    with pytest.raises(ValueError):grid_probe.move_frame(source,target)


@pytest.mark.parametrize('fault',['unselected','stale','occupied','incoming','outgoing','wrong_block','duplicate'])
def test_move_refuses_stale_connected_occupied_or_wrong_fixture_before_transport(fault):
    dev=device();dev._check_edit_target=lambda:None
    cells=[shared.GridCell(4,0,46,False,0)]
    if fault=='occupied':cells.append(shared.GridCell(4,1,118,False,0))
    if fault=='incoming':cells[0].cable_in_mask=8
    if fault=='outgoing':cells.append(shared.GridCell(2,1,118,False,32))
    if fault=='wrong_block':cells[0].effect_id=58
    if fault=='duplicate':cells.append(shared.GridCell(5,8,46,False,0))
    dev.read_grid=lambda:cells;dev._write=Mock()
    if fault!='unselected':
        dev._grid_probe_selection=((5,1),{} if fault=='stale' else grid.snapshot(cells))
    with pytest.raises(PermissionError):grid_probe.write(dev,grid_probe.move_frame((5,1),(5,2)))
    dev._write.assert_not_called()


def test_full_move_roundtrip_preserves_all_other_grid_cells():
    dev=device();dev._check_edit_target=lambda:None
    original=shared.GridCell(2,8,58,False,8)
    cells=[original];selected=None
    dev.read_grid=lambda:cells
    def write(frame):
        nonlocal selected
        assert grid_probe.allowed(dev,frame)
        if frame[6]==0x30:
            c,r=divmod(sum(v<<(7*i) for i,v in enumerate(frame[12:17])),6)
            selected=(r,c)
        elif frame[6]==0x32:cells.append(shared.GridCell(*selected,46,False,0))
        elif frame[6]==0x36:
            source,target=next((s,t) for s,t in grid_probe.MOVES if frame==grid_probe.move_frame(s,t))
            cell=next(c for c in cells if (c.row+1,c.col+1)==source)
            cell.row,cell.col=target[0]-1,target[1]-1
        elif frame[6]==0x33:cells[:]=[c for c in cells if (c.row,c.col)!=selected]
    dev._write=write
    for frame in grid_probe.movement_frames():
        grid_probe.write(dev,frame)
        assert dev._grid_probe_permit is None
    assert cells==[original]


@pytest.mark.parametrize('fault',['no_permit','raw','wrong_target'])
def test_move_transport_refuses_unreviewed_frames(fault):
    dev=device();frame=grid_probe.move_frame((5,1),(5,2))
    dev.guard=AxeFxIII.guard;dev.outp=Mock();dev._check_edit_target=lambda:None
    dev._approved_frame=dev._grid_probe_permit=tuple(frame)
    if fault=='no_permit':dev._grid_probe_permit=None
    if fault=='raw':dev._approved_frame=None
    if fault=='wrong_target':dev._edit_target=325
    with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
    dev.outp.send.assert_not_called()


def test_failed_move_clears_selection_and_permit_without_retry():
    dev=device();dev._check_edit_target=lambda:None
    cells=[shared.GridCell(4,0,46,False,0)]
    dev.read_grid=lambda:cells
    dev._grid_probe_selection=((5,1),grid.snapshot(cells))
    dev._write=Mock(side_effect=RuntimeError('Uncertain result'))
    with pytest.raises(RuntimeError):grid_probe.write(dev,grid_probe.move_frame((5,1),(5,2)))
    dev._write.assert_called_once()
    assert dev._grid_probe_permit is None and dev._grid_probe_selection is None

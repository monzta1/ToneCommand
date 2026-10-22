"""Measured two-row references do not authorize arbitrary routing writes."""
from types import SimpleNamespace
import pytest
from fm9 import protocol as shared
from devices.axefx3 import row_fixture,protocol,grid,fw33,fw33_profile
from devices.axefx3.registry import Registry


def cells():
    return [shared.GridCell(r-1,c-1,e,s,m) for (r,c),(e,s,m) in row_fixture.expected_grid().items()]


def test_reference_contains_only_the_82_observed_selection_insert_connect_frames():
    frames=row_fixture.frames()
    assert len(frames)==82
    assert all(protocol.valid_reply(f[1:-1]) and f[4]==0x10 for f in frames)
    assert sum(f[6]==0x32 for f in frames)==28
    assert sum(f[6]==0x35 for f in frames)==26


@pytest.mark.parametrize('col,tail,checksum',[
    (2,(3,3,0),'22'),(4,(9,6,0),'2d'),(6,(15,9,0),'24'),
    (8,(21,12,0),'3b'),(10,(27,15,0),'36'),(12,(33,18,0),'11')])
def test_undecoded_shared_row1_even_geometry_uses_exact_captured_literal(col,tail,checksum):
    with pytest.raises(ValueError):shared.build_set_grid_routing(1,col,1)
    expected='f0 00 01 74 10 01 35 00 00 00 00 00 01 00 00 00 00 00 00 02 00 '
    expected+=' '.join(f'{b:02x}' for b in tail)+f' {checksum} f7'
    assert bytes(row_fixture.connect(1,col)).hex(' ')==expected


@pytest.mark.parametrize('row,col',[(r,c) for r in (1,2) for c in range(1,14)
                                  if r==2 or c%2])
def test_other_twenty_cables_match_shared_fm9_builder(row,col):
    assert row_fixture.connect(row,col)==grid.reframe(shared.build_set_grid_routing(row,col,row))


def test_shunts_keep_captured_slot_ids_and_payload_six_not_cursor_position():
    for col in range(1,15):
        frame=row_fixture.insert(2,col)
        assert shared.decode14(*frame[8:10])==1024+col-1
        assert frame[12:17]==[6,0,0,0,0]
    assert row_fixture.insert(1,7)[12:17]==[7,0,0,0,0]
    assert row_fixture.select(1,7)[12:17]==[36,0,0,0,0]


@pytest.mark.parametrize('row,col',[(0,1),(3,1),(1,0),(1,15),(True,1),(1,True),(None,1)])
def test_other_coordinates_are_not_inferred(row,col):
    for builder in (row_fixture.select,row_fixture.insert,row_fixture.connect):
        with pytest.raises(ValueError):builder(row,col)


def test_column14_has_no_outgoing_reference():
    with pytest.raises(ValueError):row_fixture.connect(1,14)


def test_reference_does_not_promote_profile_or_transport_permissions():
    dev=SimpleNamespace(reg=Registry(fw33_profile.KEY),_edit_target=320)
    for frame in row_fixture.frames():
        assert not grid.valid_write(frame,dev.reg)
        with pytest.raises(PermissionError):fw33.check_frame(dev,frame)


def test_exact_native_readback_is_read_only_and_detached_not_a_playable_graph():
    report=row_fixture.readback(cells(),fw33_profile.KEY)
    assert report['cells']==28 and report['cables']==26
    assert report['detached_shunt_test_row']
    assert not report['hardware_writes_supported'] and not report['physical_volume_verified']


@pytest.mark.parametrize('fault',['firmware','empty','missing','duplicate','wrong_effect','wrong_mask',
    'cross_row','wrong_shunt','boolean_mask','boolean_position'])
def test_readback_refuses_incomplete_foreign_or_miswired_grid(fault):
    actual=cells();fw=fw33_profile.KEY
    if fault=='firmware':fw='33.01'
    if fault=='empty':actual=[]
    if fault=='missing':actual.pop()
    if fault=='duplicate':actual.append(actual[0])
    if fault=='wrong_effect':actual[0].effect_id=38
    if fault=='wrong_mask':actual[1].cable_in_mask=0
    if fault=='cross_row':actual[1].cable_in_mask=4
    if fault=='wrong_shunt':actual[-1].is_shunt=False
    if fault=='boolean_mask':actual[0].cable_in_mask=False
    if fault=='boolean_position':actual[0].row=False
    with pytest.raises(ValueError):row_fixture.readback(actual,fw)

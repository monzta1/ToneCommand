"""Exact detached two-by-two measurement, not public arbitrary routing."""
from unittest.mock import Mock
import pytest
from fm9 import protocol as shared
from devices.axefx3 import parallel_fixture as fixture,grid,row_probe,fw33
from tests.test_axefx3_row_probe import device,cells
from devices.axefx3.adapter import AxeFxIII


def test_captured_order_and_96_masks_preserve_both_source_bits():
    steps=fixture.steps()
    assert len(steps)==24 and tuple(f for f,_,_ in steps)==fixture.frames()+fixture.removal_frames()
    assert steps[0][1]==steps[-1][2]=={}
    assert steps[11][2]==fixture.expected_grid()
    assert steps[12][2][5,2][2]==64 and steps[12][2][6,2][2]==96
    assert steps[13][2][5,2][2]==64 and steps[13][2][6,2][2]==64
    assert steps[14][2][5,2][2]==0 and steps[14][2][6,2][2]==64
    assert steps[15][2][6,2][2]==0
    assert all(steps[i][2]==steps[i+1][1] for i in range(23))


@pytest.mark.parametrize('source,target',fixture.EDGES)
@pytest.mark.parametrize('op',[1,2])
def test_eight_literals_match_shared_fm9_builder(source,target,op):
    assert fixture.cable(source,target,op)==grid.reframe(shared.build_set_grid_routing(source,1,target,op=op))


@pytest.mark.parametrize('row,col',[(1,1),(4,1),(5,3),(6,3),(True,1),(5,True)])
def test_other_positions_never_enabled(row,col):
    for builder in (fixture.select,fixture.insert,fixture.delete):
        with pytest.raises(ValueError):builder(row,col)


@pytest.mark.parametrize('source,target,op',[(4,5,1),(5,4,1),(5,6,3),(True,6,1),(5,6,True)])
def test_other_geometry_and_operations_never_enabled(source,target,op):
    with pytest.raises(ValueError):fixture.cable(source,target,op)


def test_native_order_probe_simulation_and_default_transport_refusal(monkeypatch):
    monkeypatch.setattr(row_probe.time,'sleep',lambda _:None)
    dev=device();probe=row_probe.Probe(dev,mode='parallel');state={}
    dev.read_grid=lambda:cells(state)
    def write(frame):
        assert row_probe.allowed(dev,frame);fw33.check_frame(dev,frame)
        state.clear();state.update(probe.sequence[probe.index][2])
    dev._write=Mock(side_effect=write)
    for frame,_,_ in probe.sequence:probe.write(frame)
    assert state=={} and probe.index==24 and dev._write.call_count==24
    assert dev._row_probe_permit is None
    dev.guard=AxeFxIII.guard;dev.outp=Mock();dev._approved_frame=None
    for frame,_,_ in probe.sequence:
        with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
        assert not grid.valid_write(frame,dev.reg)
    dev.outp.send.assert_not_called()


@pytest.mark.parametrize('mode',[None,True,'unknown','parallel '])
def test_probe_never_accepts_arbitrary_sequence_mode(mode):
    with pytest.raises(PermissionError):row_probe.Probe(device(),mode=mode)

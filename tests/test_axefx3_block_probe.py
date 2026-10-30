"""Exact322 block fixture cannot promote raw or public free-grid writes."""
from types import SimpleNamespace
from threading import RLock
from unittest.mock import Mock
import pytest
from fm9 import protocol as shared
from devices.axefx3 import block_probe as fixture,fw33,fw33_profile,grid
from devices.axefx3.registry import Registry
from devices.axefx3.adapter import AxeFxIII


def cells(state):
    return [shared.GridCell(r-1,c-1,e,s,m) for (r,c),(e,s,m) in state.items()]


def device():
    reg=Registry(fw33_profile.KEY);reg.hardware_variant='mk2'
    return SimpleNamespace(reg=reg,_edit_target=322,_lock=RLock(),
        _check_edit_target=Mock(),read_grid=lambda:[],_write=Mock(),
        _block_probe_permit=None,_block_probe=None)


def test_literal_sequences_are_isolated_and_exclude_feedback_and_extra_outputs():
    assert len(fixture.BLOCKS)==34 and len(fixture.steps())==136
    ids={item[2] for item in fixture.BLOCKS}
    assert len(ids)==34 and {202,206}<=ids and not ids.intersection({182,183,186,187,43,44,45})
    for index,(frame,before,after) in enumerate(fixture.steps()):
        assert frame[5]==1 and frame[6] in (0x30,0x32,0x33)
        assert shared.checksum(frame[1:-2])==frame[-2]
        assert len(before)<=1 and len(after)<=1
        assert all(value[2]==0 for value in dict(after).values())
        if index:assert fixture.steps()[index-1][2]==before
    assert fixture.steps()[0][1]==fixture.steps()[-1][2]==()


def test_all_136_steps_with_checked_transport_and_no_general_grid_promotion(monkeypatch):
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    dev=device();state={};probe=fixture.Probe(dev)
    dev.read_grid=lambda:cells(state)
    dev.guard=AxeFxIII.guard;dev.outp=Mock();dev._approved_frame=None
    def write(frame):
        assert fixture.allowed(dev,frame)
        fw33.check_frame(dev,frame)
        dev._approved_frame=tuple(frame)
        AxeFxIII._send(dev,frame)
        dev._approved_frame=None
        state.clear();state.update(dict(fixture.steps()[probe.index][2]))
    dev._write=Mock(side_effect=write)
    for frame,_,_ in fixture.steps():probe.write(frame)
    assert probe.index==136 and state=={} and dev._write.call_count==136
    assert dev.outp.send.call_count==136 and dev._block_probe_permit is None
    with pytest.raises(PermissionError):probe.write(fixture.steps()[0][0])
    for frame,_,_ in fixture.steps():
        assert not fixture.allowed(dev,frame)
        # Some cursor-only frames coincide with the existing NAM foundation.
        # That old frame predicate alone still cannot authorize transmission.
        if grid.valid_write(list(frame),dev.reg):
            assert frame[6]==0x30 and frame in tuple(
                tuple(grid.reframe(shared.build_select_grid_cell(3,col))) for col in range(1,8))
        with pytest.raises(PermissionError):AxeFxIII._send(dev,list(frame))
    assert dev.outp.send.call_count==136


@pytest.mark.parametrize('target',[None,True,320,321,323,324,329])
def test_other_presets_never_write(target):
    dev=device();dev._edit_target=target
    with pytest.raises(PermissionError):fixture.Probe(dev)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault',['firmware','variant','occupied','session','duplicate'])
def test_constructor_guards(fault):
    dev=device()
    if fault=='firmware':dev.reg=Registry('32.06')
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='occupied':dev.read_grid=lambda:cells({(6,14):(42,False,0)})
    if fault=='session':dev._check_edit_target.side_effect=PermissionError('No consent')
    if fault=='duplicate':dev._block_probe=object()
    with pytest.raises(PermissionError):fixture.Probe(dev)
    dev._write.assert_not_called()


@pytest.mark.parametrize('fault',['out_of_order','stale_grid','transport','readback','target','variant','identity','detached_probe'])
def test_fault_consumes_probe_without_retry_or_restore(monkeypatch,fault):
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    dev=device();probe=fixture.Probe(dev);frame=fixture.steps()[0][0]
    if fault=='out_of_order':frame=fixture.steps()[1][0]
    if fault=='stale_grid':dev.read_grid=lambda:cells({(1,1):(37,False,0)})
    if fault=='transport':dev._write.side_effect=OSError('Unknown send outcome')
    if fault=='readback':dev._write.side_effect=lambda _:setattr(dev,'read_grid',lambda:cells({(1,1):(37,False,0)}))
    if fault=='target':dev._edit_target=321
    if fault=='variant':dev.reg.hardware_variant='mk1'
    if fault=='identity':dev.reg=Registry('32.06')
    if fault=='detached_probe':dev._block_probe=None
    with pytest.raises((PermissionError,OSError,ValueError)):probe.write(frame)
    count=dev._write.call_count
    with pytest.raises(PermissionError):probe.write(frame)
    assert dev._write.call_count==count and dev._block_probe_permit is None and probe.failed


def test_single_frame_and_normal_action_permits_both_required():
    dev=device();probe=fixture.Probe(dev);frame=list(fixture.steps()[0][0])
    dev.guard=AxeFxIII.guard;dev.outp=Mock();dev._approved_frame=None
    dev._block_probe_permit=tuple(frame)
    assert not fixture.allowed(dev,frame)
    probe.failed=True
    assert fixture.allowed(dev,frame)
    with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
    dev._approved_frame=tuple(frame)
    AxeFxIII._send(dev,frame)
    dev._edit_target=321
    with pytest.raises(PermissionError):AxeFxIII._send(dev,frame)
    assert dev.outp.send.call_count==1


def test_chain_exactly_matches_previously_captured_complete_first_row():
    from devices.axefx3 import row_fixture
    steps=fixture.steps('chain')
    assert len(steps)==41
    assert tuple(s[0] for s in steps)==tuple(tuple(f) for f in row_fixture.frames()[:41])
    final=dict(steps[-1][2])
    assert len(final)==14
    assert final[1,1]==(37,False,0) and final[1,14]==(42,False,2)
    assert sum(f[6]==0x32 for f,_,_ in steps)==14
    assert sum(f[6]==0x35 and f[12]==1 for f,_,_ in steps)==13
    assert all(steps[i][2]==steps[i+1][1] for i in range(40))
    assert set(v[0] for v in final.values())=={e for e,_ in row_fixture.BLOCKS}


def test_chain_runs_checked_transport_and_stops_at_complete_connected_grid(monkeypatch):
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    dev=device();state={};probe=fixture.Probe(dev,mode='chain')
    dev.read_grid=lambda:cells(state)
    dev.guard=AxeFxIII.guard;dev.outp=Mock();dev._approved_frame=None
    def write(frame):
        assert fixture.allowed(dev,frame)
        fw33.check_frame(dev,frame)
        dev._approved_frame=tuple(frame)
        AxeFxIII._send(dev,frame)
        dev._approved_frame=None
        state.clear();state.update(dict(fixture.steps('chain')[probe.index][2]))
    dev._write=Mock(side_effect=write)
    for frame,_,_ in fixture.steps('chain'):probe.write(frame)
    assert probe.index==41 and len(state)==14 and dev.outp.send.call_count==41
    assert dev._block_probe_permit is None
    with pytest.raises(PermissionError):probe.write(fixture.steps('chain')[0][0])
    assert dev.outp.send.call_count==41


@pytest.mark.parametrize('mode',[None,True,'parallel','chain ','','arbitrary'])
def test_arbitrary_sequence_mode_is_never_authorized(mode):
    dev=device()
    with pytest.raises(PermissionError):fixture.Probe(dev,mode=mode)
    dev._write.assert_not_called()


@pytest.mark.parametrize('mode',['isolated','chain'])
def test_other_mode_frame_cannot_be_substituted(monkeypatch,mode):
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    dev=device();probe=fixture.Probe(dev,mode=mode);state={}
    dev.read_grid=lambda:cells(state)
    dev._write=Mock(side_effect=lambda _:state.update(dict(fixture.steps(mode)[probe.index][2])))
    for frame,_,_ in fixture.steps(mode)[:2]:probe.write(frame)
    alternative='chain' if mode=='isolated' else 'isolated'
    with pytest.raises(PermissionError):probe.write(fixture.steps(alternative)[2][0])
    assert dev._write.call_count==2 and probe.failed and dev._block_probe_permit is None


def test_connection_only_sequence_never_repeats_an_insert(monkeypatch):
    monkeypatch.setattr(fixture.time,'sleep',lambda _:None)
    sequence=fixture.steps('chain_connect')
    assert len(sequence)==13 and sequence==fixture.steps('chain')[28:]
    assert all(frame[6]==0x35 and frame[12]==1 for frame,_,_ in sequence)
    dev=device();state=dict(sequence[0][1]);dev.read_grid=lambda:cells(state)
    probe=fixture.Probe(dev,mode='chain_connect')
    def write(frame):
        assert fixture.allowed(dev,frame);fw33.check_frame(dev,frame)
        state.clear();state.update(dict(sequence[probe.index][2]))
    dev._write=Mock(side_effect=write)
    for frame,_,_ in sequence:probe.write(frame)
    assert probe.index==13 and state==dict(sequence[-1][2])
    assert dev._write.call_count==13 and dev._block_probe_permit is None


@pytest.mark.parametrize('fault',['empty','missing_block','existing_cable','wrong_id','extra_block'])
def test_connection_only_sequence_requires_exact_known_partial_state(fault):
    state=dict(fixture.steps('chain_connect')[0][1]);dev=device()
    if fault=='empty':state={}
    if fault=='missing_block':state.pop((1,14))
    if fault=='existing_cable':state[1,2]=(94,False,2)
    if fault=='wrong_id':state[1,8]=(74,False,0)
    if fault=='extra_block':state[6,14]=(43,False,0)
    dev.read_grid=lambda:cells(state)
    with pytest.raises(PermissionError):fixture.Probe(dev,mode='chain_connect')
    dev._write.assert_not_called()

"""Independent, in-memory checks of captured Chorus insertion, never hardware."""
import copy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fm9 import protocol as shared
from fm9.device import FM9
from fm9.protocol import BlockStatus, GridCell
from devices.axefx3 import grid, insertion, protocol, tone_review
from devices.axefx3.registry import Registry
from devices.axefx3.adapter import AxeFxIII


ROUTE = ['Input 1', 'Amp 1', 'Cab 1', 'Chorus 1', 'Delay 1',
         'Reverb 1', 'Output 1']
ADD = [dict(kind='add_block', block='CHORUS', instance=1)]


@pytest.fixture
def dev(monkeypatch):
    ids = [37, None, None, 58, 62, 70, 66, 42]
    state = dict(
        grid=[GridCell(2, c, eid, eid is None, 8 if c else 0)
              for c, eid in enumerate(ids)],
        blocks=[BlockStatus(eid, eid == 66, i % 4, 4)
                for i, eid in enumerate(ids) if eid is not None],
        bulk={eid: [eid, 11, 22, 33] * 32 for eid in ids if eid is not None},
        modifiers=[dict(words=[i] * 25, effect_id=58 if i == 0 else 0,
                        param_id=1 if i == 0 else 0, source=12 if i == 0 else 0)
                   for i in range(32)],
        preset=(324, 'Protected preset'), scene=3,
        scene_names=[(i, f'Protected scene {i}') for i in range(1, 9)],
        firmware='32.06', cabs=[])
    d = SimpleNamespace(reg=Registry('32.06'), state=state, writes=[],
                        selected=None, fault=None, move_count=0,
                        _grid_move_permit=None)
    d.read_grid = Mock(side_effect=lambda: copy.deepcopy(state['grid']))
    d.status_dump = Mock(side_effect=lambda: copy.deepcopy(state['blocks']))
    monkeypatch.setattr(tone_review, 'snapshot', lambda device: copy.deepcopy(device.state))
    monkeypatch.setattr(insertion.time, 'sleep', lambda _: None)

    def write(frame):
        d.writes.append(list(frame))
        payload = frame[6:-2]
        if payload[:2] == [0x30, 0]:
            pos = sum(v << (7*i) for i, v in enumerate(payload[6:11]))
            col, row = divmod(pos, 6)
            d.selected = (row, col)
        elif payload[:2] == [0x36, 0]:
            assert tuple(frame) == d._grid_move_permit
            d.move_count += 1
            if d.fault == 'exception':
                raise RuntimeError('Injected move exception')
            if d.fault == 'dropped':
                return
            row, col = d.selected
            source = next(c for c in state['grid'] if (c.row, c.col) == (row, col))
            state['grid'].remove(source)
            state['grid'].append(replace(source, col=col + (2 if d.fault == 'misplaced' else 1),
                                         cable_in_mask=0))
            if d.fault == 'collateral':
                state['grid'][0] = replace(state['grid'][0], cable_in_mask=8)
            mutate(d.fault, state)
        elif payload[:2] == [0x32, 0]:
            eid = shared.decode14(*payload[2:4])
            pos = shared.decode14(*payload[6:8])
            col, row = divmod(pos, 6)
            assert eid in (78,118,46)
            state['grid'].append(GridCell(row, col, eid, False, 0))
            state['blocks'].append(BlockStatus(eid, True, 0, 4))
            state['bulk'][eid] = [eid] * 128
            if d.fault == 'placement_state':
                state['bulk'][58][1] += 1
        elif payload[:2] == [0x35, 0]:
            if d.fault == 'cable':
                return
            match = next((r, c, dst) for r in range(2, 6) for c in range(1, 14)
                         for dst in range(2, 6)
                         if frame == grid.reframe(shared.build_set_grid_routing(r, c, dst)))
            r, c, dst = match
            cell = next(cell for cell in state['grid'] if (cell.row, cell.col) == (dst-1, c))
            state['grid'][state['grid'].index(cell)] = replace(cell, cable_in_mask=1 << r)
        else:
            raise AssertionError(f'Unexpected write {payload}')
    d._write = Mock(side_effect=write)
    d.place_block = Mock(side_effect=lambda position, eid: grid.place(d, position, eid))
    d.connect_cells = Mock(side_effect=lambda r, c, dst: grid.connect(d, r, c, dst))
    return d


def mutate(fault, state):
    if fault == 'bulk':
        state['bulk'][58][1] += 1
    elif fault == 'modifiers':
        state['modifiers'][0]['words'][0] += 1
    elif fault == 'preset':
        state['preset'] = (325, 'Different')
    elif fault == 'scene':
        state['scene'] = 4
    elif fault == 'names':
        state['scene_names'][0] = (1, 'Changed')
    elif fault in ('channel', 'bypass', 'channels_supported'):
        key = {'channel': 'channel', 'bypass': 'bypassed',
               'channels_supported': 'channels_supported'}[fault]
        value = not state['blocks'][0].bypassed if fault == 'bypass' else 2
        state['blocks'][0] = replace(state['blocks'][0], **{key: value})


def test_move_right_frame_matches_capture():
    assert insertion.move_right_frame() == protocol.envelope(
        1, [54, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0])


def test_success_preserves_shunts_and_full_original_state(dev, monkeypatch):
    before = copy.deepcopy(dev.state)
    shared_plan = FM9.plan_splice
    spy = Mock(side_effect=lambda device, row, col: shared_plan(device, row, col))
    monkeypatch.setattr(FM9, 'plan_splice', spy)
    result = insertion.build(dev, ROUTE, ADD)
    assert result.ok, result.detail
    spy.assert_called_once_with(dev, 3, 6)
    assert result.display_before == [37, 58, 62, 70, 66, 42]
    assert result.display_after == [37, 58, 62, 78, 70, 66, 42]
    assert insertion._held(before, dev.state)
    assert dev.state['grid'][:3] == before['grid'][:3]
    assert grid.snapshot(dev.state['grid']) == {
        (3, c+1): (eid, eid is None, 8 if c else 0)
        for c, eid in enumerate([37, None, None, 58, 62, 78, 70, 66, 42])}
    assert dev.move_count == 3
    assert [call.args for call in dev.connect_cells.call_args_list] == [
        (3, c, 3) for c in range(5, 9)]
    assert {tuple(f[6:8]) for f in dev.writes} == {
        (0x30, 0), (0x36, 0), (0x32, 0), (0x35, 0)}
    assert all(f[5] == 1 for f in dev.writes)
    assert dev._grid_move_permit is None


@pytest.mark.parametrize('bad', ['row', 'branch', 'missing_cab',
                                'no_slack', 'full_grid', 'gap', 'firmware'])
def test_invalid_complete_grid_refused_without_writes(dev, bad):
    cells = dev.state['grid']
    if bad == 'row':
        dev.state['grid'] = [replace(c, row=1, cable_in_mask=4 if c.col else 0) for c in cells]
    elif bad == 'branch':
        cells[5] = replace(cells[5], cable_in_mask=12)
    elif bad == 'downstream_shunt':
        dev.state['grid'] = [replace(c, col=c.col+1) if c.col >= 6 else c for c in cells]
        dev.state['grid'].append(GridCell(2, 6, None, True, 8))
    elif bad == 'missing_cab':
        cells[4] = replace(cells[4], effect_id=None, is_shunt=True)
        dev.state['blocks'] = [b for b in dev.state['blocks'] if b.effect_id != 62]
        del dev.state['bulk'][62]
    elif bad == 'no_slack':
        dev.state['grid'] = [replace(c, col=c.col+6) for c in cells]
    elif bad == 'full_grid':
        dev.state['grid'] = [replace(c, col=c.col+6) if c.col else c for c in cells]
        dev.state['grid'].extend(GridCell(2, c, None, True, 8) for c in range(1, 7))
    elif bad == 'gap':
        dev.state['grid'] = [replace(c, col=c.col+1) if c.col >= 5 else c for c in cells]
    else:
        dev.reg.firmware = 'unknown'
    with pytest.raises(ValueError):
        insertion.build(dev, ROUTE, ADD)
    assert not dev.writes
    dev.place_block.assert_not_called()
    dev.connect_cells.assert_not_called()


@pytest.mark.parametrize('fault', ['dropped', 'misplaced', 'collateral', 'bulk',
                                 'modifiers', 'preset', 'scene', 'names', 'channel',
                                 'bypass', 'channels_supported'])
def test_move_or_original_state_failure_halts_before_further_writes(dev, fault):
    dev.fault = fault
    result = insertion.build(dev, ROUTE, ADD)
    assert not result.ok
    assert 'keep external audio muted' in result.detail
    assert dev.move_count == 1
    assert len(dev.writes) == 2
    assert dev._grid_move_permit is None
    dev.place_block.assert_not_called()
    dev.connect_cells.assert_not_called()


def test_cable_failure_halts_without_later_connections(dev):
    dev.fault = 'cable'
    result = insertion.build(dev, ROUTE, ADD)
    assert not result.ok
    assert 'Cable did not verify' in result.detail
    dev.connect_cells.assert_called_once_with(3, 5, 3)
    assert dev._grid_move_permit is None


def test_placement_mutation_is_not_reported_as_success(dev):
    dev.fault = 'placement_state'
    result = insertion.build(dev, ROUTE, ADD)
    assert not result.ok
    assert 'Existing state changed' in result.detail


def test_move_permit_cleared_after_exception(dev):
    dev.fault = 'exception'
    with pytest.raises(RuntimeError, match='Injected move exception'):
        insertion.build(dev, ROUTE, ADD)
    assert dev._grid_move_permit is None
    assert dev.move_count == 1
    dev.place_block.assert_not_called()
    dev.connect_cells.assert_not_called()


@pytest.mark.parametrize('family,eid',[('FUZZ',118),('COMP',46)])
def test_preamp_insertion_preserves_downstream_shunts_and_settings(dev,family,eid):
    before=copy.deepcopy(dev.state)
    route=['Input 1', ('Drive 1' if eid==118 else 'Compressor 1'),
           'Amp 1','Cab 1','Delay 1','Reverb 1','Output 1']
    result=insertion.build(dev,route,[dict(kind='add_block',block=family)])
    assert result.ok,result.detail
    assert insertion._held(before,dev.state)
    assert result.display_after==[37,eid,58,62,70,66,42]
    assert sum(c.is_shunt for c in dev.state['grid'])==2
    assert dev._grid_move_permit is None


def test_combined_drive_comp_insertions_preserve_shunts_without_clearing(dev):
    before=copy.deepcopy(dev.state)
    route=['Input 1','Drive 1','Compressor 1','Amp 1','Cab 1','Delay 1','Reverb 1','Output 1']
    result=insertion.build(dev,route,[dict(kind='add_block',block=f) for f in ('FUZZ','COMP')])
    assert result.ok,result.detail
    assert insertion._held(before,dev.state)
    assert result.display_after==[37,118,46,58,62,70,66,42]
    assert sum(c.is_shunt for c in dev.state['grid'])==2
    assert not any(f[6:8]==[51,0] for f in dev.writes)


@pytest.mark.parametrize('approved', [False, True])
def test_transport_boundary_denies_raw_move_without_transaction_permit(approved):
    # Bypass constructor entirely: no ports, discovery or device requests.
    device = object.__new__(AxeFxIII)
    frame = insertion.move_right_frame()
    device.reg = Registry('32.06')
    device.outp = Mock()
    device._approved_frame = tuple(frame) if approved else None
    device._grid_move_permit = None
    device._check_edit_target = Mock()
    with pytest.raises(PermissionError):
        device._send(frame)
    device.outp.send.assert_not_called()
    device._check_edit_target.assert_not_called()

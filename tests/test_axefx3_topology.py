"""Synthetic graph checks do not authorize FW33 grid traffic."""
from dataclasses import replace
import pytest
from fm9.protocol import GridCell,BlockStatus
from devices.axefx3 import topology,fw33_profile
from devices.axefx3.registry import Registry


def rig():
    cells=[GridCell(2,0,37,False,0),GridCell(2,1,58,False,8),
           GridCell(1,2,70,False,8),GridCell(3,2,78,False,8),
           GridCell(2,3,42,False,4|16)]
    return cells,[BlockStatus(c.effect_id,False,0,4) for c in cells],Registry(fw33_profile.KEY)


def test_parallel_graph_preserves_both_branches_without_promoting_writes():
    cells,status,reg=rig();result=topology.inspect(cells,status,reg)
    assert result['parallel'] and len(result['edges'])==5
    assert ((2,1),(1,2)) in result['edges'] and ((3,2),(2,3)) in result['edges']
    assert not result['hardware_writes_supported'] and not result['physical_volume_verified']
    assert fw33_profile.NAM_ROUTE==(37,206,62,70,78,66,42)


def test_serial_with_shunt_is_not_flattened():
    cells=[GridCell(2,0,37,False,0),GridCell(2,1,None,True,8),GridCell(2,2,42,False,8)]
    status=[BlockStatus(e,False,0,4) for e in (37,42)]
    result=topology.inspect(cells,status,Registry('32.06'))
    assert not result['parallel'] and len(result['nodes'])==3 and len(result['edges'])==2


@pytest.mark.parametrize('field,value',[('row',6),('row',True),('col',14),('col',-1),
    ('cable_in_mask',True),('cable_in_mask',1),('cable_in_mask',128),('cable_in_mask',-1),
    ('is_shunt',1),('effect_id',True),('effect_id',999)])
def test_malformed_cells_refuse(field,value):
    cells,status,reg=rig();cells[2]=replace(cells[2],**{field:value})
    with pytest.raises(ValueError):topology.inspect(cells,status,reg)


@pytest.mark.parametrize('fault',['disconnected','no_source','extra_cell','duplicate','status','feedback','input_cable','after_output','dead_end','extra_io'])
def test_invalid_complete_graph_is_not_treated_as_a_working_chain(fault):
    cells,status,reg=rig()
    if fault=='disconnected':cells[2]=replace(cells[2],cable_in_mask=0)
    if fault=='no_source':cells[2]=replace(cells[2],cable_in_mask=2)
    if fault=='extra_cell':cells.append(GridCell(4,4,None,True,8))
    if fault=='duplicate':cells.append(cells[0])
    if fault=='status':status.pop()
    if fault=='feedback':
        cells[2]=replace(cells[2],effect_id=182);status[2]=BlockStatus(182,False,0,4)
    if fault=='input_cable':cells[0]=replace(cells[0],cable_in_mask=8)
    if fault=='after_output':cells.append(GridCell(2,4,None,True,8))
    if fault=='dead_end':cells[-1]=replace(cells[-1],cable_in_mask=4)
    if fault=='extra_io':
        cells[2]=replace(cells[2],effect_id=38);status[2]=BlockStatus(38,False,0,4)
    with pytest.raises(ValueError):topology.inspect(cells,status,reg)


def test_only_actual_empty_state_is_empty():
    reg=Registry(fw33_profile.KEY)
    assert topology.inspect([],[],reg)['nodes']=={}
    for cells,status in [(None,[]),([],None),([],[BlockStatus(37,False,0,4)])]:
        with pytest.raises(ValueError):topology.inspect(cells,status,reg)

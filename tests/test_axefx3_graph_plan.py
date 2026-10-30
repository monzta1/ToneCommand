"""Explicit graph proposals remain read-only and separate from SEND actions."""
from copy import deepcopy
import pytest
from fm9.protocol import GridCell,BlockStatus
from devices.axefx3 import graph_plan,fw33_profile
from devices.axefx3.registry import Registry


def spec(names=('Input','Amp','Cab','Output')):
    return dict(cells=[dict(position=[3,i],block=name,instance=1) for i,name in enumerate(names,1)],
                connections=[dict(source=[3,i],target=[3,i+1]) for i in range(1,len(names))])


def state():
    ids=(37,58,62,42)
    return dict(preset=(324,'Test'),scene=1,firmware=fw33_profile.KEY,
        grid=[GridCell(2,i,e,False,8 if i else 0) for i,e in enumerate(ids)],
        blocks=[BlockStatus(e,False,0,4) for e in ids],bulk={e:[0]*16 for e in ids},
        modifiers=[dict(slot=i,words=[0]*25,effect_id=0) for i in range(1,33)],
        scene_names=[(i,'Test') for i in range(1,9)])


def test_identical_graph_has_no_changes_and_cannot_send():
    current=state();before=deepcopy(current)
    report=graph_plan.review(current,spec(),Registry(fw33_profile.KEY))
    assert report['operations']==[] and current==before
    assert not report['hardware_writes_supported'] and not report['physical_volume_verified']
    assert not report['stored'] and 'token' not in report and 'actions' not in report


def test_upper_mk2_snapshot_cannot_be_reused_as_mk1():
    from devices.axefx3 import profile
    current=state();current['preset']=(1023,'Upper MK2')
    reg=Registry(fw33_profile.KEY);profile.apply(reg,'mk2')
    assert graph_plan.review(current,spec(),reg)['operations']==[]
    profile.apply(reg,'mk1')
    with pytest.raises(ValueError,match='identity'):graph_plan.review(current,spec(),reg)


def test_insertion_reports_existing_moves_not_delete_and_recreate():
    report=graph_plan.review(state(),spec(('Input','Amp','Drive','Cab','Output')),Registry(fw33_profile.KEY))
    moved=[o for o in report['operations'] if o['kind']=='move_block']
    assert {o['effect_id'] for o in moved}=={62,42}
    assert all(o['preserve_full_state'] for o in moved)
    assert not any(o['kind']=='remove_block' for o in report['operations'])
    # The geometrically unchanged2->3 cable still needs rewiring: its target changed.
    assert dict(kind='disconnect',source=[3,2],target=[3,3]) in report['operations']
    assert dict(kind='connect',source=[3,2],target=[3,3]) in report['operations']


def test_parallel_proposal_preserves_edges_and_reports_modifier_impacts():
    request=dict(cells=[dict(position=[3,1],block='Input',instance=1),
        dict(position=[3,2],block='Amp',instance=1),
        dict(position=[2,3],block='Cab',instance=1),
        dict(position=[4,3],block='Chorus',instance=1),
        dict(position=[3,4],block='Output',instance=1)],
        connections=[dict(source=a,target=b) for a,b in [([3,1],[3,2]),([3,2],[2,3]),
            ([3,2],[4,3]),([2,3],[3,4]),([4,3],[3,4])]])
    current=state();current['modifiers'][0]['effect_id']=62
    report=graph_plan.review(current,request,Registry(fw33_profile.KEY))
    assert report['parallel'] and report['affected_modifier_slots']==[1]
    assert dict(kind='connect',source=[4,3],target=[3,4]) in report['operations']


@pytest.mark.parametrize('fault',['empty','extra','position','backward','skip','duplicate_cable',
    'duplicate_position','duplicate_block','unknown','boolean_instance','dangling','missing_output','feedback'])
def test_invalid_graph_never_becomes_a_proposal(fault):
    request=spec()
    if fault=='empty':request['cells']=[]
    if fault=='extra':request['auto_send']=True
    if fault=='position':request['cells'][0]['position']=[True,1]
    if fault=='backward':request['connections'][0]=dict(source=[3,2],target=[3,1])
    if fault=='skip':request['connections'][0]['target']=[3,3]
    if fault=='duplicate_cable':request['connections'].append(request['connections'][0])
    if fault=='duplicate_position':request['cells'][1]['position']=[3,1]
    if fault=='duplicate_block':request['cells'][2]['block']='Amp'
    if fault=='unknown':request['cells'][1]['block']='unverified'
    if fault=='boolean_instance':request['cells'][1]['instance']=True
    if fault=='dangling':request['connections'].pop()
    if fault=='missing_output':request['cells'][-1]['block']='Delay'
    if fault=='feedback':request['cells'][1]['block']='feedback return'
    with pytest.raises(ValueError):graph_plan.review(state(),request,Registry(fw33_profile.KEY))


@pytest.mark.parametrize('fault',['identity','scene','firmware','bulk','modifiers','names','grid'])
def test_incomplete_baseline_is_not_reviewable(fault):
    current=state()
    if fault=='identity':current['preset']=(True,'Test')
    if fault=='scene':current['scene']=0
    if fault=='firmware':current['firmware']='future'
    if fault=='bulk':current['bulk'].pop(58)
    if fault=='modifiers':current['modifiers'][0]['words'].pop()
    if fault=='names':current['scene_names'].pop()
    if fault=='grid':current['grid']=None
    with pytest.raises(ValueError):graph_plan.review(current,spec(),Registry(fw33_profile.KEY))


def test_full_state_fingerprint_changes_even_when_topology_does_not():
    current=state();reg=Registry(fw33_profile.KEY)
    first=graph_plan.review(current,spec(),reg)
    current['bulk'][58][0]=1
    second=graph_plan.review(current,spec(),reg)
    assert first['operations']==second['operations']==[]
    assert first['state_fingerprint']!=second['state_fingerprint']


def test_shunt_is_explicit_and_not_an_empty_cell():
    request=spec();request['cells'][1]=dict(position=[3,2],shunt=True)
    report=graph_plan.review(state(),request,Registry(fw33_profile.KEY))
    assert dict(kind='add_shunt',position=[3,2]) in report['operations']
    assert any(o['kind']=='remove_block' and o['effect_id']==58 for o in report['operations'])
    request['cells'][1]['block']='Amp'
    with pytest.raises(ValueError):graph_plan.review(state(),request,Registry(fw33_profile.KEY))


def test_real_numbered_blank_scene_names_are_valid_but_missing_numbers_are_not():
    current=state();current['scene_names']=[(i,'') for i in range(1,9)]
    assert graph_plan.review(current,spec(),Registry(fw33_profile.KEY))['operations']==[]
    current['scene_names'][0]=(2,'')
    with pytest.raises(ValueError):graph_plan.review(current,spec(),Registry(fw33_profile.KEY))

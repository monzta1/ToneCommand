"""Closed core grammar and preservation contracts, not hardware acceptance."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from devices.axefx3 import beta5_core as core,beta5_core_plan as plans
from devices.axefx3.beta5_core_codec import Operation,operations,grid,NODES,STRIDES
from devices.axefx3.registry import Registry,SUPPORTED_FIRMWARE
from devices.axefx3 import firmware_identity,profile,protocol
from fm9 import protocol as shared


def reg(variant='mk2'):
    r=Registry(firmware_identity.BETA5_KEY);r.hardware_variant=variant;return r


def design(**extra):
    return dict(name='Core Test',scene_name='Crunch',summary='British crunch approximation.',
        amp_model='Brit 800 2204 High',cab=dict(bank=1,slot=516),
        amp=dict(gain=5.2,bass=4.2,mid=6.3,treble=5.1,master=5.,depth=2.3,presence=3.8,level=-18.),**extra)


def state():
    return dict(grid=grid(),status=[dict(effect_id=e,channel=0,bypassed=e==58,channels_supported=4) for e in NODES],
        bulk={str(e):[0]*(4*STRIDES[e]) for e in NODES},preset=[327,'<EMPTY>'],scenes=[[n,''] for n in range(1,9)])


def test_compiler_exact_names_ir_slot_and_single_prefix():
    p=plans.compile_design(reg(),design())
    assert p['name']=='AI-Core Test' and p['scenes']==['Crunch']
    assert p['cab_choices'][0]['name']=='4x12 Brit 70s GB 57 A'
    assert plans.compile_design(reg('mk1'),design())==p
    raw=design();raw['name']=p['name'];assert plans.compile_design(reg(),raw)['name']==p['name']
    assert firmware_identity.BETA5_KEY not in SUPPORTED_FIRMWARE


@pytest.mark.parametrize('change',[{'amp_model':'made up'},{'name':' bad '},{'name':'x'*30},
    {'cab':{'bank':True,'slot':1}},{'cab':{'bank':6,'slot':1}},
    {'cab':{'bank':0,'slot':0}},{'cab':{'bank':0,'slot':1025}},
    {'extra':'MIDI'},{'scene_name':'bad\nname'}])
def test_invalid_proposal_cannot_mint_an_operation(change):
    raw=design();raw.update(change)
    with pytest.raises(ValueError):plans.compile_design(reg(),raw)


def test_reserved_mk1_user2_metadata_cannot_be_selected():
    r=reg('mk1');r.cab_catalog.names[(3,0)]='Private model name'
    raw=design();raw['cab']={'bank':3,'slot':1}
    with pytest.raises(ValueError,match='reserved'):plans.compile_design(r,raw)
    r.hardware_variant='mk2';assert plans.compile_design(r,raw)['cab_choices'][0]['wire_bank']==3


@pytest.mark.parametrize('field,value',[('gain',True),('gain',10.1),('mid',float('nan')),
    ('level',-11.9),('level',float('inf')),('master',5.01),('depth',-1)])
def test_amp_domains_fail_closed(field,value):
    raw=design();raw['amp'][field]=value
    with pytest.raises(ValueError):plans.compile_design(reg(),raw)


def test_literal_graph_and_type_a_frames_only():
    p=plans.compile_design(reg(),design());ops=operations(p,True)
    assert ops[:4]==(Operation('select',42),Operation('insert',42),Operation('channel',42),Operation('param',42,12,-18))
    assert [op.eid for op in ops if op.kind=='insert']==[42,37,58,62]
    assert [op.eid for op in ops if op.kind=='edge']==[58,62,42]
    assert all(frame[4]==16 and frame[5]==1 and protocol.valid_reply(frame[1:-1]) for frame in (op.frame(327) for op in ops))
    assert Operation('select',62).frame(327)[6:-2]==[48,0,0,0,0,0,12,0,0,0,0,0,0,0,0]
    assert Operation('edge',58).frame(327)[-4:]==[1,64,99,247]
    assert not any(op.kind in ('insert','select','edge') for op in operations(p,False))


@pytest.mark.parametrize('op', [Operation('delete',58),Operation('insert',206),Operation('edge',37),
    Operation('channel',58,value=1),Operation('param',42,12,0),Operation('param',62,0,6),
    Operation('param',62,4,1024),Operation('param',58,0,336),Operation('param',58,21,0),
    Operation('param',62,25,0),Operation('param',62,13,0),Operation('name',pid=2,text='wrong')])
def test_no_raw_generic_graph_resource_or_unsafe_level_operation(op):
    with pytest.raises(ValueError):op.frame(327)


def test_display_float32_first_and_literal_zero_setter():
    f=plans.amp_frame('gain',5.2)
    assert f[6:12]==[9,0,58,0,1,0]
    assert shared.decode_f32_septets(f[12:17])==pytest.approx(.5199999809265137)
    assert plans.amp_frame('depth',0)[6:8]==[9,0]


@pytest.mark.parametrize('damage',['other_word','other_channel','grid','names','status'])
def test_numeric_readback_does_not_hide_collateral_state(damage):
    before=state();after=deepcopy(before);after['bulk']['58'][1]=round(.52*65534)
    core._expected(before,after,Operation('param',58,1,5.2))
    if damage=='other_word':after['bulk']['58'][2]=1
    elif damage=='other_channel':after['bulk']['58'][143]=1
    elif damage=='grid':after['grid'][1]['cable_in_mask']=4
    elif damage=='names':after['scenes'][2][1]='changed'
    else:after['status'][1]['channel']=1
    with pytest.raises(ValueError):core._expected(before,after,Operation('param',58,1,5.2))


def test_model_reset_is_a_only_bypassed_quiet_and_level_preserved():
    before=state();before['bulk']['58'][21]=round(.62*65534)
    after=deepcopy(before);after['bulk']['58'][0]=10;after['bulk']['58'][3]=123
    core._expected(before,after,Operation('param',58,0,10))
    for field in ('bypass','level','other_channel'):
        old,new=deepcopy(before),deepcopy(after)
        if field=='bypass':old['status'][1]['bypassed']=False;new['status'][1]['bypassed']=False
        elif field=='level':new['bulk']['58'][21]=50000
        else:new['bulk']['58'][142]=10
        with pytest.raises(ValueError):core._expected(old,new,Operation('param',58,0,10))


def test_cab_slot_level_is_not_block_level_and_mix_is_explicit():
    before=state();after=deepcopy(before);after['bulk']['62'][8]=65534
    core._expected(before,after,Operation('param',62,8,0))
    after['bulk']['62'][8]=52427
    with pytest.raises(ValueError):core._expected(before,after,Operation('param',62,8,0))
    ops=operations(plans.compile_design(reg(),design()),True)
    assert [op.value for op in ops if op.eid==62 and op.pid in range(24,28)]==[0,1,1,1]


def test_default_readonly_and_explicit_profile_only(monkeypatch):
    d=SimpleNamespace(reg=reg());monkeypatch.delenv('TONECOMMAND_BETA5_CORE',raising=False)
    assert not core.supported(d)
    monkeypatch.setenv('TONECOMMAND_BETA5_CORE','1');assert core.supported(d)
    d.reg.hardware_variant=None;assert not core.supported(d)
    d.reg=Registry('33.00');d.reg.hardware_variant='mk2';assert not core.supported(d)


def test_stale_and_declined_send_are_consumed_before_io(monkeypatch):
    d=Mock();review=core.Reviews(clock=lambda:10)
    monkeypatch.setattr(core,'snapshot',Mock(side_effect=AssertionError('must not read or write')))
    for values in [(False,True),(True,False)]:
        review.pending=dict(device=d,token='token',expires=20)
        with pytest.raises(ValueError):review.send(d,'token',*values)
        assert review.pending is None
    review.pending=dict(device=d,token='token',expires=10)
    with pytest.raises(ValueError):review.send(d,'token',True,True)
    d.outp.send.assert_not_called()


def reader_fixture():
    from tests.test_axefx3_firmware_identity import BETA5
    from fm9.protocol import BlockStatus
    class Device:pass
    d=Device();d.reg=reg()
    d._request=lambda *a:list(BETA5)
    d.current_preset=lambda:(327,'<EMPTY>');d.current_scene=lambda:1
    d.status_dump=lambda:[BlockStatus(200,False,0,1),BlockStatus(201,False,0,1)]
    d.read_grid=lambda:[]
    d.bulk_read=lambda eid:[65535]*1525 if eid==200 else [0]*350
    d.read_modifier=lambda n:[0]*25
    d.scene_name=lambda n:(n,'')
    return d


def test_empty_complete_snapshot_retains_controller_sentinel_words(monkeypatch):
    monkeypatch.setenv('TONECOMMAND_BETA5_CORE','1');d=reader_fixture()
    current=core.snapshot(d);core.prepare_base(current)
    assert current['bulk']['200'][0]==65535 and current['grid']==[]


@pytest.mark.parametrize('fault',['identity','preset','scene','missing_bulk','short_bulk','active_modifier',
    'assigned_modifier','missing_modifier','missing_scene','unknown_block','duplicate_block'])
def test_native_inspection_refuses_incomplete_or_changed_context(monkeypatch,fault):
    from fm9.protocol import BlockStatus
    monkeypatch.setenv('TONECOMMAND_BETA5_CORE','1');d=reader_fixture()
    if fault=='identity':d._request=lambda *a:protocol.envelope(8,[33,0])[1:-1]
    elif fault=='preset':d.current_preset=lambda:(1024,'Out of range')
    elif fault=='scene':d.current_scene=lambda:2
    elif fault=='missing_bulk':d.bulk_read=lambda eid:None
    elif fault=='short_bulk':d.bulk_read=lambda eid:[0]
    elif fault=='active_modifier':d.read_modifier=lambda n:[1]+[0]*24
    elif fault=='assigned_modifier':d.read_modifier=lambda n:[0]*8+[58]+[0]*16
    elif fault=='missing_modifier':d.read_modifier=lambda n:None
    elif fault=='missing_scene':d.scene_name=lambda n:None
    elif fault=='unknown_block':d.status_dump=lambda:[BlockStatus(200,False,0,1),BlockStatus(201,False,0,1),BlockStatus(206,False,0,4)]
    else:d.status_dump=lambda:[BlockStatus(200,False,0,1),BlockStatus(200,False,0,1),BlockStatus(201,False,0,1)]
    with pytest.raises(ValueError):core.snapshot(d)

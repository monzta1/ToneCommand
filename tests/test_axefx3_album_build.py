"""Synthetic bounded album execution; native acceptance is separately recorded."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from fm9.device import SetResult
from fm9 import protocol as shared
from devices.axefx3 import album_build as build,album_planning as planning,executor,fw33,serial_build,tone_review
from devices.axefx3 import store_review
from devices.axefx3.adapter import AxeFxIII
from test_axefx3_serial_build import fake
import server
from tests.scene_intent_fixtures import with_goals


def design():
    d=build.seed().model_dump()
    d['name']='Metallica albums'
    for c,a in enumerate(d['albums']):
        a['amp']['gain']=float(5+c*.7)
        a['amp_model']=planning.MODELS[14 if c==0 else 267]
        a['cab']='Greenback' if c==0 else 'Recto'
        a['lead']['name']=f'Album {c+1} Lead'
        a['solo'].update(name=f'Album {c+1} Solo',delay=True,chorus=True)
    return d


def device(monkeypatch):
    d=fake(True);name=['Test'];scene=[1];names=[(n,'Scene'+str(n)) for n in range(1,9)]
    d.guard=AxeFxIII.guard;d.outp=Mock();d._approved_frame=None
    d.current_preset=lambda:(322,name[0]);d.current_scene=lambda:scene[0]
    d.scene_name=lambda n:names[n-1]
    d.rename_preset=Mock(side_effect=lambda v:(name.__setitem__(0,v) or (322,v)))
    d.rename_scene=Mock(side_effect=lambda n,v:(names.__setitem__(n-1,(n,v)) or (n,v)))
    d.get_channel=lambda e:d._test_blocks[e].channel
    d.get_bypass=lambda e:d._test_blocks[e].bypassed
    words=[0]*424
    for c in range(4):
        words[c*106+8:c*106+12]=[65534]*4
        words[c*106+12:c*106+16]=[32767]*4
        words[c*106+24:c*106+28]=[0,1,1,1]
    d._test_bulk[62]=words
    scenes={n:dict(d._test_blocks) for n in range(1,9)}
    original_bypass=d.set_bypass.side_effect
    def bypass(e,value):
        result=original_bypass(e,value)
        scenes[scene[0]]=dict(d._test_blocks)
        return result
    d.set_bypass.side_effect=bypass
    def param(spec,value):
        c=d.get_channel(spec.effect_id);stride=len(d._test_bulk[spec.effect_id])//4
        d._test_bulk[spec.effect_id][c*stride+spec.param_id]=round(shared.display_to_normalized(value,spec.dmin,spec.dmax,spec.scale)*65534)
        return SetResult(True,'Independent display matched',None,value)
    d.set_param_display=Mock(side_effect=param)
    def channel(e,c):
        d._test_blocks[e]=replace(d._test_blocks[e],channel=c)
        scenes[scene[0]]=dict(d._test_blocks)
        return c
    d.set_channel=Mock(side_effect=channel)
    def activate(number):
        scenes[scene[0]]=dict(d._test_blocks)
        scene[0]=number;d._test_blocks.clear();d._test_blocks.update(scenes[number])
        return number
    d.set_scene=Mock(side_effect=activate)
    def write(frame):
        assert build.frame_allowed(d,frame)
        d._approved_frame=tuple(frame)
        try:AxeFxIII._send(d,frame)
        finally:d._approved_frame=None
        item=d._album_session.item
        if item.action['kind']=='set_scene':
            activate(item.value)
        elif item.action['kind']=='set_channel':channel(item.effect_id,item.value)
        elif item.action['kind']=='set_bypass':
            d._test_blocks[item.effect_id]=replace(d._test_blocks[item.effect_id],bypassed=item.value)
            scenes[scene[0]]=dict(d._test_blocks)
        else:
            eid=shared.decode14(*frame[8:10]);pid=shared.decode14(*frame[10:12])
            value=int(shared.decode_f32_septets(frame[12:17]));stride=len(d._test_bulk[eid])//4
            d._test_bulk[eid][stride*d.get_channel(eid)+pid]=value
    d._write=Mock(side_effect=write)
    d._test_scenes=scenes
    monkeypatch.setattr(build.time,'sleep',lambda _:None)
    return d


def plan(d):return planning.compile_design(d.reg,design(),list(serial_build.ROUTE),8)


def test_canonical_eight_scenes_and_one_shared_voice_per_album(monkeypatch):
    d=device(monkeypatch);p=plan(d)
    build.validate_actions(d.reg,p['actions'],True)
    assert p['mode']=='album' and len(p['scenes'])==8
    assert [m['amp'] for m in p['channel_mapping']]==list('AABBCCDD')
    assert all(m['delay']==m['chorus']==m['output']=='A' for m in p['channel_mapping'])
    assert len([a for a in p['actions'] if a['kind']=='set_type'])==4
    assert len([a for a in p['actions'] if a['kind']=='set_cab'])==4
    assert not any(a['kind'] in ('store','bind_controller','bind_pedal','select_nam') for a in p['actions'])
    empty=planning.compile_design(d.reg,design(),[],8)
    build.validate_actions(d.reg,empty['actions'],False)
    assert len([a for a in empty['actions'] if a['kind']=='add_block'])==12


def test_normal_review_send_full_state_checks_and_no_nam_or_store(monkeypatch):
    d=device(monkeypatch);p=plan(d);reviews=tone_review.Reviews()
    initial=tone_review.snapshot(d,include_nam=False)
    prepared=reviews.prepare(d,p,initial)
    d._write.assert_not_called();d.set_param_display.assert_not_called()
    result=reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'],result
    assert result['skipped']==0 and d.current_scene()==8
    assert len(result['album_verification']['scene_fingerprints'])==8
    assert d.current_preset()[1]=='AI-Metallica albums'
    assert d._album_session is None and d._serial_session is None
    assert all(d._test_blocks[e].bypassed for e in serial_build.RESERVE)
    assert [d._test_bulk[58][142*c] for c in range(4)]==[14,267,267,267]
    assert [d._test_bulk[62][106*c+4] for c in range(4)]==[515,799,799,799]
    for n,states in d._test_scenes.items():
        assert not states[58].bypassed and not states[62].bypassed
        assert states[58].channel==states[62].channel==(n-1)//2
        assert states[70].bypassed==bool(n%2) and states[78].bypassed==bool(n%2)
        assert all(states[e].bypassed for e in serial_build.RESERVE)
    assert not result['stored'];d.store_preset.assert_not_called();d.read_nam_slot.assert_not_called()
    with pytest.raises(ValueError):reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)


@pytest.mark.parametrize('fault',['output','unsafe_amp','negative','model','cab','bank','right','fifth_channel',
    'reserve','reorder','extra','incomplete','modifier','ir2','pan','legacy','layout','scene','variant','route'])
def test_invalid_contract_fails_before_writes(monkeypatch,fault):
    d=device(monkeypatch);p=plan(d);a=p['actions']
    if fault=='output':a[0]['value']=-6
    if fault=='unsafe_amp':next(x for x in a if x.get('param')=='DISTORT_LEVEL')['value']=-1
    if fault=='negative':next(x for x in a if x.get('param')=='DISTORT_DEPTH')['value']=-.01
    if fault=='model':next(x for x in a if x['kind']=='set_type')['type_name']='Unknown amplifier'
    if fault=='cab':next(x for x in a if x['kind']=='set_cab')['value']=841
    if fault=='bank':next(x for x in a if x['kind']=='set_cab')['bank']=2
    if fault=='right':next(x for x in a if x['kind']=='set_cab')['cab_side']='right'
    if fault=='fifth_channel':next(x for x in a if x['kind']=='set_channel')['value']=4
    if fault=='reserve':next(x for x in a if x.get('block')=='WAH')['bypassed']=False
    if fault=='reorder':a[1],a[2]=a[2],a[1]
    if fault=='extra':a.append(dict(kind='set_scene',value=1))
    if fault=='incomplete':a.pop(5)
    if fault=='modifier':d.read_modifier=lambda slot:([1]+[0]*24) if slot==1 else [0]*25
    if fault=='ir2':d._test_bulk[62][25]=0
    if fault=='pan':d._test_bulk[62][12]=0
    if fault=='legacy':d._test_bulk[62][31]=1
    if fault=='layout':d._test_bulk[58]=[0]*142
    if fault=='scene':d.current_scene=lambda:2
    if fault=='variant':d.reg.hardware_variant='mk1'
    if fault=='route':d._test_cells[(2,1)]=d._test_cells.pop((1,1))
    with pytest.raises((ValueError,KeyError)):executor.prepare(d,a,p['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called();d.set_bypass.assert_not_called()


@pytest.mark.parametrize('fault',['drop','other_channel','other_block','modifier'])
def test_failed_write_consumes_session_without_retry_or_store(monkeypatch,fault):
    d=device(monkeypatch);p=plan(d);original=d._write.side_effect
    def bad(frame):
        if fault!='drop':original(frame)
        if fault=='other_channel':d._test_bulk[58][400]=99
        if fault=='other_block':d._test_bulk[70][88]=99
        if fault=='modifier':d.read_modifier=lambda _:([1]+[0]*24)
    d._write.side_effect=bad
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert not result['ok'] and result['skipped']>0
    assert d._write.call_count==1 and d._album_session is None
    d.store_preset.assert_not_called()


def test_raw_frames_need_both_active_reviewed_action_and_approved_frame(monkeypatch):
    d=device(monkeypatch);p=plan(d);resolved=[executor.resolve(d.reg,a) for a in p['actions']]
    item=next(i for i in resolved if i.action['kind']=='set_type')
    frame=build.protocol.param_frame(58,0,14,opcode=9)
    with pytest.raises((PermissionError,ValueError,KeyError)):AxeFxIII._send(d,frame)
    with build.execution(d,resolved,True) as s:
        s.item=item;s.frame=tuple(frame)
        assert build.frame_allowed(d,frame)
        with pytest.raises(PermissionError):AxeFxIII._send(d,frame)
        d._approved_frame=tuple(frame);AxeFxIII._send(d,frame)
        d._approved_frame=None
        for wrong in (build.protocol.param_frame(58,0,15,opcode=9),build.protocol.param_frame(62,4,799,opcode=9)):
            s.frame=tuple(wrong);assert not build.frame_allowed(d,wrong)
    assert d.outp.send.call_count==1


def test_registered_amp_plan_review_and_send_without_nam(monkeypatch):
    d=device(monkeypatch)
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None);monkeypatch.setenv('PLANNER_BACKEND','cli')
    ask=Mock(side_effect=lambda *args,**kw:dict(**kw['validate'](with_goals(design())),backend='cli',model='synthetic'))
    monkeypatch.setattr(server.planner,'plan',ask)
    server._afx3_tone_reviews.clear()
    with TestClient(server.app) as client:
        response=client.post('/api/axefx3/plan',json=dict(prompt='Metallica four albums lead and solo',expected_preset=322,mode='amp',scenes=8))
        assert response.status_code==200,response.text
        prepared=response.json();assert prepared['mode']=='album' and prepared['target']['nam'] is None
        d._write.assert_not_called();d.set_param_display.assert_not_called()
        assert 'not necessarily four album pairs' in ask.call_args.kwargs['system']
        sent=client.post('/api/axefx3/send',json=dict(token=prepared['token'],target_confirmed=True,external_audio_muted=True))
        assert sent.status_code==200 and sent.json()['ok'],sent.text
    d.read_nam_slot.assert_not_called();d.store_preset.assert_not_called()
    server._afx3_tone_reviews.clear()


def test_user_cab_request_uses_imported_names_without_automatic_send(monkeypatch):
    d=device(monkeypatch)
    d.reg.import_cab_names('U1.0028 Metallica V30', 'user')
    monkeypatch.setattr(server,'_context',server.DeviceContext('axefx3',d.reg,d,'Axe-Fx III'))
    monkeypatch.setattr(server,'_gig_mode',{'on':False});monkeypatch.setattr(server,'_plan_revisions',{})
    monkeypatch.setattr(server,'_audition',{'open':False})
    monkeypatch.setattr(server.ai_settings,'apply_to_env',lambda:None);monkeypatch.setenv('PLANNER_BACKEND','cli')
    from test_axefx3_cab_design import design as cab_design
    raw=cab_design()
    for album in raw['albums']:
        album['cab']['irs'][0].update(bank=2,slot=28)
    ask=Mock(side_effect=lambda *args,**kw:dict(**kw['validate'](with_goals(raw)),backend='cli',model='synthetic'))
    monkeypatch.setattr(server.planner,'plan',ask)
    with TestClient(server.app) as client:
        state=client.get('/api/axefx3/state').json()
        assert state['workspace']['contract']=='fx3-workspace-20261012'
        assert state['album_build_supported'] and 'User cab selection' in state['cab_selection_note']
        response=client.post('/api/axefx3/plan',json=dict(
            prompt='Metallica albums, zoek een geschikte CAB in de usercab bibliotheek',
            expected_preset=322,mode='amp',scenes=8))
        assert response.status_code==200,response.text
        assert response.json()['cab_choices'][0]['irs'][0]['name']=='Metallica V30'
    ask.assert_called_once();d._write.assert_not_called();d.set_param_display.assert_not_called()
    d.store_preset.assert_not_called()


def test_album_store_is_separate_and_requires_complete_unchanged_send(monkeypatch):
    d=device(monkeypatch);p=plan(d);stores=store_review.Stores()
    monkeypatch.setattr(store_review,'get_store_slots',lambda:{322})
    d.slot_name=Mock(return_value=SimpleNamespace(number=322,name='<EMPTY>'))
    d.store_preset=Mock(return_value=(322,'AI-Metallica albums'))
    with pytest.raises(ValueError):stores.prepare(d,322)
    reviews=tone_review.Reviews();prepared=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    sent=reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    assert sent['ok'] and d._album_store_stamp
    preview=stores.prepare(d,322);d.store_preset.assert_not_called()
    with pytest.raises(PermissionError):stores.send(d,preview['token'],False,True)
    stored=stores.send(d,preview['token'],True,True)
    assert stored['stored'] and not stored['reloaded']
    assert d.store_preset.call_count==1
    with pytest.raises(ValueError):stores.send(d,preview['token'],True,True)
    with pytest.raises(ValueError):stores.prepare(d,323)
    preview=stores.prepare(d,322);d._album_store_stamp=None
    with pytest.raises(ValueError):stores.send(d,preview['token'],True,True)
    assert d.store_preset.call_count==1
    d.read_nam_slot.assert_not_called()


def test_store_detects_hidden_changed_scene_after_return_to_scene8(monkeypatch):
    d=device(monkeypatch);p=plan(d)
    monkeypatch.setattr(store_review,'get_store_slots',lambda:{322})
    d.slot_name=Mock(return_value=SimpleNamespace(number=322,name='<EMPTY>'))
    reviews=tone_review.Reviews();prepared=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    assert reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)['ok']
    d._test_scenes[1][58]=replace(d._test_scenes[1][58],bypassed=True)
    stores=store_review.Stores();preview=stores.prepare(d,322)
    assert 'alle acht scenes' in preview['verification_note']
    with pytest.raises(ValueError,match='Saved scene mapping'):
        stores.send(d,preview['token'],True,True)
    d.store_preset.assert_not_called()
    assert d._album_store_stamp is None


@pytest.mark.parametrize('family,key',[('delay','feedback'),('delay','mix'),('chorus','depth'),('chorus','mix')])
def test_schema_never_advertises_unmeasured_zero_fx_values(monkeypatch,family,key):
    from devices.axefx3 import fw33_profile
    monkeypatch.setattr(fw33_profile,'FX_ZERO_RELEASED',False)
    d=device(monkeypatch);raw=design();raw[family][key]=0.
    with pytest.raises(ValueError):planning.compile_design(d.reg,raw,list(serial_build.ROUTE),8)


def test_stale_addressed_bulk_is_not_accepted_even_with_matching_display(monkeypatch):
    d=device(monkeypatch);p=plan(d)
    d.set_param_display.side_effect=lambda spec,value:SetResult(True,'display matches but bulk stale',None,value)
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert not result['ok'] and d.set_param_display.call_count==1
    assert result['skipped']==len(p['actions'])-1
    d._write.assert_not_called();d.store_preset.assert_not_called()


def test_final_survey_checks_saved_states_without_rewriting_them(monkeypatch):
    d=device(monkeypatch);p=plan(d);rename=d.rename_scene.side_effect
    def changed(number,name):
        result=rename(number,name)
        if number==8:d._test_scenes[1][58]=replace(d._test_scenes[1][58],bypassed=True)
        return result
    d.rename_scene.side_effect=changed
    result=executor.execute(d,p['actions'],p['required_route'],expected_preset=322,external_audio_muted=True)
    assert not result['ok'] and result['skipped']==7 and not result.get('album_verification')
    assert d.current_scene()==1 and d.get_bypass(58) is True
    d.store_preset.assert_not_called()


def test_final_marker_cannot_certify_new_unverified_state(monkeypatch):
    d=device(monkeypatch);p=plan(d);reviews=tone_review.Reviews()
    prepared=reviews.prepare(d,p,tone_review.snapshot(d,include_nam=False))
    snapshot=tone_review.snapshot
    def changed(dev,*args,**kw):
        if (dev.current_scene()==8 and dev.current_preset()[1]=='AI-Metallica albums'
                and getattr(dev,'_album_session',None) is None):
            dev._test_bulk[70][300]+=1
        return snapshot(dev,*args,**kw)
    monkeypatch.setattr(tone_review,'snapshot',changed)
    with pytest.raises(ValueError,match='Final state changed'):
        reviews.send(d,prepared['token'],target_confirmed=True,external_audio_muted=True)
    assert d._album_store_stamp is None and d._album_store_proof is None
    d.store_preset.assert_not_called()

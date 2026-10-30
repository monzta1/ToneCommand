"""Expanded CAB grammar, mix budgets and normal review execution."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from fm9.device import SetResult
from devices.axefx3 import album_planning as planning, album_build, executor, tone_review, serial_build
from test_axefx3_album_build import device as album_device, design as album_design


def design():
    result=album_design()
    for c,album in enumerate(result['albums']):
        album['cab']=dict(irs=[dict(bank=(2 if c%2==0 else 3) if i==0 else 0,
            slot=1024 if i==0 else 1,mode='normal' if i<2 else 'mute',
            level_db=-6.1 if i<2 else 0.,pan=-70. if i==0 else 70. if i==1 else 0.) for i in range(4)])
    return result


def device(monkeypatch):
    d=album_device(monkeypatch)
    from devices.axefx3 import profile
    profile.apply(d.reg,'mk2')
    d.reg.import_cab_names('U1.1024 Last User1\nU2.1024 Last User2','user')
    original=d.set_param_display.side_effect
    def param(spec,value):
        if spec.family!='CABINET':return original(spec,value)
        c=d.get_channel(spec.effect_id)
        from fm9.protocol import display_to_normalized
        d._test_bulk[62][106*c+spec.param_id]=(int(value) if spec.kind=='enum' else
            round(display_to_normalized(value,spec.dmin,spec.dmax,spec.scale)*65534))
        return SetResult(True,'Synthetic independent readback',None,value)
    d.set_param_display=Mock(side_effect=param)
    return d


def plan(d):return planning.compile_design(d.reg,design(),list(serial_build.ROUTE),8)


def test_expanded_cab_normal_review_send_preserves_other_words(monkeypatch):
    d=device(monkeypatch);p=plan(d)
    before=list(d._test_bulk[62])
    assert len(p['actions'])<512
    assert len([a for a in p['actions'] if a['kind']=='set_cab'])==16
    album_build.validate_actions(d.reg,p['actions'],True)
    reviews=tone_review.Reviews();initial=tone_review.snapshot(d,include_nam=False)
    review=reviews.prepare(d,p,initial)
    d.set_param_display.assert_not_called();d._write.assert_not_called()
    result=reviews.send(d,review['token'],target_confirmed=True,external_audio_muted=True)
    assert result['ok'],result
    allowed=set(range(16))|set(range(24,28))
    assert all(a==b or i%106 in allowed for i,(a,b) in enumerate(zip(before,d._test_bulk[62])))
    for c in range(4):
        values=d._test_bulk[62][106*c:106*(c+1)]
        assert values[0]==(2 if c%2==0 else 3) and values[4]==1023
        assert values[24:28]==[0,0,1,1]
        assert values[12]<32767<values[13]
    d.store_preset.assert_not_called();d.read_nam_slot.assert_not_called()


@pytest.mark.parametrize('fault',['gain','empty','unknown','fullres_wrong_ir','fullres_range','unsafe_bank',
    'duplicate_mode','stage','order','other_param','extra','channel'])
def test_bad_mix_or_action_shape_stops_before_writes(monkeypatch,fault):
    d=device(monkeypatch);raw=design()
    if fault=='gain':raw['albums'][0]['cab']['irs'][0]['level_db']=0.
    if fault=='empty':d.reg.import_cab_names('U1.1024 <EMPTY>','user')
    if fault=='unknown':raw['albums'][0]['cab']['irs'][0]['slot']=600
    if fault=='fullres_wrong_ir':raw['albums'][0]['cab']['irs'][0].update(bank=6,slot=1)
    if fault=='fullres_range':raw['albums'][0]['cab']['irs'][3].update(bank=6,slot=65)
    if fault=='unsafe_bank':raw['albums'][0]['cab']['irs'][0]['bank']=4
    with pytest.raises((ValueError,KeyError,IndexError)):
        p=planning.compile_design(d.reg,raw,list(serial_build.ROUTE),8)
        actions=p['actions']
        cab=[a for a in actions if a.get('block')=='CABINET']
        if fault=='duplicate_mode':cab[1]['value']=2
        if fault=='stage':cab[1]['value']=0
        if fault=='order':
            i=next(i for i,a in enumerate(actions) if a.get('param')=='CABINET_LEVEL1')
            actions[i],actions[i+1]=actions[i+1],actions[i]
        if fault=='other_param':next(a for a in cab if a.get('param')=='CABINET_LEVEL1')['param']='OUTPUT_LEVEL'
        if fault=='extra':actions.append(dict(kind='set_scene',value=1))
        if fault=='channel':cab[0]['value']=3
        executor.prepare(d,actions,p['required_route'],322)
    d._write.assert_not_called();d.set_param_display.assert_not_called()


def test_solo_does_not_hide_an_unsafe_latent_mix(monkeypatch):
    d=device(monkeypatch);raw=design()
    raw['albums'][0]['cab']['irs'][0].update(mode='solo',level_db=0.)
    with pytest.raises(ValueError,match='combined linear gain'):
        planning.compile_design(d.reg,raw,list(serial_build.ROUTE),8)


def test_old_aliases_still_compile_the_old_reviewed_grammar(monkeypatch):
    d=device(monkeypatch)
    p=planning.compile_design(d.reg,album_design(),list(serial_build.ROUTE),8)
    assert not any(a.get('block')=='CABINET' and a['kind']=='set_param' for a in p['actions'])
    album_build.validate_actions(d.reg,p['actions'],True)


def test_muted_ir_pan_or_total_gain_cannot_manufacture_base_tone_difference(monkeypatch):
    from devices.axefx3 import scene_intent
    d=device(monkeypatch);p=plan(d)
    first=scene_intent.scenes(p)[0]
    changed=deepcopy(first)
    changed['base']['cab']['irs'][2].update(bank=1,slot=1024,pan=100.)
    for ir in changed['base']['cab']['irs']:
        if ir['mode']!='mute':ir['level_db']-=2.;ir['pan']=-ir['pan']
    assert scene_intent._base(first)==scene_intent._base(changed)
    changed['base']['cab']['irs'][0]['slot']=28 if changed['base']['cab']['irs'][0]['slot']!=28 else 29
    assert scene_intent._base(first)!=scene_intent._base(changed)


def test_mixer_wire_permission_is_bound_to_exact_reviewed_value(monkeypatch):
    from devices.axefx3 import protocol
    from devices.axefx3.adapter import AxeFxIII
    d=device(monkeypatch);p=plan(d)
    resolved=[executor.resolve(d.reg,a) for a in p['actions']]
    item=next(i for i in resolved if i.action.get('param')=='CABINET_LEVEL1')
    frame=protocol.set_parameter(d.reg,item.spec,item.value)
    d._approved_frame=tuple(frame)
    with pytest.raises(PermissionError):AxeFxIII._send(d,frame)
    with album_build.execution(d,resolved,True) as session:
        session.item=item
        AxeFxIII._send(d,frame)
        wrong=protocol.set_parameter(d.reg,item.spec,-4.)
        d._approved_frame=tuple(wrong)
        with pytest.raises(PermissionError):AxeFxIII._send(d,wrong)
    assert d.outp.send.call_count==1

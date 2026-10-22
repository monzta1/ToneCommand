"""Normal reviewed execution of the strictly measured eight-scene template.

No generic model, Cab mixer, graph, controller, memory or raw-write permission.
Each action consumes a fresh full-state check; any failure stops the session.
"""
from contextlib import contextmanager
from dataclasses import replace
import time
from fm9.device import SetResult
from fm9 import protocol as shared
from . import album_planning as planning, fw33_profile, serial_build, protocol, grid, tone_review,reviewed_effects,wah_voicing
from .controller_review import digest


def supported(reg): return serial_build.supported(reg)


def seed():
    amp=dict(gain=5.,bass=4.,mid=5.,treble=5.,master=5.,depth=2.,presence=4.,level=-18.)
    role=dict(name='Scene',delay=False,chorus=False)
    return planning.Design.model_validate(dict(name='Album',summary='Measured template',
        albums=[dict(amp_model=planning.MODELS[14],cab='Greenback',amp=amp,lead=role,solo=role)]*4,
        delay=dict(active=False,time_ms=320.,feedback=20.,mix=15.),
        chorus=dict(active=False,rate_hz=.7,depth=25.,mix=10.)))


def validate_actions(reg,actions,existing):
    """Exact deterministic grammar, not an untrusted mode flag from the AI."""
    base=seed()
    names=[a.get('value') for a in actions if a.get('kind')=='rename_scene']
    count=len(names)
    if count not in fw33_profile.ALBUM_SCENE_COUNTS or names!=list(range(1,count+1)) or any(type(n) is not int for n in names):
        raise ValueError('Exactly the released scene count and ordered scene names required')
    base.scene_count=count
    expanded=any(a.get('kind')=='set_param' and a.get('block')=='CABINET' for a in actions)
    if expanded:
        # Reconstruct only the explicit CAB subgrammar, then regenerate it.
        # No AI mode flag, arbitrary fields, writes or order are trusted.
        first_scene=next((i for i,a in enumerate(actions) if a.get('kind')=='set_scene'),len(actions))
        starts=[i for i,a in enumerate(actions[:first_scene]) if a.get('kind')=='set_channel' and a.get('block')=='CABINET']
        if len(starts)!=5:raise ValueError('Four explicit Cab voicings and final channel-A reset required')
        for c,start in enumerate(starts[:4]):
            irs=[]
            for slot in range(4):
                group=actions[start+5+3*slot:start+8+3*slot]
                if len(group)!=3:raise ValueError('Incomplete Cab voicing')
                selection,level,pan=group
                mode=actions[start+17+slot].get('value')
                if type(mode) is not int or mode not in range(3):raise ValueError('Invalid Cab mode')
                irs.append(dict(bank=selection.get('bank'),slot=selection.get('value',-1)+1,
                    mode=('normal','mute','solo')[mode],level_db=level.get('value'),pan=pan.get('value')))
            base.albums[c].cab=planning.CabVoice.model_validate(dict(irs=irs))
    with_drive=any(a.get('kind')=='set_param' and a.get('block')=='FUZZ' for a in actions)
    if with_drive and not fw33_profile.DRIVE_RELEASED:
        raise ValueError('Drive prototype not released; independent normal SEND/editor acceptance required')
    if with_drive:
        first_scene=next((i for i,a in enumerate(actions) if a.get('kind')=='set_scene'),len(actions))
        starts=[i for i,a in enumerate(actions[:first_scene]) if a.get('kind')=='set_channel' and a.get('block')=='FUZZ']
        if len(starts)!=5:raise ValueError('Four explicit Drive voicings and final A reset required')
        for c,start in enumerate(starts[:4]):
            group=actions[start+1:start+7]
            if len(group)!=6:raise ValueError('Incomplete Drive voicing')
            base.albums[c].drive=planning.Drive.model_validate(dict(model=group[0].get('type_name'),
                gain=group[2].get('value'),tone=group[3].get('value'),mix=group[4].get('value'),level=group[5].get('value')))
        scene=0
        for a in actions[first_scene:]:
            if a.get('kind')=='set_scene':scene=a.get('value')
            if a.get('kind')=='set_bypass' and a.get('block')=='FUZZ':
                if type(scene) is not int or scene not in range(1,9) or type(a.get('bypassed')) is not bool:
                    raise ValueError('Invalid Drive scene state')
                setattr(base.albums[(scene-1)//2].lead if scene%2 else base.albums[(scene-1)//2].solo,'drive',not a['bypassed'])
        mapping=planning.layout(base.model_dump())
        scene=0
        for a in actions[first_scene:]:
            if a.get('kind')=='set_scene':scene=a.get('value')
            if a.get('kind')=='set_channel' and a.get('block') in ('DISTORT','CABINET'):
                if type(scene) is not int or scene not in range(1,9):raise ValueError('Invalid Drive scene context')
                mapping[scene-1]['amp_channel' if a['block']=='DISTORT' else 'cab_channel']=a.get('value')
        base.scene_layout=[planning.SceneLayout.model_validate(item) for item in mapping]
    if any(a.get('block') in ('COMP','GEQ') and a['kind']=='set_param' for a in actions):
        first_scene=next((i for i,a in enumerate(actions) if a['kind']=='set_scene'),len(actions))
        reviewed_effects.reconstruct(base,actions,first_scene,planning)
    wah_values={a.get('param'):a.get('value') for a in actions[:next((i for i,a in enumerate(actions) if a['kind']=='set_scene'),len(actions))]
        if a.get('block')=='WAH' and a['kind']=='set_param'}
    controller=None
    bindings=[a for a in actions if a['kind']=='bind_controller']
    if wah_values:
        if not wah_voicing.RELEASED:raise ValueError('Wah planner not released')
        base.wah=wah_voicing.Voice.model_validate({key:wah_values.get(name) for key,name in wah_voicing.FIELDS.items()})
        mapping=planning.layout(base.model_dump());scene=0
        for a in actions:
            if a['kind']=='set_scene':scene=a['value']
            if scene and a['kind']=='set_bypass' and a.get('block')=='WAH':
                if type(a.get('bypassed')) is not bool or type(scene) is not int or scene not in range(1,count+1):
                    raise ValueError('Invalid Wah scene mapping')
                mapping[scene-1]['wah']=not a['bypassed']
        base.scene_layout=[planning.SceneLayout.model_validate(item) for item in mapping]
    if bindings:
        if len(bindings)!=1 or base.wah is None:raise ValueError('One explicitly voiced Wah binding required')
        controller=wah_voicing.controller(bindings[0].get('source'),bindings[0].get('auto_engage'))
        if controller is None:raise ValueError('Explicit controller source required')
    expected=planning.actions_for(reg,base,existing,controller)
    if len(actions)!=len(expected): raise ValueError('Incomplete or extra album actions')
    role_flags={j for i,a in enumerate(expected) if a['kind']=='rename_scene' for j in (i-2,i-1)}
    # Same measured A-D selectors; only musical assignment is generalized.
    # Initial voicing/staging and the final verification survey stay fixed.
    scene_channel_indices=set()
    first_scene=next(i for i,a in enumerate(expected) if a['kind']=='set_scene')
    scene=0
    for i,a in enumerate(expected):
        if a['kind']=='set_scene':scene=a['value']
        if (first_scene<i<len(expected)-count and a['kind']=='set_channel'
                and a['block'] in ('DISTORT','CABINET')):
            if type(actions[i].get('value')) is not int or actions[i]['value'] not in range(4):
                raise ValueError('Scene channel must be a measured A-D channel')
            if scene==1 and actions[i]['value']!=0:
                raise ValueError('Scene1 retains Amp/Cab A as the review starting point')
            scene_channel_indices.add(i)
    for index,(actual,template) in enumerate(zip(actions,expected)):
        if set(actual)!=set(template): raise ValueError('Unexpected album action fields')
        allowed=set()
        kind=template['kind']
        if kind=='set_param':
            quiet_stage=(template['param']=='DISTORT_LEVEL' and
                (expected[index+1]['kind']=='set_type' or (expected[index+1]['kind']=='set_channel'
                    and expected[index+1].get('block') in ('FUZZ','COMP','GEQ'))
                    or expected[index+1].get('param')=='WAH_LEVEL'))
            quiet_stage=quiet_stage or (template['param']=='WAH_LEVEL' and expected[index+1]['kind']=='set_type')
            if template['param']!='OUTPUT_LEVEL' and not (
                    quiet_stage):
                allowed={'value'}
            if template['param']=='DISTORT_LEVEL' and actual['value']>-12:
                raise ValueError('Album Amp level must remain <= -12dB')
            if template['param'].startswith('DISTORT_') and template['param']!='DISTORT_LEVEL' and (
                    actual['value']<0 or (actual['value']==0 and not fw33_profile.AMP_ZERO_RELEASED)):
                raise ValueError('Exact-zero Amp knobs are not released or the value is negative')
            if (template['param'] in fw33_profile.FX_ZERO_NAMES and actual['value']==0
                    and not fw33_profile.FX_ZERO_RELEASED):
                raise ValueError('Exact-zero effect controls are not released')
        if kind=='set_type':
            names=(planning.MODELS.values() if template['block']=='DISTORT' else
                (reviewed_effects.model(template['block'])[4],) if template['block'] in ('COMP','GEQ') else
                ('Cry Babe',) if template['block']=='WAH' else ('T808 Mod',))
            if actual['type_name'] not in names: raise ValueError('Unmeasured album model')
            allowed={'type_name'}
        if kind=='set_cab':
            if not expanded:
                if actual['value'] not in (515,799): raise ValueError('Unmeasured album IR1')
                allowed={'value'}
        if template.get('block') in ('CABINET','FUZZ','COMP','GEQ') and kind=='set_param':allowed=set()
        if kind in ('rename_preset','rename_scene'): allowed={'type_name'}
        if index in role_flags: allowed={'bypassed'}
        if index in scene_channel_indices: allowed={'value'}
        if any(actual[key]!=value for key,value in template.items() if key not in allowed):
            raise ValueError('Album action order, channel, reserve or safety staging differs')


def cab_layout(words,*,expanded=False):
    if not isinstance(words,list) or len(words)!=424: raise ValueError('Complete Legacy Cab layout required')
    for c in range(4):
        v=words[c*106:(c+1)*106]
        if expanded:
            if v[31]!=0 or any(x not in (0,1,2) for x in v[24:28]) or v[28]>52427:
                raise ValueError('Readable Legacy mixer with no positive block gain required')
        elif v[31]!=0 or v[24:28]!=[0,1,1,1] or v[8:12]!=[65534]*4 or v[12:16]!=[32767]*4:
            raise ValueError('Measured IR1-only Legacy mixer required; no automatic unmute or pan')


def prepare(dev,resolved,expected,actual):
    if not supported(dev.reg) or tuple(expected)!=serial_build.ROUTE or (actual and tuple(actual)!=serial_build.ROUTE):
        raise ValueError('Album build requires the exact measured MK2/FW33 serial route')
    validate_actions(dev.reg,[i.action for i in resolved],bool(actual))
    now=tone_review.snapshot(dev,include_nam=False)
    if now['scene']!=1 or (grid.snapshot(now['grid']) and grid.snapshot(now['grid'])!=serial_build.expected_grid()):
        raise ValueError('Album build begins on scene1 of empty or exact measured row1')
    if not wah_voicing.modifiers_allowed(now['modifiers']): raise ValueError('Album build preserves only independently assessed Wah1 modifiers')
    if any(i.action['kind']=='bind_controller' for i in resolved) and actual:
        from . import pedal_control
        for item in resolved:
            if item.action['kind']=='bind_controller':pedal_control.preflight(dev,item.effect_id,*item.value)
    if actual:
        if any(b.channel!=0 or b.channels_supported!=4 for b in now['blocks'] if b.effect_id in expected):
            raise ValueError('Existing album foundation must begin on channel A')
        if len(now['bulk'].get(58,[]))!=568: raise ValueError('Complete four-channel Amp layout required')
        cab_layout(now['bulk'].get(62),expanded=any(i.family=='CABINET' and i.spec for i in resolved))
        for item in resolved:
            if item.spec is not None:
                from . import fw33
                error=fw33.zero_control_error(dev,item.spec,item.value)
                if error:raise ValueError(error)
            if item.spec is not None and item.spec.tempo_param_id is not None:
                from . import tempo_control
                tempo_control.preflight(dev,item.spec)
    return resolved,expected,actual


def frame_allowed(dev,frame):
    session=getattr(dev,'_album_session',None)
    active=(isinstance(session,Session) and session.dev is dev and not session.failed
        and supported(dev.reg) and session.target==getattr(dev,'_edit_target',None)
        and session.frame==tuple(frame) and session.item is not None)
    if not active: return False
    item=session.item
    if item.action['kind']=='set_bypass' and item.effect_id in (118,46,50,94):
        return frame==protocol.param_frame(item.effect_id,{118:7,46:9,50:18,94:12}[item.effect_id],int(item.value),opcode=9)
    if item.action['kind']=='set_type':
        eid=item.effect_id
        if eid in (46,50):
            _,_,selector,ordinal,name=reviewed_effects.model(item.family)
            return item.value==name and frame==protocol.param_frame(eid,selector,ordinal,opcode=9)
        ordinal=next(k for k,v in planning.MODELS.items() if v==item.value) if eid==58 else 2 if eid==94 else 8
        return eid in (58,118,94) and frame==protocol.param_frame(eid,0,ordinal,opcode=9)
    if item.action['kind']=='set_cab':
        bank,ordinal,side=item.value
        slot=int(side[2:])-1 if side.startswith('ir') else 0
        return frame in [protocol.param_frame(62,p,v,opcode=9) for p,v in ((slot,bank),(4+slot,ordinal))]
    if item.action['kind']=='set_channel' and item.effect_id in (58,62,118,46,50):
        return frame==protocol.envelope(1,[22,0,item.effect_id,0,0,0,item.value,0,0,0,0,0,0,0,0])
    if item.action['kind']=='set_scene': return frame==protocol.envelope(0x0c,[item.value-1])
    return False


def amp_domain(dev,spec,channel):
    session=getattr(dev,'_album_session',None)
    return (isinstance(session,Session) and not session.failed and session.item is not None
        and session.item.action['kind']=='set_param' and session.item.spec==spec
        and (spec.effect_id,spec.family) in ((58,'DISTORT'),(62,'CABINET'),(118,'FUZZ'),(46,'COMP'),(50,'GEQ')) and channel in range(4)
        and supported(dev.reg) and session.target==getattr(dev,'_edit_target',None))


class Session:
    def __init__(self,dev,resolved):
        dev._check_edit_target()
        if not supported(dev.reg) or getattr(dev,'_album_session',None) is not None:
            raise PermissionError('One measured album session required')
        self.dev,self.target,self.resolved=dev,dev._edit_target,resolved
        self.index,self.failed,self.frame,self.item=0,False,None,None
        self.scene_states={}
        self.scene_count=sum(i.action['kind']=='rename_scene' for i in resolved)
        self.expected=tone_review.snapshot(dev,include_nam=False)
        self.expanded=any(i.family=='CABINET' and i.spec for i in resolved)
        self.wah=any(i.family=='WAH' and i.spec for i in resolved)
        cab_layout(self.expected['bulk'].get(62),expanded=self.expanded)
        dev._album_session=self

    def write(self,frame):
        if self.failed or self.item is None: raise PermissionError('Album operation not active')
        self.frame=tuple(frame)
        try: self.dev._write(frame)
        finally: self.frame=None

    def settle(self,match):
        for _ in range(5):
            time.sleep(.2)
            now=tone_review.snapshot(self.dev,include_nam=False)
            if match(now): return now
        raise ValueError('Independent full-state mismatch; no write retry or rollback')

    def channel(self,eid,value):
        if eid not in (58,62,118,46,50): return self.dev.set_channel(eid,value)
        before=self.expected
        wanted={**before,'blocks':[replace(b,channel=value) if b.effect_id==eid else b for b in before['blocks']]}
        if before==wanted: return value
        self.write(protocol.envelope(1,[22,0,eid,0,0,0,value,0,0,0,0,0,0,0,0]))
        self.settle(lambda now:now==wanted)
        return value

    def drive_bypass(self,value):
        if not value:
            level=self.dev.get_param_display(self.dev.reg.find_param('FUZZ','FUZZ_LEVEL'))
            c=next(b.channel for b in self.expected['blocks'] if b.effect_id==118)
            if (self.expected['bulk'][118][44*c]!=8 or type(level) not in (int,float)
                    or not 0<=level<=2.5):
                raise PermissionError('T808 Mod and explicit bounded final level required before engage')
        # FW33 Axe-Edit uses the captured typed bypass setter, not an
        # assumed family-independent0x0a write. Status/full-state readback
        # below and in run() remain independent of the write response.
        self.write(protocol.param_frame(118,7,int(value),opcode=9))
        for _ in range(5):
            time.sleep(.15)
            if self.dev.get_bypass(118) is value:return value
        raise ValueError('Drive bypass status mismatch; no retry or rollback')

    def wah_bypass(self,value):
        if self.dev.get_channel(94)!=0:raise PermissionError('Wah requires independently measured channel A')
        if not value:
            level=self.dev.get_param_display(self.dev.reg.find_param('WAH','WAH_LEVEL'))
            if self.expected['bulk'][94][0]!=2 or type(level) not in (int,float) or level>0:
                raise PermissionError('Cry Babe and nonpositive final Wah level required')
        self.write(protocol.param_frame(94,12,int(value),opcode=9))
        for _ in range(5):
            time.sleep(.15)
            if self.dev.get_bypass(94) is value:return value
        raise ValueError('Wah bypass status mismatch; no retry')

    def model(self,name):
        before=self.expected
        eid=self.item.effect_id;stride=fw33_profile.STRIDES[self.item.family]
        channel=next(b.channel for b in before['blocks'] if b.effect_id==eid)
        base=stride*channel
        selector=0
        if eid in (46,50):_,_,selector,ordinal,_=reviewed_effects.model(self.item.family)
        else:ordinal=next(k for k,v in planning.MODELS.items() if v==name) if eid==58 else 2 if eid==94 else 8
        if before['bulk'][eid][base+selector]==ordinal: return SetResult(True,'Model retained without reset',name,name)
        level=self.dev.get_param_display(self.dev.reg.find_param('DISTORT','DISTORT_LEVEL'))
        if (self.dev.get_bypass(58) is not True or self.dev.get_bypass(eid) is not True
                or type(level) not in (int,float) or level>-18):
            raise PermissionError('Bypassed and verified quiet Amp required before model write')
        self.write(protocol.param_frame(eid,selector,ordinal,opcode=9))
        def match(now):
            if now['bulk'][eid][base+selector]!=ordinal: return False
            words=list(before['bulk'][eid]);words[base:base+stride]=now['bulk'][eid][base:base+stride]
            return now=={**before,'bulk':{**before['bulk'],eid:words}}
        self.settle(match)
        return SetResult(True,'Measured model and independent full-channel preservation verified',before['bulk'][eid][base],name)

    def cab(self,bank,ordinal,side='left'):
        before=self.expected
        channel=next(b.channel for b in before['blocks'] if b.effect_id==62)
        base=106*channel
        cab_layout(before['bulk'][62],expanded=self.expanded)
        slot=int(side[2:])-1 if side.startswith('ir') else 0
        current=before
        for pid,value in ((slot,bank),(4+slot,ordinal)):
            if current['bulk'][62][base+pid]==value: continue
            words=list(current['bulk'][62]);words[base+pid]=value
            wanted={**current,'bulk':{**current['bulk'],62:words}}
            self.write(protocol.param_frame(62,pid,value,opcode=9))
            current=self.settle(lambda now:now==wanted)
        return SetResult(True,f'IR{slot+1} selected, other IRs and full mixer preserved',None,(bank,ordinal,f'IR{slot+1}'))

    def run(self,item,operation):
        if self.failed or self.index>=len(self.resolved) or item is not self.resolved[self.index]:
            raise PermissionError('Album session consumed or action out of order')
        dev=self.dev
        if tone_review.snapshot(dev,include_nam=False)!=self.expected:
            self.failed=True;raise PermissionError('Fresh state changed before album action')
        self.item=item
        try:
            result=operation()
            if not result.ok: self.failed=True; return result
            before=self.expected
            kind,eid=item.action['kind'],item.effect_id
            def match(now):
                wanted=dict(before)
                if kind=='set_param':
                    channel=next(b.channel for b in before['blocks'] if b.effect_id==eid)
                    stride=fw33_profile.STRIDES[item.family]
                    pos=channel*stride+item.spec.param_id
                    # FW33 display/bulk anchors agree with this normalized
                    # law (including literal 1ms, not wire_min=0). Allow one
                    # quantization word, never copy an arbitrary stale value.
                    target=round(shared.display_to_normalized(item.value,item.spec.dmin,
                        item.spec.dmax,item.spec.scale)*65534)
                    if item.spec.kind=='enum':target=int(item.value)
                    if abs(now['bulk'][eid][pos]-target)>(0 if item.spec.kind=='enum' else 1): return False
                    words=list(before['bulk'][eid]);words[pos]=now['bulk'][eid][pos]
                    wanted['bulk']={**before['bulk'],eid:words}
                elif kind=='set_type':
                    stride=fw33_profile.STRIDES[item.family]
                    c=next(b.channel for b in before['blocks'] if b.effect_id==eid);base=stride*c
                    words=list(before['bulk'][eid]);words[base:base+stride]=now['bulk'][eid][base:base+stride]
                    wanted['bulk']={**before['bulk'],eid:words}
                elif kind=='set_cab':
                    c=next(b.channel for b in before['blocks'] if b.effect_id==62);base=106*c
                    side=item.value[2];slot=int(side[2:])-1 if side.startswith('ir') else 0
                    words=list(before['bulk'][62]);words[base+slot],words[base+4+slot]=item.value[:2]
                    wanted['bulk']={**before['bulk'],62:words}
                elif kind in ('set_channel','set_bypass'):
                    field='channel' if kind=='set_channel' else 'bypassed'
                    wanted['blocks']=[replace(b,**{field:item.value}) if b.effect_id==eid else b for b in before['blocks']]
                elif kind=='set_scene':
                    wanted['scene']=item.value
                    old={b.effect_id:b for b in before['blocks']}
                    if any(b.effect_id not in old or replace(b,channel=old[b.effect_id].channel,bypassed=old[b.effect_id].bypassed)!=old[b.effect_id] for b in now['blocks']): return False
                    if len(old)!=len(now['blocks']): return False
                    wanted['blocks']=now['blocks']
                    if self.index>=len(self.resolved)-self.scene_count:
                        if len(self.scene_states)!=self.scene_count: return False
                        wanted['blocks']=self.scene_states[item.value]
                        if self.wah_auto(now):
                            wanted['blocks']=[replace(b,bypassed=next(x.bypassed for x in now['blocks'] if x.effect_id==94)) if b.effect_id==94 else b for b in wanted['blocks']]
                elif kind=='bind_controller':
                    from . import pedal_control
                    wanted_words=[m['words'].copy() for m in before['modifiers']]
                    found=[i for i,w in enumerate(wanted_words) if w[8:10]==[94,5]]
                    if found:slot=found[0]
                    else:
                        slot=next(i for i,w in enumerate(wanted_words) if w[0]==w[8]==0)
                        wanted_words[slot]=pedal_control.default_words(94)
                    wanted_words[slot][0]=item.value[0]
                    if item.value[1] is not None:wanted_words[slot][10]=pedal_control.MODES[item.value[1]]
                    if [m['words'] for m in now['modifiers']]!=wanted_words:return False
                    wanted['modifiers']=now['modifiers']
                    wanted['blocks']=[replace(b,bypassed=next(x.bypassed for x in now['blocks'] if x.effect_id==94)) if b.effect_id==94 else b for b in before['blocks']]
                elif kind=='rename_preset': wanted['preset']=(before['preset'][0],item.value)
                elif kind=='rename_scene':
                    wanted['scene_names']=list(before['scene_names'])
                    wanted['scene_names'][item.value-1]=(item.value,item.action['type_name'])
                return now==wanted
            now=self.settle(match)
            if dev.get_param_display(dev.reg.find_param('OUTPUT','OUTPUT_LEVEL'))!=-18:
                raise PermissionError('Output attenuation changed; retain external mute')
            self.expected=now;self.index+=1
            if kind=='rename_scene': self.scene_states[item.value]=list(now['blocks'])
            if kind=='bind_controller' or (kind=='set_scene' and self.index>len(self.resolved)-self.scene_count):
                self.scene_states[now['scene']]=list(now['blocks'])
            return result
        except BaseException:
            self.failed=True
            raise
        finally: self.item=None;self.frame=None

    def wah_auto(self,state):
        return any(m['active'] and m['words'][8:10]==[94,5] and m['words'][0] in (12,13)
            and m['words'][10]==6 for m in state['modifiers'])

    def proof(self):
        if self.failed or self.index!=len(self.resolved) or len(self.scene_states)!=self.scene_count:
            raise PermissionError('Incomplete album cannot certify a Store proof')
        return dict(final_fingerprint=digest(self.expected),scene_fingerprints={str(n):
            digest({**self.expected,'scene':n,'blocks':self.scene_states[n]}) for n in range(1,self.scene_count+1)})


@contextmanager
def execution(dev,resolved,enabled):
    if not enabled: yield None; return
    session=Session(dev,resolved)
    try: yield session
    finally:
        session.failed=True;session.frame=None;session.item=None
        dev._album_session=None

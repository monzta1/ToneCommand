"""Bounded Compressor/GEQ grammar for the measured fourteen-block route."""
from . import effect_voicing as voices,protocol

FAMILIES=(('compressor','COMP'),('geq','GEQ'))


def reconstruct(base,actions,first_scene,planning):
    """Rebuild typed voices, then let the ordinary exact grammar compare them."""
    for key,family in FAMILIES:
        if not any(a.get('block')==family and a['kind']=='set_param' for a in actions):continue
        released=voices.COMPRESSOR_RELEASED if family=='COMP' else voices.GEQ_RELEASED
        if not released:raise ValueError(f'{family} normal builder not released')
        starts=[i for i,a in enumerate(actions[:first_scene]) if a['kind']=='set_channel' and a.get('block')==family]
        if len(starts)!=5:raise ValueError('Four auxiliary voicings and final channel-A reset required')
        for c,start in enumerate(starts[:4]):
            length=len(voices.parameters(family,voices.default(family)))
            group=actions[start+1:start+2+length]
            if len(group)!=length+1:raise ValueError('Incomplete auxiliary voicing')
            params={a.get('param'):a.get('value') for a in group[1:]}
            if family=='COMP':
                voice=voices.Compressor.model_validate(dict(model=group[0].get('type_name'),
                    threshold=params.get('COMP_THRESH'),ratio=params.get('COMP_RATIO'),attack_ms=params.get('COMP_ATTACK'),
                    release_ms=params.get('COMP_RELEASE'),mix=params.get('COMP_MIX'),level=params.get('COMP_LEVEL')))
            else:
                voice=voices.GraphicEQ.model_validate(dict(model=group[0].get('type_name'),
                    gains=[params.get(f'GEQ_GAIN{i}') for i in range(1,11)],q=params.get('GEQ_Q'),level=params.get('GEQ_LEVEL')))
            setattr(base.albums[c],key,voice)
    mapping=planning.layout(base.model_dump());scene=0
    for a in actions[first_scene:]:
        if a['kind']=='set_scene':scene=a.get('value')
        if a['kind']=='set_channel' and a.get('block') in ('DISTORT','CABINET'):
            if type(scene) is not int or scene not in range(1,len(mapping)+1):raise ValueError('Invalid scene context')
            mapping[scene-1]['amp_channel' if a['block']=='DISTORT' else 'cab_channel']=a.get('value')
        if a['kind']=='set_bypass' and a.get('block') in ('COMP','GEQ'):
            if type(scene) is not int or scene not in range(1,len(mapping)+1) or type(a.get('bypassed')) is not bool:
                raise ValueError('Invalid auxiliary scene state')
            mapping[scene-1]['compressor' if a['block']=='COMP' else 'geq']=not a['bypassed']
    base.scene_layout=[planning.SceneLayout.model_validate(item) for item in mapping]


def model(family):
    return voices.MODELS[family]


def engaged_domain(session,eid):
    family='COMP' if eid==46 else 'GEQ'
    _,stride,selector,ordinal,_=model(family)
    c=next(b.channel for b in session.expected['blocks'] if b.effect_id==eid)
    words=session.expected['bulk'][eid][stride*c:stride*(c+1)]
    if words[selector]!=ordinal:return False
    level=session.dev.get_param_display(session.dev.reg.find_param(family,family+'_LEVEL'))
    if type(level) not in (int,float) or level>0:return False
    if family=='COMP':return words[6]==words[16]==0
    return all(w<=32767 for w in words[:10])


def typed_bypass(session,eid,value):
    if not value and not engaged_domain(session,eid):
        raise PermissionError('Explicit measured auxiliary model, manual modes and nonpositive levels required before engage')
    session.write(protocol.param_frame(eid,9 if eid==46 else 18,int(value),opcode=9))
    # The enclosing run independently settles status and the entire state.
    return value

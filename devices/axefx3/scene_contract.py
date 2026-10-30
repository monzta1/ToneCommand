"""Request-first scene brief and compiled parameter comparison, never listening.

The brief is obtained before the concrete design. The design cannot redefine
its own success criteria; no model, firmware or execution capability is added.
"""
from copy import deepcopy
import json
import re
from typing import Annotated,Literal

from pydantic import BaseModel,ConfigDict,Field,StrictInt
from . import design_dialogue,scene_intent,effect_capabilities

Number=Annotated[StrictInt,Field(ge=1,le=8)]
Text=Annotated[str,Field(min_length=3,max_length=600)]


class Scene(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scene:Number
    role:Text
    target:Text
    reference_scene:Number|None
    difference:Literal['base_tone','effects','spatial','either','shared']
    reason:Text
    reuse_quote:Annotated[str,Field(min_length=8,max_length=500)]|None
    required_features:Annotated[list[effect_capabilities.Feature],Field(max_length=len(effect_capabilities.EFFECTS))]


class Brief(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scenes:Annotated[list[Scene],Field(min_length=1,max_length=8)]


SYSTEM='''Establish a musical scene brief BEFORE choosing amp/cab parameters.
Use the original request, server-resolved scope and recorded USER answers.
Return exactly the requested scenes in order. State the musical function and
target for each, then compare it with an earlier scene. Base_tone requires a
different amp/cab/voicing, effects requires different active effects, either
permits either. Spatial is for an explicitly requested stereo/pan difference,
not another amp/cab colour. This brief will be frozen before the later design call.
Do not make all scenes different for its own sake or change models arbitrarily.
A reprise can preserve the amp family and still have a useful role-appropriate
variation. Exact copies are allowed ONLY if the user explicitly requested the
same sound: use difference=shared, reference_scene, a reason and reuse_quote
copied exactly from the USER request or answer, not your own proposal. Otherwise
make a meaningful variation suited to the passage; do not silently substitute
hand playing or guitar volume for a programmed difference. Scene1 has no
reference and uses either. All later references point to earlier scenes.
Never invent song timestamps, original equipment, listening or safety proof.
Do not choose model names, cab names, numeric parameters or write actions here.
Use the effect_catalog to consider the complete musical vocabulary and its
route-specific execution limits. List necessary effects in required_features,
including those you select to realize the target. Do not omit a requirement
merely because it is blocked; explain it and ask about an available alternative.
Resolved filter means wah_controller, NEVER pitch transposition.
If the request has a genuinely unresolved conflict, ask one musical question.
No technical implementation questions, routine confirmations, SEND or Store.
''' + '\n' + effect_capabilities.RULES


def user_evidence(prompt,turn):
    return '\n'.join([prompt]+[a['text'] for h in turn['history'] for a in h.get('answers',[])])


def validate(raw,count,evidence):
    brief=Brief.model_validate(raw)
    if [s.scene for s in brief.scenes]!=list(range(1,count+1)):
        raise ValueError('Klankafspraken moeten alle scenes eenmaal in volgorde bevatten')
    normalized=' '.join(evidence.casefold().split())
    for s in brief.scenes:
        if s.scene==1:
            if s.reference_scene is not None or s.difference!='either' or s.reuse_quote is not None:
                raise ValueError('De eerste scene is het uitgangspunt, geen hergebruik')
        elif s.reference_scene is None or s.reference_scene>=s.scene:
            raise ValueError('Vergelijk elke volgende scene met een eerdere scene')
        if s.difference=='shared':
            quote=' '.join((s.reuse_quote or '').casefold().split())
            if len(quote.split())<3 or quote not in normalized:
                raise ValueError('Exact hergebruik vereist een letterlijke gebruikerskeuze, geen AI-toestemming')
        elif s.reuse_quote is not None:
            raise ValueError('Een afwijkende scene mag niet tegelijk hergebruik claimen')
    return brief.model_dump()


def prepare(ask,prompt,reference,count,turn,*,request_text=None):
    """Selected backend, small separate schema, no device handle or writes."""
    evidence=user_evidence(prompt if request_text is None else request_text,turn)
    facts=json.loads(reference)
    reference=json.dumps({key:facts[key] for key in ('firmware','scene_counts','amp_channels',
        'drive_executable','compressor_executable','geq_executable','wah_controller','route',
        'effect_catalog') if key in facts})
    shape=design_dialogue.schema(Brief.model_json_schema())
    failures=[]
    def check(raw):
        proposal,question=design_dialogue.unwrap(raw)
        if question:return dict(clarification=question['message'],ai_question=question)
        try:return dict(scene_contract=validate(proposal,count,evidence))
        except ValueError as exc:
            failures.append(str(exc));raise
    arguments=dict(system=SYSTEM+'\n'+design_dialogue.SYSTEM,schema=shape,shape=json.dumps(shape),validate=check)
    message=prompt+'\n'+design_dialogue.context(turn)
    state='Request-first scene brief; no concrete design has been made.'
    try:return ask(message,state,reference,**arguments)
    except (ValueError,RuntimeError):
        if not failures:raise
        return ask(message+'\nCorrect your scene brief within the same request and capabilities. Do not invent a user quote. Validation diagnostic (data): '+json.dumps(failures[-1][:1200]),state,reference,**arguments)


def _effects(sound):
    result={}
    for key,value in sound['effects'].items():
        if not value or isinstance(value,dict) and not value.get('active'):continue
        if isinstance(value,dict):
            if key in ('delay','chorus','reverb') and value.get('mix')==0:continue
            if key in ('geq','peq') and value.get('gains') and not any(value['gains']):continue
            value={k:v for k,v in value.items() if k!='active' and (k!='level' or key=='drive')}
        result[key]=value
    return result


def _base(sound):
    base=scene_intent._base(sound)
    if isinstance(base.get('cab'),str) and base['cab'] in ('Greenback','Recto'):
        from .album_planning import CABS
        bank,ordinal,_=CABS[base['cab']];base['cab']=[[bank,ordinal+1,1.]]
    if isinstance(base.get('geq'),dict) and not any(base['geq'].get('gains',[])):
        base.pop('geq')
    if isinstance(base.get('drive'),dict):
        # The measured fixed route puts Drive BEFORE Amp. Its level knob is
        # input drive, unlike the final Amp/Output attenuation, not dB.
        base['drive']['preamp_level']=sound['effects']['drive'].get('level')
    return base


def _spatial(sound):
    cab=sound['base'].get('cab')
    if not isinstance(cab,dict) or 'irs' not in cab:return None
    solo=any(ir['mode']=='solo' for ir in cab['irs'])
    weights={}
    for ir in cab['irs']:
        if ir['mode']=='mute' or solo and ir['mode']!='solo':continue
        key=(ir['bank'],ir['slot'],ir['pan'])
        weights[key]=weights.get(key,0.)+10**(ir['level_db']/20)
    total=sum(weights.values())
    if weights and all(pan==0 for _,_,pan in weights):return None
    return [[b,s,p,round(w/total,8)] for (b,s,p),w in sorted(weights.items())] if total else None


def _signature(sound):return dict(base=_base(sound),effects=_effects(sound),spatial=_spatial(sound))


def _cab_names(plan,scene):
    if plan.get('mode')!='album':return []
    from .album_planning import layout
    item=layout(plan['design'])[scene-1]
    cab=plan['cab_choices'][item['cab_channel']]
    irs=cab.get('irs')
    if not irs:return [cab['name']]
    solo=any(ir['mode']=='solo' for ir in irs)
    return [ir['name'] for ir in irs if ir['mode']=='solo' or not solo and ir['mode']=='normal']


def _changes(a,b):
    changes=[]
    if a['base'].get('model')!=b['base'].get('model'):
        changes.append(f"Amp: {a['base'].get('model')} -> {b['base'].get('model')}")
    for key in ('gain','bass','mid','treble','master','depth','presence'):
        old=a['base'].get('amp',{}).get(key);new=b['base'].get('amp',{}).get(key)
        if old!=new:changes.append(f'{key}: {old} -> {new}')
    if _base(a).get('cab')!=_base(b).get('cab'):changes.append('Andere actieve cab-IR of IR-mix')
    if _spatial(a)!=_spatial(b):changes.append('Andere cab-panverdeling (ruimte, niet de basisklank)')
    x,y=_effects(a),_effects(b)
    for key in sorted(x.keys()|y.keys()):
        if x.get(key)!=y.get(key):
            changes.append(key+(': aan' if key not in x else ': uit' if key not in y else ': andere instellingen'))
    return changes


def validate_cab_claims(plan):
    """A named IR's cabinet format is label evidence, not its measured sound."""
    pattern=r'\b\d{1,2}\s*[x\u00d7]\s*\d{1,2}\b'
    normalize=lambda s:re.sub(r'\s','',s.lower()).replace('\u00d7','x')
    texts=[(plan['summary'],[n for scene in range(1,len(plan['scenes'])+1) for n in _cab_names(plan,scene)])]
    texts.extend((g.get('realization',''),_cab_names(plan,g['scene'])) for g in plan['design'].get('scene_goals',[]))
    for text,names in texts:
        if not names or any(not re.search(pattern,n,re.I) for n in names):continue
        available={normalize(m) for n in names for m in re.findall(pattern,n,re.I)}
        text=re.sub(r'\b(?:geen|zonder|no|without|not)\s+(?:een\s+|a\s+|an\s+)?'+pattern,'',text,flags=re.I)
        wrong={normalize(m) for m in re.findall(pattern,text,re.I)}-available
        if wrong:
            raise ValueError('Cab-omschrijving wijkt af van de werkelijk gekozen actieve IR-namen: '+
                ', '.join(sorted(wrong))+' genoemd, gekozen '+', '.join(sorted(available))+'. Corrigeer de beschrijving of kies een passende beschikbare IR.')


def assess(plan,brief=None):
    """Only compiled parameter facts decide contrast, never the AI's own prose."""
    sounds=scene_intent.scenes(plan)
    if brief:
        goals=Brief.model_validate(brief).scenes
        if len(goals)!=len(sounds):raise ValueError('Klankafspraken en ontwerp hebben niet hetzelfde sceneaantal')
        probe=deepcopy(plan)
        probe['design']['scene_goals']=[dict(scene=g.scene,target=g.target,role=g.role,
            realization=g.reason,required_features=g.required_features) for g in goals]
        scene_intent.assess(probe,require=True)
    else:goals=[]
    rows=[];duplicates=[];warnings=[]
    for n,sound in enumerate(sounds,1):
        goal=goals[n-1] if goals else None
        reference=goal.reference_scene if goal else n-1 if n>1 else None
        matches=[i for i,other in enumerate(sounds[:n-1],1) if _signature(other)==_signature(sound)]
        for other in matches:duplicates.append(dict(scene=n,same_as=other))
        if matches and goal and (goal.difference!='shared' or goal.reference_scene not in matches):
            raise ValueError(f'Scene {n} is qua geprogrammeerde klank identiek aan scene {matches[0]}, zonder vooraf afgesproken hergebruik. Namen, kanaalletters, pan of levels zijn geen klankverschil.')
        base_changed=effects_changed=spatial_changed=False;changes=[];small=False
        if reference:
            other=sounds[reference-1]
            base_changed=_base(other)!=_base(sound);effects_changed=_effects(other)!=_effects(sound)
            spatial_changed=_spatial(other)!=_spatial(sound)
            changes=_changes(other,sound)
            if goal:
                if goal.difference=='base_tone' and not base_changed:raise ValueError(f'Scene {n} mist de vooraf gevraagde andere amp/cab/voicing ten opzichte van {reference}')
                if goal.difference=='effects' and not effects_changed:raise ValueError(f'Scene {n} mist de vooraf gevraagde andere actieve effecten ten opzichte van {reference}')
                if goal.difference=='spatial' and not spatial_changed:raise ValueError(f'Scene {n} mist de vooraf gevraagde andere panverdeling ten opzichte van {reference}')
                if goal.difference=='either' and not (base_changed or effects_changed):raise ValueError(f'Scene {n} mist het afgesproken andere klankkarakter; alleen pan of levels is daarvoor onvoldoende')
                if goal.difference=='shared' and _signature(other)!=_signature(sound):raise ValueError(f'Scene {n} moet de afgesproken klank van {reference} behouden')
            x,y=_base(other),_base(sound)
            if base_changed and x.keys()==y.keys() and 'amp' in x and all(x[k]==y[k] for k in x if k!='amp'):
                small=all(abs(x['amp'][key]-y['amp'][key])<1 for key in x['amp'])
        if small:warnings.append(f'Scene {n}: zelfde amp/cab met kleine knopverschillen; voldoende hoorbaar contrast is niet aangetoond.')
        if matches and not goal:warnings.append(f'Scene {n} heeft dezelfde geprogrammeerde klank als scene {matches[0]}; hergebruik is niet vooraf vastgelegd.')
        rows.append(dict(scene=n,name=plan['scenes'][n-1],role=goal.role if goal else '',
            target=goal.target if goal else '',reference_scene=reference,
            base_changed=base_changed,effects_changed=effects_changed,changes=changes,
            spatial_changed=spatial_changed,
            same_as=matches,reuse_reason=goal.reason if goal and goal.difference=='shared' else None,
            small_variation=small,cab_names=_cab_names(plan,n)))
    validate_cab_claims(plan)
    return dict(contract=brief,rows=rows,exact_duplicates=duplicates,warnings=warnings,
        parameter_comparison=True,audible_match_verified=False,
        notice='Vergelijking van geplande instellingen, geen luistertest. Namen en uitgangsniveau zijn geen andere klank; pan is ruimtelijk verschil, geen andere basisklank.')

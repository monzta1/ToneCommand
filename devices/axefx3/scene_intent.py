"""Musical intent and structural checks, never an audible-match certificate.

No MIDI or capability promotion. Compare actual compiled settings, not names,
AI prose or arbitrary numeric distance masquerading as a listening test.
"""
import json
import math
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt


class Goal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scene: Annotated[StrictInt, Field(ge=1, le=8)]
    target: Annotated[str, Field(min_length=3, max_length=500)]
    role: Annotated[str, Field(min_length=1, max_length=100)]
    realization: Annotated[str, Field(min_length=3, max_length=600)]
    distinct_from: Annotated[list[Annotated[StrictInt, Field(ge=1, le=8)]], Field(max_length=7)] = []
    distinction: Literal['base_tone', 'effects', 'shared'] = 'shared'
    required_features: Annotated[list[Literal['drive','compressor','post_eq','reverb','wah_controller','pitch']], Field(max_length=6)] = []


class IntentDesign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Defaults allow historical designs to be inspected, not silently certified.
    scene_goals: Annotated[list[Goal], Field(max_length=8)] = []


SYSTEM = '''For EVERY requested scene return scene_goals, in exact scene order.
State its requested tonal target, musical role and how the actual settings
realize it. Preserve backing versus lead. This applies to any artist, song,
album, clean/crunch switch or user listening feedback, not one named band.
Use distinct_from only where the request needs a difference: base_tone means
amp/cab/voicing, effects means ambience/modulation, shared means intentionally
the same voice. Do not manufacture differences the user did not request.
Different names, level alone or tiny EQ changes are not evidence of another
tone. Never claim audible success. If the measured tools cannot represent a
requested contrast, disclose that limitation, not an invented effect write.
For listening adjustments preserve untargeted scene settings and preset name;
check shared channels before changing them. Use only the supplied capabilities.
List explicitly requested drive/compressor/post_eq/reverb/wah_controller/pitch in each
goal's required_features. An unsupported requirement cannot silently disappear.
'''


class MissingFeature(ValueError):
    """A musical requirement failed validation, not an AI connection failure."""
    def __init__(self, scene, feature):
        self.scene, self.feature = scene, feature
        super().__init__(f'Scene {scene}: vereist {feature}, maar dit is niet geverifieerd in het ontwerp. Geen onbewezen bediening of stilzwijgende vervanging.')


def _key(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))


def scenes(plan):
    """Canonical per-scene stored sound, including inactive shared settings."""
    d = plan['design']
    result = []
    if plan.get('mode') == 'album':
        from .album_planning import layout
        for item in layout(d):
            amp, cab = d['albums'][item['amp_channel']], d['albums'][item['cab_channel']]
            result.append(dict(name=item['name'], base=dict(model=amp['amp_model'],
                amp=amp['amp'], cab=cab['cab']), effects=dict(
                delay={**d['delay'], 'active': item['delay']},
                chorus={**d['chorus'], 'active': item['chorus']}),
                channels=dict(amp=item['amp_channel'],cab=item['cab_channel'])))
            if any(a.get('drive') is not None for a in d['albums']):
                voice=amp.get('drive') or dict(model='T808 Mod',gain=0.,tone=5.,level=0.,mix=100.)
                result[-1]['effects']['drive']={**voice,'active':item.get('drive',False)}
                result[-1]['channels']['drive']=item['amp_channel']
            if d.get('wah') is not None:
                result[-1]['effects']['wah']={**d['wah'],'active':item.get('wah',False)}
                result[-1]['channels']['wah']=0
            for key,family in (('compressor','COMP'),('geq','GEQ')):
                if any(a.get(key) is not None for a in d['albums']):
                    from . import effect_voicing
                    voice=amp.get(key) or effect_voicing.default(family).model_dump()
                    result[-1]['effects'][key]={**voice,'active':item.get(key,False)}
                    result[-1]['channels'][key]=item['amp_channel']
    elif plan.get('mode') == 'serial':
        result.append(dict(name=d['scene_name'], base=dict(amp=d['amp'], model='retained', cab='retained'),
                           effects=dict(delay=d['delay'], chorus=d['chorus'])))
    elif plan.get('mode') == 'nam':
        for s in d['scenes']:
            result.append(dict(name=s['name'], base=dict(nam=s['nam'], capture=plan['capture'], cab=d['cab_active']),
                effects={key: {**d[key], 'active': s[key] and d[key]['active']} for key in ('delay','chorus','reverb')}))
    else:
        for s in d['scenes']:
            explicit = s.get('cab_left') is not None
            result.append(dict(name=s['name'], base=dict(amp=s['amp'], model=s.get('amp_model') or d['amp_model'],
                cab=[s['cab_left'], s.get('cab_right')] if explicit else [d['cab_left'], d.get('cab_right')]),
                effects={key:s.get(key) for key in ('wah','delay','chorus','reverb','drive','compressor','geq','peq')},
                output=s.get('output_level',-6)))
    return result


def _base(sound):
    base = json.loads(_key(sound['base']))
    # A level difference alone does not establish different base tone.
    for family in ('amp','nam'):
        if family in base:
            base[family].pop('level', None)
    cab=base.get('cab')
    if isinstance(cab,dict) and 'irs' in cab:
        # Muted or solo-excluded IRs and pan alone cannot certify another
        # base tone. Normalize coherent duplicate IR weights and total gain:
        # merely moving a fader or a slot must not manufacture tonal contrast.
        solo=any(ir['mode']=='solo' for ir in cab['irs'])
        weights={}
        for ir in cab['irs']:
            if ir['mode']=='mute' or (solo and ir['mode']!='solo'):continue
            key=(ir['bank'],ir['slot'])
            weights[key]=weights.get(key,0.)+10**(ir['level_db']/20)
        total=math.fsum(weights.values())
        base['cab']=[[b,s,round(v/total,8)] for (b,s),v in sorted(weights.items())] if total else []
    for family in ('wah','drive','compressor','geq','peq'):
        value=sound['effects'].get(family)
        if value and (not isinstance(value,dict) or value.get('active')):
            base[family]={k:v for k,v in value.items() if k!='level'} if isinstance(value,dict) else value
    return base


def _audible_effects(sound):
    return {key: value for key, value in sound['effects'].items()
            if (value.get('active') if isinstance(value,dict) else value)}


def assess(plan, *, require=False):
    sounds = scenes(plan)
    goals = [Goal.model_validate(g) for g in plan['design'].get('scene_goals', [])]
    if not goals:
        if require:
            raise ValueError('Elk sceneontwerp vereist een klankdoel en onderbouwing; niets verzonden.')
        return dict(goals=[], comparisons=[], warnings=['Geen vastgelegde klankdoelen in dit oudere ontwerp.'],
                    audible_match_verified=False)
    if [g.scene for g in goals] != list(range(1,len(sounds)+1)):
        raise ValueError('Klankdoelen moeten alle gevraagde scenes precies eenmaal in volgorde bevatten.')
    warnings, comparisons = [], []
    for goal in goals:
        sound=sounds[goal.scene-1]
        for feature in goal.required_features:
            fx=sound['effects']
            def active(name):
                value=fx.get(name)
                return bool(value) and (not isinstance(value,dict) or value.get('active'))
            realized=dict(drive=active('drive'),compressor=active('compressor'),post_eq=active('geq') or active('peq'),
                reverb=active('reverb'),wah_controller=bool(plan.get('controller') and
                plan['controller'].get('source')) and active('wah'),pitch=False)
            if not realized[feature]:
                raise MissingFeature(goal.scene, feature)
        if len(set(goal.distinct_from)) != len(goal.distinct_from):
            raise ValueError('Een scenevergelijking mag niet dubbel voorkomen.')
        if goal.distinction == 'shared' and goal.distinct_from:
            raise ValueError('Een gedeelde klank kan niet tegelijk als verplicht verschillend worden opgegeven.')
        for other in goal.distinct_from:
            if other == goal.scene or other > len(sounds):
                raise ValueError('Scenevergelijking verwijst naar een ongeldige of dezelfde scene.')
            a,b = sounds[goal.scene-1], sounds[other-1]
            same_base = _base(a) == _base(b)
            same_fx = _audible_effects(a) == _audible_effects(b)
            if goal.distinction == 'base_tone' and same_base:
                raise ValueError(f'Scenes {goal.scene}/{other} vragen een andere basisklank, maar delen dezelfde amp/cab-voicing. Geen schijnverschil via naam, volume of delay.')
            if goal.distinction == 'effects' and same_fx:
                raise ValueError(f'Scenes {goal.scene}/{other} vragen andere effecten, maar hebben dezelfde actieve effectinstellingen.')
            comparisons.append(dict(scene=goal.scene, other=other, kind=goal.distinction,
                                    base_changed=not same_base, effects_changed=not same_fx))
            x,y = _base(a),_base(b)
            if not same_base and x.get('model') == y.get('model') and x.get('cab') == y.get('cab') and 'amp' in x and 'amp' in y:
                delta = max(abs(x['amp'][k]-y['amp'][k]) for k in x['amp'])
                if delta < 1:
                    warnings.append(f'Scenes {goal.scene}/{other}: zelfde amp/cab met alleen kleine knopverschillen. Hoorbaar voldoende contrast is niet aangetoond.')
    return dict(goals=[g.model_dump() for g in goals], comparisons=comparisons,
                warnings=warnings, audible_match_verified=False,
                channel_groups=_groups(plan), technical_verification='Pending SEND and independent readback')


def _groups(plan):
    mappings=plan.get('channel_mapping')
    if mappings is None:
        mappings=[dict(scene=n,**{family: 'ABCD'[values[n-1]] for family,values in plan.get('scene_channels',{}).items()})
                  for n in range(1,len(plan['scenes'])+1)]
    groups={}
    for mapping in mappings:
        for family,channel in mapping.items():
            if family!='scene':groups.setdefault(f'{family} {channel}',[]).append(mapping['scene'])
    return groups


def attach(plan):
    plan['scene_intent'] = assess(plan)
    plan['warnings'].extend(plan['scene_intent']['warnings'])
    return plan


def preserve(previous, candidate, targets):
    """Protect compiled sound settings, not AI promises about shared channels."""
    before, after = scenes(previous), scenes(candidate)
    if (candidate['name'] != previous['name'] or candidate['required_route'] != previous['required_route']
            or len(before) != len(after) or candidate.get('mode') != previous.get('mode')
            or candidate.get('controller') != previous.get('controller')):
        raise ValueError('Een luisteraanpassing mag naam, bouwroute, sceneaantal of gedeelde controllerkeuze niet veranderen.')
    if not targets or len(set(targets)) != len(targets) or any(type(n) is not int or not 1<=n<=len(before) for n in targets):
        raise ValueError('Kies geldige, unieke scenes voor de luisteraanpassing.')
    changed = [i for i,(a,b) in enumerate(zip(before,after),1) if a != b]
    outside = set(changed)-set(targets)
    if outside:
        raise ValueError('Gedeelde instellingen veranderen ook niet-gevraagde scenes '+','.join(map(str,sorted(outside)))+'. Kies vrije kanalen of breid de aanpassing expliciet uit; niets verzonden.')
    def sound_key(sound):
        return dict(base=sound['base'],effects=_audible_effects(sound),output=sound.get('output'))
    if not any(sound_key(a)!=sound_key(b) for a,b in zip(before,after)):
        raise ValueError('De luisteraanpassing verandert geen instellingen; alleen tekst is geen tweak.')
    return dict(requested_scenes=targets, changed_scenes=changed,
                preserved_scenes=[n for n in range(1,len(before)+1) if n not in targets])

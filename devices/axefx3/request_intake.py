"""Read-only request clarification, never hardware capability or write consent."""
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from . import fw33_profile,wah_voicing


class Resolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pitch_meaning: Literal['filter', 'pitch'] | None = None
    accepted_omissions: list[Literal['wah_controller', 'pitch', 'reverb']] = Field(default_factory=list, max_length=3)
    scene_count_override: StrictBool = False


LABELS = dict(wah_controller='Wah control (filter/pedal), new controller binding and Auto Engage',
              pitch='Real pedal-controlled pitch increase', reverb='New reverb settings')
WORDS = dict(zip('een one twee two drie three vier four vijf five zes six zeven seven acht eight negen nine tien ten'.split(),
                 (1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10)))


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


def explicit_wah_source(prompt,selected=None):
    if selected is not None:return selected
    text=normalized(prompt)
    if not _positive(text,r'\bwah\b'):return None
    choices=set(re.findall(r'\bexternal\s*([12])\b',text))
    return 'External '+next(iter(choices)) if len(choices)==1 else None


def explicit_wah_auto_engage(prompt):
    """Infer only an unambiguous text request, never override a form choice."""
    text=normalized(prompt)
    clauses=re.split(r'[.;!?\n]',text)
    marker=r'\b(?:auto\s*-?\s*engag\w*|automatisch\s+inschakel\w*|automatically\s+engag\w*)\b'
    matches=[c for c in clauses if re.search(marker,c)]
    if len(matches)!=1:return None
    clause=matches[0]
    if re.search(r'\b(?:behoud\w*|preserv\w*|keep|niet|not|geen|zonder|without|no|off|uit|nooit|never|disabl\w*|uitschakel\w*|uitgeschakeld|slow|med|medium|speed)\b',clause):
        return None
    return 'Fast Pos'


def scene_counts(prompt):
    text = normalized(prompt)
    number = r'(-?\d{1,3}|' + '|'.join(WORDS) + r')'
    hits = re.findall(r'(?<![\w-])' + number + r'\s+scenes?\b', text)
    hits += re.findall(r'\bscenes\s*[:=]\s*' + number + r'\b', text)
    return sorted({WORDS[x] if x in WORDS else int(x) for x in hits})


def _positive(text, pattern):
    # Narrow explicit exclusions are not a demand to add the feature.
    text = re.sub(r'\b(?:geen|zonder|no|without)\s+(?:nieuwe?\s+|new\s+)?(?:wah|reverb|pitch)(?:\s+(?:controller|shift))?\b', '', text)
    text = re.sub(r'\b(?:wah|reverb|pitch)\s+(?:(?:staat|is)\s+)?(?:uit|off|bypassed|bypass)\b', '', text)
    return bool(re.search(pattern, text))


def analyze(prompt, reg, mode, scenes, resolution=None, *, refining=False, wah_source=None):
    resolution = resolution or Resolution()
    text = normalized(prompt)
    counts = scene_counts(prompt)
    count = scenes if resolution.scene_count_override or refining or len(counts) != 1 else counts[0]
    questions, missing = [], []
    if (not refining and not resolution.scene_count_override and
            (len(counts) > 1 or any(not 1 <= n <= 8 for n in counts))):
        questions.append(dict(id='scene_count', kind='scenes', text='Your text requests conflicting or unavailable scene counts. Choose 1 to 8 scenes explicitly.'))
    fw33 = reg.firmware == fw33_profile.KEY
    if (mode == 'serial' and count != 1) or (fw33 and mode == 'nam' and count > 2):
        questions.append(dict(id='route_scenes', kind='scenes', text='This build route does not support that scene count. Choose AMP/CAB for up to eight scenes, or deliberately choose fewer. An empty NAM preset needs a one-scene build first.'))
    wah = _positive(text, r'\bwah\b')
    pitch = _positive(text, r'\b(?:pitch(?:ed|\s*-?\s*shift(?:er|ing)?)?|whammy|toonhoogte(?:verhoging)?)\b')
    ambiguous = wah and pitch and bool(re.search(r'\b(?:high|hoge?|hoog|toe\s*-?\s*down|teen)\b', text))
    if ambiguous and resolution.pitch_meaning is None:
        questions.append(dict(id='pitch_meaning', kind='choice', text='By high pitch at toe-down, do you mean a brighter/higher wah filter position or a real increase in musical pitch?',
                              options=[dict(value='filter', label='Higher, brighter wah filter position'), dict(value='pitch', label='Real pitch increase (Whammy/Pitch)')]))
    actual_pitch = pitch and (not ambiguous or resolution.pitch_meaning == 'pitch')
    controller = bool(wah_source) or (wah and bool(re.search(r'\b(?:external\s*[12]|auto\s*-?\s*engag\w*|pedaal|pedal|controller)\b', text)))
    # auto is route exploration, not permission to drop requirements. Recheck
    # against the actual selected route before any design call.
    if mode != 'auto':
        supported_wah=(mode=='amp' and wah_voicing.RELEASED and getattr(reg,'hardware_variant',None)=='mk2')
        if fw33 and (wah or controller) and not supported_wah:
            missing.append('wah_controller')
        if actual_pitch:
            missing.append('pitch')
        if fw33 and mode in ('amp', 'serial') and _positive(text, r'\breverb\b'):
            missing.append('reverb')
    approved = [f for f in missing if f in resolution.accepted_omissions]
    for feature in missing:
        if feature not in approved:
            questions.append(dict(id=feature, kind='omission', text=LABELS[feature] + ' is not verified for this build route. Design only the supported part and explicitly defer this requirement? This adds no controller or effect.'))
    return dict(ready=not questions, questions=questions, requested_scene_counts=counts,
                scenes=count if 1 <= count <= 8 else scenes, approved_omissions=approved,
                pitch_meaning=resolution.pitch_meaning, readonly=True, hardware_written=False,
                notice='Request checked; no AI design, SEND or storage yet. A deferred requirement will not be executed.')


def context(intake):
    """Trusted scope rules: typed answers, not a second untrusted prompt."""
    omitted = ', '.join(intake['approved_omissions']) or 'none'
    meaning = intake['pitch_meaning'] or 'not specified'
    return ('\nSERVER-VALIDATED REQUEST SCOPE: pitch meaning=' + meaning +
            '; explicitly deferred requirements=' + omitted +
            '. Deferred requirements must be listed as NOT implemented, not promised or included '
            'in scene_goals.required_features. All other explicit requirements remain mandatory. '
            'Filter means wah-filter frequency only, NEVER musical pitch transposition. '
            'These scope answers do not enable hardware actions or authorize SEND/Store.\n')


def annotate(plan, intake):
    plan['request_intake'] = intake
    for feature in intake['approved_omissions']:
        plan['warnings'].append('Explicitly deferred, NOT executed: ' + LABELS[feature] + '.')

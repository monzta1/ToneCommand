"""Opt-in existing-preset request and normal review/confirm/send host bridge."""
from copy import deepcopy
import hashlib
import json
import os
import secrets
import threading
import time

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from fm9 import ai_settings, planner
from fm9.device import ReadOnly
from fm9.paths import resource_path
from .existing_contract import Design, compile_design
from .existing_scalar import ExistingEditor, ScalarWrite, context


FLAG = 'TONECOMMAND_AXEFX3_EXISTING_SCALAR'
SYSTEM = '''Adjust this EXISTING preset, do not build or replace it. Use only
the exact host-supplied editable_parameters. Preserve all eight original scene
names, channels, bypass, effects/models/cabinets, routes, modifiers and levels.
One shared channel affects every listed scene using it. Explain all eight
original roles; each needs a real change to an active supported control.
Use purposeful Gain/Mid changes, in tenths, at most one display unit per
review. Keep unproposed settings unchanged. Do not invent effect/width/timing
controls, controller bindings or insertion. If the musical request cannot be
met within these controls, ask one clear scope question instead of silently
omitting it or requesting technical parameter values. No audio listening,
exact match, execution or Store claim. Return design OR question, never both.
'''


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Scan(Strict):
    expected_preset: StrictInt = Field(ge=0, le=1023)
    expected_scene: StrictInt = Field(ge=1, le=8)
    target_confirmed: StrictBool = False
    external_audio_muted: StrictBool = False


class Propose(Strict):
    scan_token: StrictStr = Field(min_length=16, max_length=128)
    prompt: StrictStr = Field(min_length=3, max_length=12000)
    answer: StrictStr | None = Field(default=None, min_length=1, max_length=2000)


class Transition(Strict):
    token: StrictStr = Field(min_length=16, max_length=128)
    plan_digest: StrictStr = Field(min_length=64, max_length=64)
    expected_preset: StrictInt = Field(ge=0, le=1023)
    expected_scene: StrictInt = Field(ge=1, le=8)
    target_confirmed: StrictBool = False
    external_audio_muted: StrictBool = False


def register(app, host):
    pending = dict(scan=None, plan=None, generation=0)
    busy = threading.Lock()

    def selected():
        from .edit_routes import configured_writer
        ctx = host.device_context()
        return ctx.adapter if (os.environ.get(FLAG) == '1' and ctx.kind == 'axefx3'
                               and configured_writer() is ExistingEditor
                               and type(ctx.adapter) is ExistingEditor) else None

    def eligible():
        dev = selected()
        if dev is None or host._gig_mode['on'] is not False:
            raise ReadOnly('The explicit existing-preset connection and Gig Lock off are required')
        if host._plan_revisions:
            raise ReadOnly('Finish or discard the other pending plan first')
        dev._identity()
        return dev

    def origin_ok(request):
        origin = request.headers.get('origin')
        return origin is None or (request.url.hostname in ('127.0.0.1', 'localhost', '::1')
            and origin == f'{request.url.scheme}://{request.url.netloc}')

    def refuse(error, status=409):
        dev = selected()
        return JSONResponse(dict(error=str(error), uncertain=bool(dev and dev._uncertain),
            stored=False, undo_available=False, retry_allowed=False), status_code=status)

    def call(request, work):
        if not origin_ok(request):
            return refuse('Cross-origin existing-preset requests are refused', 403)
        try:
            return work()
        except (ReadOnly, RuntimeError, ValueError, TypeError, OSError, KeyError) as error:
            return refuse(error)

    def invalidate():
        pending.update(scan=None, plan=None, generation=pending['generation'] + 1)

    def view(p):
        return dict(token=p['token'], plan_digest=p['digest'], expected_preset=p['preset'],
            expected_scene=p['scene'], stage=p['stage'], proposal=p['review'].preview(),
            stored=False, undo_available=False, can_send=p['stage'] == 'confirm')

    def take(body, stage):
        p, pending['plan'] = pending['plan'], None
        if (not p or p['stage'] != stage or not body.token.isascii()
                or not secrets.compare_digest(body.token, p['token'])
                or body.plan_digest != p['digest'] or body.expected_preset != p['preset']
                or body.expected_scene != p['scene'] or time.monotonic() >= p['review']._expires
                or eligible() is not p['device'] or p['device']._delta is not p['review']):
            raise ReadOnly('The review is stale, foreign, consumed or out of order')
        if p['device'].current_preset()[0] != p['preset'] or p['device'].current_scene() != p['scene']:
            raise ReadOnly('Current preset or scene changed; scan again')
        return p

    @app.get('/axefx3-existing-edit.js')
    def script():
        return FileResponse(resource_path('ui', 'axefx3-existing-edit.js'), media_type='text/javascript')

    @app.get('/api/axefx3/existing/state')
    def state():
        with host._lock:
            dev = selected()
            if dev is None:
                return dict(configured=False, available=False)
            try:
                eligible()
                preset, scene = dev.current_preset(), dev.current_scene()
                if preset is None or scene is None:
                    raise ReadOnly('Current target is unreadable')
                return dict(configured=True, available=True, preset=preset[0], name=preset[1],
                    scene=scene, scope='Existing Amp 1/A Bassguy and B Vibrato Lux Gain/Mid only',
                    stored=False, undo_available=False)
            except (ReadOnly, ValueError, OSError) as error:
                return dict(configured=True, available=False, reason=str(error))

    @app.post('/api/axefx3/existing/scan')
    def scan(body: Scan, request: Request):
        def work():
            if not busy.acquire(blocking=False):
                raise ReadOnly('An existing-preset operation is running')
            try:
                with host._lock:
                    invalidate()
                    dev = eligible()
                    if dev.current_scene() != body.expected_scene:
                        raise ReadOnly('Current scene differs from the requested source')
                    reference = dev.scan(body.expected_preset, external_audio_muted=body.external_audio_muted,
                                         target_confirmed=body.target_confirmed)
                    token = secrets.token_urlsafe(32)
                    pending['scan'] = dict(token=token, device=dev, prompt=None, turns=[], question=None)
                    return dict(scan_token=token, reference=reference, scene_maps_verified=8,
                                parameter_writes=0, stored=False)
            finally:
                busy.release()
        return call(request, work)

    @app.post('/api/axefx3/existing/plan')
    def propose(body: Propose, request: Request):
        def work():
            if not busy.acquire(blocking=False):
                raise ReadOnly('An existing-preset operation is running')
            settings = False
            try:
                with host._lock:
                    dev = eligible()
                    scan = pending['scan']
                    if (not scan or scan['device'] is not dev or not body.scan_token.isascii()
                            or not secrets.compare_digest(body.scan_token, scan['token'])):
                        raise ReadOnly('Scan the original scenes again')
                    pending['plan'] = None
                    reference = dev.reference()
                    ctx = context(dev._scan[0])
                    revision = pending['generation']
                    if body.answer is not None:
                        if not scan['question'] or scan['prompt'] != body.prompt or len(scan['turns']) >= 3:
                            raise ReadOnly('No matching unanswered scope question')
                        scan['turns'].append(dict(question=scan['question'], answer=body.answer))
                    elif scan['prompt'] != body.prompt:
                        scan.update(prompt=body.prompt, turns=[])
                    scan['question'] = None
                    instruction = body.prompt + '\nUser scope clarifications: ' + json.dumps(scan['turns'])
                settings = host._settings_lock.acquire(blocking=False)
                if not settings:
                    raise ReadOnly('AI settings are busy')
                ai_settings.apply_to_env()
                if not planner._env('PLANNER_BACKEND').strip() or len(planner.candidates()) != 1:
                    raise ReadOnly('Choose one explicit AI backend; no automatic or paid fallback')
                design_schema = Design.model_json_schema()
                definitions = design_schema.pop('$defs', {})
                schema = dict(type='object', additionalProperties=False, required=['design', 'question'],
                    properties=dict(design=dict(anyOf=[design_schema, dict(type='null')]),
                                    question=dict(anyOf=[dict(type='string', minLength=3, maxLength=600), dict(type='null')])))
                schema['$defs'] = definitions
                failures = []
                def validate(raw):
                    if type(raw) is not dict or set(raw) != {'design', 'question'}:
                        raise ValueError('Return exactly design or one scope question')
                    if raw['design'] is None and type(raw['question']) is str and 3 <= len(raw['question']) <= 600:
                        return dict(question=raw['question'])
                    if raw['question'] is not None or type(raw['design']) is not dict:
                        raise ValueError('A design and question cannot be combined')
                    try:
                        compile_design(raw['design'], ctx)
                        for row in raw['design']['changes']:
                            match = next(p for p in ctx['editable_parameters'] if p['channel'] == row['channel']
                                         and p['effect_id'] == row['effect_id'] and p['parameter'] == row['parameter'])
                            if abs(row['value'] - match['current']) > 1.00001:
                                raise ValueError('At most one display unit per scalar review')
                            channel = 'ABCD'.index(row['channel'])
                            ScalarWrite(channel, ctx['observed_state']['bulk']['58'][channel * 142],
                                        row['parameter'], row['value'])
                    except ValueError as error:
                        failures.append(str(error))
                        raise
                    return dict(design=raw['design'])
                musical_rules = resource_path('config', 'tone_rules.md').read_text(encoding='utf-8')
                system = SYSTEM + '\nMusical reference only; existing-preset preservation and the exact editable surface take priority over new-build recipes:\n' + musical_rules
                args = dict(system=system, schema=schema, shape=json.dumps(schema), validate=validate)
                try:
                    result = planner.plan(instruction, 'Existing eight-scene preset', json.dumps(reference), **args)
                except (ValueError, RuntimeError):
                    if not failures:
                        raise
                    result = planner.plan(instruction + '\nCorrect the rejected proposal: ' + failures[-1],
                        'Same original preset and bounded controls', json.dumps(reference), **args)
                with host._lock:
                    if eligible() is not dev or pending['generation'] != revision or pending['scan'] is not scan:
                        raise ReadOnly('Device or scan changed during planning')
                    if result.get('question'):
                        scan['question'] = result['question']
                        return dict(question=result['question'], scan_token=scan['token'], stored=False)
                    review = dev.prepare_delta(result['design'])
                    proposal = review.preview()
                    digest = hashlib.sha256(json.dumps(proposal,sort_keys=True).encode('utf-8')).hexdigest()
                    p = dict(device=dev, review=review, token=secrets.token_urlsafe(32), digest=digest,
                        preset=proposal['target']['preset'], scene=proposal['target']['scene'], stage='plan')
                    pending['plan'] = p
                    return dict(**view(p), backend=result.get('backend'), model=result.get('model'))
            finally:
                if settings:
                    host._settings_lock.release()
                busy.release()
        return call(request, work)

    def transition(body, request, step):
        def work():
            if not busy.acquire(blocking=False):
                raise ReadOnly('An existing-preset operation is running')
            try:
                with host._lock:
                    previous = {'review':'plan', 'confirm':'review', 'send':'confirm'}[step]
                    if step == 'review' and pending['plan'] and pending['plan']['stage'] == 'confirm':
                        previous = 'confirm'  # Explicit back-to-review revokes the short SEND arm.
                    p = take(body, previous)
                    if step in ('confirm', 'send') and (body.target_confirmed is not True or body.external_audio_muted is not True):
                        raise ReadOnly('Confirm the exact target and fully muted external monitoring')
                    if step == 'send':
                        if time.monotonic() >= p['armed_until']:
                            raise ReadOnly('SEND arm expired; prepare a fresh review')
                        return p['device'].apply_delta(p['review'], external_audio_muted=True, target_confirmed=True)
                    p['stage'] = step
                    if step == 'confirm':
                        p['armed_until'] = time.monotonic() + 8
                    pending['plan'] = p
                    return view(p)
            finally:
                busy.release()
        return call(request, work)

    @app.post('/api/axefx3/existing/review')
    def review(body: Transition, request: Request):
        return transition(body, request, 'review')

    @app.post('/api/axefx3/existing/confirm')
    def confirm(body: Transition, request: Request):
        return transition(body, request, 'confirm')

    @app.post('/api/axefx3/existing/send')
    def send(body: Transition, request: Request):
        return transition(body, request, 'send')

    @app.post('/api/axefx3/existing/discard')
    def discard(request: Request):
        if not origin_ok(request):
            return refuse('Cross-origin discard refused', 403)
        with host._lock:
            invalidate()
            return dict(stage='request', stored=False)

    return pending

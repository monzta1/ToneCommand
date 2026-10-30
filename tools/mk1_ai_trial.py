"""Experimental MK1 request -> selected AI -> review -> confirmed SEND UI.

Separate entry point. Neither the original read-only kit nor production
capabilities are changed. No account, hardware or model download is automatic.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import sys
import threading
import time
import webbrowser

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from fm9 import ai_settings, planner
from devices.axefx3 import mk1_trial as trial

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.5.16-fx3.4-mk1-ai-trial.1'


def verify_package(root=ROOT):
    root = Path(root).resolve()
    manifest = json.loads((root/'MK1-AI-PACKAGE.json').read_text(encoding='utf-8'))
    required = {'tools/mk1_ai_trial.py', 'devices/axefx3/mk1_trial.py',
                'packaging/mk1-ai/index.html', 'packaging/mk1-ai/trial.js'}
    if (manifest.get('version') != VERSION or manifest.get('experimental') is not True
            or not isinstance(manifest.get('files'), dict)
            or not required <= manifest['files'].keys()
            or not re.fullmatch('[0-9a-f]{40}', str(manifest.get('source_commit', '')))):
        raise ValueError('Use the named MK1 AI trial ZIP, not an old kit or generic Source code download')
    for name, digest in manifest['files'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Package source changed; no hardware trial started')
    return manifest['source_commit']


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Plan(Body):
    prompt: str = Field(min_length=3, max_length=6000)
    expected_preset: StrictInt = Field(ge=0, le=511)


class Send(Body):
    token: str = Field(min_length=20, max_length=100)
    expected_preset: StrictInt = Field(ge=0, le=511)
    target_confirmed: StrictBool = False
    external_audio_muted: StrictBool = False
    experimental_mk1_consent: StrictBool = False


class Settings(Body):
    backend: str = Field(pattern=r'^(codex|cli|api|openai|grok)$')
    model: str = Field(default='', max_length=200)
    baseUrl: str = Field(default='', max_length=1000)
    apiKey: str = Field(default='', max_length=2000)


class Reply(Body):
    question: str | None = Field(default=None, max_length=2000)
    design: trial.Design | None = None


SYSTEM = '''You are ToneCommand's experimental MK1 one-scene guitar designer.
Use the user's text to design an AMP/CAB sound, optionally chorus, delay and reverb.
Artist, album and song references are tonal interpretations, never proven reproductions.
One scene only. No NAM, User cabs, pedals, controllers, Drive, pitch, storage or globals.
Choose an exact amp name from the complete supplied 336-model Axe-Fx III catalog.
Cabs: Greenback or Recto, built-in Factory2. These are the available cab choices,
not a claim that either is the original recording cabinet.
Work out the requested musical role, era, body, saturation, sustain and articulation
before choosing the amp/cab and gain/EQ. Do not default every artist to one family
or a named example. A singing lead needs suitable gain structure and midrange, not
just added output level or heavy ambience. A bright vintage sound is not necessarily
a thin sound. Do not apply a universal bass/gain boost or claim listening to audio.
Choose each effect only when useful; preserve a clear dry guitar contribution.
Explain the musical reason and any approximation, without inventing original gear.
All numeric schema bounds are strict; do not silently omit explicitly required features.
If an unsupported requirement or meaningful ambiguity prevents this scope, ask ONE
concise question using question, with design null. Otherwise question null and a design.
Explain choices and limitations in summary. Use a printable ASCII preset name <=31 chars.
FX enable booleans decide whether each is heard; their values are still required.
Output -18dB, Amp -12dB, IR1 -3dB, FX -1dB are fixed by the executor, not a limiter.
Do not return MIDI, extra fields, actions, code, invented capabilities or a successful-build claim.'''


def ask(prompt, baseline):
    if not planner._env('PLANNER_BACKEND').strip() or len(planner.candidates()) != 1:
        raise ValueError('Choose one AI backend in Settings first. No automatic/paid fallback.')
    def validate(raw):
        reply = Reply.model_validate(raw)
        if bool(reply.question) == (reply.design is not None):
            raise ValueError('Return either one question or one design')
        return (dict(clarification=reply.question) if reply.question else
                dict(design=reply.design.model_dump(), summary=reply.design.summary))
    return planner.plan(prompt,
        json.dumps(dict(device='Axe-Fx III MK1 experimental', scene=1,
                        preset=baseline['preset'][0], empty=True)),
        json.dumps(dict(amps=list(trial.AMPS), cabs=list(trial.CABS), scenes=1,
                        amp_catalog_count=len(trial.AMPS),
                        model_acceptance='Shared MK2 catalog; MK1 selections are experimental and require independent readback.',
                        unsupported=['Drive','pitch','controllers','NAM','User cabs','multiple scenes','Store'])),
        system=SYSTEM, shape=json.dumps(Reply.model_json_schema()),
        schema=Reply.model_json_schema(), validate=validate)


def create_app(factory=trial.Device, ask_ai=ask, *, source_info=None, check_source=None):
    app = FastAPI(title='Unofficial FX3 MK1 experimental AI builder')
    lock = threading.Lock()
    manifest = ROOT/'MK1-AI-PACKAGE.json'
    source = (source_info['source_commit'] if source_info is not None else
              json.loads(manifest.read_text(encoding='utf-8'))['source_commit'] if manifest.exists() else 'development-checkout')
    state = dict(dev=None, review=None, attempts=[], version=VERSION, source_commit=source)
    provenance = deepcopy(source_info or dict(source_commit=source, development=False))
    state.update(provenance)
    app.state.trial = state

    def verify_source():
        if check_source is not None:
            try:
                check_source()
            except (ValueError, OSError) as error:
                state['review'] = None
                raise HTTPException(409, str(error)) from None

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _error):
        return JSONResponse({'detail': 'Invalid request fields. No submitted secrets are echoed.'}, status_code=422)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        if request.url.hostname not in ('localhost', '127.0.0.1'):
            return JSONResponse({'detail': 'Local TC access only'}, status_code=403)
        if request.method == 'POST' and (request.headers.get('x-tonecommand') != '1' or
                request.headers.get('origin') not in (None, str(request.base_url).rstrip('/'))):
            return JSONResponse({'detail': 'Use the local TC interface'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    def device():
        if state['dev'] is None:
            raise HTTPException(409, 'Connect the MK1 explicitly; close Axe-Edit first')
        return state['dev']

    @app.get('/')
    def page():
        return FileResponse(ROOT / 'packaging/mk1-ai/index.html')

    @app.get('/trial.js')
    def javascript():
        return FileResponse(ROOT / 'packaging/mk1-ai/trial.js', media_type='text/javascript')

    @app.get('/trial.css')
    def stylesheet():
        source = (ROOT / 'ui/index.html').read_text(encoding='utf-8')
        return Response(source.split('<style>', 1)[1].split('</style>', 1)[0], media_type='text/css')

    @app.get('/api/settings')
    def settings():
        return dict(settings=ai_settings.panel_state(), model=ai_settings.load().model_for(), backends=ai_settings.available_backends(),
                    planning=ai_settings.planning_line())

    @app.post('/api/settings')
    def save_settings(body: Settings):
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Wait until TC finishes before changing AI settings')
        try:
            state['review'] = None
            return dict(settings=ai_settings.save(body.model_dump()).public())
        except ValueError:
            raise HTTPException(400, 'AI settings not accepted. Check the selected backend and fields.') from None
        finally:
            lock.release()

    @app.post('/api/connect')
    def connect():
        with lock:
            verify_source()
            if state['dev'] is not None:
                raise HTTPException(409, 'Already connected; do not open a second MIDI owner')
            dev = factory()
            try:
                dev.identity()
            except (ValueError, RuntimeError, OSError):
                dev.close()
                raise HTTPException(409, 'MK1 firmware fingerprint not accepted. No write attempted.') from None
            state['dev'], state['review'] = dev, None
            return dict(connected=True, experimental=True)

    @app.post('/api/disconnect')
    def disconnect():
        with lock:
            state['review'] = None
            dev, state['dev'] = state['dev'], None
            if dev:
                dev.close()
            return dict(connected=False)

    @app.get('/api/state')
    def status():
        with lock:
            verify_source()
            dev = state['dev']
            if dev is None:
                return dict(connected=False, version=VERSION, **provenance)
            try:
                dev.identity()
                preset = dev.current_preset()
            except (ValueError, RuntimeError, OSError):
                raise HTTPException(409, 'Identity/state could not be verified. Disconnect and inspect; no retry.') from None
            if not preset:
                raise HTTPException(409, 'Current preset unreadable; no navigation attempted')
            return dict(connected=True, preset=preset[0], scene=dev.current_scene(),
                        version=VERSION, **provenance, uncertain=dev.uncertain)

    @app.post('/api/discard')
    def discard():
        with lock:
            state['review'] = None
            return dict(discarded=True)

    @app.post('/api/plan')
    def plan(body: Plan):
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'TC is busy; your request was not submitted again')
        try:
            state['review'] = None
            verify_source()
            dev = device()
            baseline = dev.observe(body.expected_preset)
            if baseline['grid'] or set(baseline['blocks']) - {200, 201} or dev.outp.owner:
                raise ValueError('Use a genuinely empty preset on a new connection; no automatic rebuild')
            result = ask_ai(body.prompt, baseline)
            if result.get('clarification'):
                return dict(question=result['clarification'], sent=False)
            design = trial.Design.model_validate(result['design'])
            verify_source()
            if dev.observe(body.expected_preset) != baseline:
                raise ValueError('Device changed during planning. Nothing sent; review the state.')
            token = secrets.token_urlsafe(32)
            state['review'] = dict(token=token, design=design, baseline=baseline,
                                   expires=time.monotonic()+300, target=body.expected_preset)
            return dict(token=token, design=design.model_dump(), scene=1,
                        target=body.expected_preset, backend=result.get('backend'), model=result.get('model'),
                        routing='Input 1 -> Amp 1 -> Cab 1 -> Chorus 1 -> Delay 1 -> Reverb 1 -> Output 1',
                        actions=[s.label for s in trial.steps(design)], sent=False, stored=False,
                        source=deepcopy(provenance))
        except (ValueError, RuntimeError, OSError) as error:
            raise HTTPException(409, str(error)) from None
        finally:
            lock.release()

    @app.post('/api/send')
    def send(body: Send):
        with lock:
            review, state['review'] = state['review'], None
            if (not review or not secrets.compare_digest(review['token'], body.token) or
                    review['target'] != body.expected_preset or time.monotonic() >= review['expires']):
                raise HTTPException(409, 'Review expired or consumed; nothing resent')
            if not (body.target_confirmed and body.external_audio_muted and body.experimental_mk1_consent):
                raise HTTPException(409, 'Confirm target, muted monitoring and experimental MK1 writes')
            verify_source()
            dev = device()
            executor = trial.Execution(dev, review['target'], review['design'],
                                       review['baseline'], review['expires'])
            record = dict(timestamp=datetime.now(timezone.utc).isoformat(),
                          target=review['target'], verified=False, stored=False)
            state['attempts'].append(record)
            try:
                result = executor.run(muted=True, target_confirmed=True, check_source=check_source)
                record.update(result)
                return dict(**result, editor_check_required=True,
                    note='Keep monitoring muted. Disconnect MIDI, verify in Axe-Edit, then audition at low physical level. No Store.')
            except (ValueError, RuntimeError, OSError) as error:
                record.update(attempted_frames=dev.outp.writes, verified_frames=len(executor.verified),
                    failed_step=executor.sequence[min(executor.index, len(executor.sequence)-1)].label,
                    error_type=type(error.__cause__ or error).__name__)
                raise HTTPException(409, str(error)) from None

    @app.get('/api/report')
    def report():
        return dict(version=VERSION, **provenance, experimental=True, mk1_production_write_release=False,
                    attempts=deepcopy(state['attempts']),
                    note='No prompt, credentials, preset names, raw frames or model payloads included.')

    return app


def configure():
    # Own private state. Do not inherit another installation's credentials/slots.
    private = ROOT / 'test-results/private/mk1-ai'
    private.mkdir(parents=True, exist_ok=True)
    for key in tuple(os.environ):
        if key.startswith('PLANNER_') or key in ai_settings._MANAGED:
            os.environ.pop(key, None)
    os.environ.update(TONECOMMAND_SIM='0',
        TONECOMMAND_STORE_SLOTS='', TONECOMMAND_CAB_SLOTS='', TONECOMMAND_NAM_SLOTS='',
        TONECOMMAND_AI_SETTINGS=str(private/'ai-settings.json'),
        TONECOMMAND_STORE_SLOTS_FILE=str(private/'no-store.json'),
        TONECOMMAND_USER_CABS=str(private/'no-user-cabs.json'),
        TONECOMMAND_AXEFX3_STATE_DIR=str(private/'state'),
        TONECOMMAND_TONE3000_DIR=str(private/'no-tone3000'))
    ai_settings.apply_to_env()


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        raise SystemExit('Use Windows and 64-bit Python 3.12. No driver/firmware installation is performed.')
    try:
        verify_package()
    except (ValueError, OSError, KeyError):
        raise SystemExit('Package integrity could not be verified. Extract the named MK1 AI trial ZIP to a NEW folder; do not use the generic Source code download or an old checkout.') from None
    configure()
    serve_app(create_app())


def serve_app(app, *, no_browser=False):
    """One exclusive local listener; no reload or automatic second instance."""
    import uvicorn
    sock = socket.socket()
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(('127.0.0.1', 8909))
        sock.listen(64)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8909))
        def browser():
            while not server.started:
                time.sleep(.2)
            webbrowser.open('http://127.0.0.1:8909/')
        if not no_browser:
            threading.Thread(target=browser, daemon=True).start()
        server.run(sockets=[sock])
    finally:
        dev = app.state.trial['dev']
        if dev:
            dev.close()
        sock.close()


if __name__ == '__main__':
    main()

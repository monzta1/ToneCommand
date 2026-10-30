"""Local-only Tone3000 account/catalog and optional two-phase NAM installer.

Account/catalog actions have no hardware side effects. Only the separate
installer routes invoke the supplied, independently guarded hardware service.
"""
from __future__ import annotations

import html

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from . import tone3000 as t3

COOKIE = 'tc_tone3000_login'


class PrivateRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request):
            try:
                response = await original(request)
            except RequestValidationError:
                # Do not echo a mistaken password/token in Pydantic's input.
                response = JSONResponse({'error':'Invalid request fields. Use the TC form; do not supply passwords or tokens.'},status_code=422)
            response.headers['Cache-Control'] = 'no-store'
            return response

        return handle


def local_request(request: Request):
    """DNS-rebinding and browser-CSRF boundary for account and private library."""
    host = request.url.hostname
    if host not in ('127.0.0.1', 'localhost', '::1'):
        raise t3.ToneError('Tone3000 is available only from the local TC address.', 403)
    origin = request.headers.get('origin')
    expected = str(request.base_url).rstrip('/')
    if origin and origin != expected:
        raise t3.ToneError('Cross-site Tone3000 requests are not allowed.', 403)
    if request.headers.get('X-ToneCommand') != '1':
        raise t3.ToneError('Open Tone3000 from the TC interface.', 403)


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ConfigBody(Body):
    # Empty/short values get a useful setup message, not generic HTTP 422.
    client_id: str = Field(default='', max_length=200)


class AuthBody(Body):
    mode: str = 'signin'


class SelectBody(Body):
    tone_id: int = Field(gt=0)
    model_id: int | None = Field(default=None, gt=0)


class SuggestBody(Body):
    query: str = Field(min_length=1, max_length=200)
    prompt: str = Field(default='', max_length=4000)


class InstallPreviewBody(Body):
    model_id: StrictInt = Field(gt=0)
    expected_preset: StrictInt = Field(ge=0, le=1023)
    slot: StrictInt = Field(ge=1,le=256)


class InstallBody(Body):
    prepared_id: str = Field(min_length=20, max_length=100)
    external_audio_muted: StrictBool = False
    confirm_permanent_write: StrictBool = False
    confirm_overwrite: StrictBool = False


def router(recommend, installer=None):
    routes = APIRouter(prefix='/api/axefx3/tone3000', dependencies=[Depends(local_request)], route_class=PrivateRoute)

    @routes.get('/status')
    def status():
        result = t3.client.status()
        if installer:
            result.update(installer().capability())
        return result

    @routes.post('/install/prepare')
    def prepare_install(body: InstallPreviewBody):
        if not installer:
            raise t3.ToneError('Native NAM installer is not available.', 422)
        return installer().prepare(body.model_id, body.expected_preset, body.slot)

    @routes.get('/slots')
    def slots():
        if not installer:
            raise t3.ToneError('Native NAM inventory is not available.',422)
        return installer().inventory()

    @routes.post('/install')
    def install(body: InstallBody):
        if not installer:
            raise t3.ToneError('Native NAM installer is not available.', 422)
        return installer().commit(body.prepared_id, body.external_audio_muted,
                                  body.confirm_permanent_write, body.confirm_overwrite)

    @routes.post('/config')
    def configure(body: ConfigBody):
        return t3.client.configure(body.client_id)

    @routes.post('/auth/start')
    def start(body: AuthBody, request: Request):
        redirect = str(request.base_url).rstrip('/') + '/api/tone3000/callback'
        url, browser = t3.client.start(redirect, body.mode)
        response = JSONResponse({'url': url})
        response.set_cookie(COOKIE, browser, max_age=600, httponly=True, samesite='lax',
                            secure=request.url.scheme == 'https', path='/api/tone3000')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @routes.post('/disconnect')
    def disconnect():
        t3.client.disconnect()
        return {'ok': True, 'connected': False}

    @routes.get('/tones')
    def search(query: str = '', collection: str = 'search', page: int = 1, architecture: str = '2'):
        return t3.client.search(query, collection, page, architecture)

    @routes.get('/tones/{tone_id}')
    def detail(tone_id: int, architecture: str = '2'):
        return t3.client.tone(tone_id, architecture)

    @routes.post('/select')
    def select(body: SelectBody):
        return t3.client.select_tone(body.tone_id, body.model_id)

    @routes.post('/selection/clear')
    def clear_selection():
        t3.client.clear_selection()
        return {'ok': True}

    @routes.get('/download/{model_id}')
    def download(model_id: int):
        data, filename = t3.client.download(model_id)
        return Response(data, media_type='application/octet-stream', headers={
            'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff'})

    @routes.post('/suggest')
    def suggest(body: SuggestBody):
        candidates = t3.client.search(body.query)['data']
        if not candidates:
            return {'tone_id': 0, 'reason': 'No NAM candidates found. Try a broader amp or band name.'}
        choice = recommend(body.prompt or body.query, candidates)
        tone_id = choice.get('tone_id')
        if type(tone_id) is not int or tone_id not in {0, *(x['id'] for x in candidates)}:
            raise t3.ToneError('The AI did not select an available Tone3000 candidate.', 502)
        # Suggestion only: not persisted, downloaded, installed or applied.
        return {**choice, 'tone': next((x for x in candidates if x['id'] == tone_id), None)}

    return routes


def callback(request: Request):
    """No custom header on the external redirect; state AND HttpOnly cookie bind it."""
    if request.url.hostname not in ('127.0.0.1', 'localhost', '::1'):
        return Response(status_code=403)
    try:
        query = request.query_params
        raw_id = query.get('tone_id')
        tone_id = t3.client._id(raw_id) if raw_id else None
        t3.client.callback(query.get('state'), request.cookies.get(COOKIE), query.get('code'),
                           failed=bool(query.get('error')) or query.get('canceled') == 'true', tone_id=tone_id)
        message = 'Tone3000 connected. Return to your ToneCommand tab; you can close this window.'
        status = 200
    except t3.ToneError as exc:
        message, status = str(exc), exc.status
    except Exception:
        message, status = 'Tone3000 login could not be completed. Start again from TC.', 502
    response = HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8">'
                            '<title>ToneCommand / Tone3000</title><h1>ToneCommand / Tone3000</h1><p>'
                            + html.escape(message) + '</p></html>', status_code=status,
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                     'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"})
    response.delete_cookie(COOKIE, path='/api/tone3000')
    return response

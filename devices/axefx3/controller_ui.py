"""Scoped controller workspace inside TC; no generic FM9 executor on AFX3."""
import os
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, Field

from fm9.paths import resource_path
from .adapter import AxeFxIII
from .registry import Registry
from .controller_review import Reviews, inspect


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    effect_id: StrictInt
    source: StrictInt
    auto_engage: Literal['Off', 'Fast Pos'] | None = None


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    external_audio_muted: StrictBool
    target_confirmed: StrictBool


def register(app, host):
    reviews = Reviews()

    def selected():
        ctx = host.device_context()
        if ctx.kind != 'axefx3' or ctx.adapter is None:
            raise HTTPException(409, 'Connect the Axe-Fx III controller workspace first.')
        return ctx.adapter

    def editable():
        if host._gig_mode['on']:
            raise HTTPException(423, 'GIG LOCK is on. Nothing sent.')
        if host._plan_revisions:
            raise HTTPException(409, 'Discard or finish the pending tone plan first.')
        if host._audition['open']:
            raise HTTPException(409, 'End the cab audition before changing controller connections.')

    def hardware():
        if os.environ.get('TONECOMMAND_SIM') == '1':
            raise ValueError('No live Axe-Fx III connection in simulator mode.')
        return AxeFxIII()

    # Dependency seam for offline API/browser tests; never a public route.
    reviews.connect_device = hardware

    @app.middleware('http')
    async def limit_afx3_workspace(request, call_next):
        if request.method == 'POST' and request.url.path.startswith(('/api/controllers/', '/api/axefx3/', '/api/tone3000/')):
            origin = request.headers.get('origin')
            if origin and origin != f'{request.url.scheme}://{request.url.netloc}':
                return JSONResponse({'error': 'Cross-origin controller requests are not allowed.'}, status_code=403)
        if host.device_context().kind == 'axefx3':
            allowed = {'/controllers', '/controllers.js', '/axefx3', '/axefx3.js', '/axefx3.css', '/logo.png', '/api/device'}
            allowed.update({'/api/tone3000/login', '/api/tone3000/callback', '/api/tone3000/status',
                            '/api/tone3000/load', '/api/tone3000/logout'})
            if request.url.path == '/':
                return RedirectResponse('/axefx3')
            if request.url.path not in allowed and not request.url.path.startswith(('/api/controllers/', '/api/axefx3/', '/language/')):
                return JSONResponse({'error': 'Use the dedicated Axe-Fx III text/controller workspace; FM9 execution is blocked.',
                                     'controller_workspace': '/controllers'}, status_code=409)
        return await call_next(request)

    @app.get('/controllers')
    def page():
        return FileResponse(resource_path('ui', 'controllers.html'))

    @app.get('/controllers.js')
    def script():
        return FileResponse(resource_path('ui', 'controllers.js'), media_type='text/javascript')

    @app.get('/api/controllers/state')
    def state():
        with host._lock:
            if host.device_context().kind != 'axefx3':
                return dict(connected=False, controller_selected=False, gig_locked=host._gig_mode['on'])
            if host.device_context().adapter is None:
                return dict(connected=False, controller_selected=True, gig_locked=host._gig_mode['on'])
            try:
                return dict(connected=True, controller_selected=True, gig_locked=host._gig_mode['on'], **inspect(selected()))
            except (ValueError, RuntimeError, OSError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post('/api/controllers/connect')
    def connect():
        with host._lock:
            editable()
            if host.device_context().kind == 'axefx3' and host.device_context().adapter is not None:
                return dict(connected=True)
            if os.environ.get('TONECOMMAND_SIM') == '1' and reviews.connect_device is hardware:
                raise HTTPException(409, 'No live Axe-Fx III connection in simulator mode.')
            # Explicit handoff; no second device owner and no startup routing restore.
            previous = host.device_context()
            if previous.kind == 'fm9':
                host.drop_fm9()
            elif previous.adapter is not None:
                previous.adapter.close()
            host.select_device_context(host.DeviceContext('axefx3', Registry(), None, 'Axe-Fx III'))
            host._selected_kind['kind'] = 'axefx3'
            reviews.clear()
            try:
                dev = reviews.connect_device()
            except (ValueError, RuntimeError, OSError) as exc:
                raise HTTPException(503, f'Connection failed. Close Axe-Edit/other TC sessions first: {exc}') from exc
            host.select_device_context(host.DeviceContext('axefx3', dev.reg, dev, 'Axe-Fx III'))
            return dict(connected=True)

    @app.post('/api/controllers/disconnect')
    def disconnect():
        with host._lock:
            if host.device_context().kind != 'axefx3':
                return dict(connected=False)
            editable()
            dev = host.device_context().adapter
            if dev is not None:
                dev.close()
            reviews.clear()
            host.select_device_context(host._default_context)
            host._selected_kind['kind'] = None
            return dict(connected=False)

    @app.post('/api/controllers/review')
    def review(body: Selection):
        with host._lock:
            editable()
            try:
                return reviews.prepare(selected(), body.model_dump())
            except (ValueError, RuntimeError, OSError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post('/api/controllers/discard')
    def discard():
        with host._lock:
            reviews.clear()
            return dict(ok=True)

    @app.post('/api/controllers/send')
    def send(body: Confirmation):
        with host._lock:
            editable()
            try:
                return reviews.send(selected(), **body.model_dump())
            except (ValueError, RuntimeError, OSError) as exc:
                raise HTTPException(409, str(exc)) from exc

    return reviews

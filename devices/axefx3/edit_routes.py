"""Opt-in one-edit host wiring, separate from the generic FM9 executor.

Default connections stay read-only. Only an explicitly selected AmpWriter
on the existing III connection can enter the reviewed bridge. No AI, model,
grid, Store, retry, rollback or automatic SEND.
"""
import os

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from fm9.device import ReadOnly
from fm9.paths import resource_path
from .amp_writer import AmpWriter, AmpReadbackError
from .beta5_amp_writer import Beta5AmpWriter
from .edit_workflow import EditWorkflow


def enabled():
    return configured_writer() is not None


def configured_writer():
    legacy = os.environ.get('TONECOMMAND_AXEFX3_REVIEWED_AMP') == '1'
    beta5 = os.environ.get('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5') == '1'
    if legacy == beta5:  # Neither, or conflicting explicit selections: no writer.
        return None
    return Beta5AmpWriter if beta5 else AmpWriter


def connect(chassis):
    """One constructor, no fallback or second MIDI connection."""
    if (os.environ.get('TONECOMMAND_AXEFX3_REVIEWED_AMP') == '1'
            and os.environ.get('TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5') == '1'):
        raise ReadOnly('Select only one explicitly measured Amp experiment')
    if not enabled():
        from .readonly_adapter import AxeFxIII
        return AxeFxIII(chassis=chassis)
    if chassis != 'mk2':
        raise ReadOnly('The reviewed Amp experiment requires declared MK2 hardware')
    if os.environ.get('TONECOMMAND_SIM') == '1':
        raise ReadOnly('The opt-in writer cannot open physical MIDI in simulator mode')
    return configured_writer()(chassis=chassis)


class Preparation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    actions: list[dict] = Field(min_length=1, max_length=1)
    expected_preset: StrictInt = Field(ge=0, le=1023)
    expected_scene: StrictInt = Field(ge=1, le=8)
    whole_rig: StrictBool = False


class Transition(Preparation):
    token: StrictStr = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    plan_digest: StrictStr = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')


class Confirmation(Transition):
    target_confirmed: StrictBool
    external_audio_muted: StrictBool


def register(app, host):
    def selected():
        ctx = host.device_context()
        dev = ctx.adapter
        return dev if (enabled() and ctx.kind == 'axefx3'
                       and type(dev) is configured_writer()) else None

    flow = EditWorkflow(selected=selected, host_lock=host._lock,
                        gig_locked=lambda: host._gig_mode['on'], fingerprint=host.plan_digest)

    def refused(message, status=409, uncertain=False):
        return JSONResponse(dict(error=str(message), stored=False, undo_available=False,
            uncertain=uncertain, retry_allowed=False), status_code=status)

    def origin_ok(request):
        origin = request.headers.get('origin')
        if origin is None:
            return True  # Explicit local tools, not a browser cross-origin grant.
        return (request.url.hostname in ('127.0.0.1','localhost','::1')
                and request.url.scheme in ('http','https')
                and origin == f'{request.url.scheme}://{request.url.netloc}')

    def call(request, method, **payload):
        if not origin_ok(request):
            return refused('Cross-origin reviewed-edit requests are not allowed', 403)
        if selected() is None:
            flow.discard()
            return refused('This connection has no explicitly enabled reviewed Amp writer')
        try:
            return getattr(flow, method)(**payload)
        except AmpReadbackError as exc:
            return refused('A write may have happened. Keep external audio muted; no retry or Undo. '+str(exc), uncertain=True)
        except ReadOnly as exc:
            return refused(exc)
        except (TypeError, ValueError) as exc:
            return refused(exc, 400)
        except OSError:
            return refused('Device inspection failed. Keep external audio muted and inspect before continuing.', 503)

    @app.get('/axefx3-reviewed-edit.js')
    def script():
        return FileResponse(resource_path('ui', 'axefx3-reviewed-edit.js'), media_type='text/javascript')

    @app.get('/api/axefx3/edit/state')
    def state():
        with host._lock:
            dev = selected()
            if dev is None:
                return dict(configured=False, available=False)
            try:
                dev._identity()  # Exact measured identity, never just a version label.
                preset, scene, blocks = dev.current_preset(), dev.current_scene(), dev.status_dump()
                if not preset or not scene or blocks is None:
                    raise ReadOnly('Current target is unreadable')
                amps = [b for b in blocks if b.effect_id == 58]
                if len(amps) != 1 or amps[0].channel != 0 or amps[0].channels_supported != 4:
                    raise ReadOnly('An existing four-channel Amp 1 on channel A is required')
                if type(dev) is Beta5AmpWriter:
                    words = dev._bulk(58)
                    if words is None or words[0] != 0:
                        raise ReadOnly('This Beta5 experiment requires existing 59 Bassguy Bright on Amp 1/A')
                values = {'DISTORT_DRIVE':dev._display(1), 'DISTORT_MID':dev._display(3)}
                if any(type(v) not in (int,float) or not 0 <= v <= 10 for v in values.values()):
                    raise ReadOnly('Independent Gain and Mid displays must be readable')
                return dict(configured=True, available=not host._gig_mode['on'],
                    preset=preset[0], scene=scene, values=values, gig_locked=host._gig_mode['on'], stored=False)
            except (ReadOnly, ValueError, OSError) as exc:
                return dict(configured=True, available=False, reason=str(exc))

    @app.post('/api/axefx3/edit/prepare')
    def prepare(body: Preparation, request: Request):
        # This is manual bounded editing, not permission to enter the III AI
        # planner or to bypass a pending plan for another device.
        if host._plan_revisions:
            flow.discard()
            return refused('Finish or discard the pending plan before preparing an experimental edit')
        result = call(request, 'prepare', **body.model_dump())
        if isinstance(result, JSONResponse):
            return result
        result['afx3_edit'] = True
        result['summary'] = 'One reviewed Amp 1/A edit. Other scenes sharing A may change. No Store or automatic Undo.'
        result['device'] = dict(preset=dict(number=result['expected_preset'], name=''),
                                scene=dict(number=result['expected_scene']))
        result['values'] = {result['actions'][0]['param']:result['change']['before']}
        return result

    @app.post('/api/axefx3/edit/review')
    def review(body: Transition, request: Request):
        return call(request, 'review', **body.model_dump())

    @app.post('/api/axefx3/edit/confirm')
    def confirm(body: Confirmation, request: Request):
        return call(request, 'confirm', **body.model_dump())

    @app.post('/api/axefx3/edit/send')
    def send(body: Confirmation, request: Request):
        return call(request, 'send', **body.model_dump())

    @app.post('/api/axefx3/edit/discard')
    def discard(request: Request):
        if not origin_ok(request):
            return refused('Cross-origin reviewed-edit requests are not allowed', 403)
        return flow.discard()  # Invalidation only, even after disconnect.

    return flow

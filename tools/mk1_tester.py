"""Opt-in MK1 evaluation harness around the unchanged TC application.

Only explicit Gen-3 read queries reach its output port. This is not an MK1
write release, an installer for NAM, or permission to copy MK2 memory frames.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time
from typing import Literal
import urllib.request
import webbrowser
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from devices.axefx3.adapter import AxeFxIII
from devices.axefx3 import grid, profile, protocol, runtime
from fm9 import midi_transport, protocol as shared

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.5.16-fx3.3-mk1-test.2'
NOTICE = ('MK1 evaluation: READ ONLY. Preset/scene selection, SEND, Store, '
          'controller assignment, IR upload and NAM installation are blocked. '
          'Select sounds manually with external monitoring muted. Use /mk1-test for the English checklist.')


def utc():
    return datetime.now(timezone.utc).isoformat()


def read_query(frame):
    """Exact request shapes only. Never allow parameter0, memory or GET-as-SET."""
    if (not isinstance(frame, (list, tuple)) or len(frame) < 8
            or frame[0] != 0xf0 or frame[-1] != 0xf7
            or not protocol.valid_reply(list(frame[1:-1]))):
        return False
    fn, payload = frame[5], list(frame[6:-2])
    if fn in (8, 0x13):
        return payload == []
    if fn == 0x0d:
        return (len(payload) == 2 and
                (payload == [127, 127] or shared.decode14(*payload) < 512))
    if fn == 0x0c:
        return payload == [127]
    if fn == 0x0e:
        return len(payload) == 1 and payload[0] in (*range(8), 127)
    if fn in (0x0a, 0x0b):
        return len(payload) == 3 and payload[2] == 127
    # Grid read only. No bulk parameter, modifier, NAM-name or memory query.
    return list(frame) == grid.reframe(shared.build_request_grid_layout())


class ReadOnlyOutput:
    def __init__(self, port):
        self.port = port
        self.queries = Counter()
        self.rejected = 0

    def send(self, message):
        frame = [0xf0, *message.data, 0xf7] if message.type == 'sysex' else []
        if not read_query(frame):
            self.rejected += 1
            raise PermissionError('MK1 tester refused a non-read MIDI message; nothing sent.')
        self.queries[f'{frame[5]:02x}'] += 1
        self.port.send(message)

    def close(self):
        self.port.close()


class ReadOnlyAxeFxIII(AxeFxIII):
    def __init__(self, ports=None):
        inp, outp = ports if ports is not None else midi_transport.open_ports('axe-fx')
        self.firmware_reply_sha256 = None
        super().__init__((inp, ReadOnlyOutput(outp)))
        profile.apply(self.reg, 'mk1')

    def _pending(self):
        for data in super()._pending():
            if data[4] == 8:
                self.firmware_reply_sha256 = hashlib.sha256(bytes(data)).hexdigest()
            yield data

    def capabilities(self):
        return replace(super().capabilities(), verifies_writes=False, can_rename=False)

    def _check_edit_target(self):
        raise PermissionError('MK1 tester is read-only; no edit session is permitted.')


def configure_environment(root=ROOT):
    """Use new local state, never an owner's inherited credentials or slots."""
    root = Path(root).resolve()
    local = root / 'test-results' / 'private'
    local.mkdir(parents=True, exist_ok=True)
    for name in list(os.environ):
        if (name.startswith(('PLANNER_', 'TONECOMMAND_')) or name in
                ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'XAI_API_KEY', 'GROK_API_KEY',
                 'CLAUDE_CLI_MODEL', 'CLAUDE_API_MODEL', 'CODEX_CLI_MODEL')):
            os.environ.pop(name, None)
    os.environ.update(TONECOMMAND_SIM='0', PYTHONUTF8='1',
        TONECOMMAND_STORE_SLOTS='', TONECOMMAND_CAB_SLOTS='', TONECOMMAND_NAM_SLOTS='',
        TONECOMMAND_AI_SETTINGS=str(local / 'empty-ai.json'),
        TONECOMMAND_STORE_SLOTS_FILE=str(local / 'empty-store.json'),
        TONECOMMAND_USER_CABS=str(local / 'empty-cabs.json'),
        TONECOMMAND_AXEFX3_STATE_DIR=str(local / 'fx3-state'),
        TONECOMMAND_TONE3000_DIR=str(local / 'empty-tone3000'),
        TONECOMMAND_CACHE_DIR=str(local / 'cache'))


def provenance(root=ROOT):
    manifest = Path(root) / 'MK1-PACKAGE.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        return dict(version=VERSION, source_commit=data['source_commit'],
                    archive_build=data['version'])
    return dict(version=VERSION, source_commit='development-checkout', archive_build=None)


def dependency_versions():
    result = {}
    for name in ('tonecommand', 'fastapi', 'pydantic', 'mido', 'python-rtmidi'):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = 'not-installed'
    return result


def snapshot(dev):
    """Read names/status/grid without changing selection or querying selectors."""
    with dev._lock:
        before, scene = dev.current_preset(), dev.current_scene()
        firmware = dev.firmware_label()
        blocks, cells = dev.status_dump(), dev.read_grid()
        names = [dev.scene_name(i) for i in range(1, 9)]
        after, end_scene = dev.current_preset(), dev.current_scene()
        end_blocks = dev.status_dump()
    coherent = (before is not None and before == after and scene is not None
                and scene == end_scene and blocks is not None and blocks == end_blocks)
    errors = [key for key, value in [('preset', before), ('scene', scene),
              ('blocks', blocks), ('grid', cells)] if value is None]
    if any(n is None for n in names):
        errors.append('scene_names')
    return dict(timestamp_utc=utc(), firmware=firmware,
        firmware_reply_sha256=getattr(dev, 'firmware_reply_sha256', None),
        preset=before[0] if before else None, name=before[1] if before else '',
        scene=scene, scene_names=names, coherent=coherent, read_errors=errors,
        blocks=[asdict(b) for b in blocks or []],
        grid=[asdict(c) for c in cells or []], hardware_written=False)


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    consent: StrictBool = False
    label: str = Field(default='baseline', pattern=r'^[A-Za-z0-9 _.-]{1,60}$')
    firmware_on_screen: str = Field(default='', pattern=r'^[A-Za-z0-9 ._()+-]{0,100}$')
    axe_edit_version: str = Field(default='', pattern=r'^[A-Za-z0-9 ._()+-]{0,60}$')


class Chassis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    variant: Literal['mk1']


def summary(state, label, firmware_on_screen='', axe_edit_version=''):
    """No names, paths, raw SysEx, presets, accounts or model weights exported."""
    return dict(label=label, timestamp_utc=state['timestamp_utc'],
        firmware=state['firmware'], firmware_on_screen=firmware_on_screen,
        axe_edit_version=axe_edit_version,
        firmware_reply_sha256=state.get('firmware_reply_sha256'),
        preset_number=state['preset'], scene=state['scene'],
        coherent=state['coherent'], read_errors=state['read_errors'],
        complete=state['coherent'] and not state['read_errors'],
        block_count=len(state['blocks']), grid_cell_count=len(state['grid']),
        scene_names_read=sum(n is not None for n in state['scene_names']))


def create_app(host=None, factory=ReadOnlyAxeFxIII):
    if host is None:
        import server as host
    app = FastAPI(title='Unofficial FX3 MK1 read-only evaluation')
    app.state.observations = []
    app.state.completed_queries = Counter()
    app.state.completed_rejections = 0
    app.state.host = host
    host.select_device_context(host.DeviceContext('axefx3', None, None, 'Axe-Fx III MK1 tester'))
    workspace = runtime.identity()

    @app.middleware('http')
    async def boundary(request, call_next):
        path = request.url.path
        safe_posts = {'/api/controllers/connect', '/api/controllers/disconnect',
                      '/api/axefx3/profile', '/api/mk1-test/observe'}
        if request.method not in ('GET', 'HEAD', 'POST') or (
                request.method == 'POST' and path not in safe_posts):
            return JSONResponse({'error': NOTICE, 'hardware_written': False}, status_code=423)
        if request.method == 'POST':
            origin = request.headers.get('origin')
            if (request.headers.get('x-tonecommand') != '1' or
                    (origin and origin != f'{request.url.scheme}://{request.url.netloc}')):
                return JSONResponse({'error': 'Use the local MK1 tester interface.'}, status_code=403)
        if path.startswith('/api/') and path not in safe_posts | {
                '/api/axefx3/state', '/api/mk1-test/status', '/api/mk1-test/report'}:
            return JSONResponse({'error': 'This endpoint is outside the MK1 read-only evaluation.'}, status_code=423)
        return await call_next(request)

    def selected():
        ctx = host.device_context()
        if ctx.kind != 'axefx3' or ctx.adapter is None:
            raise HTTPException(409, 'Connect the MK1 first; close Axe-Edit before connecting.')
        return ctx.adapter

    @app.get('/mk1-test')
    def welcome():
        return FileResponse(ROOT / 'packaging/mk1/welcome.html')

    @app.get('/')
    def index():
        return RedirectResponse('/mk1-test')

    @app.get('/mk1-guide')
    def guide():
        return FileResponse(ROOT / 'docs/MK1-TESTER-GUIDE.md', media_type='text/plain')

    @app.get('/api/mk1-test/status')
    def status():
        with host._lock:
            dev = host.device_context().adapter
            return dict(**provenance(), declared_chassis='mk1', read_only=True,
                connected=dev is not None, notice=NOTICE,
                python='.'.join(map(str, sys.version_info[:3])), windows=sys.platform == 'win32',
                python_bits=struct.calcsize('P') * 8, dependencies=dependency_versions(),
                native_mk1_acceptance=False)

    @app.post('/api/controllers/connect')
    def connect():
        with host._lock:
            if host.device_context().adapter is None:
                try:
                    dev = factory()
                except (ValueError, RuntimeError, OSError):
                    raise HTTPException(503, 'MK1 connection failed. Close Axe-Edit and other MIDI owners, check USB/driver, then reconnect manually.') from None
                host.select_device_context(host.DeviceContext('axefx3', dev.reg, dev, 'Axe-Fx III MK1 tester'))
            return dict(connected=True, read_only=True, hardware_written=False)

    @app.post('/api/controllers/disconnect')
    def disconnect():
        with host._lock:
            dev = host.device_context().adapter
            if dev is not None:
                output = getattr(dev, 'outp', None)
                app.state.completed_queries.update(getattr(output, 'queries', {}))
                app.state.completed_rejections += getattr(output, 'rejected', 0)
                dev.close()
            host.select_device_context(host.DeviceContext('axefx3', None, None, 'Axe-Fx III MK1 tester'))
            return dict(connected=False, read_only=True, hardware_written=False)

    @app.post('/api/axefx3/profile')
    def fixed_profile(body: Chassis):
        return dict(profile=dict(variant='mk1', write_supported=False, nam_writes=False,
                                 warning=NOTICE), hardware_written=False)

    @app.get('/api/axefx3/state')
    def state():
        with host._lock:
            dev = host.device_context().adapter
            base = dict(workspace=workspace, profile=dict(variant='mk1', write_supported=False,
                nam_writes=False, user2_cabs=False, warning=NOTICE), route_problem=NOTICE,
                navigation_supported=False, amp_refresh_supported=False, cab_count=0,
                connected=dev is not None, read_only=True)
            if dev is None:
                return base
            try:
                observed = snapshot(dev)
            except (ValueError, RuntimeError, OSError):
                raise HTTPException(409, 'A read could not be validated. No write or automatic recovery was attempted.') from None
            base.update({key: observed[key] for key in ('firmware', 'preset', 'name', 'scene', 'scene_names')})
            base['profile']['user2_cabs'] = observed['firmware'] == '32.06'
            base['mk1_observation'] = summary(observed, 'interface-refresh')
            return base

    @app.post('/api/mk1-test/observe')
    def observe(body: Observation):
        if body.consent is not True:
            raise HTTPException(400, 'Confirm read-only observation and muted external monitoring.')
        with host._lock:
            if len(app.state.observations) >= 50:
                raise HTTPException(409, 'Export the current report before starting another session.')
            try:
                observed = snapshot(selected())
            except (ValueError, RuntimeError, OSError):
                raise HTTPException(409, 'Observation failed. No write or automatic recovery was attempted.') from None
            record = summary(observed, body.label, body.firmware_on_screen, body.axe_edit_version)
            app.state.observations.append(record)
            return dict(observation=record, local_view=observed)

    @app.get('/api/mk1-test/report')
    def report():
        with host._lock:
            dev = host.device_context().adapter
            output = getattr(dev, 'outp', None)
            return dict(**provenance(), schema=1, timestamp_utc=utc(),
                declared_chassis='mk1', independently_verified_chassis=False,
                read_only=True, hardware_written=False, mk1_write_release=False,
                python='.'.join(map(str, sys.version_info[:3])), platform=sys.platform,
                dependencies=dependency_versions(),
                observations=app.state.observations,
                queries=dict(app.state.completed_queries + Counter(getattr(output, 'queries', {}))),
                rejected_messages=app.state.completed_rejections + getattr(output, 'rejected', 0),
                note='Review before sharing. No names, raw SysEx, credentials, screenshots or model payloads are included.')

    app.mount('/', host.app)
    return app


def request_local(path, payload=None):
    url = 'http://127.0.0.1:8909' + path
    request = urllib.request.Request(url, headers={'X-ToneCommand': '1'},
        data=json.dumps(payload).encode('utf-8') if payload is not None else None)
    if payload is not None:
        request.add_header('Content-Type', 'application/json')
    # Do not route local reports through a proxy from the caller's environment.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=30) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--no-browser', action='store_true')
    observation = commands.add_parser('observe')
    observation.add_argument('--label', default='baseline')
    observation.add_argument('--consent-read-only', action='store_true')
    commands.add_parser('export')
    args = parser.parse_args(argv)
    if args.command == 'serve':
        if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
            parser.error('The MK1 evaluation package requires Windows and 64-bit Python 3.12.')
        configure_environment()
        import uvicorn
        app = create_app()
        sock = socket.socket()
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', 8909))
            sock.listen(64)
        except OSError:
            sock.close()
            parser.error('Port8909 is occupied. Close the other TC normally. No second instance was started.')
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8909))
        if not args.no_browser:
            def browser():
                for _ in range(100):
                    if server.started:
                        webbrowser.open('http://127.0.0.1:8909/mk1-test')
                        return
                    time.sleep(.2)
            threading.Thread(target=browser, daemon=True).start()
        print(NOTICE, flush=True)
        try:
            server.run(sockets=[sock])
        finally:
            dev = app.state.host.device_context().adapter
            if dev is not None:
                dev.close()
            sock.close()
        return 0
    status = request_local('/api/mk1-test/status')
    if status.get('version') != VERSION or status.get('read_only') is not True:
        parser.error('This is not the matching read-only MK1 tester. Nothing exported.')
    if args.command == 'observe':
        if not args.consent_read_only:
            parser.error('--consent-read-only is required after muting external monitoring')
        observed = request_local('/api/mk1-test/observe', dict(consent=True, label=args.label))
        print(json.dumps(observed['observation'], indent=2))
        return 0
    report = request_local('/api/mk1-test/report')
    destination = ROOT / 'test-results' / 'share'
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = destination / f'MK1-report-{stamp}.zip'
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('report.json', json.dumps(report, indent=2))
    print(f'Review locally before sharing: {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Reviewed exact row1 construction, not an arbitrary grid encoder.

Only the independently captured14-cell sequence is used. Failed sessions are
consumed; no deletion, insertion into existing chains or partial-state retry.
"""
from contextlib import contextmanager
import time

from fm9.device import SetResult
from fm9 import protocol as shared
from . import fw33_profile, row_fixture, grid, modifiers, route_guard, protocol

ROUTE = tuple(e for e, _ in row_fixture.BLOCKS)
RESERVE = frozenset({94,118,46,122,114,82,50,55})


def supported(reg):
    return reg.firmware == fw33_profile.KEY and getattr(reg,'hardware_variant',None) == 'mk2'


def expected_grid():
    return {p:v for p,v in row_fixture.expected_grid().items() if p[0] == 1}


def state(dev):
    from . import tone_review
    return tone_review.snapshot(dev, include_nam=False)


def verify_base(now, before, added=()):
    for key in ('preset','scene','firmware','variant','modifiers','scene_names','cabs'):
        if now[key] != before[key]:
            raise ValueError('State changed outside reviewed construction: '+key)
    old = {b.effect_id:b for b in before['blocks']}
    new = {b.effect_id:b for b in now['blocks']}
    if set(new) != set(old) | set(added) or any(new[e] != b for e,b in old.items()):
        raise ValueError('Another block status changed during construction')
    if set(now['bulk']) != set(before['bulk']) | set(added):
        raise ValueError('Incomplete block inventory after construction')
    if any(now['bulk'][e] != words for e,words in before['bulk'].items()):
        raise ValueError('Existing block parameters changed during construction')
    for eid in added:
        if new[eid].channel != 0 or new[eid].channels_supported != 4:
            raise ValueError('Created block is not on the measured four-channel A layout')


def prepare(dev, resolved, expected, actual):
    if not supported(dev.reg) or tuple(expected) != ROUTE or (actual and tuple(actual) != ROUTE):
        raise ValueError('Only the exact measured row1 serial route is supported')
    if dev.current_scene() != 1:
        raise ValueError('Serial construction/voicing requires current scene1; no automatic scene switch')
    cells = grid.snapshot(dev.read_grid())
    if cells and cells != expected_grid():
        raise ValueError('Existing serial chain positions/cables differ from the measured row1 layout')
    status = dev.status_dump()
    if status is None or any(b.channel != 0 or b.channels_supported != 4 for b in status if b.effect_id in ROUTE):
        raise ValueError('All existing serial blocks must already use measured channel A')
    entries = modifiers.inspect(dev)
    if len(entries) != 32 or any(len(e['words']) != 25 or e['active'] for e in entries):
        raise ValueError('All32 complete inactive modifiers required; no controller is cleared')
    additions = [i.effect_id for i in resolved if i.action['kind'] == 'add_block']
    if actual and additions:
        raise ValueError('Existing serial chain is reused without ADD actions')
    if not actual and (len(additions) != 12 or set(additions) != set(ROUTE)-{37,42}):
        raise ValueError('Empty serial foundation requires all12 explicit effect additions')
    if not resolved or resolved[0].spec is None or resolved[0].spec.name != 'OUTPUT_LEVEL' or resolved[0].value != -18:
        raise ValueError('Serial plan must first stage Output1 at-18dB')
    final = {}
    bypass = {}
    for item in resolved:
        kind = item.action['kind']
        if kind not in {'add_block','set_param','set_bypass','rename_preset','rename_scene'}:
            raise ValueError('No serial models, selectors, controllers, scene or channel transitions')
        if item.effect_id is not None and item.effect_id not in ROUTE:
            raise ValueError('Action outside measured serial chain')
        if kind == 'rename_scene' and item.value != 1:
            raise ValueError('Serial voicing changes scene1 only')
        if kind == 'set_bypass':
            if item.effect_id in RESERVE and item.value is not True:
                raise ValueError('Unvoiced reserve effects must remain bypassed')
            bypass[item.effect_id] = item.value
        if kind == 'set_param':
            if item.spec.family not in {'DISTORT','OUTPUT','DELAY','CHORUS'}:
                raise ValueError('Only measured Amp/Output/Delay/Chorus numeric controls')
            final[item.spec.name] = item.value
            if actual:
                from . import fw33
                error = fw33.domain_error(dev,item.spec,0)
                if error: raise ValueError(error)
                if item.spec.tempo_param_id is not None:
                    require_tempo(dev,item.spec)
    if final.get('OUTPUT_LEVEL') != -18 or final.get('DISTORT_LEVEL',1) > -12:
        raise ValueError('Explicit quiet Amp and Output final levels are required')
    if any(bypass.get(e) is not True for e in RESERVE):
        raise ValueError('All reserve effects must explicitly remain bypassed')
    for family in ('DELAY','CHORUS'):
        if family+'_LEVEL' not in final:
            raise ValueError('Explicit final effect levels are required')
    return resolved,expected,actual


def require_tempo(dev,spec):
    stride = fw33_profile.STRIDES[spec.family]
    words = dev.bulk_read(spec.effect_id)
    if (not isinstance(words,list) or len(words) != 4*stride
            or words[spec.tempo_param_id] != 0
            or str(dev.read_display_text(spec.effect_id,spec.tempo_param_id)).strip().upper() != 'NONE'):
        raise ValueError('Serial timing requires independently verified Tempo NONE; no tempo write')


class Session:
    def __init__(self,dev):
        dev._check_edit_target()
        if not supported(dev.reg) or getattr(dev,'_serial_session',None) is not None:
            raise PermissionError('Exact FW33/MK2 and one confirmed serial session required')
        self.dev,self.target,self.failed,self.index = dev,dev._edit_target,False,0
        self.frame = None
        dev._serial_session = self

    def write(self,frame,before,after):
        if self.failed or self.index >= 41: raise PermissionError('Serial session consumed or complete; never retry')
        self.failed = True
        self.dev._check_edit_target()
        if grid.snapshot(self.dev.read_grid()) != before:
            raise PermissionError('Fresh grid differs before serial write')
        reference = row_fixture.steps()[self.index]
        if (tuple(frame) != tuple(reference[0]) or before != reference[1] or after != reference[2]):
            raise PermissionError('Only exact ordered captured row1 frames')
        self.frame = tuple(frame)
        try:
            self.dev._write(frame)
        finally:
            self.frame = None
        for _ in range(5):
            time.sleep(.2)
            if grid.snapshot(self.dev.read_grid()) == after:
                self.index += 1
                self.failed = False
                return
        raise ValueError('Serial write did not verify; no retry or rollback')


def allowed(dev,frame):
    session = getattr(dev,'_serial_session',None)
    if (not isinstance(session,Session) or session.dev is not dev or not supported(dev.reg)
            or session.target != getattr(dev,'_edit_target',None)):
        return False
    return (session.failed and session.frame == tuple(frame) and session.index < 41
            and tuple(frame) == tuple(row_fixture.steps()[session.index][0]))


def bypass_allowed(dev,frame):
    session = getattr(dev,'_serial_session',None)
    return (isinstance(session,Session) and session.dev is dev and not session.failed
            and supported(dev.reg) and session.target == getattr(dev,'_edit_target',None)
            and getattr(dev,'_serial_bypass_permit',None) == tuple(frame)
            and frame[5] == 0x0a and len(frame[6:-2]) == 3
            and shared.decode14(*frame[6:8]) in ROUTE and frame[8] in (0,1)
            and (shared.decode14(*frame[6:8]) not in RESERVE or frame[8] == 1))


@contextmanager
def execution(dev,expected):
    if not supported(dev.reg) or tuple(expected) != ROUTE:
        yield
        return
    session = Session(dev)
    try:
        yield session
    finally:
        session.failed = True
        session.frame = None
        dev._serial_session = None
        dev._serial_bypass_permit = None


def bypass(dev,eid,value):
    frame = protocol.envelope(0x0a,[*shared.encode14(eid),int(value)])
    dev._serial_bypass_permit = tuple(frame)
    try:
        return dev.set_bypass(eid,value)
    finally:
        dev._serial_bypass_permit = None


def stage(dev,family,name):
    before = state(dev)
    spec = dev.reg.find_param(family,name)
    result = dev.set_param_display(spec,-18)
    if not result.ok: raise ValueError(result.detail)
    if dev.get_param_display(spec) != -18:
        raise ValueError('Quiet staging display no longer matches')
    after = state(dev)
    held = dict(before)
    held['bulk'] = dict(before['bulk'])
    words = list(before['bulk'][spec.effect_id])
    words[spec.param_id] = after['bulk'][spec.effect_id][spec.param_id]
    held['bulk'][spec.effect_id] = words
    verify_base(after,held)
    if grid.snapshot(after['grid']) != grid.snapshot(before['grid']):
        raise ValueError('Grid changed during quiet staging')


def build(dev,required_route,actions):
    session = getattr(dev,'_serial_session',None)
    if not isinstance(session,Session) or grid.snapshot(dev.read_grid()):
        raise PermissionError('Serial foundation requires a reviewed session and empty grid')
    album=any(a.get('kind')=='set_type' for a in actions)
    if album:
        from . import album_build
        album_build.validate_actions(dev.reg,actions,False)
    baseline = state(dev)
    for frame,before,after in row_fixture.steps()[:41]:
        prior = state(dev)
        session.write(frame,before,after)
        now = state(dev)
        added = set(now['bulk'])-set(prior['bulk'])
        expected_added = {v[0] for p,v in after.items() if p not in before}
        if added != expected_added:
            raise ValueError('Unexpected new block after placement')
        verify_base(now,prior,added)
        if session.index == 28:
            stage(dev,'OUTPUT','OUTPUT_LEVEL')
            stage(dev,'DISTORT','DISTORT_LEVEL')
            from . import executor,fw33
            for action in actions:
                item = executor.resolve(dev.reg,action)
                if item.spec is not None:
                    error = (construction_domain_error(dev,item.spec) if album and
                        item.family in ('CABINET','FUZZ','COMP','GEQ') else fw33.domain_error(dev,item.spec,0))
                    if error: raise ValueError(error)
                    if item.spec.tempo_param_id is not None: require_tempo(dev,item.spec)
    route_guard.check_route(dev,dev.reg,required_route,complete=True)
    if any(now[k] != baseline[k] for k in ('modifiers','scene_names','preset')):
        raise ValueError('Baseline changed during serial construction')
    return SetResult(True,'Measured14-block serial chain independently verified; no Store',[],list(ROUTE))


def construction_domain_error(dev,spec):
    """Read-only layout check before future reviewed model/mixer writes.

    Does not authorize a frame, create an album session or waive runtime
    model/channel/parameter checks. No model or mixer is written here.
    """
    session=getattr(dev,'_serial_session',None)
    if (not isinstance(session,Session) or session.dev is not dev or session.failed
            or session.index!=28 or session.target!=getattr(dev,'_edit_target',None)
            or not supported(dev.reg) or grid.snapshot(dev.read_grid())!=row_fixture.steps()[27][2]
            or dev.get_channel(spec.effect_id)!=0):
        return 'Read-only construction check requires the exact placed/disconnected foundation on A'
    eid={'CABINET':62,'FUZZ':118,'COMP':46,'GEQ':50}.get(spec.family)
    if eid is None or eid!=spec.effect_id or spec.instance!=1:
        return 'Unmeasured future construction parameter'
    words=dev.bulk_read(eid)
    dev.status_dump()
    if (dev._channels.get(eid)!=4 or not isinstance(words,list)
            or len(words)!=4*fw33_profile.STRIDES[spec.family]):
        return 'Complete four-channel future-control layout required'
    if spec.family=='CABINET':
        from .album_build import cab_layout
        try:cab_layout(words,expanded=True)
        except ValueError as exc:return str(exc)
    return None

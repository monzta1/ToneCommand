"""Reviewed minimal Beta5 construction, separate from legacy write approval.

One scene, channel A, exact four-node route. A failed/uncertain execution is
consumed and locks this connection until reconnect. No write retries, clearing,
rollback, Store, resource-memory writes or physical audio guarantees.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import secrets
import time
import weakref

import mido
from fm9.safety import sysex_guard
from . import protocol, firmware_identity, profile
from . import beta5_core_plan as plans
from .beta5_core_codec import NODES, STRIDES, grid, operations

# This opt-in is not a firmware override. Exact identity, layout and every
# operation remain independently checked, including during native acceptance.
def supported(dev):
    import os
    return (os.environ.get('TONECOMMAND_BETA5_CORE') == '1'
            and dev.reg.firmware == firmware_identity.BETA5_KEY
            and getattr(dev.reg, 'hardware_variant', None) in ('mk1','mk2'))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False,
                                     separators=(',',':')).encode()).hexdigest()


def snapshot(dev):
    if not supported(dev):raise ValueError('The bounded Beta5 core experiment is not enabled')
    ident=dev._request(protocol.envelope(8,[]),lambda x:x if x[4]==8 else None)
    if not ident or firmware_identity.identify(ident)!=firmware_identity.BETA5_KEY:
        raise ValueError('Full firmware identity differs; no write profile inferred')
    preset,scene=dev.current_preset(),dev.current_scene()
    if not preset or scene!=1:raise ValueError('Select the intended preset and scene1 first')
    profile.validate_preset(dev.reg,preset[0])
    status,cells=dev.status_dump(),dev.read_grid()
    if status is None or cells is None:raise ValueError('Status or grid read is incomplete')
    ids={b.effect_id for b in status}
    if len(ids)!=len(status) or not {200,201}<=ids or not ids<=set(NODES)|{200,201}:
        raise ValueError('Only the minimal four-node core or an empty grid is admitted')
    bulk={str(b.effect_id):dev.bulk_read(b.effect_id) for b in status}
    sizes={**{str(e):4*s for e,s in STRIDES.items()},'200':1525,'201':350}
    if any(type(v) is not list or len(v)!=sizes[k] or any(type(w) is not int or not 0<=w<=65535 for w in v) for k,v in bulk.items()):
        raise ValueError('The complete measured block layout is required')
    if any(b.channel not in range(4) or b.channels_supported!=(1 if b.effect_id in (200,201) else 4) for b in status):
        raise ValueError('Block channel layout differs')
    mods=[dev.read_modifier(n) for n in range(1,33)]
    if any(type(w) is not list or len(w)!=25 or w[0]!=0 or w[8]!=0 for w in mods):
        raise ValueError('All32 complete unassigned modifiers required; none will be cleared')
    names=[dev.scene_name(n) for n in range(1,9)]
    if any(type(v) not in (tuple,list) or len(v)!=2 or v[0]!=n or type(v[1]) is not str for n,v in enumerate(names,1)):
        raise ValueError('All scene names must be read')
    if dev.current_preset()!=preset or dev.current_scene()!=scene:
        raise ValueError('Preset or scene changed during inspection')
    return json.loads(json.dumps(dict(identity=ident,preset=preset,scene=scene,
        variant=dev.reg.hardware_variant,firmware=dev.reg.firmware,
        status=sorted((asdict(b) for b in status),key=lambda b:b['effect_id']),
        grid=sorted((asdict(c) for c in cells),key=lambda c:(c['row'],c['col'])),
        bulk=bulk,modifiers=mods,scenes=names,
        catalogs=sorted((b,o,n) for (b,o),n in dev.reg.cab_catalog.names.items()))))


def prepare_base(now):
    if now['grid'] and now['grid']!=grid():
        raise ValueError('Existing grid is not the exact minimal route; it will not be cleared or replaced')
    actual={b['effect_id'] for b in now['status']}-{200,201}
    if actual!=(set(NODES) if now['grid'] else set()):
        raise ValueError('Grid and status inventory disagree')
    for b in now['status']:
        if b['effect_id'] in (37,42) and b['bypassed']:
            raise ValueError('Input/Output must already be active; no unverified bypass setter')


def _expected(before,after,op):
    """Normalize only the one addressed surface, then compare everything else."""
    wanted=deepcopy(before)
    eid,pid,value=op.eid,op.pid,op.value
    status=lambda state,e:next(b for b in state['status'] if b['effect_id']==e)
    if op.kind=='insert':
        if str(eid) in before['bulk']:raise ValueError('Cannot insert an existing block')
        added=status(after,eid)
        if eid in (37,42) and added['bypassed']:raise ValueError('Inserted Input/Output is bypassed')
        wanted['status']=sorted(wanted['status']+[added],key=lambda b:b['effect_id'])
        wanted['bulk'][str(eid)]=after['bulk'][str(eid)]
        wanted['grid']=sorted(wanted['grid']+[grid(False)[NODES.index(eid)]],key=lambda c:c['col'])
    elif op.kind=='edge':
        cell=next(c for c in wanted['grid'] if c['effect_id']==eid)
        if cell['cable_in_mask']!=0:raise ValueError('Connection already exists or differs')
        cell['cable_in_mask']=2
    elif op.kind=='channel':status(wanted,eid)['channel']=0
    elif op.kind=='name':
        if pid:wanted['scenes'][0][1]=op.text
        else:wanted['preset'][1]=op.text
    elif op.kind=='param':
        if status(before,eid)['channel']!=0:raise ValueError('Explicit channel A readback required')
        if (eid,pid) in ((58,28),(62,32)):status(wanted,eid)['bypassed']=bool(value)
        elif eid==58 and pid==0:
            old,new=before['bulk']['58'],after['bulk']['58']
            if not status(before,58)['bypassed'] or old[21]>round(.68*65534)+1:
                raise ValueError('Model changes require a bypassed quiet amp')
            if new[0]!=value or new[21]!=old[21]:raise ValueError('Model or quiet level was not preserved')
            wanted['bulk']['58'][:142]=new[:142]
        else:
            if eid==58 or (eid,pid) in ((42,12),(62,28)):
                raw=round(((value+80)/100 if pid==21 or eid!=58 else value/10)*65534)
            elif (eid,pid)==(62,8):raw=65534
            elif (eid,pid)==(62,12):raw=32767
            else:raw=int(value)
            got=after['bulk'][str(eid)][pid]
            if abs(got-raw)>(1 if eid==58 or pid in (8,12,28) else 0):
                raise ValueError('Independent parameter readback differs')
            wanted['bulk'][str(eid)][pid]=got
    if wanted!=after:raise ValueError('Another observed block, channel, grid, modifier or name changed')


class Reviews:
    def __init__(self,clock=time.monotonic,pause=time.sleep):
        self.clock,self.pause=clock,pause
        self.pending=None
        self.uncertain=weakref.WeakSet()
        self.guard=sysex_guard('Exact Beta5 minimal core',{1})

    def clear(self):self.pending=None

    def prepare(self,dev,plan,initial):
        self.clear()
        if dev in self.uncertain:raise ValueError('Reconnect after uncertain execution; no automatic retry')
        checked=plans.compile_design(dev.reg,plan['design'])
        if any(plan[k]!=checked[k] for k in ('name','amp_ordinal','cab_choices','required_route')):
            raise ValueError('Compiled design differs from the current catalog')
        now=snapshot(dev);prepare_base(now)
        if now!=initial or snapshot(dev)!=now:raise ValueError('Device changed while planning')
        ops=operations(checked,not now['grid'])
        checked['actions']=[asdict(op) for op in ops]
        token=secrets.token_urlsafe(32)
        self.pending=dict(device=dev,plan=checked,ops=ops,stamp=digest(now),expires=self.clock()+600,token=token)
        return dict(**checked,token=token,expires_in=600,stored=False,
                    target=dict(preset=now['preset'][0],name=now['preset'][1],scene=1))

    def owns(self,token):
        return bool(self.pending and type(token) is str and secrets.compare_digest(self.pending['token'],token))

    def send(self,dev,token,external_audio_muted,target_confirmed):
        ticket=self.pending
        self.clear()  # Single use, including stale/declined/uncertain attempts.
        if (not ticket or ticket['device'] is not dev or type(token) is not str
                or not secrets.compare_digest(ticket['token'],token)
                or external_audio_muted is not True or target_confirmed is not True
                or self.clock()>=ticket['expires'] or dev in self.uncertain):
            raise ValueError('Fresh matching review, target confirmation and external mute are required')
        results=[]
        with dev._lock:
            current=snapshot(dev);prepare_base(current)
            if digest(current)!=ticket['stamp']:raise ValueError('Preset changed since review; nothing sent')
            # Revalidate memory ownership, names and all typed operations before the first SET.
            plans.compile_design(dev.reg,ticket['plan']['design'])
            try:
                for op in ticket['ops']:
                    before=snapshot(dev)
                    if before!=current or snapshot(dev)!=before:raise ValueError('Concurrent device change; execution stopped')
                    frame=op.frame(before['preset'][0]);self.guard.check(frame[5])
                    # The only final write boundary. Frame is minted from the server-owned
                    # typed operation, never accepted from an AI, JSON action list or URL.
                    dev.outp.send(mido.Message('sysex',data=frame[1:-1]))
                    error=None
                    for _ in range(5):
                        self.pause(.15);after=snapshot(dev)
                        try:_expected(before,after,op)
                        except ValueError as exc:error=exc;continue
                        if snapshot(dev)==after:break
                    else:raise ValueError('Write not independently verified; no retry/rollback') from error
                    current=after;results.append(dict(ok=True,detail=f'{op.kind}: {op.eid}/{op.pid} verified'))
                if current['grid']!=grid():raise ValueError('Final full route differs')
                for name,pid in plans.AMP_PIDS.items():
                    text=dev.read_display_text(58,pid)
                    if text is None or abs(float(text.removesuffix(' dB'))-ticket['plan']['design']['amp'][name])>.011:
                        raise ValueError('Independent final amp display differs')
                text=dev.read_display_text(42,12)
                if text is None or float(text.removesuffix(' dB'))!=-18:
                    raise ValueError('Independent final Output display differs')
                if snapshot(dev)!=current:raise ValueError('State changed during final display inspection')
                return dict(ok=True,stored=False,results=results,skipped=0,
                    detail='Minimal one-scene AMP/CAB route and parameters verified. '
                    'No Store or listening test. Keep external audio muted until ready to audition at low physical volume.')
            except (ValueError,RuntimeError,OSError,KeyError,TypeError) as exc:
                self.uncertain.add(dev)
                return dict(ok=False,stored=False,results=results,skipped=len(ticket['ops'])-len(results),
                    detail=str(exc)+'. Keep audio muted. No automatic retry, rollback or Store; reconnect and inspect first.')

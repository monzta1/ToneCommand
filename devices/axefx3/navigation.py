"""Explicit human navigation, separate from AI actions and automatic reload."""
import secrets
import time

import mido
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictInt,StrictBool
from typing import Literal

from . import protocol,fw33_profile,modifiers
from .controller_review import digest


def supported(dev):
    return dev.reg.firmware in ('32.06',fw33_profile.KEY)


def snapshot(dev):
    preset,scene=dev.current_preset(),dev.current_scene()
    if not supported(dev) or dev.firmware_label()!=dev.reg.firmware or not preset or type(scene) is not int or scene not in range(1,9):
        raise ValueError('Fresh verified device, preset and scene required.')
    blocks,grid=dev.status_dump(),dev.read_grid()
    if blocks is None or grid is None:raise ValueError('Navigation state could not be read.')
    bulk={b.effect_id:dev.bulk_read(b.effect_id) for b in blocks if b.effect_id not in (200,201)}
    if any(not isinstance(v,list) or not v for v in bulk.values()):raise ValueError('Incomplete block state.')
    entries=modifiers.inspect(dev)
    names=[dev.scene_name(n) for n in range(1,9)]
    if len(entries)!=32 or any(len(e['words'])!=25 for e in entries) or any(n is None for n in names):
        raise ValueError('Incomplete modifier/scene state.')
    if dev.current_preset()!=preset or dev.current_scene()!=scene:raise ValueError('Target changed while reading.')
    return dict(preset=preset,scene=scene,firmware=dev.reg.firmware,blocks=blocks,grid=grid,
        bulk=bulk,modifiers=entries,scene_names=names)


def switch_preset(dev,number,source,*,external_audio_muted,confirm_discard_edits):
    """Measured bank/PC path, only explicit UI confirmation. Never an AI action."""
    if type(number) is not int or number not in range(512):raise ValueError('Preset must be 0..511.')
    if external_audio_muted is not True or confirm_discard_edits is not True:
        raise PermissionError('Confirm external mute and discarding the edit buffer.')
    if (not supported(dev) or dev.firmware_label()!=dev.reg.firmware or dev.current_preset()!=source
            or dev._edit_target is not None):raise PermissionError('Navigation target changed or an edit is active.')
    bank,pc=divmod(number,128)
    dev.outp.send(mido.Message('control_change',control=0,value=bank))
    dev.outp.send(mido.Message('program_change',program=pc))
    for _ in range(8):
        time.sleep(.15)
        got=dev.current_preset()
        if got and got[0]==number:return got
    raise RuntimeError('Preset selection was sent but readback failed. No retry or rollback.')


def switch_scene(dev,number,source,*,external_audio_muted):
    if type(number) is not int or number not in range(1,9):raise ValueError('Scene must be 1..8.')
    frame=protocol.envelope(0x0c,[number-1])
    with dev.edit_session(external_audio_muted=external_audio_muted,expected_preset=source[0]):
        dev._navigation_frame_permit=tuple(frame)
        try:
            dev.set_scene(number)
            for _ in range(8):
                time.sleep(.1)
                got=dev.current_scene()
                if got==number and dev.current_preset()==source:return got
            raise RuntimeError('Scene selection was sent but readback failed. No retry or rollback.')
        finally:
            dev._navigation_frame_permit=None


class Prepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['preset','scene']
    value:StrictInt=Field(ge=0,le=511)
    expected_preset:StrictInt=Field(ge=0,le=511)
    expected_scene:StrictInt=Field(ge=1,le=8)


class Select(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=10,max_length=200)
    external_audio_muted:StrictBool=False
    confirm_discard_edits:StrictBool=False


class Reviews:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.pending=None
    def prepare(self,dev,body):
        self.pending=None
        if body.kind=='scene' and body.value not in range(1,9):raise ValueError('Scene must be 1..8.')
        now=snapshot(dev)
        if now['preset'][0]!=body.expected_preset or now['scene']!=body.expected_scene:
            raise ValueError('Preset or scene changed. RESCAN before choosing.')
        if body.kind=='preset':
            slot=dev.slot_name(body.value)
            if slot is None or slot.number!=body.value:raise ValueError('Destination preset name unreadable.')
            destination=dict(number=slot.number,name=slot.name)
        else:destination=dict(number=body.value,name=now['scene_names'][body.value-1][1])
        token=secrets.token_urlsafe(32)
        self.pending=dict(token=token,device=dev,state=now,stamp=digest(now),kind=body.kind,
            value=body.value,destination=destination,expires=self.clock()+120)
        return dict(token=token,kind=body.kind,destination=destination,source=now['preset'],
            source_scene=now['scene'],expires_seconds=120,hardware_written=False,
            warning='Preset loading discards unstored edit-buffer changes. Nothing is stored. External mute is required; no physical limiter.')
    def select(self,dev,body):
        pending=self.pending
        if (not pending or not body.token.isascii() or not secrets.compare_digest(body.token,pending['token'])):
            raise ValueError('Navigation confirmation missing or already used.')
        self.pending=None
        if body.external_audio_muted is not True:raise PermissionError('Confirm external mute first.')
        if pending['kind']=='preset' and body.confirm_discard_edits is not True:
            raise PermissionError('Confirm discarding unstored edit-buffer changes.')
        if pending['device'] is not dev or self.clock()>=pending['expires']:
            raise ValueError('Navigation confirmation expired or connection changed.')
        if digest(snapshot(dev))!=pending['stamp']:raise ValueError('Preset state changed. Review selection again.')
        source=pending['state']['preset']
        dev._album_store_stamp=None
        dev._album_store_proof=None
        if pending['kind']=='preset':
            slot=dev.slot_name(pending['value'])
            if slot is None or dict(number=slot.number,name=slot.name)!=pending['destination']:
                raise ValueError('Destination changed. Review selection again.')
            got=switch_preset(dev,pending['value'],source,external_audio_muted=True,confirm_discard_edits=True)
        else:got=switch_scene(dev,pending['value'],source,external_audio_muted=True)
        return dict(ok=True,kind=pending['kind'],selected=got,stored=False,physical_volume_verified=False)


def register(app,host,tone_reviews,planning_lock,editable,selected):
    reviews=Reviews()
    @app.get('/api/axefx3/navigation/presets')
    def presets(start:int=0,end:int=511):
        with host._lock:
            try:
                dev=selected()
                if not supported(dev) or dev.firmware_label()!=dev.reg.firmware or not 0<=start<=end<512:
                    raise ValueError('Verified device and valid preset range required.')
                origin=dev.current_preset()
                if origin is None:raise ValueError('Current preset unreadable.')
                slots=list(dev.scan_slots(start,end))
                if len(slots)!=end-start+1 or [s.number for s in slots]!=list(range(start,end+1)):
                    raise ValueError('Incomplete preset scan. No preset is assumed empty.')
                if dev.current_preset()!=origin:raise ValueError('Preset changed during scan.')
                return dict(slots=[dict(number=s.number,name=s.name,empty=s.empty) for s in slots],readonly=True)
            except (ValueError,RuntimeError,OSError) as exc:raise HTTPException(409,str(exc)) from exc
    @app.post('/api/axefx3/navigation/prepare')
    def prepare(body:Prepare):
        if not planning_lock.acquire(blocking=False):raise HTTPException(409,'A plan is running. Wait before selecting.')
        try:
            with host._lock:
                editable()
                return reviews.prepare(selected(),body)
        except (ValueError,RuntimeError,OSError) as exc:raise HTTPException(409,str(exc)) from exc
        finally:planning_lock.release()
    @app.post('/api/axefx3/navigation/select')
    def select(body:Select):
        if not planning_lock.acquire(blocking=False):raise HTTPException(409,'A plan is running. Wait before selecting.')
        try:
            with host._lock:
                editable()
                tone_reviews.clear()
                return reviews.select(selected(),body)
        except PermissionError as exc:raise HTTPException(403,str(exc)) from exc
        except (ValueError,RuntimeError,OSError) as exc:raise HTTPException(409,str(exc)) from exc
        finally:planning_lock.release()
    return reviews

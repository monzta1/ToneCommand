"""Measured FW33 Tempo NONE only, bound to one active reviewed timing action.

Read existing enum labels but never write an arbitrary tempo division or BPM.
The fixed Analog Stereo Chorus A / Digital Mono Delay A domains are deliberate.
"""
import hashlib
from importlib.resources import files
import json
import time
from . import fw33_profile,protocol,tone_review

DOMAINS={'CHORUS':(78,32,3,3,'CHORUS_RATE'),'DELAY':(70,89,0,9,'DELAY_TIME')}
LABEL_SHA='8b6f5a5c0a2c984c4ee4c5e71d0968c33e7436b059186a679a37cb1ae4fdbfe5'


def labels():
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_zero_tempo_calibration.json').read_text(encoding='utf-8'))
    result=data.get('tempo_labels')
    if (not isinstance(result,list) or len(result)!=79 or
            hashlib.sha256(json.dumps(result,separators=(',',':')).encode('ascii')).hexdigest()!=LABEL_SHA):
        raise ValueError('Closed FW33 tempo enum metadata required')
    return tuple(result)


def frame(spec):
    return protocol.param_frame(spec.effect_id,spec.tempo_param_id,0,opcode=9)


def preflight(dev,spec):
    """Read-only readiness. Existing NONE needs no new write capability."""
    if (spec.family not in DOMAINS or spec.instance!=1 or dev.reg.firmware!=fw33_profile.KEY
            or getattr(dev.reg,'hardware_variant',None)!='mk2'):
        raise ValueError('Measured FW33/MK2 timing domain required')
    eid,stride,model,pid,name=DOMAINS[spec.family]
    if (spec.effect_id,spec.name,spec.tempo_param_id)!=(eid,name,pid):
        raise ValueError('Exact reviewed timing parameter required')
    words=dev.bulk_read(eid);shown=str(dev.read_display_text(eid,pid)).strip().upper()
    if not isinstance(words,list) or len(words)!=4*stride or dev.get_channel(eid)!=0:
        raise ValueError('Complete timing channel A is required')
    value=words[pid]
    if type(value) is not int:raise ValueError('Integral tempo enum required')
    if value==0 and shown=='NONE':return False
    if not fw33_profile.TEMPO_NONE_RELEASED:
        raise ValueError('FW33 automatic Tempo NONE awaits normal SEND/editor acceptance')
    roster=labels()
    if (type(words[0]) is not int or words[0]!=model or value not in range(1,len(roster))
            or shown!=roster[value].strip().upper()):
        raise ValueError('Existing tempo enum or measured effect model could not be verified')
    return True


def session_for(dev,spec):
    from . import album_build
    session=getattr(dev,'_album_session',None)
    if (not isinstance(session,album_build.Session) or session.failed or session.dev is not dev
            or session.item is None or session.item.action['kind']!='set_param'
            or session.item.spec!=spec or session.target!=getattr(dev,'_edit_target',None)):
        raise PermissionError('Tempo NONE requires its exact active reviewed timing operation')
    return session


def allowed(dev,candidate):
    permit=getattr(dev,'_fw33_tempo_permit',None)
    if not fw33_profile.TEMPO_NONE_RELEASED or permit!=tuple(candidate):return False
    session=getattr(dev,'_album_session',None)
    spec=getattr(getattr(session,'item',None),'spec',None)
    if spec is None or spec.family not in DOMAINS:return False
    try:session_for(dev,spec)
    except PermissionError:return False
    eid,_,_,pid,name=DOMAINS[spec.family]
    return (dev.reg.firmware==fw33_profile.KEY and getattr(dev.reg,'hardware_variant',None)=='mk2'
        and spec.instance==1 and (spec.effect_id,spec.tempo_param_id,spec.name)==(eid,pid,name)
        and list(candidate)==frame(spec))


def ensure(dev,spec):
    """Single measured enum write and full-state readback; never retry/rollback."""
    if not preflight(dev,spec):return
    session=session_for(dev,spec);before=session.expected
    if tone_review.snapshot(dev,include_nam=False)!=before:
        raise PermissionError('Timing state changed before Tempo NONE; nothing sent')
    eid,stride,model,pid,_=DOMAINS[spec.family]
    words=list(before['bulk'][eid]);words[pid]=0
    wanted={**before,'bulk':{**before['bulk'],eid:words}}
    sent=frame(spec);dev._fw33_tempo_permit=tuple(sent)
    try:dev._write(sent)
    except BaseException:
        session.failed=True
        raise
    finally:dev._fw33_tempo_permit=None
    for _ in range(5):
        time.sleep(.15);now=tone_review.snapshot(dev,include_nam=False)
        if (now==wanted and dev.get_channel(eid)==0 and
                str(dev.read_display_text(eid,pid)).strip().upper()=='NONE'):
            session.expected=now
            return
    session.failed=True
    raise ValueError('Tempo NONE independent full-state mismatch; no retry or rollback')

"""Private successful-design history, never saved SEND/Store authorization.

Checksums detect corruption, not a hostile process with the same user account.
Resuming requires fresh all-scene device verification and creates a new ticket.
"""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from . import fw33_profile,audio_measurements,scene_contract
from .controller_review import digest

LIMIT=2*1024*1024


def directory():
    override=os.environ.get('TONECOMMAND_AXEFX3_STATE_DIR','').strip()
    if os.environ.get('TONECOMMAND_SIM')=='1' and not override:
        raise ValueError('Set an isolated TONECOMMAND_AXEFX3_STATE_DIR for simulator history')
    return (Path(override) if override else Path.home()/'.tonecommand'/'axefx3')/'design-history'


def canonical(data):
    return json.dumps(data,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):
        raise ValueError('Invalid local design identifier')
    return value


def validate(data):
    fields={'version','id','created','preset','firmware','variant','plan','proof','stamp'}
    plan=data.get('plan') if isinstance(data,dict) else None
    version=data.get('version') if isinstance(data,dict) else None
    allowed={'mode','design'}
    if version==2:allowed.add('reference_measurements')
    if version==3:
        allowed.add('scene_contract')
        if isinstance(plan,dict) and 'reference_measurements' in plan:allowed.add('reference_measurements')
    if (not isinstance(data,dict) or set(data)!=fields or type(data['version']) is not int or data['version'] not in (1,2,3)
            or type(data['preset']) is not int or data['preset'] not in range(512)
            or data['firmware']!=fw33_profile.KEY or data['variant']!='mk2'
            or not isinstance(data['created'],str) or len(data['created'])>40
            or not isinstance(data['plan'],dict) or set(data['plan'])!=allowed
            or data['plan']['mode']!='album' or not isinstance(data['plan']['design'],dict)
            or not isinstance(data['proof'],dict)
            or set(data['proof'])!={'final_fingerprint','scene_fingerprints'}):
        raise ValueError('Unsupported or invalid local design record')
    if 'reference_measurements' in data['plan']:
        evidence=data['plan']['reference_measurements']
        if not isinstance(evidence,dict) or audio_measurements.private_evidence(evidence)!=evidence:
            raise ValueError('Only bounded private numeric reference evidence may be saved')
    identifier(data['id'])
    try:datetime.fromisoformat(data['created'])
    except ValueError:raise ValueError('Invalid local design date') from None
    proof=data['proof'];scenes=proof['scene_fingerprints']
    count=data['plan']['design'].get('scene_count',8)
    if (type(count) is not int or count not in range(1,9) or not isinstance(scenes,dict)
            or set(scenes)!=set(map(str,range(1,count+1)))):
        raise ValueError('Complete evidence for every designed scene required')
    if data['version']==3:
        brief=scene_contract.Brief.model_validate(data['plan']['scene_contract'])
        scene_contract.validate(brief.model_dump(),count,'\n'.join(s.reuse_quote or '' for s in brief.scenes))
    for value in [data['stamp'],proof['final_fingerprint'],*scenes.values()]:
        if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
            raise ValueError('Invalid stored device fingerprint')
    if data['stamp']!=proof['final_fingerprint'] or scenes[str(count)]!=data['stamp']:
        raise ValueError('Final scene evidence differs from saved state')
    return data


def remember(plan,proof,state):
    """Only a fully successful album SEND may create a history record."""
    saved=dict(mode=plan.get('mode'),design=deepcopy(plan['design']))
    if plan.get('reference_measurements') is not None:
        saved['reference_measurements']=audio_measurements.private_evidence(plan['reference_measurements'])
    if plan.get('scene_comparison',{}).get('contract') is not None:
        saved['scene_contract']=deepcopy(plan['scene_comparison']['contract'])
    version=3 if 'scene_contract' in saved else 2 if 'reference_measurements' in saved else 1
    record=validate(dict(version=version,id=secrets.token_hex(16),created=datetime.now(timezone.utc).isoformat(),
        preset=state['preset'][0],firmware=state['firmware'],variant=state['variant'],
        plan=saved,
        proof=deepcopy(proof),stamp=digest(state)))
    payload=dict(record=record,checksum=hashlib.sha256(canonical(record).encode('ascii')).hexdigest())
    text=canonical(payload)
    if len(text.encode('ascii'))>LIMIT:raise ValueError('Local design record is too large')
    root=directory();root.mkdir(parents=True,exist_ok=True)
    if len(list(root.glob('*.json')))>=2000:raise ValueError('Local history is full; no records automatically deleted')
    fd,name=tempfile.mkstemp(prefix='.pending-',suffix='.tmp',dir=root)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,root/(record['id']+'.json'))
    finally:
        if temporary.exists():temporary.unlink()
    return dict(id=record['id'],created=record['created'],preset=record['preset'],
                name=record['plan']['design'].get('name',''),hardware_written=False)


def load(value):
    path=directory()/(identifier(value)+'.json')
    if path.is_symlink() or not path.is_file() or path.stat().st_size>LIMIT:
        raise ValueError('Local design record is missing or oversized')
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or set(data)!={'record','checksum'}:
        raise ValueError('Invalid local history envelope')
    record=validate(data['record'])
    checksum=hashlib.sha256(canonical(record).encode('ascii')).hexdigest()
    if (record['id']!=value or not isinstance(data['checksum'],str)
            or not secrets.compare_digest(checksum,data['checksum'])):
        raise ValueError('Local design checksum failed; nothing resumed')
    return record


def entries():
    root=directory()
    if not root.exists():return dict(designs=[],unreadable=0,hardware_written=False)
    result=[];bad=0
    # The app never removes history as a side effect of reading it.
    for path in sorted(root.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:2000]:
        try:
            item=load(path.stem)
            result.append(dict(id=item['id'],created=item['created'],preset=item['preset'],
                firmware=item['firmware'],variant=item['variant'],name=item['plan']['design'].get('name','')))
        except (OSError,ValueError,KeyError,TypeError):bad+=1
        if len(result)>=50:break
    return dict(designs=result,unreadable=bad,hardware_written=False)

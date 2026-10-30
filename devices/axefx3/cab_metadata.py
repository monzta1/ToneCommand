"""Private name-cache persistence only. Never IR audio or hardware writes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from . import fw33_profile
from .chassis import modern_cab_metadata


def path_for(reg):
    variant=getattr(reg,'hardware_variant',None)
    if not modern_cab_metadata(reg.firmware) or variant not in ('mk1','mk2'):return None
    override=os.environ.get('TONECOMMAND_AXEFX3_STATE_DIR','').strip()
    if os.environ.get('TONECOMMAND_SIM')=='1' and not override:return None
    root=Path(override) if override else Path.home()/'.tonecommand'/'axefx3'
    build = 'fw33' if reg.firmware == fw33_profile.KEY else 'fw33-beta5-20261026'
    return root/f'cab-names-{build}-{variant}.json'


def canonical(data):
    return json.dumps(data,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))


def save(reg):
    path=path_for(reg)
    if path is None:return False
    data=dict(version=1,firmware=reg.firmware,variant=reg.hardware_variant,
        entries=[list(k)+[v] for k,v in sorted(reg.cab_catalog.names.items())])
    payload=dict(data=data,checksum=hashlib.sha256(canonical(data).encode('ascii')).hexdigest())
    text=canonical(payload)
    if len(text)>2*1024*1024:raise ValueError('Local cabinet-name cache exceeds 2MiB')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.cab-pending-',suffix='.tmp',dir=path.parent)
    temp=Path(name)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
    reg.cab_catalog.cache_note='Cabnamen lokaal bewaard; geen IR-audio of live geheugenbewijs.'
    return True


def restore_if_empty(reg):
    path=path_for(reg)
    if path is None or reg.cab_catalog.names or not path.exists():return 0
    if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('Invalid local cabinet-name cache')
    payload=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload,dict) or set(payload)!={'data','checksum'}:
        raise ValueError('Invalid cabinet-name cache envelope')
    data=payload['data']
    if (not isinstance(data,dict) or set(data)!={'version','firmware','variant','entries'}
            or data['version']!=1 or data['firmware']!=reg.firmware or data['variant']!=reg.hardware_variant
            or not isinstance(data['entries'],list) or len(data['entries'])>8192
            or hashlib.sha256(canonical(data).encode('ascii')).hexdigest()!=payload['checksum']):
        raise ValueError('Cabinet-name cache checksum or profile differs')
    incoming={}
    for row in data['entries']:
        if not isinstance(row,list) or len(row)!=3:raise ValueError('Invalid cached cabinet entry')
        bank,ordinal,name=row
        reg.cab_catalog.position(bank,ordinal)
        if (not isinstance(name,str) or not 1<=len(name)<=160 or any(ord(c)<32 for c in name)
                or (bank,ordinal) in incoming or (bank==3 and not reg.cab_catalog.user2_enabled)
                or (bank==6 and not reg.cab_catalog.fullres_enabled)):
            raise ValueError('Invalid or reserved cached cabinet entry')
        incoming[bank,ordinal]=name
    reg.cab_catalog.names=incoming
    reg.cab_catalog.cache_note='Lokale cabnamen herladen; geen live inventarisatie. Werk de import bij na een IR-wijziging.'
    return len(incoming)

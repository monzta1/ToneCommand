"""Read local editor facts and report changes without promoting write domains."""
import hashlib
import os
from pathlib import Path
import re
import sys
from . import amp_inventory,amp_cache,fw33_profile


def cache_directory():
    # No caller-controlled filesystem path, network, editor launch or MIDI.
    if sys.platform=='win32' and os.environ.get('APPDATA'):
        return Path(os.environ['APPDATA'])/'Fractal Audio'/'Axe-Edit III'
    return None


def latest_cache():
    root=cache_directory()
    if root is None or not root.is_dir():return None
    candidates=[]
    for path in root.glob('effectDefinitions_10_*.cache'):
        match=re.fullmatch(r'effectDefinitions_10_(\d{1,5})p(\d{1,5})\.cache',path.name)
        if match and path.is_file() and not path.is_symlink():
            candidates.append((tuple(map(int,match.groups())),path))
        if len(candidates)>64:raise ValueError('Too many editor metadata files')
    return max(candidates,key=lambda item:item[0])[1] if candidates else None


def refresh(reg):
    from .album_planning import MODELS
    active=amp_inventory.roster(reg.firmware)
    if reg.firmware==fw33_profile.KEY and active!=MODELS:
        raise ValueError('The TC model list changed on disk. Restart TC with the verified update; refresh does not change active AI choices.')
    usable=reg.firmware==fw33_profile.KEY and getattr(reg,'hardware_variant',None)=='mk2'
    result=dict(inventory=amp_inventory.report(reg) if usable else None,
        firmware=reg.firmware,hardware_written=False,permissions_changed=False,
        live_list_fetched=False,source_count=None,source_file=None,
        added=[],changed=[],removed=[],status='bundled_only',
        message='Bundled model list reloaded. No local Axe-Edit cache found; no live model list was fetched from the Fractal.')
    if not usable:
        result.update(status='verification_required',message='This firmware/chassis is not released for model writes. Refresh only compares local model names; it releases no capability automatically.')
    try:
        path=latest_cache()
        if path is None:return result
        with path.open(mode='rb') as stream:data=stream.read(amp_cache.MAX_BYTES+1)
        names=amp_cache.amp_names(data)
    except (ValueError,OSError):
        result.update(status='source_unreadable',message='The local Axe-Edit cache could not be read completely and safely. The verified list and write guards are unchanged.')
        return result
    result.update(source_count=len(names),source_file=path.name,source_sha256=hashlib.sha256(data).hexdigest())
    result['added']=[dict(ordinal=k,name=v) for k,v in names.items() if k not in active]
    result['changed']=[dict(ordinal=k,name=v,verified_name=active[k]) for k,v in names.items() if k in active and active[k]!=v]
    result['removed']=[dict(ordinal=k,name=v) for k,v in active.items() if k not in names]
    if usable and names==active:
        result.update(status='up_to_date',message=f'Up to date: all {len(active)} model names and ordinals match the local Axe-Edit cache. AI uses this full verified list. No preset settings changed.')
    else:
        prefix='' if usable else 'Firmware/chassis not released. '
        result.update(status='verification_required',message=prefix+f'Local cache: {len(names)} models; {len(result["added"])} added, {len(result["changed"])} changed, {len(result["removed"])} missing compared with the firmware list. Differences require independent verification and a TC update; existing write guards still apply.')
    return result

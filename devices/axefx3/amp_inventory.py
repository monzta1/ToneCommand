"""Exact-FW33 amplifier names/ordinals, not FM9 IDs or generic SET authority.

Source is the installed editor's firmware-specific definition enum. Only
factual names/IDs are bundled. No editor binary, account or private IR table.
The executor still requires the reviewed quiet, bypassed Amp1 operation.
"""
import json
from importlib.resources import files
from . import fw33_profile


def roster(firmware):
    if firmware != fw33_profile.KEY:
        return {}
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_amp_models.json').read_text(encoding='utf-8'))
    names=data.get('models')
    if (data.get('firmware')!=firmware or data.get('model_byte')!=16
            or data.get('selector_pid')!=0 or not isinstance(names,dict)
            or set(names)!=set(map(str,range(336)))
            or any(not isinstance(v,str) or not v.strip() or len(v)>120
                   or any(not 32<=ord(c)<=126 for c in v) for v in names.values())
            or len(set(names.values()))!=336
            or names.get('0')!='59 Bassguy Bright' or names.get('335')!='Brit JVM Crunch Red'):
        raise ValueError('Firmware-specific amplifier inventory is incomplete or invalid')
    return {int(k):v for k,v in names.items()}


def ordinal(firmware,name):
    result=next((key for key,value in roster(firmware).items() if value==name),None)
    if result is None:
        raise ValueError('Amp model is not in the exact firmware inventory')
    return result


def report(reg):
    names=roster(reg.firmware)
    return dict(firmware=reg.firmware,count=len(names),
        models=[dict(ordinal=k,name=v) for k,v in names.items()],
        source='Bundled exact-firmware Axe-Edit definition names/IDs, not a live device enumeration',
        live_list_fetched=False,
        selection_scope='Reviewed FW33/MK2 Amp1 A-D build only',
        generic_setter_enabled=False)

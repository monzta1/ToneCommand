"""Exact-FW33 public Factory names and explicit local User metadata.

An inventory entry is not proof that an IR is in the mix or audible. No memory
installation, hardware discovery, Legacy-bank alias or selector permission.
"""
import json
from importlib.resources import files
from . import fw33_profile


def factory_roster(firmware):
    if firmware != fw33_profile.KEY:
        return {}
    data=json.loads(files('devices.axefx3').joinpath('data','fw33_cab_models.json').read_text(encoding='utf-8'))
    banks=data.get('banks')
    if (data.get('firmware')!=firmware or data.get('model_byte')!=16
            or not isinstance(banks,dict) or set(banks)!={'0','1'}):
        raise ValueError('Invalid firmware-specific Factory cabinet inventory')
    result={}
    for bank,names in banks.items():
        if (not isinstance(names,dict) or set(names)!=set(map(str,range(1024)))
                or any(not isinstance(n,str) or not n.strip() or len(n)>160
                       or any(not 32<=ord(c)<=126 for c in n) for n in names.values())):
            raise ValueError('Factory bank must have all 1024 bounded names')
        result.update({(int(bank),int(o)):n for o,n in names.items()})
    if result[0,0]!='1x4 Pig 57' or result[1,1023]!='TOTALLY-FLAT':
        raise ValueError('Factory inventory boundary labels changed')
    return result


def occupied(name):
    return isinstance(name,str) and bool(name.strip()) and name.strip().upper() not in ('<EMPTY>','EMPTY','<NONE>')


def choices(reg, *, include_fullres=False):
    """Selectable metadata, not wire authorization. Never suggest empty memory."""
    if reg.firmware!=fw33_profile.KEY:
        return []
    names={**reg.cab_catalog.names,**factory_roster(reg.firmware)}
    return [dict(bank=b,slot=o+1,name=n,position=reg.cab_catalog.position(b,o),
                 fullres=b==6,eligible_ir_slots=[3,4] if b==6 else [1,2,3,4])
            for (b,o),n in sorted(names.items())
            if occupied(n) and b in (0,1,2,3,6) and (include_fullres or b!=6)
            and (b!=6 or reg.cab_catalog.fullres_enabled)
            and (b!=3 or reg.cab_catalog.user2_enabled)]


def selection(reg,bank,ordinal,ir):
    if (reg.firmware!=fw33_profile.KEY or type(bank) is not int or type(ordinal) is not int
            or type(ir) is not int or ir not in range(1,5) or bank not in (0,1,2,3,6)
            or not 0<=ordinal<(64 if bank==6 else 1024) or (bank==6 and ir<3)
            or (bank==6 and not reg.cab_catalog.fullres_enabled)
            or (bank==3 and not reg.cab_catalog.user2_enabled)):
        raise ValueError('Cab bank/slot is outside the firmware/chassis/IR-slot policy')
    name=(factory_roster(reg.firmware) if bank in (0,1) else reg.cab_catalog.names).get((bank,ordinal))
    if not occupied(name):
        raise ValueError('Cab name is missing or the selected IR memory is empty')
    return name

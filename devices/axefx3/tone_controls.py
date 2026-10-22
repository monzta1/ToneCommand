"""Captured existing-block Drive/Compressor/EQ controls, FW32.06 only.

2026-10-06 muted TestPreset323 Axe-Edit SETs and independent TC reads.
Filter-type edits, insertion, modifier and raw restore remain separate gates.
"""

LAYOUTS = {'FUZZ':(118,44), 'COMP':(46,37), 'GEQ':(50,20), 'PEQ':(54,33)}


def definition(pid,label,unit,lo,hi,divisor=1,scale='linear',tol=.051,zero=False):
    return dict(pid=pid,label=label,unit=unit,min=lo,max=hi,set_opcode='09',
                set_divisor=divisor,scale=scale,display_tolerance=tol,
                firmware_versions=('32.06',),bulk_restore_supported=False,
                zero_typed=zero)


DEFINITIONS = {
    'FUZZ': {
        'FUZZ_DRIVE':definition(1,'Distortion','0-10',0,10,10,zero=True),
        'FUZZ_TONE':definition(2,'Filter','0-10',0,10,10,zero=True),
        'FUZZ_LEVEL':definition(3,'Level','0-10',0,10,10,zero=True),
        'FUZZ_MIX':definition(4,'Mix','%',0,100,100,zero=True),
    },
    'COMP': {
        'COMP_THRESH':definition(0,'Threshold','dB',-60,20,zero=True),
        'COMP_RATIO':definition(1,'Ratio','ratio',1,20,scale='log10',tol=.00051),
        'COMP_ATTACK':definition(2,'Attack Time','ms',.1,100,1000,'log10',tol=.011),
        'COMP_RELEASE':definition(3,'Release Time','ms',2,2000,1000,'log10',tol=.2),
        'COMP_LEVEL':definition(4,'Level','dB',-20,20,zero=True),
        'COMP_MIX':definition(11,'Mix','%',0,100,100,zero=True),
    },
    'GEQ': {f'GEQ_GAIN{i+1}':definition(i,f'Band {i+1}','dB',-12,12,tol=.011,zero=True)
            for i in range(10)},
    'PEQ': {},
}
DEFINITIONS['GEQ']['GEQ_LEVEL']=definition(11,'Level','dB',-80,20,zero=True)
for i,(lo,hi) in enumerate(((20,2000),(100,10000),(100,10000),(100,10000),(200,20000))):
    DEFINITIONS['PEQ'][f'PEQ_FREQ{i+1}']=definition(i,f'Frequency {i+1}','Hz',lo,hi,scale='log10',tol=1.6)
    DEFINITIONS['PEQ'][f'PEQ_GAIN{i+1}']=definition(i+10,f'Gain {i+1}','dB',-20,20,tol=.011,zero=True)
DEFINITIONS['PEQ']['PEQ_LEVEL']=definition(20,'Level','dB',-80,20,zero=True)
ZERO_TYPED=frozenset(name for defs in DEFINITIONS.values() for name,d in defs.items() if d['zero_typed'])


def domain_error(dev,spec,channel):
    """Refuse unmeasured model/mode/layout before any parameter write."""
    if spec.family not in LAYOUTS:
        return None
    eid,stride=LAYOUTS[spec.family]
    if (dev.reg.firmware!='32.06' or spec.effect_id!=eid or spec.instance!=1
            or type(channel) is not int or channel not in range(4)):
        return 'Existing-block control address/firmware is not verified'
    words=dev.bulk_read(eid)
    if dev.get_channel(eid)!=channel:
        return 'Existing-block layout/channel unreadable; nothing written'
    return profile_error(spec,words,channel)


def profile_error(spec,words,channel):
    """Inspect a future explicitly chosen channel without selecting it."""
    eid,stride=LAYOUTS[spec.family]
    if (type(channel) is not int or channel not in range(4)
            or not isinstance(words,list) or len(words)!=4*stride):
        return 'Existing-block layout/channel unreadable; nothing written'
    part=words[channel*stride:(channel+1)*stride]
    valid={'FUZZ':lambda:part[0] in (0,6,8),
           'COMP':lambda:part[12] in (0,13),
           'GEQ':lambda:part[15]==4,
           'PEQ':lambda:part[15:20]==[0]*5}[spec.family]()
    return None if valid else 'Model/filter mode is not in the captured control profile; nothing written'

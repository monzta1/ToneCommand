"""Closed379-step factual metadata; no runtime permissions or I/O."""
MODELS={'COMP':(46,37,12,0,'Modern VCA Compressor'),
        'GEQ':(50,20,15,4,'10 Band Variable Q')}
AUTO_OFF={'COMP_AUTO_MAKEUP':6,'COMP_AUTO_ATT_REL':16}


def definition(pid,label,unit,lo,hi,*,scale='linear',divisor=1.,tol=.051,kind='float'):
    return dict(pid=pid,label=label,unit=unit,min=lo,max=hi,scale=scale,
        set_divisor=divisor,set_opcode='52' if unit=='switch' else '09',
        display_tolerance=tol,kind=kind,firmware_versions=('33.00-beta.20261006',),
        hardware_verified=True,bulk_restore_supported=False)


DEFINITIONS={
    'COMP':{
        'COMP_THRESH':definition(0,'Threshold','dB',-60,20),
        'COMP_RATIO':definition(1,'Ratio','',1,20,scale='log10',tol=.0011),
        'COMP_ATTACK':definition(2,'Attack Time','ms',.1,100,scale='log10',divisor=1000.,tol=.011),
        'COMP_RELEASE':definition(3,'Release Time','ms',2,2000,scale='log10',divisor=1000.,tol=.21),
        'COMP_LEVEL':definition(4,'Level','dB',-20,20),
        'COMP_MIX':definition(11,'Mix','%',0,100,divisor=100.),
        **{name:definition(pid,label,'switch',0,1,kind='enum') for name,pid,label in (
            ('COMP_AUTO_MAKEUP',6,'Auto Makeup'),('COMP_AUTO_ATT_REL',16,'Auto Attack Release'))},
    },
    'GEQ':{
        **{f'GEQ_GAIN{i+1}':definition(i,f'Band {i+1}','dB',-12,12,tol=.026) for i in range(10)},
        'GEQ_LEVEL':definition(11,'Level','dB',-80,20),
        'GEQ_Q':definition(16,'Q','',.1,10,scale='log10',tol=.011),
    },
}
ZERO_TYPED=frozenset({'COMP_THRESH','COMP_LEVEL','COMP_MIX','GEQ_LEVEL'}|{f'GEQ_GAIN{i+1}' for i in range(10)})
